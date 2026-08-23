"""Video Studio foundation: scenes, audio, subtitles, templates, versions.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-23

Takes the sketch in 0001 to the shape the tools actually need.

Three kinds of change, all additive or in-place — nothing here loses data:

  * **Five new tables.** `video_templates`, `video_scenes`, `video_audio`,
    `video_subtitles`, `video_project_versions`.

  * **`render_jobs` becomes `video_renders`.** A rename, not a drop-and-create,
    so any queued job survives it. Three columns are added (`error_code`,
    `error_stage`, `duration_seconds`) and the status vocabulary is normalised
    to draft/processing/completed/failed/cancelled — `running` becomes
    `processing`, `succeeded` becomes `completed`.

  * **Three JSON columns leave `video_projects`.** `scenes`, `subtitles` and
    `subtitle_style` are now rows in the new tables. The data in them is copied
    across before the columns are dropped, so a project written against 0001
    keeps its scenes and its captions.

`batch_alter_table` is used for every ALTER because SQLite cannot drop a column
or add a foreign key in place — it rebuilds the table instead. Postgres ignores
the batching and issues the plain ALTER. Both are needed: production is
Postgres, the test suite is SQLite.
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_NOW = sa.func.now()


def upgrade() -> None:
    # ---- video_templates -------------------------------------------------
    # First, because video_projects gains a foreign key pointing at it.
    op.create_table(
        "video_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=40), nullable=False, server_default="other"),
        sa.Column("platform", sa.String(length=40), nullable=False, server_default="youtube_shorts"),
        sa.Column("aspect_ratio", sa.String(length=12), nullable=False, server_default="9:16"),
        sa.Column("width", sa.Integer(), nullable=False, server_default="1080"),
        sa.Column("height", sa.Integer(), nullable=False, server_default="1920"),
        sa.Column("fps", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("preview_asset_id", sa.Integer(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["preview_asset_id"], ["video_assets.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_video_templates_key", "video_templates", ["key"], unique=True)
    op.create_index("ix_video_templates_user_id", "video_templates", ["user_id"])
    op.create_index("ix_video_templates_category", "video_templates", ["category"])

    # ---- video_scenes ----------------------------------------------------
    op.create_table(
        "video_scenes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("visual_prompt", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("asset_id", sa.Integer(), nullable=True),
        sa.Column("voice_asset_id", sa.Integer(), nullable=True),
        sa.Column("start_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Float(), nullable=False, server_default="5"),
        sa.Column("transition", sa.String(length=20), nullable=False, server_default="cut"),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["video_assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["voice_asset_id"], ["video_assets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_video_scenes_project_id", "video_scenes", ["project_id"])
    op.create_index("ix_video_scenes_asset_id", "video_scenes", ["asset_id"])

    # ---- video_audio -----------------------------------------------------
    op.create_table(
        "video_audio",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="music"),
        sa.Column("label", sa.String(length=200), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("start_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("trim_start", sa.Float(), nullable=False, server_default="0"),
        sa.Column("trim_end", sa.Float(), nullable=True),
        sa.Column("volume", sa.Float(), nullable=False, server_default="1"),
        sa.Column("fade_in", sa.Float(), nullable=False, server_default="0"),
        sa.Column("fade_out", sa.Float(), nullable=False, server_default="0"),
        sa.Column("ducking", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("loop", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("muted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["video_assets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_video_audio_project_id", "video_audio", ["project_id"])
    op.create_index("ix_video_audio_asset_id", "video_audio", ["asset_id"])
    op.create_index("ix_video_audio_role", "video_audio", ["role"])

    # ---- video_subtitles -------------------------------------------------
    op.create_table(
        "video_subtitles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=False, server_default="en-US"),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("cues", sa.JSON(), nullable=False),
        sa.Column("style", sa.JSON(), nullable=False),
        sa.Column("cue_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("asset_id", sa.Integer(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["video_assets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_video_subtitles_project_id", "video_subtitles", ["project_id"])

    # ---- video_project_versions -----------------------------------------
    op.create_table(
        "video_project_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reason", sa.String(length=20), nullable=False, server_default="autosave"),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_video_project_versions_project_id", "video_project_versions", ["project_id"]
    )
    op.create_index(
        "ix_video_project_versions_revision", "video_project_versions", ["revision"]
    )
    op.create_index(
        "ix_video_project_versions_created_at", "video_project_versions", ["created_at"]
    )

    # ---- render_jobs -> video_renders ------------------------------------
    # Indexes are dropped first: Postgres carries them across a rename under
    # their old names, which would then collide with the new ones.
    op.drop_index("ix_render_jobs_user_id", table_name="render_jobs")
    op.drop_index("ix_render_jobs_project_id", table_name="render_jobs")
    op.drop_index("ix_render_jobs_status", table_name="render_jobs")
    op.rename_table("render_jobs", "video_renders")

    with op.batch_alter_table("video_renders") as batch:
        batch.add_column(sa.Column("error_code", sa.String(length=30), nullable=True))
        batch.add_column(sa.Column("error_stage", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("duration_seconds", sa.Float(), nullable=True))

    op.create_index("ix_video_renders_user_id", "video_renders", ["user_id"])
    op.create_index("ix_video_renders_project_id", "video_renders", ["project_id"])
    op.create_index("ix_video_renders_status", "video_renders", ["status"])

    op.execute("UPDATE video_renders SET status = 'processing' WHERE status = 'running'")
    op.execute("UPDATE video_renders SET status = 'completed' WHERE status = 'succeeded'")

    # ---- video_projects --------------------------------------------------
    _move_project_documents_into_tables()

    with op.batch_alter_table("video_projects") as batch:
        batch.add_column(sa.Column("description", sa.Text(), nullable=True))
        batch.add_column(sa.Column("template_id", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("last_autosave_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.create_foreign_key(
            "fk_video_projects_template_id",
            "video_templates",
            ["template_id"],
            ["id"],
            ondelete="SET NULL",
        )
        # Now rows in video_scenes / video_subtitles — see the copy above.
        batch.drop_column("scenes")
        batch.drop_column("subtitles")
        batch.drop_column("subtitle_style")

    op.execute("UPDATE video_projects SET status = 'processing' WHERE status = 'rendering'")
    op.execute("UPDATE video_projects SET status = 'completed' WHERE status = 'rendered'")


def _move_project_documents_into_tables() -> None:
    """Copy each project's `scenes` and `subtitles` JSON into the new rows.

    Runs before the columns are dropped. Written with the core expression
    language rather than the ORM because a migration must not depend on what
    the models look like today — the models have already moved on, and reading
    a dropped attribute is how a migration stops being replayable.

    A project with nothing in those columns produces no rows, which is the
    normal case: 0001 shipped hours ago and these tables are new.
    """
    connection = op.get_bind()

    projects = sa.table(
        "video_projects",
        sa.column("id", sa.Integer),
        sa.column("scenes", sa.JSON),
        sa.column("subtitles", sa.JSON),
        sa.column("subtitle_style", sa.JSON),
    )
    scenes_table = sa.table(
        "video_scenes",
        sa.column("project_id", sa.Integer),
        sa.column("position", sa.Integer),
        sa.column("title", sa.String),
        sa.column("text", sa.Text),
        sa.column("visual_prompt", sa.Text),
        sa.column("source", sa.String),
        sa.column("start_seconds", sa.Float),
        sa.column("duration_seconds", sa.Float),
        sa.column("transition", sa.String),
        sa.column("settings", sa.JSON),
    )
    subtitles_table = sa.table(
        "video_subtitles",
        sa.column("project_id", sa.Integer),
        sa.column("language", sa.String),
        sa.column("source", sa.String),
        sa.column("is_primary", sa.Boolean),
        sa.column("cues", sa.JSON),
        sa.column("style", sa.JSON),
        sa.column("cue_count", sa.Integer),
        sa.column("duration_seconds", sa.Float),
        sa.column("meta", sa.JSON),
    )

    rows = connection.execute(
        sa.select(
            projects.c.id, projects.c.scenes, projects.c.subtitles, projects.c.subtitle_style
        )
    ).all()

    for project_id, raw_scenes, raw_cues, raw_style in rows:
        scenes = _as_list(raw_scenes)
        if scenes:
            start = 0.0
            payload = []
            for position, scene in enumerate(scenes):
                if not isinstance(scene, dict):
                    continue
                duration = _as_float(scene.get("duration"), 5.0)
                payload.append(
                    {
                        "project_id": project_id,
                        "position": position,
                        "title": (scene.get("title") or None),
                        "text": (scene.get("text") or None),
                        "visual_prompt": (
                            scene.get("visual_prompt") or scene.get("visual") or None
                        ),
                        "source": "pending",
                        "start_seconds": start,
                        "duration_seconds": duration,
                        "transition": (scene.get("transition") or "cut"),
                        "settings": {},
                    }
                )
                start += duration
            if payload:
                connection.execute(sa.insert(scenes_table), payload)

        cues = _as_list(raw_cues)
        if cues:
            style = raw_style if isinstance(raw_style, dict) else {}
            end = 0.0
            for cue in cues:
                if isinstance(cue, dict):
                    end = max(end, _as_float(cue.get("end"), 0.0))
            connection.execute(
                sa.insert(subtitles_table),
                [
                    {
                        "project_id": project_id,
                        "language": "en-US",
                        "source": "manual",
                        "is_primary": True,
                        "cues": cues,
                        "style": style,
                        "cue_count": len(cues),
                        "duration_seconds": end,
                        "meta": {"migrated_from": "video_projects.subtitles"},
                    }
                ],
            )


def _as_list(value) -> list:
    """JSON columns come back as a list on Postgres and, on some drivers, a
    string. Anything else is treated as empty rather than raising — a
    migration that dies on one malformed row blocks every deploy after it."""
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except ValueError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _as_float(value, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def downgrade() -> None:
    # The JSON columns come back empty. Their contents are in video_scenes and
    # video_subtitles, which this drops — a downgrade of a data-moving migration
    # cannot be lossless, and pretending otherwise by half-restoring is worse
    # than saying so here.
    op.execute("UPDATE video_projects SET status = 'rendering' WHERE status = 'processing'")
    op.execute("UPDATE video_projects SET status = 'rendered' WHERE status = 'completed'")

    with op.batch_alter_table("video_projects") as batch:
        batch.add_column(sa.Column("scenes", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("subtitles", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("subtitle_style", sa.JSON(), nullable=True))
        batch.drop_constraint("fk_video_projects_template_id", type_="foreignkey")
        batch.drop_column("last_autosave_at")
        batch.drop_column("template_id")
        batch.drop_column("description")

    op.execute("UPDATE video_projects SET scenes = '[]', subtitles = '[]', subtitle_style = '{}'")

    op.execute("UPDATE video_renders SET status = 'running' WHERE status = 'processing'")
    op.execute("UPDATE video_renders SET status = 'succeeded' WHERE status = 'completed'")

    op.drop_index("ix_video_renders_status", table_name="video_renders")
    op.drop_index("ix_video_renders_project_id", table_name="video_renders")
    op.drop_index("ix_video_renders_user_id", table_name="video_renders")
    with op.batch_alter_table("video_renders") as batch:
        batch.drop_column("duration_seconds")
        batch.drop_column("error_stage")
        batch.drop_column("error_code")
    op.rename_table("video_renders", "render_jobs")
    op.create_index("ix_render_jobs_user_id", "render_jobs", ["user_id"])
    op.create_index("ix_render_jobs_project_id", "render_jobs", ["project_id"])
    op.create_index("ix_render_jobs_status", "render_jobs", ["status"])

    op.drop_table("video_project_versions")
    op.drop_table("video_subtitles")
    op.drop_table("video_audio")
    op.drop_table("video_scenes")
    op.drop_table("video_templates")
