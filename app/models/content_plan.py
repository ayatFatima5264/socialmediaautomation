"""Content Planner ORM models.

`ContentPlan` is one AI-generated content calendar (a "campaign"): the user's
preferences, the AI-proposed strategy (topics), and generation progress. The
generated posts themselves live in the existing `posts` table, linked back via
`Post.plan_id` — so the scheduler and calendar reuse works unchanged.

`PlannerSettings` stores per-user defaults so "Quick Generate" can run the whole
pipeline with one click, and the wizard can pre-fill sensible values.

Everything here is additive: existing posts/flows are untouched.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ContentPlan(Base):
    __tablename__ = "content_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    name: Mapped[str] = mapped_column(String(200), default="Content Plan", nullable=False)
    # "wizard" (Advanced Planner) or "quick" (Quick Generate).
    source: Mapped[str] = mapped_column(String(20), default="wizard", nullable=False)

    # ---- Preferences (Step 1) ------------------------------------------------
    duration_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    frequency: Mapped[str] = mapped_column(String(20), default="daily", nullable=False)
    posts_per_week: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    platforms: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    goals: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    content_mix: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    user_prompt: Mapped[str | None] = mapped_column(Text, default=None)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    auto_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ---- AI strategy (Step 2) ------------------------------------------------
    # The AI Marketing Manager's plan-level thinking: a theme + a rationale that
    # explains why this calendar serves the user's goals.
    theme: Mapped[str | None] = mapped_column(String(200), default=None)
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    # List of {id, date, weekday, content_type, topic} — editable before
    # generation. The single source of truth for what will be generated.
    topics: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # ---- Lifecycle / progress ------------------------------------------------
    # strategy -> generating -> ready -> scheduled  (or failed)
    status: Mapped[str] = mapped_column(
        String(20), default="strategy", index=True, nullable=False
    )
    total_posts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    generated_posts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, default=None)

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
        return f"<ContentPlan id={self.id} user={self.user_id} status={self.status}>"


class PlannerSettings(Base):
    """Per-user planner defaults, reused by the wizard and Quick Generate."""

    __tablename__ = "planner_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )

    default_duration_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    default_frequency: Mapped[str] = mapped_column(
        String(20), default="daily", nullable=False
    )
    default_posts_per_week: Mapped[int] = mapped_column(
        Integer, default=7, nullable=False
    )
    default_platforms: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    default_goals: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    default_content_mix: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    auto_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

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
        return f"<PlannerSettings user={self.user_id}>"
