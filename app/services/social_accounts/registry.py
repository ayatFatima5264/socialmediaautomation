"""Provider registry — the single place that knows every supported platform.

Adding a platform: create its provider file and add one line here. Nothing else
(routes, schemas, UI) hardcodes the platform list; they all read it from here.
"""
from __future__ import annotations

from app.schemas.post import Platform
from app.services.social_accounts.base import OAuthProvider
from app.services.social_accounts.facebook import FacebookProvider
from app.services.social_accounts.instagram import InstagramProvider
from app.services.social_accounts.linkedin import LinkedInProvider
from app.services.social_accounts.pinterest import PinterestProvider
from app.services.social_accounts.threads import ThreadsProvider
from app.services.social_accounts.x import XProvider

# Instantiate once — providers are stateless (config read lazily from settings).
_PROVIDER_CLASSES: list[type[OAuthProvider]] = [
    FacebookProvider,
    InstagramProvider,
    LinkedInProvider,
    XProvider,
    PinterestProvider,
    ThreadsProvider,
]

PROVIDERS: dict[Platform, OAuthProvider] = {
    cls.platform: cls() for cls in _PROVIDER_CLASSES
}

# Public URL/config slug -> Platform (e.g. "x" -> Platform.twitter).
_SLUG_TO_PLATFORM: dict[str, Platform] = {p.slug: p.platform for p in PROVIDERS.values()}


def get_provider(platform: Platform) -> OAuthProvider:
    provider = PROVIDERS.get(platform)
    if provider is None:  # pragma: no cover — every Platform has a provider
        raise KeyError(f"No provider registered for platform {platform!r}")
    return provider


def provider_for_slug(slug: str) -> OAuthProvider | None:
    """Resolve a public callback slug (e.g. 'x') to its provider."""
    platform = _SLUG_TO_PLATFORM.get(slug)
    return PROVIDERS.get(platform) if platform else None
