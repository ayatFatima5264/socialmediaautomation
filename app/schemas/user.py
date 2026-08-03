"""Auth/user API schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: str | None = Field(default=None, max_length=255)


class UserUpdate(BaseModel):
    """Fields a signed-in user may change about their own account.

    Deliberately narrow. Email is excluded because changing it requires a
    verification round-trip we don't have yet, and password changes go through
    the existing reset-token flow rather than a plain field here.
    """

    full_name: str | None = Field(default=None, max_length=255)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str | None
    is_active: bool
    onboarding_completed: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10)
    password: str = Field(min_length=8, max_length=72)


class MessageResponse(BaseModel):
    message: str
