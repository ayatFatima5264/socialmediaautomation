"""Base OAuth 2.0 provider — the shared authorization-code flow.

Concrete platforms (facebook, instagram, linkedin, x, pinterest, threads)
subclass this and declare only what differs: endpoints, scopes, token-auth
style, PKCE, and how to read a user profile. Everything mechanical — building
the authorize URL, exchanging the code, refreshing — lives here so the per-
platform files stay tiny.

Design goals: production-ready (real endpoints, real token exchange, clear
errors), and extensible (a new platform is one subclass + one registry line).
"""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from dataclasses import dataclass, field
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.schemas.post import Platform

logger = logging.getLogger(__name__)


class OAuthError(Exception):
    """An OAuth step failed; message is safe to surface to the user."""


@dataclass
class OAuthTokens:
    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None  # seconds until the access token expires
    raw: dict = field(default_factory=dict)


@dataclass
class ProfileInfo:
    """Normalized profile used to populate the SocialAccount row."""

    account_id: str
    username: str | None = None
    display_name: str | None = None
    profile_picture: str | None = None
    page_id: str | None = None
    # Human hint for the account picker (e.g. the linked Facebook Page name).
    page_name: str | None = None


def generate_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for PKCE S256."""
    verifier = secrets.token_urlsafe(64)[:96]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


class OAuthProvider:
    """Abstract base. Subclasses set the class attributes and parse profiles."""

    # Internal platform (the app's Platform enum). X maps to Platform.twitter.
    platform: Platform
    # Public URL/config slug: facebook, instagram, linkedin, x, pinterest,
    # threads. Drives both the callback URL and the *_client_id/secret lookup.
    slug: str

    authorize_endpoint: str
    token_endpoint: str
    scopes: list[str] = []
    # Subset of `scopes` that is mandatory for full functionality. If a stored
    # account was authorized without one of these (e.g. a scope added after it
    # connected), the app flags it as needing re-authorization. Empty by default
    # so platforms opt in explicitly and none are flagged retroactively.
    required_scopes: list[str] = []
    # Scope delimiter — most use space; Meta/Threads use comma.
    scope_separator: str = " "
    # "body" sends client_secret in the token request body; "basic" uses an
    # HTTP Basic Authorization header (X, Pinterest).
    token_auth: str = "body"
    use_pkce: bool = False

    # ---- configuration ---------------------------------------------------
    @property
    def client_id(self) -> str | None:
        return settings.oauth_credentials(self.slug)[0]

    @property
    def client_secret(self) -> str | None:
        return settings.oauth_credentials(self.slug)[1]

    @property
    def redirect_uri(self) -> str:
        return settings.callback_url(self.slug)

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    # Extra query params merged into the authorize URL (e.g. forcing a fresh
    # login / account selection). Overridden per provider.
    authorize_params: dict[str, str] = {}

    # ---- authorize -------------------------------------------------------
    def authorize_url(self, *, state: str, code_challenge: str | None = None) -> str:
        params = {
            "client_id": self.client_id or "",
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": self.scope_separator.join(self.scopes),
            "state": state,
            **self.authorize_params,
        }
        if self.use_pkce and code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        return f"{self.authorize_endpoint}?{urlencode(params)}"

    # ---- token exchange --------------------------------------------------
    async def exchange_code(
        self, code: str, *, code_verifier: str | None = None
    ) -> OAuthTokens:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
        }
        if self.use_pkce and code_verifier:
            data["code_verifier"] = code_verifier
        return await self._token_request(data)

    async def refresh(self, refresh_token: str) -> OAuthTokens:
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        return await self._token_request(data)

    async def _token_request(self, data: dict) -> OAuthTokens:
        headers = {"Accept": "application/json"}
        auth = None
        if self.token_auth == "basic":
            auth = (self.client_id or "", self.client_secret or "")
        else:  # secret in body
            data = {**data, "client_id": self.client_id, "client_secret": self.client_secret}
        # PKCE public-client token requests still need client_id present.
        data.setdefault("client_id", self.client_id)

        try:
            async with httpx.AsyncClient(timeout=settings.ai_request_timeout) as client:
                resp = await client.post(
                    self.token_endpoint, data=data, headers=headers, auth=auth
                )
        except httpx.HTTPError as exc:
            raise OAuthError(f"{self.slug}: token request failed ({exc}).") from exc

        payload = _json(resp)
        if resp.status_code != 200 or "access_token" not in payload:
            raise OAuthError(_provider_error(self.slug, resp, payload))

        return OAuthTokens(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_in=payload.get("expires_in"),
            raw=payload,
        )

    # ---- profile (each platform implements) ------------------------------
    async def fetch_profile(self, tokens: OAuthTokens) -> ProfileInfo:
        raise NotImplementedError

    # Message shown when the account has nothing connectable (overridable).
    no_accounts_error: str = "No connectable account was found."

    async def list_accounts(self, tokens: OAuthTokens) -> list[ProfileInfo]:
        """Return every account the user could connect for this platform.

        Default: the single profile from `fetch_profile`. Providers where one
        login can expose several accounts (e.g. Instagram Business accounts
        across Facebook Pages) override this to return all candidates so the UI
        can let the user choose.
        """
        return [await self.fetch_profile(tokens)]

    # ---- small shared HTTP helper for profile calls ----------------------
    async def _get_json(
        self, url: str, *, token: str, params: dict | None = None, bearer: bool = True
    ) -> dict:
        headers = {"Accept": "application/json"}
        params = dict(params or {})
        if bearer:
            headers["Authorization"] = f"Bearer {token}"
        else:
            params["access_token"] = token
        try:
            async with httpx.AsyncClient(timeout=settings.ai_request_timeout) as client:
                resp = await client.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise OAuthError(f"{self.slug}: profile request failed ({exc}).") from exc
        payload = _json(resp)
        if resp.status_code != 200:
            raise OAuthError(_provider_error(self.slug, resp, payload))
        return payload


def _json(resp: httpx.Response) -> dict:
    try:
        data = resp.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {"data": data}


def _provider_error(slug: str, resp: httpx.Response, payload: dict) -> str:
    """Best-effort human message from a provider's varied error shapes."""
    err = payload.get("error")
    if isinstance(err, dict):
        msg = err.get("message") or err.get("error_description") or err.get("type")
    else:
        msg = payload.get("error_description") or payload.get("message") or err
    return f"{slug}: {msg or f'request failed ({resp.status_code})'}"
