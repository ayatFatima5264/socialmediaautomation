"""User ORM model — the root of multi-tenancy.

Posts and schedules added later will carry a `user_id` foreign key back to
this table so all data is scoped per account.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    full_name: Mapped[str | None] = mapped_column(String(255), default=None)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # IANA timezone (e.g. "America/New_York"). Used by the Content Planner to
    # schedule posts at the right local time. Defaults to UTC.
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    # Has the user finished (or dismissed) the business-onboarding wizard? New
    # users start False and see the wizard once; existing users are migrated to
    # True so they never see it. Set True on wizard finish.
    onboarding_completed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} email={self.email!r}>"
