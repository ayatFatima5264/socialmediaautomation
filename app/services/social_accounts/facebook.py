"""Facebook OAuth provider (Meta Login)."""
from __future__ import annotations

from app.config import settings
from app.schemas.post import Platform
from app.services.social_accounts.base import OAuthProvider, OAuthTokens, ProfileInfo


class FacebookProvider(OAuthProvider):
    platform = Platform.facebook
    slug = "facebook"

    scopes = ["public_profile", "email", "pages_show_list", "pages_manage_posts"]
    scope_separator = ","
    token_auth = "body"
    # Force a fresh Facebook login + account selection on every connect.
    authorize_params = {"auth_type": "reauthenticate"}

    # Facebook & Instagram share the single Meta app's credentials.
    @property
    def client_id(self) -> str | None:  # type: ignore[override]
        return settings.meta_app_id

    @property
    def client_secret(self) -> str | None:  # type: ignore[override]
        return settings.meta_app_secret

    @property
    def redirect_uri(self) -> str:  # type: ignore[override]
        return settings.meta_redirect_uri or settings.callback_url("facebook")

    @property
    def authorize_endpoint(self) -> str:  # type: ignore[override]
        return f"https://www.facebook.com/{settings.meta_graph_version}/dialog/oauth"

    @property
    def token_endpoint(self) -> str:  # type: ignore[override]
        return f"https://graph.facebook.com/{settings.meta_graph_version}/oauth/access_token"

    async def fetch_profile(self, tokens: OAuthTokens) -> ProfileInfo:
        base = f"https://graph.facebook.com/{settings.meta_graph_version}"
        data = await self._get_json(
            f"{base}/me",
            token=tokens.access_token,
            params={"fields": "id,name,picture.type(large)"},
            bearer=False,
        )
        picture = (data.get("picture") or {}).get("data", {}).get("url")
        return ProfileInfo(
            account_id=str(data.get("id", "")),
            username=data.get("name"),
            display_name=data.get("name"),
            profile_picture=picture,
        )
