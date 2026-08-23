"""Video Studio: projects, assets, render jobs, usage events, dev object store.

Revision ID: 0001
Revises:
Create Date: 2026-08-22

This is the first Alembic revision in the project. It creates only Video Studio
tables — the ten tables that predate it are still managed by
`Base.metadata.create_all` on startup, and `migrations/env.py` deliberately
hides them from autogenerate. See migrations/README.md.

Two things were changed from what autogenerate produced, and both matter:

  * **The circular foreign key is broken apart.** `video_assets.project_id`
    points at `video_projects`, and `video_projects.thumbnail_asset_id` points
    back at `video_assets`. Autogenerate emitted them as two ordinary tables
    and put `video_assets` first, which cannot apply — the referenced table
    does not exist yet. The projects table is therefore created without its
    thumbnail constraint, and the constraint is added once both tables exist.

  * **`server_default` uses `sa.func.now()`, not `sa.text("now()")`.**
    `now()` is Postgres syntax; the test suite and a fresh local checkout run
    on SQLite, where it is a syntax error. `func.now()` compiles to the right
    thing on both.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Every timestamp column in this revision. Defined once so a new table cannot
# accidentally get a subtly different default.
_NOW = sa.func.now()


def upgrade() -> None:
    # ---- video_projects --------------------------------------------------
    # Created first (minus the thumbnail FK) because video_assets references it.
    op.create_table(
        "video_projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("project_type", sa.String(length=30), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("aspect_ratio", sa.String(length=12), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("fps", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("script", sa.JSON(), nullable=False),
        sa.Column("scenes", sa.JSON(), nullable=False),
        sa.Column("timeline", sa.JSON(), nullable=False),
        sa.Column("subtitles", sa.JSON(), nullable=False),
        sa.Column("subtitle_style", sa.JSON(), nullable=False),
        sa.Column("brand", sa.JSON(), nullable=False),
        sa.Column("template_key", sa.String(length=80), nullable=True),
        sa.Column("export_settings", sa.JSON(), nullable=False),
        # The constraint is added at the end of this migration.
        sa.Column("thumbnail_asset_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_video_projects_user_id", "video_projects", ["user_id"])
    op.create_index("ix_video_projects_status", "video_projects", ["status"])

    # ---- video_assets ----------------------------------------------------
    op.create_table(
        "video_assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("storage_backend", sa.String(length=20), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["video_projects.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_video_assets_user_id", "video_assets", ["user_id"])
    op.create_index("ix_video_assets_project_id", "video_assets", ["project_id"])
    op.create_index("ix_video_assets_kind", "video_assets", ["kind"])
    op.create_index("ix_video_assets_token", "video_assets", ["token"], unique=True)

    # The other half of the cycle, now that both tables exist.
    #
    # Through `batch_alter_table`, not a bare `op.create_foreign_key`: SQLite
    # cannot ALTER a constraint at all, and the bare call raises
    # NotImplementedError there. Batch mode recreates the table with the
    # constraint on SQLite and issues the plain ALTER on Postgres, so the same
    # revision applies to the test suite and to production.
    with op.batch_alter_table("video_projects") as batch:
        batch.create_foreign_key(
            "fk_video_projects_thumbnail_asset_id",
            "video_assets",
            ["thumbnail_asset_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # ---- render_jobs -----------------------------------------------------
    op.create_table(
        "render_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("stage", sa.String(length=20), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("timeline_snapshot", sa.JSON(), nullable=False),
        sa.Column("output_asset_id", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["video_projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["output_asset_id"], ["video_assets.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_render_jobs_user_id", "render_jobs", ["user_id"])
    op.create_index("ix_render_jobs_project_id", "render_jobs", ["project_id"])
    op.create_index("ix_render_jobs_status", "render_jobs", ["status"])

    # ---- usage_events ----------------------------------------------------
    op.create_table(
        "usage_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("metric", sa.String(length=40), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["video_projects.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usage_events_user_id", "usage_events", ["user_id"])
    op.create_index("ix_usage_events_metric", "usage_events", ["metric"])
    op.create_index("ix_usage_events_created_at", "usage_events", ["created_at"])

    # ---- storage_objects -------------------------------------------------
    # The development fallback for object storage. Empty in production, where
    # STORAGE_BACKEND resolves to R2. See app/models/storage_object.py.
    op.create_table(
        "storage_objects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_storage_objects_key", "storage_objects", ["key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_storage_objects_key", table_name="storage_objects")
    op.drop_table("storage_objects")

    op.drop_index("ix_usage_events_created_at", table_name="usage_events")
    op.drop_index("ix_usage_events_metric", table_name="usage_events")
    op.drop_index("ix_usage_events_user_id", table_name="usage_events")
    op.drop_table("usage_events")

    op.drop_index("ix_render_jobs_status", table_name="render_jobs")
    op.drop_index("ix_render_jobs_project_id", table_name="render_jobs")
    op.drop_index("ix_render_jobs_user_id", table_name="render_jobs")
    op.drop_table("render_jobs")

    # Drop the added constraint before the table it points at, or the drop of
    # video_assets fails on a database that enforces foreign keys. Batch mode
    # for the same reason as the upgrade — SQLite cannot ALTER a constraint.
    with op.batch_alter_table("video_projects") as batch:
        batch.drop_constraint(
            "fk_video_projects_thumbnail_asset_id", type_="foreignkey"
        )

    op.drop_index("ix_video_assets_token", table_name="video_assets")
    op.drop_index("ix_video_assets_kind", table_name="video_assets")
    op.drop_index("ix_video_assets_project_id", table_name="video_assets")
    op.drop_index("ix_video_assets_user_id", table_name="video_assets")
    op.drop_table("video_assets")

    op.drop_index("ix_video_projects_status", table_name="video_projects")
    op.drop_index("ix_video_projects_user_id", table_name="video_projects")
    op.drop_table("video_projects")
