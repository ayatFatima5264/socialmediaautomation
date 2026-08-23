"""UsageEvent ORM model — what a user consumed, recorded as it happens.

Video Studio is the first part of AutoSocial with a real marginal cost per
action: seconds of speech synthesised, minutes of audio transcribed, CPU-minutes
spent encoding, megabytes parked in a bucket. There is no billing system yet
(see the honesty rules in frontend/src/config/pricing.js), and this table
deliberately does not invent one.

What it does is make metering possible later without a backfill. Every metered
operation appends one row as it completes. A plan, a quota or an invoice is then
a query over these rows — and until such a thing exists, the same rows are what
answer "is this costing anything?" honestly.

No prices, no plan names, no tiers. An amount, a unit, and what produced it.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# The metered quantities. Each is measured in the unit that actually varies with
# cost, not in "credits" — a credit is a pricing decision and this table holds
# facts. Limits live in app/services/video/metering.py.
METRICS = (
    "voice_seconds",          # speech synthesised
    "transcription_seconds",  # audio transcribed
    "render_seconds",         # output duration encoded
    "ai_images",              # scene visuals generated
    "storage_bytes",          # bytes written to object storage
    "exports",                # files handed to the user
    "repurpose_clips",        # shorts cut from a long video
)


class UsageEvent(Base):
    __tablename__ = "usage_events"
    __table_args__ = {"info": {"alembic_only": True}}

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Which project it was spent on, when there was one. Voice Studio used on
    # its own produces usage with no project, exactly as it produces assets
    # with no project.
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("video_projects.id", ondelete="SET NULL"), default=None
    )

    metric: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Which feature spent it — "voice_studio", "subtitle_studio", "render".
    # Kept so a future limit can be scoped to a tool rather than to the account.
    source: Mapped[str | None] = mapped_column(String(40), default=None)

    # Provider, model, voice, language: whatever makes the number explainable
    # after the fact.
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<UsageEvent user={self.user_id} {self.metric}={self.quantity} "
            f"source={self.source}>"
        )
