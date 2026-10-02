"""Repair two pieces of wrong data written by earlier code.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-29

Two data fixes, no schema change. Nothing is dropped and no asset is deleted.

**1. Projects whose "thumbnail" is a video.** `renders.complete` used to point
`video_projects.thumbnail_asset_id` at the rendered MP4, on the theory that a
video has a poster frame. It does not have a *stored* one, so every project
rendered before this fix ended up with a thumbnail that was a video: the export
manifest advertised PNG and JPG, and the download then failed trying to decode
MP4 bytes as an image. The renderer now extracts a real poster frame into its
own asset; this revision brings the rows written before that in line.

Each broken row is re-pointed at a poster frame the newer renderer already
stored for that project, and failing that at any other image already attached
to it. Otherwise it is set to NULL — the honest value, since the project
genuinely has no thumbnail, and the manifest then says "Set a thumbnail in
Thumbnail Studio first" rather than promising a file it cannot produce. Only
rows whose asset is *not* an image are touched, so a real thumbnail keeps it.
The rendered video stays in the library and is still downloadable as the MP4
export.

**2. Assets filed as `upload` that are plainly images or video.**
`POST /api/video/media/upload` defaulted its `kind` form field to the literal
string `upload`, so a client that did not name a kind put every photo and every
clip into the same bucket as an MP3. In the library that meant a PNG showed up
under neither Images nor Videos, and appeared under Audio instead.

The upload endpoint now infers the kind from the media type, and the library's
filter tabs match on content type as well as kind — which fixes rows written by
any path. This revision additionally corrects the stored `kind` on the obvious
ones so the two agree.

Deliberately narrow: only `kind='upload'` rows whose content type is
unambiguously `image/*` or `video/*` are re-filed. An `upload` row whose type is
audio, text, or unknown is left alone, because `upload` is a real answer for
those and misfiling them would be a new bug rather than a fix. `voice`, `music`,
`subtitle`, `thumbnail` and `render` are never touched — those kinds are set by
the studio that produced the file, and mean something the media type cannot.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# (old kind, new kind, content-type prefix)
_REFILES = (
    ("upload", "image", "image/"),
    ("upload", "video", "video/"),
)


def _repair_thumbnails(connection) -> int:
    meta = sa.MetaData()
    projects = sa.Table("video_projects", meta, autoload_with=connection)
    assets = sa.Table("video_assets", meta, autoload_with=connection)

    # The broken rows: a thumbnail pointing at something that is not an image.
    # Selected on content_type rather than on `kind`, because the bug wrote a
    # `kind='render'` asset into the column and the column itself carries no
    # constraint — content_type is the thing the export actually decodes.
    broken = sa.select(
        projects.c.id,
        projects.c.thumbnail_asset_id,
    ).where(
        projects.c.thumbnail_asset_id.isnot(None),
        projects.c.thumbnail_asset_id.in_(
            sa.select(assets.c.id).where(
                sa.or_(
                    assets.c.content_type.is_(None),
                    ~assets.c.content_type.like("image/%"),
                )
            )
        ),
    )

    repaired = 0
    for project_id, old_asset_id in connection.execute(broken).fetchall():
        # A poster frame the newer renderer stored for this project. `meta` is
        # JSON, so this is a LIKE on the rendered text rather than a nested
        # query that would not run the same way on SQLite and Postgres.
        poster = connection.execute(
            sa.select(assets.c.id)
            .where(
                assets.c.project_id == project_id,
                assets.c.content_type.like("image/%"),
                assets.c.meta.like("%render_poster%"),
            )
            .order_by(assets.c.id.desc())
            .limit(1)
        ).scalar()

        if poster is None:
            # No poster for this project: fall back to any other image already
            # attached to it, so a user who uploaded one is not left without it.
            poster = connection.execute(
                sa.select(assets.c.id)
                .where(
                    assets.c.project_id == project_id,
                    assets.c.content_type.like("image/%"),
                    assets.c.id != old_asset_id,
                )
                .order_by(assets.c.id.desc())
                .limit(1)
            ).scalar()

        connection.execute(
            projects.update()
            .where(projects.c.id == project_id)
            .values(thumbnail_asset_id=poster)
        )
        repaired += 1

    return repaired


def _refile_uploads(connection) -> int:
    meta = sa.MetaData()
    assets = sa.Table("video_assets", meta, autoload_with=connection)

    moved = 0
    for old_kind, new_kind, prefix in _REFILES:
        result = connection.execute(
            assets.update()
            .where(
                assets.c.kind == old_kind,
                assets.c.content_type.like(f"{prefix}%"),
            )
            .values(kind=new_kind)
        )
        moved += result.rowcount or 0

    return moved


def upgrade() -> None:
    connection = op.get_bind()

    repaired = _repair_thumbnails(connection)
    if repaired:
        print(
            f"0004: repaired {repaired} project thumbnail(s) that pointed at a video"
        )

    refiled = _refile_uploads(connection)
    if refiled:
        print(f"0004: re-filed {refiled} misclassified upload(s) by media type")


def downgrade() -> None:
    """Nothing to undo.

    Both fixes overwrite values that were wrong, and neither can be recovered:
    which asset the old code would have put in `thumbnail_asset_id` is not
    recorded anywhere, and `kind` has always been a claim about intent that the
    database does not keep a copy of. Re-deriving either would mean putting
    known-broken values back on purpose, so the downgrade is deliberately a
    no-op.
    """
    return None
