"""VideoAsset ORM model — one file Video Studio holds, wherever it came from.

Uploads, generated voice-overs, stock clips, AI images, music, subtitle files,
thumbnails and finished renders are all rows here. One table rather than one per
medium because the Media Library lists them together, the timeline references
them by a single id space, and a render's output is an asset like any other.

The bytes are never in this row — `storage_key` points into object storage (see
app/services/storage). That is what keeps a 40 MB render out of the database and
what lets the whole library move buckets without touching a project.

`project_id` is NULLABLE, and that is the product rule made structural: Voice
Studio, Subtitle Studio and Thumbnail Studio must work with no project at all.
An asset made that way belongs to the user and shows up in their library; it
gains a project when — and only when — they press "Add to Project".
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Mirrors KINDS in app/services/storage/keys.py — the value is also the bucket
# prefix, so the two lists must not drift.
ASSET_KINDS = (
    "upload",
    "voice",
    "music",
    "subtitle",
    "image",
    "video",
    "thumbnail",
    "render",
)


class VideoAsset(Base):
    __tablename__ = "video_assets"
    __table_args__ = {"info": {"alembic_only": True}}

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # NULL until the user connects this asset to a project. See the module docs.
    # SET NULL rather than CASCADE: deleting a project must not delete a
    # voice-over the user also downloaded and may still want.
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("video_projects.id", ondelete="SET NULL"),
        index=True,
        default=None,
    )

    kind: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="Untitled", nullable=False)
    filename: Mapped[str | None] = mapped_column(String(255), default=None)

    # ---- Where the bytes are --------------------------------------------
    # `token` is the unguessable id in the public URL; `storage_key` is the
    # object's address inside the bucket. Both are stored because the read
    # route looks up by token and the storage layer addresses by key, and
    # deriving either from the other would hardcode the key layout.
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    # Which backend wrote it, so an asset stored before a migration to R2 can
    # still be read from where it actually is.
    storage_backend: Mapped[str] = mapped_column(String(20), default="database", nullable=False)

    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    # SHA-256 of the bytes, hex. This is how the Media Library avoids storing
    # the same file twice: ingest hashes first and, if this user already has an
    # asset of the same kind with the same digest, returns that row instead of
    # writing a second object. The same stock clip dropped into four projects
    # is one object in the bucket and one line on the storage bill.
    #
    # Nullable because rows written before this column existed have no digest
    # and must not be treated as "matches everything with no checksum".
    # `(user_id, checksum)` is indexed together — the lookup is always both.
    checksum: Mapped[str | None] = mapped_column(String(64), index=True, default=None)

    # ---- Media properties -----------------------------------------------
    # Null for anything without them (a subtitle file has no dimensions, an
    # image has no duration). Populated on ingest so the timeline can lay a
    # clip out without decoding the file again.
    duration_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    width: Mapped[int | None] = mapped_column(Integer, default=None)
    height: Mapped[int | None] = mapped_column(Integer, default=None)

    # Everything kind-specific: the voice and language of a voice-over, the
    # provider and prompt behind a generated image, the licence and attribution
    # of a stock clip, the transcript a subtitle file was built from.
    # Named `meta` because `metadata` is reserved on the declarative base.
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<VideoAsset id={self.id} kind={self.kind} "
            f"title={self.title!r} size={self.size_bytes}>"
        )
