"""Contact-form schemas.

Validation lives here rather than in the route so the same rules apply to any
future caller (an admin tool, a test) and so FastAPI returns a precise 422
naming the offending field instead of a generic failure.

The messages are written to be shown to the person who typed the form: the
marketing page renders whatever comes back verbatim, and pydantic's own
defaults ("String should have at least 10 characters") read like a stack trace
leaking into the UI.
"""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator

NAME_MAX = 120
# Long enough for a real enquiry, short enough that the endpoint can't be used
# to push megabytes into the database.
MESSAGE_MIN = 10
MESSAGE_MAX = 4000


class ContactCreate(BaseModel):
    name: str
    email: EmailStr
    message: str

    # A honeypot field the real form renders hidden and leaves empty. Bots fill
    # every input they find, so a non-empty value here is a bot — the route
    # answers 200 anyway so it learns nothing from the response.
    website: str | None = Field(default=None, max_length=200)

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Please tell us your name.")
        if len(v) > NAME_MAX:
            raise ValueError(f"Please keep your name under {NAME_MAX} characters.")
        return v

    @field_validator("message")
    @classmethod
    def _check_message(cls, v: str) -> str:
        v = v.strip()
        if len(v) < MESSAGE_MIN:
            raise ValueError(
                "Please add a little more detail — your message needs at least "
                f"{MESSAGE_MIN} characters."
            )
        if len(v) > MESSAGE_MAX:
            raise ValueError(
                f"Please keep your message under {MESSAGE_MAX} characters."
            )
        return v


class ContactAccepted(BaseModel):
    """What the form gets back. Deliberately says nothing about storage or
    email delivery — the submitter only needs to know it arrived."""

    ok: bool = True
    message: str = "Thanks — your message has been received."
