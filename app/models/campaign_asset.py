"""Campaign asset ORM model — one thing a generator produced for a campaign.

Every image, banner, carousel slide, video, headline, caption and CTA made
inside AI Ads Studio lands here, attached to the campaign it was made in. That
is what turns a campaign from a form into a project: the tools stop being
one-shot generators whose output is lost on navigation, and the campaign gains
a library it owns.

Images and videos carry a `url`; copy carries `body`. One table rather than two
because the library shows them side by side, filters across them, and counts
them together — splitting by medium would mean every read joining them back up.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# The kinds the library groups by. Mirrors ASSET_KINDS in
# frontend/src/lib/ads/assets.js — the sections shown on a campaign.
ASSET_KINDS = (
    "image",
    "banner",
    "carousel",
    "video",
    "headline",
    "caption",
    "cta",
)


class CampaignAsset(Base):
    __tablename__ = "campaign_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Denormalised from the campaign so ownership can be checked, and the
    # user's recent assets listed, without a join on every read.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("ad_campaigns.id", ondelete="CASCADE"), index=True, nullable=False
    )

    kind: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="Untitled", nullable=False)

    # A visual asset's source. Text, not String: generated images come back as
    # provider URLs with long query strings.
    url: Mapped[str | None] = mapped_column(Text, default=None)
    # A copy asset's words.
    body: Mapped[str | None] = mapped_column(Text, default=None)

    # Which generator made it — shown on the card so a user can go back to the
    # tool that produced an asset rather than guessing.
    tool: Mapped[str | None] = mapped_column(String(60), default=None)

    # Everything tool-specific: banner size, aspect ratio, platform, slide
    # index, duration. Named `meta` because `metadata` is reserved by
    # SQLAlchemy's declarative base.
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
        return f"<CampaignAsset id={self.id} kind={self.kind} title={self.title!r}>"
