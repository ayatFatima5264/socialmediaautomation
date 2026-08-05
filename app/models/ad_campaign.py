"""Ad campaign ORM model — an advertising campaign in AI Ads Studio.

A campaign groups the creatives, copy and platforms of one advertising effort
so it can be scheduled and measured as a unit. Distinct from `Post`, which is
one organic social post: an ad has a budget, a funnel objective, and a
performance reading, and it outlives any single creative in it.

Every campaign belongs to a user (multi-tenancy), the same as Post.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AdCampaign(Base):
    __tablename__ = "ad_campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    objective: Mapped[str] = mapped_column(String(60), default="Brand Awareness")
    # Stored as a JSON array; works on both SQLite and PostgreSQL, matching how
    # Post stores its hashtags.
    platforms: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # draft · scheduled · active · paused · completed (see lib/ads/constants.js)
    status: Mapped[str] = mapped_column(
        String(20), default="draft", index=True, nullable=False
    )

    brief: Mapped[str | None] = mapped_column(Text, default=None)
    # How many creatives have been produced for this campaign so far.
    creatives: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ---- Performance -------------------------------------------------------
    # Nullable on purpose: a campaign that has not run has no click-through
    # rate, and 0.0 would read as "it ran and nobody clicked" — a different and
    # much worse fact. The UI shows "Not started" while this is NULL.
    ctr: Mapped[float | None] = mapped_column(default=None)
    impressions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

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
        return f"<AdCampaign id={self.id} name={self.name!r} status={self.status}>"
