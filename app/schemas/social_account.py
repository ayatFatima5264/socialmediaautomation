"""Pydantic models for connected social accounts.

SocialAccountRead is deliberately token-free: the access token never leaves the
backend. The connect payloads carry the secrets in, only.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.post import Platform


class InstagramConnectRequest(BaseModel):
    """Manual connect: paste a token (and optionally a Page id).

    The backend resolves the Instagram Business account id + username from the
    Graph API, and — if META_APP_ID/SECRET are set and the token is short-lived
    — exchanges it for a long-lived token before storing.
    """
    access_token: str = Field(..., min_length=10, description="A Meta user or page access token.")
    # If omitted, the backend picks the first Page that has a linked IG account.
    page_id: str | None = Field(default=None, description="Facebook Page id linked to the IG account.")


class SocialAccountRead(BaseModel):
    """Safe, token-free view of a connected account."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: Platform
    account_id: str
    page_id: str | None
    username: str | None
    token_expires_at: datetime | None
    created_at: datetime
