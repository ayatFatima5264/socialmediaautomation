"""Instagram OAuth provider — Instagram Business via official Facebook Login.

The production model used by Buffer/Hootsuite/Later: the user authenticates with
**Facebook**, grants Pages access, and we enumerate the Instagram
**Business/Creator** accounts linked to those Pages. If several exist, the user
picks one (handled by the connect service); only the chosen account is stored.

Instagram authentication uses Meta OAuth internally, but Instagram is a separate
connection — connecting it never marks Facebook as connected.
"""
from __future__ import annotations

from app.config import settings
from app.schemas.post import Platform
from app.services.social import meta_graph
from app.services.social_accounts.base import (
    OAuthError,
    OAuthProvider,
    OAuthTokens,
    ProfileInfo,
)

NO_IG_ACCOUNT_MESSAGE = (
    "No Instagram Business account was found. Please convert your Instagram "
    "account to a Professional account and link it to a Facebook Page before "
    "connecting."
)


class InstagramProvider(OAuthProvider):
    platform = Platform.instagram
    slug = "instagram"

    # Instagram Business scopes, granted through the Facebook Login dialog. These
    # cover current publishing needs and the roadmap (image, carousel, reel,
    # story, insights).
    scopes = [
        "instagram_basic",
        "instagram_content_publish",
        "instagram_manage_insights",
        "pages_show_list",
        "pages_read_engagement",
        "business_management",
    ]
    scope_separator = ","
    token_auth = "body"
    # Force a fresh Facebook login + account selection on every connect.
    authorize_params = {"auth_type": "reauthenticate"}
    no_accounts_error = NO_IG_ACCOUNT_MESSAGE

    # Instagram shares the single Meta app with Facebook.
    @property
    def client_id(self) -> str | None:  # type: ignore[override]
        return settings.meta_app_id

    @property
    def client_secret(self) -> str | None:  # type: ignore[override]
        return settings.meta_app_secret

    @property
    def redirect_uri(self) -> str:  # type: ignore[override]
        return settings.instagram_redirect_uri or settings.callback_url("instagram")

    @property
    def authorize_endpoint(self) -> str:  # type: ignore[override]
        return f"https://www.facebook.com/{settings.meta_graph_version}/dialog/oauth"

    @property
    def token_endpoint(self) -> str:  # type: ignore[override]
        return f"https://graph.facebook.com/{settings.meta_graph_version}/oauth/access_token"

    async def exchange_code(
        self, code: str, *, code_verifier: str | None = None
    ) -> OAuthTokens:
        # Facebook returns a short-lived user token; exchange for long-lived
        # (~60 day) so the scheduler can keep publishing.
        short = await super().exchange_code(code, code_verifier=code_verifier)
        try:
            long_token, expires_in = await meta_graph.exchange_for_long_lived_token(
                short.access_token
            )
        except meta_graph.GraphAPIError as exc:
            raise OAuthError(f"instagram: {exc}") from exc
        return OAuthTokens(access_token=long_token, expires_in=expires_in, raw=short.raw)

    async def list_accounts(self, tokens: OAuthTokens) -> list[ProfileInfo]:
        """Every Instagram Business account linked to a granted Page."""
        try:
            found = await meta_graph.list_instagram_accounts(tokens.access_token)
        except meta_graph.GraphAPIError as exc:
            raise OAuthError(f"instagram: {exc}") from exc
        return [
            ProfileInfo(
                account_id=a["account_id"],
                page_id=a.get("page_id"),
                username=a.get("username"),
                display_name=a.get("name") or a.get("username"),
                profile_picture=a.get("profile_picture_url"),
                page_name=a.get("page_name"),
            )
            for a in found
        ]

    async def fetch_profile(self, tokens: OAuthTokens) -> ProfileInfo:
        accounts = await self.list_accounts(tokens)
        if not accounts:
            raise OAuthError(self.no_accounts_error)
        return accounts[0]
