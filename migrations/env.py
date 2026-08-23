"""Alembic environment.

Two things differ from the generated default, both on purpose:

  * The database URL is read from app.config.settings, never from alembic.ini.
    One source of truth means a migration cannot be applied to a database the
    app is not using, and no password is committed.

  * Autogenerate only considers tables marked ``alembic_only``. Everything
    older is still created by `create_all` (see app/database.py), and without
    this filter every autogenerate would propose dropping or recreating tables
    Alembic has never managed.
"""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.database import Base, _normalize_db_url

# Registers every model on Base.metadata. Without it autogenerate sees nothing.
import app.models  # noqa: F401,E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# app.database.run_migrations() sets this before calling upgrade(); a developer
# running `alembic` from a shell gets it from settings instead.
if not config.get_main_option("sqlalchemy.url", None):
    config.set_main_option(
        "sqlalchemy.url", _normalize_db_url(settings.database_url).replace("%", "%%")
    )

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Restrict Alembic to the tables it owns.

    A table is Alembic's when its model declares
    ``__table_args__ = {"info": {"alembic_only": True}}``. Anything else — the
    original AutoSocial schema — belongs to `create_all` and must be invisible
    here, or autogenerate writes a migration that drops it.
    """
    if type_ == "table":
        # `reflected` objects come from the database, where `info` is empty.
        # Look the name up in the model metadata instead.
        model_table = target_metadata.tables.get(name)
        if model_table is None:
            return False
        return bool(model_table.info.get("alembic_only"))

    # Columns, indexes and constraints follow their table.
    parent = getattr(obj, "table", None)
    if parent is not None:
        model_table = target_metadata.tables.get(parent.name)
        return bool(model_table is not None and model_table.info.get("alembic_only"))
    return True


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (`alembic upgrade --sql`)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
