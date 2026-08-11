"""MediaAsset ORM model — an image uploaded from the composer.

Why this exists: platforms publish an image by **fetching a URL themselves**
(Pinterest's `media_source.image_url`, the Meta Graph API's `image_url`). A file
picked in the browser is only a local `blob:` preview, so it can't be published.
This gives every upload a durable, publicly reachable URL.

The bytes live in the database on purpose. The app already runs on managed
Postgres, so uploads survive restarts and redeploys — unlike a container's
filesystem, which is wiped on every deploy and would silently break scheduled
posts whose image was uploaded days earlier.

`token` is a random, unguessable id used in the public URL. The public read
route is deliberately unauthenticated (Pinterest fetches it with no
credentials), so the token — not a session — is what keeps one user's uploads
from being enumerated by another.

Moving to object storage later (S3 / Vercel Blob / Cloudinary) means writing the
bytes there and storing the returned URL instead; `public_url` on the row stays
the only thing the rest of the app reads.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Owner, so a user can only ever list/delete their own uploads.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # Unguessable id used in the public URL (never the primary key, which is
    # sequential and would let anyone walk the whole table).
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    filename: Mapped[str | None] = mapped_column(String(255), default=None)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<MediaAsset id={self.id} user={self.user_id} "
            f"type={self.content_type} size={self.size_bytes}>"
        )
