"""Threads OAuth provider (Threads API, graph.threads.net).

Same shape as Instagram: short-lived code exchange, then a long-lived token
exchange so publishing can happen in the background.
"""
from __future__ import annotations

import httpx

from app.config import settings
from app.schemas.post import Platform
from app.services.social_accounts.base import OAuthError, OAuthProvider, OAuthTokens, ProfileInfo


class ThreadsProvider(OAuthProvider):
    platform = Platform.threads
    slug = "threads"

    authorize_endpoint = "https://threads.net/oauth/authorize"
    token_endpoint = "https://graph.threads.net/oauth/access_token"
    scopes = ["threads_basic", "threads_content_publish"]
    scope_separator = ","
    token_auth = "body"

    _GRAPH = "https://graph.threads.net"

    async def exchange_code(
        self, code: str, *, code_verifier: str | None = None
    ) -> OAuthTokens:
        short = await super().exchange_code(code, code_verifier=code_verifier)
        return await self._to_long_lived(short)

    async def _to_long_lived(self, short: OAuthTokens) -> OAuthTokens:
        try:
            async with httpx.AsyncClient(timeout=settings.ai_request_timeout) as client:
                resp = await client.get(
                    f"{self._GRAPH}/access_token",
                    params={
                        "grant_type": "th_exchange_token",
                        "client_secret": self.client_secret or "",
                        "access_token": short.access_token,
                    },
                )
        except httpx.HTTPError as exc:
            raise OAuthError(f"threads: long-lived exchange failed ({exc}).") from exc
        data = resp.json() if resp.content else {}
        if resp.status_code != 200 or "access_token" not in data:
            raise OAuthError("threads: could not obtain a long-lived token.")
        return OAuthTokens(
            access_token=data["access_token"],
            expires_in=data.get("expires_in"),
            raw={**short.raw, **data},
        )

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
