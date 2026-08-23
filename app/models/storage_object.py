"""StorageObject — the development fallback for the object store.

Production keeps Video Studio's bytes in Cloudflare R2. Locally there is often
no bucket, and a developer who has just cloned the repo should still be able to
record a voice-over and play it back. This table is that fallback: the same
`ObjectStorage` contract, backed by a BYTEA column.

It is NOT a production storage backend and the factory refuses to select it
when `STORAGE_BACKEND=r2`. Video files in a row are exactly what the R2
decision was made to avoid — they bloat backups, they stream badly, and Postgres
charges for every byte at database prices.

`token` is the unguessable id that appears in the public read URL, mirroring
`media_assets`: the read route has no session, because a social platform
fetching an asset brings no credentials of ours.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StorageObject(Base):
    __tablename__ = "storage_objects"
    # Owned by Alembic, not by create_all — see app/database.py.
    __table_args__ = {"info": {"alembic_only": True}}

    id: Mapped[int] = mapped_column(primary_key=True)

    # The storage key, identical to the one R2 would use. Keeping the key
    # space the same across backends is what makes a later migration a copy
    # loop rather than a rewrite of every row that references an object.
    key: Mapped[str] = mapped_column(String(512), unique=True, index=True, nullable=False)

    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    filename: Mapped[str | None] = mapped_column(String(255), default=None)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<StorageObject key={self.key!r} size={self.size_bytes}>"
