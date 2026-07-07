"""LinkedIn OAuth provider (OpenID Connect + w_member_social for posting)."""
from __future__ import annotations

from app.schemas.post import Platform
from app.services.social_accounts.base import OAuthProvider, OAuthTokens, ProfileInfo


class LinkedInProvider(OAuthProvider):
    platform = Platform.linkedin
    slug = "linkedin"

    authorize_endpoint = "https://www.linkedin.com/oauth/v2/authorization"
    token_endpoint = "https://www.linkedin.com/oauth/v2/accessToken"
    scopes = ["openid", "profile", "email", "w_member_social"]
    scope_separator = " "
    token_auth = "body"

    async def fetch_profile(self, tokens: OAuthTokens) -> ProfileInfo:
        # OpenID Connect userinfo — sub is the stable member id.
        data = await self._get_json(
            "https://api.linkedin.com/v2/userinfo", token=tokens.access_token
        )
        return ProfileInfo(
            account_id=str(data.get("sub", "")),
            username=data.get("email") or data.get("name"),
            display_name=data.get("name"),
            profile_picture=data.get("picture"),
        )
