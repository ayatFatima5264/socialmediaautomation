# Database migrations

Alembic owns every table added from Video Studio onwards. Everything older is
still created by `Base.metadata.create_all` on startup, exactly as before — see
`_create_all_tables()` in `app/database.py` for why both exist and how they are
kept from fighting.

A table opts into Alembic by declaring:

```python
class VideoProject(Base):
    __tablename__ = "video_projects"
    __table_args__ = {"info": {"alembic_only": True}}
```

`migrations/env.py` filters autogenerate to exactly those tables. Without that
filter, every `--autogenerate` would propose dropping the ten tables Alembic has
never managed.

## Day to day

```bash
venv/Scripts/alembic revision --autogenerate -m "add subtitle presets"
venv/Scripts/alembic upgrade head
venv/Scripts/alembic downgrade -1
venv/Scripts/alembic current
```

Always read a generated revision before committing it. Autogenerate is a first
draft: it does not see data, and it will happily write a `NOT NULL` column with
no default onto a populated table.

## In production

Nobody runs these by hand. `app.database.run_migrations()` calls `upgrade head`
during FastAPI startup, because the app deploys as one container with no release
phase. A migration failure is logged and does **not** take the API down — the
rest of AutoSocial keeps working and Video Studio reports the missing tables.

## The database URL

There is no `sqlalchemy.url` in `alembic.ini`. It is read from
`app.config.settings.database_url`, so migrations and the application can never
point at different databases, and no connection string is committed.
