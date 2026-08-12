"""Threads OAuth provider (Threads API, graph.threads.net).

Same shape as Instagram: a short-lived code exchange, then a long-lived token
exchange so publishing can happen in the background without the user present.

Token lifecycle (Threads API):
  * short-lived   — returned by the code exchange, valid ~1 hour.
  * long-lived    — `GET /access_token?grant_type=th_exchange_token`, 60 days.
  * refresh       — `GET /refresh_access_token?grant_type=th_refresh_token`,
                    which returns a *new* 60-day token. Threads issues no
                    separate refresh token, so the access token refreshes
                    itself (hence `refresh_uses_access_token`).

A token must be at least 24 hours old to be refreshable, and one left
unrefreshed for 60 days dies for good — the account must then be reconnected.
That is why the scheduler refreshes proactively rather than on expiry.
"""
from __future__ import annotations

import httpx

from app.config import settings
from app.schemas.post import Platform
from app.services.social_accounts.base import (
    OAuthError,
    OAuthProvider,
    OAuthTokens,
    ProfileInfo,
)


class ThreadsProvider(OAuthProvider):
    platform = Platform.threads
    slug = "threads"

    authorize_endpoint = "https://threads.net/oauth/authorize"
    token_endpoint = "https://graph.threads.net/oauth/access_token"
    scopes = ["threads_basic", "threads_content_publish"]
    # Both are needed to publish: threads_basic identifies the account,
    # threads_content_publish creates and publishes the post. An account
    # authorized without one is flagged for reconnect rather than failing later.
    required_scopes = ["threads_basic", "threads_content_publish"]
    scope_separator = ","
    token_auth = "body"
    # Threads returns no refresh token; the access token renews itself.
    refresh_uses_access_token = True

    _GRAPH = "https://graph.threads.net"

    # ---- configuration ---------------------------------------------------
    # Meta calls these the App ID / App secret, so THREADS_APP_ID and
    # THREADS_APP_SECRET are accepted as aliases of the project's usual
    # {slug}_client_id / {slug}_client_secret pair. Either naming works.
    @property
    def client_id(self) -> str | None:  # type: ignore[override]
        return settings.threads_client_id or settings.threads_app_id

    @property
    def client_secret(self) -> str | None:  # type: ignore[override]
        return settings.threads_client_secret or settings.threads_app_secret

    @property
    def redirect_uri(self) -> str:  # type: ignore[override]
        """Meta matches this against the registered URI exactly, so an explicit
        override wins over the derived {backend_url}/... default."""
        return settings.threads_redirect_uri or settings.callback_url(self.slug)

    # ---- tokens ----------------------------------------------------------
    async def exchange_code(
        self, code: str, *, code_verifier: str | None = None
    ) -> OAuthTokens:
        short = await super().exchange_code(code, code_verifier=code_verifier)
        return await self._to_long_lived(short)

    async def _to_long_lived(self, short: OAuthTokens) -> OAuthTokens:
        data = await self._token_exchange(
            "access_token",
            {
                "grant_type": "th_exchange_token",
                "client_secret": self.client_secret or "",
                "access_token": short.access_token,
            },
            failure="could not obtain a long-lived token",
        )
        return OAuthTokens(
            access_token=data["access_token"],
            expires_in=data.get("expires_in"),
            raw={**short.raw, **data},
        )

    async def refresh(self, refresh_token: str) -> OAuthTokens:
        """Renew a long-lived token. Takes the *access* token: Threads has no
        separate refresh token and returns a fresh 60-day one in its place."""
        data = await self._token_exchange(
            "refresh_access_token",
            {"grant_type": "th_refresh_token", "access_token": refresh_token},
            failure="token refresh failed — reconnect the account",
        )
        return OAuthTokens(
            access_token=data["access_token"],
            expires_in=data.get("expires_in"),
            raw=data,
        )

    async def _token_exchange(self, path: str, params: dict, *, failure: str) -> dict:
        """GET a token endpoint and return its payload, or raise OAuthError.

        The error text carries Meta's own message but never the parameters that
        produced it — those include the client secret and the access token.
        """
        try:
            async with httpx.AsyncClient(timeout=settings.ai_request_timeout) as client:
                resp = await client.get(f"{self._GRAPH}/{path}", params=params)
        except httpx.HTTPError as exc:
            raise OAuthError(f"threads: {failure} ({exc}).") from exc

        try:
            data = resp.json() if resp.content else {}
        except ValueError:
            data = {}
        if resp.status_code != 200 or "access_token" not in data:
            detail = ""
            if isinstance(data, dict) and isinstance(data.get("error"), dict):
                detail = data["error"].get("message") or ""
            raise OAuthError(f"threads: {failure}.{f' {detail}' if detail else ''}")
        return data

    # ---- profile ---------------------------------------------------------
    async def fetch_profile(self, tokens: OAuthTokens) -> ProfileInfo:
        data = await self._get_json(
            f"{self._GRAPH}/v1.0/me",
            token=tokens.access_token,
            params={"fields": "id,username,name,threads_profile_picture_url"},
            bearer=False,
        )
        return ProfileInfo(
            account_id=str(data.get("id", "")),
            username=data.get("username"),
            display_name=data.get("name") or data.get("username"),
            profile_picture=data.get("threads_profile_picture_url"),
        )
