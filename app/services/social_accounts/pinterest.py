"""Pinterest OAuth provider (API v5) — HTTP Basic client auth."""
from __future__ import annotations

from app.schemas.post import Platform
from app.services.social_accounts.base import OAuthProvider, OAuthTokens, ProfileInfo


class PinterestProvider(OAuthProvider):
    platform = Platform.pinterest
    slug = "pinterest"

    authorize_endpoint = "https://www.pinterest.com/oauth/"
    token_endpoint = "https://api.pinterest.com/v5/oauth/token"
    scopes = ["user_accounts:read", "boards:read", "pins:read", "pins:write"]
    scope_separator = ","
    token_auth = "basic"

    async def fetch_profile(self, tokens: OAuthTokens) -> ProfileInfo:
        data = await self._get_json(
            "https://api.pinterest.com/v5/user_account", token=tokens.access_token
        )
        username = data.get("username")
        return ProfileInfo(
            # v5 user_account keys on the username; use it as the stable id.
            account_id=str(username or data.get("id") or ""),
            username=username,
            display_name=data.get("business_name") or username,
            profile_picture=data.get("profile_image"),
        )
