"""SocialAccount ORM model — a user's connected platform account.

Holds the per-account credentials the publisher adapters need (access token +
the platform's account/page ids). One row per (user, platform). Tokens are
stored here so the background scheduler can publish without the user present;
they are never returned by the API (see schemas.social_account.SocialAccountRead).

NOTE: tokens are stored as-is for now. For production, encrypt `access_token`
at rest (e.g. Fernet / a KMS) — left as a clearly-marked follow-up.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SocialAccount(Base):
    __tablename__ = "social_accounts"
    # A user connects at most one account per platform.
    __table_args__ = (
        UniqueConstraint("user_id", "platform", name="uq_social_account_user_platform"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    platform: Mapped[str] = mapped_column(String(20), nullable=False)

    # Long-lived access token used to call the platform API.
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    # Platform account identifiers. For Instagram:
    #   account_id  -> Instagram Business/Creator account id (publishing target)
    #   page_id     -> the linked Facebook Page id
    #   username    -> @handle, for display
    account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    page_id: Mapped[str | None] = mapped_column(String(255), default=None)
    username: Mapped[str | None] = mapped_column(String(255), default=None)

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
            f"<SocialAccount id={self.id} user={self.user_id} "
            f"platform={self.platform} username={self.username!r}>"
        )
