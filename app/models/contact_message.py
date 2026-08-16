"""Contact-form submission ORM model.

Messages are persisted BEFORE the notification email is attempted, and the
email is best-effort on top. That ordering is the whole point of the table: a
mail outage — or an install with no SMTP configured at all — must never be the
reason someone's message disappears. Whatever happens to the email, the row is
already committed and readable from the database.

Not user-scoped: the contact form is public, so there is no account to attach a
message to. The submitter's email address is the only way back to them.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ContactMessage(Base):
    __tablename__ = "contact_messages"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Request context, kept for abuse triage only.
    ip_address: Mapped[str | None] = mapped_column(String(64), default=None)
    user_agent: Mapped[str | None] = mapped_column(String(400), default=None)

    # False when the notification email could not be sent (or SMTP is not
    # configured), so unsent messages can be found with a single query.
    emailed: Mapped[bool] = mapped_column(default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover — debugging aid
        return f"<ContactMessage id={self.id} from={self.email!r}>"
