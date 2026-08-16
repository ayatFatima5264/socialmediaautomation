"""Database engine, session factory and declarative base.

Everything is driven by settings.database_url, so the same models run on
SQLite (local dev) and PostgreSQL (production) with no code changes — switch
by setting DATABASE_URL in .env.
"""
from __future__ import annotations

import logging
from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

# Managed Postgres providers (Render, Railway, Heroku, Neon, Supabase) hand out
# connection strings with a bare "postgres://" or "postgresql://" scheme, which
# SQLAlchemy maps to the psycopg2 driver. We ship psycopg (v3), so normalize the
# scheme to "postgresql+psycopg://" — no change needed to the env var itself.
def _normalize_db_url(url: str) -> str:
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = _normalize_db_url(settings.database_url)

# SQLite needs check_same_thread disabled for FastAPI's threadpool; Postgres
# and others take no special connect args.
_connect_args = (
    {"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    pool_pre_ping=True,  # transparently recover dropped Postgres connections
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a request-scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables for all imported models. Called on app startup.

    Importing app.models here guarantees every model is registered on
    Base.metadata before create_all runs.
    """
    import app.models  # noqa: F401  (registers models)

    Base.metadata.create_all(bind=engine)
    _run_lightweight_migrations()
    encrypt_existing_tokens()


# Columns added to a table after its first release. `create_all` only creates
# missing *tables*, never alters existing ones, so we add any missing columns in
# place — idempotent and safe on both SQLite and Postgres. Only ever *adds*
# columns, never drops or retypes one, so it can never lose data. A column
# declared NOT NULL must carry a DEFAULT, which is what lets the ALTER backfill
# the rows that already exist instead of failing on them.
# (table -> {column -> SQL type used in `ALTER TABLE ... ADD COLUMN`}.)
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "social_accounts": {
        "refresh_token": "TEXT",
        "display_name": "VARCHAR(255)",
        "profile_picture": "TEXT",
        "status": "VARCHAR(20) DEFAULT 'connected'",
        "connected_at": "TIMESTAMP",
        "last_synced_at": "TIMESTAMP",
        "scopes": "TEXT",
        # The platform's own login id for this person, which Meta's
        # deauthorize / data-deletion callbacks name in their signed_request.
        "platform_user_id": "VARCHAR(255)",
    },
    "users": {
        "onboarding_completed": "BOOLEAN",
        "timezone": "VARCHAR(64) DEFAULT 'UTC'",
    },
    # Content Planner fields — added to the existing posts table.
    "posts": {
        "plan_id": "INTEGER",
        "content_type": "VARCHAR(40)",
        "topic": "VARCHAR(300)",
        "approval_status": "VARCHAR(20)",
        "media": "JSON",
        # Per-platform publishing choices (e.g. the Pinterest board a Pin goes to).
        "platform_options": "JSON",
    },
    # Strategy theme/rationale added after the plan table's first release.
    "content_plans": {
        "theme": "VARCHAR(200)",
        "summary": "TEXT",
        # Plan-level template / brand / image-style defaults.
        "image_defaults": "JSON",
    },
    # Campaign memory — what a campaign advertises, and the voice it uses.
    # Every generator inherits these, so an existing campaign needs them
    # backfilled rather than the column simply appearing on new rows.
    #
    # campaign_type carries NOT NULL to match `nullable=False` on the model.
    # The DEFAULT is what makes that safe to add to a populated table: both
    # SQLite and Postgres backfill existing rows with it as part of the ALTER.
    # A database migrated before this constraint was added keeps a nullable
    # column — harmless, since the ORM always supplies a value and the DEFAULT
    # already filled the rows that predate it.
    "ad_campaigns": {
        "campaign_type": "VARCHAR(60) NOT NULL DEFAULT 'Product Promotion'",
        "tone": "VARCHAR(60)",
        "audience": "VARCHAR(300)",
    },
    # Brand Kit — branding overlaid on generated images.
    "business_profiles": {
        "logo_url": "TEXT",
        "brand_colors": "JSON",
        "phone": "VARCHAR(40)",
        "email": "VARCHAR(255)",
        "address": "VARCHAR(500)",
    },
}


def _run_lightweight_migrations() -> None:
    """Add columns introduced after a table's initial release. Runs on startup."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in tables:
                continue
            existing = {col["name"] for col in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name in existing:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                logger.info("Migrated %s: added column %r", table, name)
                # Pre-existing users predate onboarding — mark them completed so
                # only brand-new users ever see the wizard.
                if table == "users" and name == "onboarding_completed":
                    conn.execute(
                        text("UPDATE users SET onboarding_completed = TRUE")
                    )
                    logger.info("Marked existing users as onboarding-completed")


def encrypt_existing_tokens() -> None:
    """Re-write any plaintext OAuth token in place as ciphertext. Idempotent.

    Accounts connected before encryption was switched on still hold plaintext
    tokens, and the column type only encrypts on write — so without this they
    would stay in the clear until each user happened to reconnect. Reading and
    writing through raw SQL is deliberate: it bypasses the `EncryptedString`
    type, which is what makes it possible to see what is actually stored.

    A no-op when no key is configured (nothing to encrypt with) and, after the
    first run, on every subsequent boot. Never logs a token — only how many.
    """
    from app.core import crypto

    if not crypto.is_enabled():
        return

    inspector = inspect(engine)
    if "social_accounts" not in set(inspector.get_table_names()):
        return

    updated = 0
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT id, access_token, refresh_token FROM social_accounts")
        ).all()
        for row_id, access_token, refresh_token in rows:
            changes: dict[str, str] = {}
            if access_token and not crypto.is_encrypted(access_token):
                changes["access_token"] = crypto.encrypt(access_token)
            if refresh_token and not crypto.is_encrypted(refresh_token):
                changes["refresh_token"] = crypto.encrypt(refresh_token)
            if not changes:
                continue
            assignments = ", ".join(f"{col} = :{col}" for col in changes)
            conn.execute(
                text(f"UPDATE social_accounts SET {assignments} WHERE id = :id"),
                {**changes, "id": row_id},
            )
            updated += 1

    if updated:
        logger.info("Encrypted stored OAuth tokens for %d connected account(s)", updated)
