"""Pinterest OAuth provider (API v5) — HTTP Basic client auth.

Scopes follow the API v5 security requirements exactly: `POST /v5/pins`
(create Pin) requires **boards:read, boards:write, pins:read, pins:write**, and
`GET /v5/user_account` (the connected profile shown in the UI) requires
`user_accounts:read`. All four publishing scopes are marked required, so an
account authorized before one of them was requested is flagged for reconnect
instead of failing later at publish time.

Token lifetimes (Pinterest v5): the access token lasts 30 days and the
continuous refresh token 60 days, refreshable indefinitely. Apps created before
2025-09-25 only receive a continuous refresh token when the token request sends
`continuous_refresh=true`; newer apps get one automatically and ignore the
field — so it is always sent, which is correct for both.

Environment: a Trial-tier app may only create Pins in Pinterest's Sandbox, so
the token exchange follows `pinterest_api.api_base()` rather than being pinned
to production. Tokens are not portable between the two, which is why changing
`PINTEREST_SANDBOX` requires reconnecting the account.
"""
from __future__ import annotations

from app.config import settings
from app.schemas.post import Platform
from app.services.social import pinterest_api
from app.services.social_accounts.base import OAuthProvider, OAuthTokens, ProfileInfo


class PinterestProvider(OAuthProvider):
    platform = Platform.pinterest
    slug = "pinterest"

    # The consent screen is always the real Pinterest — a user authorizes with
    # their actual account either way. Only the token exchange and the API calls
    # move hosts, which is why a sandbox connection needs its own reconnect.
    authorize_endpoint = "https://www.pinterest.com/oauth/"
    scopes = [
        "user_accounts:read",
        "boards:read",
        "boards:write",
        "pins:read",
        "pins:write",
    ]
    # Everything POST /v5/pins needs. user_accounts:read is deliberately absent:
    # it only powers the profile card, so a missing one is not worth forcing a
    # reconnect over.
    required_scopes = ["boards:read", "boards:write", "pins:read", "pins:write"]
    scope_separator = ","
    token_auth = "basic"
    token_params = {"continuous_refresh": "true"}

    @property
    def token_endpoint(self) -> str:
        """Tokens must come from the environment they will be used against — a
        production token is rejected by Sandbox and vice versa."""
        return f"{pinterest_api.api_base()}/oauth/token"

    @property
    def redirect_uri(self) -> str:
        """Pinterest matches this byte-for-byte against the registered URI, so an
        explicit override wins over the derived {backend_url}/... default."""
        return settings.pinterest_redirect_uri or settings.callback_url(self.slug)

    async def fetch_profile(self, tokens: OAuthTokens) -> ProfileInfo:
        data = await self._get_json(
            f"{pinterest_api.api_base()}/user_account", token=tokens.access_token
        )
        username = data.get("username")
        return ProfileInfo(
            # v5 user_account keys on the username; use it as the stable id.
            account_id=str(username or data.get("id") or ""),
            username=username,
            display_name=data.get("business_name") or username,
            profile_picture=data.get("profile_image"),
        )
