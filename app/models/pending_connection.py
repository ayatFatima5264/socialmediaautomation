"""PendingConnection — a short-lived OAuth result awaiting the user's choice.

When one OAuth login exposes several connectable accounts (e.g. multiple
Instagram Business accounts across a user's Facebook Pages), we can't decide for
them. We stash the freshly-obtained token plus the candidate list here, hand the
browser an opaque id, and let the user pick. On selection we store only the
chosen account and delete this row. Rows expire (see service) so tokens don't
linger.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PendingConnection(Base):
    __tablename__ = "pending_connections"

    # Opaque, unguessable id handed to the browser (secrets.token_urlsafe).
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)

    # The freshly-obtained (long-lived) token the chosen account will be saved
    # with. Server-side only — never sent to the browser.
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    # JSON list of candidate accounts (id/username/avatar/page) for the picker.
    candidates: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PendingConnection id={self.id} user={self.user_id} platform={self.platform}>"
