"""Post ORM model — a generated/saved post, optionally scheduled.

Every post belongs to a user (multi-tenancy). The scheduler publishes posts
whose status is `scheduled` once their `scheduled_time` arrives.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.schemas.post import PostStatus


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Stored as a JSON array; works on both SQLite and PostgreSQL.
    hashtags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    status: Mapped[str] = mapped_column(
        String(20), default=PostStatus.draft.value, index=True, nullable=False
    )

    # ---- Content Planner fields (all nullable so standalone posts are unaffected)
    # When a post belongs to an AI Content Plan, this links back to it.
    plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("content_plans.id", ondelete="CASCADE"), index=True, default=None
    )
    # The planned content type (e.g. "Educational", "Promotional") and topic.
    content_type: Mapped[str | None] = mapped_column(String(40), default=None)
    topic: Mapped[str | None] = mapped_column(String(300), default=None)
    # Approval gate for planner posts: "pending" until the user approves, then
    # the post is promoted to status=scheduled. None for non-planner posts.
    approval_status: Mapped[str | None] = mapped_column(
        String(20), index=True, default=None
    )
    # Optional attached visuals (image / carousel), stored as JSON. Forward-
    # compatible with the AI Visuals step; empty for text-only posts.
    media: Mapped[list | None] = mapped_column(JSON, default=None)

    # Naive UTC (see app.core.timeutils).
    scheduled_time: Mapped[datetime | None] = mapped_column(
        DateTime, index=True, default=None
    )
    published_time: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    # Filled by the publisher adapter on success / failure.
    external_id: Mapped[str | None] = mapped_column(String(255), default=None)
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
        return f"<Post id={self.id} platform={self.platform} status={self.status}>"
