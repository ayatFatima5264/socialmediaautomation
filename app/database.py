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


# Columns added to a table after its first release. `create_all` only creates
# missing *tables*, never alters existing ones, so we add any missing columns in
# place — idempotent and safe on both SQLite and Postgres. Only ever *adds*
# nullable columns, so it can never lose data.
# (table -> {column -> SQL type used in `ALTER TABLE ... ADD COLUMN`}.)
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "social_accounts": {
        "refresh_token": "TEXT",
        "display_name": "VARCHAR(255)",
        "profile_picture": "TEXT",
        "status": "VARCHAR(20) DEFAULT 'connected'",
        "connected_at": "TIMESTAMP",
        "last_synced_at": "TIMESTAMP",
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
    },
    # Strategy theme/rationale added after the plan table's first release.
    "content_plans": {
        "theme": "VARCHAR(200)",
        "summary": "TEXT",
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
