"""BusinessProfile ORM model — a user's business context for the AI.

One profile per user (unique user_id). Every field is optional so the
onboarding wizard can be skipped question-by-question; the AI simply ignores
empty fields. New context fields (logo, brand colors, hashtags, competitors,
writing examples, …) can be added as nullable columns without touching the
onboarding/AI wiring.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BusinessProfile(Base):
    __tablename__ = "business_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )

    # Step 2 — Business information.
    business_name: Mapped[str | None] = mapped_column(String(255), default=None)
    industry: Mapped[str | None] = mapped_column(String(100), default=None)
    business_description: Mapped[str | None] = mapped_column(Text, default=None)

    # Step 3 — Target audience (single value or free text).
    target_audience: Mapped[str | None] = mapped_column(String(255), default=None)

    # Step 4 & 5 — multi-select, stored as JSON arrays (SQLite + Postgres safe).
    brand_voice: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    business_goals: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # Step 6 — Website (optional).
    website: Mapped[str | None] = mapped_column(String(500), default=None)

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
        return f"<BusinessProfile user={self.user_id} name={self.business_name!r}>"
