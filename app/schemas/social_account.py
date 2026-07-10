"""Pydantic models for the Social Accounts module.

The API contract between FastAPI and the React frontend for connecting,
listing, refreshing and disconnecting a user's social accounts.

Security invariant: `SocialAccountRead` is deliberately token-free — the
access/refresh tokens never leave the backend. Only the fields the UI needs
are serialized. Connect payloads carry secrets *in*, only.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.post import Platform


class AccountStatus(str, Enum):
    """Lifecycle of a connected account, surfaced to the UI as a status badge."""

    not_connected = "not_connected"
    connected = "connected"
    token_expired = "token_expired"
    syncing = "syncing"
    error = "error"


class ConnectRequest(BaseModel):
    """Generic connect payload.

    Platform-agnostic on purpose: each platform's service reads the fields it
    needs and ignores the rest. Instagram uses `access_token` (+ optional
    `page_id`); the manually-connected platforms accept an optional
    `username`/`display_name` for a nicer card, and synthesize the rest.

    All fields are optional so the same endpoint serves every platform. Each
    platform service validates what it actually requires.
    """

    access_token: str | None = Field(
        default=None, description="Platform access token (required by real-OAuth platforms)."
    )
    refresh_token: str | None = Field(default=None, description="Optional refresh token.")
    page_id: str | None = Field(
        default=None, description="Facebook Page id linked to an Instagram account."
    )
    username: str | None = Field(default=None, max_length=255)
    display_name: str | None = Field(default=None, max_length=255)


class SocialAccountRead(BaseModel):
    """Safe, token-free view of a connected account for the UI."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: Platform
    status: AccountStatus
    # True when the account is connected but was authorized without a now-required
    # scope (e.g. X's media.write): the user should reconnect to grant it. The
    # account is NOT disconnected; text-only publishing still works.
    reauth_required: bool = False
    username: str | None
    display_name: str | None
    profile_picture: str | None
    # Present so the frontend can show "linked page" style detail if it wants;
    # never a secret.
    account_id: str | None
    page_id: str | None
    token_expires_at: datetime | None
    connected_at: datetime | None
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PlatformSummary(BaseModel):
    """One row of the connection-summary strip at the top of the page."""

    platform: Platform
    connected: bool
    status: AccountStatus


class AccountsOverview(BaseModel):
    """Everything the Accounts page needs in a single call."""

    accounts: list[SocialAccountRead]
    summary: list[PlatformSummary]
    connected_count: int
    total_platforms: int


class ApiResponse(BaseModel):
    """Uniform success/error envelope for mutating endpoints.

    `authorize_url`, when present, means the client should redirect the browser
    there to complete a real OAuth flow. `account` is set when the action
    finished (e.g. selecting or refreshing an account).
    """

    success: bool
    message: str
    account: SocialAccountRead | None = None
    authorize_url: str | None = None


class AccountCandidate(BaseModel):
    """One selectable account in the "choose which to connect" step."""

    account_id: str
    username: str | None
    display_name: str | None
    profile_picture: str | None
    # Human hint for disambiguation (e.g. the Facebook Page name).
    page_name: str | None = None


class PendingConnectionRead(BaseModel):
    """The candidate list for a pending multi-account selection."""

    id: str
    platform: Platform
    candidates: list[AccountCandidate]


class SelectAccountRequest(BaseModel):
    """Finish a multi-account connect by choosing one candidate."""

    pending_id: str
    account_id: str
