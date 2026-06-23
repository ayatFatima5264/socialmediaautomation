"""Database engine, session factory and declarative base.

Everything is driven by settings.database_url, so the same models run on
SQLite (local dev) and PostgreSQL (production) with no code changes — switch
by setting DATABASE_URL in .env.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# SQLite needs check_same_thread disabled for FastAPI's threadpool; Postgres
# and others take no special connect args.
_connect_args = (
    {"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {}
)

engine = create_engine(
    settings.database_url,
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
