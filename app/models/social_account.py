"""SocialAccount ORM model — a user's connected platform account.

Holds the per-account credentials the publisher adapters need (access token +
the platform's account/page ids) plus the display metadata the Accounts UI
shows (username, display name, avatar, status, sync times).

One row per (user, platform) — enforced by a unique constraint, so a user can
connect at most one account per platform. Tokens are stored here so the
background scheduler can publish without the user present; they are never
returned by the API (see schemas.social_account.SocialAccountRead).

Tokens are encrypted at rest: `access_token` and `refresh_token` use the
`EncryptedString` column type, so they are ciphertext in the database and plain
values everywhere in the app. See app/core/crypto.py for the key handling.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto import EncryptedString
from app.database import Base
from app.schemas.social_account import AccountStatus


class SocialAccount(Base):
    __tablename__ = "social_accounts"
    # A user connects at most one account per platform. This is the DB-level
    # guarantee behind the "one account per platform" business rule.
    __table_args__ = (
        UniqueConstraint("user_id", "platform", name="uq_social_account_user_platform"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    platform: Mapped[str] = mapped_column(String(20), nullable=False)

    # ---- Credentials (never serialized, encrypted at rest) ---------------
    # Long-lived access token used to call the platform API.
    access_token: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(EncryptedString, default=None)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    # Space-delimited OAuth scopes actually granted for this token, recorded at
    # connect time. Used to detect when a newly-required scope is missing and the
    # user must reconnect. NULL for accounts connected before this was tracked.
    scopes: Mapped[str | None] = mapped_column(Text, default=None)

    # ---- Platform identifiers --------------------------------------------
    # For Instagram:
    #   account_id -> Instagram Business/Creator account id (publishing target)
    #   page_id    -> the linked Facebook Page id
    # For manually-connected platforms a synthetic id is stored so publishers
    # and lookups have a stable handle.
    account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    page_id: Mapped[str | None] = mapped_column(String(255), default=None)
    # The id the *platform's own login* knows this person by, when it differs
    # from the publishing target above. Meta names the app-scoped user id in the
    # `signed_request` it sends to the deauthorize / data-deletion callbacks, and
    # for Instagram that is the Facebook user id — not the Instagram Business
    # account id in `account_id`. Without this column those callbacks could not
    # identify which Instagram row to delete. NULL for platforms where the two
    # are the same, and for rows connected before it was recorded.
    platform_user_id: Mapped[str | None] = mapped_column(
        String(255), index=True, default=None
    )

    # ---- Display metadata (safe to serialize) ----------------------------
    username: Mapped[str | None] = mapped_column(String(255), default=None)
    display_name: Mapped[str | None] = mapped_column(String(255), default=None)
    profile_picture: Mapped[str | None] = mapped_column(Text, default=None)

    # ---- Lifecycle -------------------------------------------------------
    status: Mapped[str] = mapped_column(
        String(20), default=AccountStatus.connected.value, nullable=False
    )
    connected_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

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
            f"platform={self.platform} username={self.username!r} "
            f"status={self.status}>"
        )
