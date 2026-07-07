"""X (Twitter) OAuth 2.0 provider — PKCE + HTTP Basic client auth.

Note: the app's internal Platform is `twitter`; the public slug is `x`, so the
callback is /api/auth/x/callback as registered in the X developer portal.
"""
from __future__ import annotations

from app.schemas.post import Platform
from app.services.social_accounts.base import OAuthProvider, OAuthTokens, ProfileInfo


class XProvider(OAuthProvider):
    platform = Platform.twitter
    slug = "x"

    authorize_endpoint = "https://twitter.com/i/oauth2/authorize"
    token_endpoint = "https://api.twitter.com/2/oauth2/token"
    scopes = ["tweet.read", "tweet.write", "users.read", "offline.access"]
    scope_separator = " "
    token_auth = "basic"
    use_pkce = True

    async def fetch_profile(self, tokens: OAuthTokens) -> ProfileInfo:
        data = await self._get_json(
            "https://api.twitter.com/2/users/me",
            token=tokens.access_token,
            params={"user.fields": "profile_image_url,name,username"},
        )
        user = data.get("data", {})
        return ProfileInfo(
            account_id=str(user.get("id", "")),
            username=user.get("username"),
            display_name=user.get("name"),
            profile_picture=user.get("profile_image_url"),
        )
