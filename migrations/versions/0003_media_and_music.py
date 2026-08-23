"""Media Library de-duplication and the Music Library.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-23

Two additive changes. Nothing is dropped and nothing is rewritten, so this
revision is safe to apply to a database with live projects in it.

  * **`video_assets.checksum`.** A SHA-256 of the stored bytes, nullable. It is
    what lets the Media Library return an existing row instead of writing a
    second copy of a file the user already has. Nullable rather than
    backfilled: computing a digest for every existing object means downloading
    the whole bucket inside a migration, and a NULL simply means "unknown, so
    do not match" — the dedupe check requires a digest on both sides.

  * **`music_tracks`.** The Music Library, independent of `video_assets`
    because a track carries a licence and search facets a file does not. See
    the model docstring.

The composite `(user_id, checksum)` index is the one the dedupe lookup actually
uses; the single-column index SQLAlchemy would infer from `index=True` on the
column would leave that query scanning every asset the digest matched across
all accounts.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_NOW = sa.func.now()


def upgrade() -> None:
    # ---- video_assets.checksum ------------------------------------------
    # batch_alter_table because SQLite rebuilds the table to add a column with
    # an index; Postgres issues the plain ALTER. The test suite is SQLite and
    # production is Postgres, so both paths have to work.
    with op.batch_alter_table("video_assets") as batch:
        batch.add_column(sa.Column("checksum", sa.String(length=64), nullable=True))

    op.create_index(
        "ix_video_assets_user_checksum",
        "video_assets",
        ["user_id", "checksum"],
    )

    # ---- music_tracks ----------------------------------------------------
    op.create_table(
        "music_tracks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("external_key", sa.String(length=160), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("artist", sa.String(length=200), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="upload"),
        # ---- facets ----
        sa.Column("mood", sa.String(length=30), nullable=False, server_default="other"),
        sa.Column("genre", sa.String(length=30), nullable=False, server_default="other"),
        sa.Column("duration_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("bpm", sa.Integer(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        # ---- licence ----
        # No server_default: a track without a recorded licence must not be
        # insertable, and a default would quietly supply one.
        sa.Column("license", sa.String(length=20), nullable=False),
        sa.Column("license_url", sa.String(length=500), nullable=True),
        sa.Column("attribution", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        # ---- audio ----
        sa.Column("asset_id", sa.Integer(), nullable=True),
        sa.Column("stream_url", sa.String(length=1000), nullable=True),
        sa.Column("preview_url", sa.String(length=1000), nullable=True),
        sa.Column(
            "content_type", sa.String(length=120), nullable=False, server_default="audio/mpeg"
        ),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.PrimaryKeyConstraint("id"),
        # CASCADE on the user: somebody's uploaded tracks go with their
        # account. The catalogue rows have user_id NULL and are untouched.
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        # CASCADE on the asset, unlike everywhere else in this module: a music
        # track row whose audio has been deleted is not a track any more. There
        # are no per-track settings worth keeping — those live on the
        # `video_audio` layer, which is the thing that uses SET NULL.
        sa.ForeignKeyConstraint(["asset_id"], ["video_assets.id"], ondelete="CASCADE"),
    )

    op.create_index("ix_music_tracks_user_id", "music_tracks", ["user_id"])
    op.create_index(
        "ix_music_tracks_external_key", "music_tracks", ["external_key"], unique=True
    )
    op.create_index("ix_music_tracks_source", "music_tracks", ["source"])
    op.create_index("ix_music_tracks_mood", "music_tracks", ["mood"])
    op.create_index("ix_music_tracks_genre", "music_tracks", ["genre"])
    op.create_index("ix_music_tracks_duration", "music_tracks", ["duration_seconds"])
    op.create_index("ix_music_tracks_asset_id", "music_tracks", ["asset_id"])


def downgrade() -> None:
    for name in (
        "ix_music_tracks_asset_id",
        "ix_music_tracks_duration",
        "ix_music_tracks_genre",
        "ix_music_tracks_mood",
        "ix_music_tracks_source",
        "ix_music_tracks_external_key",
        "ix_music_tracks_user_id",
    ):
        op.drop_index(name, table_name="music_tracks")
    op.drop_table("music_tracks")

    op.drop_index("ix_video_assets_user_checksum", table_name="video_assets")
    with op.batch_alter_table("video_assets") as batch:
        batch.drop_column("checksum")
