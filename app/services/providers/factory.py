"""Provider registry + selection.

This is the single switch point for the AI backend. Pick a provider via:
  * AI_PROVIDER in .env (default primary), or
  * a per-request `provider` override.

The selected provider is tried first; if it fails at request time it falls back
to the providers listed in AI_FALLBACK_PROVIDERS (default: gemini) — so a flaky
or rate-limited primary never fails a request. See FallbackProvider.

Real providers (gemini, groq) require their API key. A fallback whose key is
missing is silently skipped; if *no* provider in the chain is configured we
raise a clear ProviderConfigError rather than degrading to mock — the mock
provider is only used when it is selected explicitly (AI_PROVIDER=mock).
"""
from __future__ import annotations

import logging

from app.config import settings
from app.services.providers.base import AIProvider, ProviderConfigError
from app.services.providers.fallback_provider import FallbackProvider
from app.services.providers.gemini_provider import GeminiProvider
from app.services.providers.groq_provider import GroqProvider
from app.services.providers.mock_provider import MockProvider

logger = logging.getLogger(__name__)

#: Provider identifiers the API advertises to clients.
available_providers: list[str] = ["gemini", "groq", "mock"]


def _build(name: str) -> AIProvider:
    name = name.lower()
    if name == "mock":
        return MockProvider()
    if name == "gemini":
        return GeminiProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            base_url=settings.gemini_base_url,
            timeout=settings.ai_request_timeout,
        )
    if name == "groq":
        return GroqProvider(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            base_url=settings.groq_base_url,
            timeout=settings.ai_request_timeout,
        )
    raise ValueError(
        f"Unknown AI provider {name!r}. Available: {', '.join(available_providers)}"
    )


def _ordered_chain(selected: str) -> list[str]:
    """Selected provider first, then the configured fallbacks (deduped)."""
    chain = [selected]
    for fb in settings.ai_fallback_providers:
        fb = fb.lower()
        if fb not in chain:
            chain.append(fb)
    return chain


def get_provider(name: str | None = None) -> AIProvider:
    """Return a provider (or fallback chain) to serve AI requests.

    `name` overrides the configured primary (settings.ai_provider). The primary
    is tried first, then settings.ai_fallback_providers in order. Fallbacks with
    no API key are skipped. If nothing in the chain is usable a
    ProviderConfigError is raised; set AI_PROVIDER=mock to use the offline
    provider on purpose.
    """
    selected = (name or settings.ai_provider).lower()

    built: list[AIProvider] = []
    errors: list[str] = []
    for provider_name in _ordered_chain(selected):
        try:
            built.append(_build(provider_name))
        except ProviderConfigError as exc:
            # Missing key: drop this link, keep going down the chain.
            errors.append(f"{provider_name}: {exc}")
            logger.warning(
                "Skipping AI provider %r in fallback chain: %s", provider_name, exc
            )

    if not built:
        raise ProviderConfigError(
            "No AI provider is configured. " + " | ".join(errors)
        )
    if len(built) == 1:
        return built[0]
    return FallbackProvider(built)
