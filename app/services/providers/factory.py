"""Provider registry + selection.

This is the single switch point for the AI backend. Pick a provider via:
  * AI_PROVIDER in .env (default), or
  * a per-request `provider` override.

Real providers (gemini, groq) require their API key. If the key is missing we
raise a clear ProviderConfigError rather than silently degrading to mock — the
mock provider is only used when it is selected explicitly (AI_PROVIDER=mock).
"""
from __future__ import annotations

import logging

from app.config import settings
from app.services.providers.base import AIProvider, ProviderConfigError
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


def get_provider(name: str | None = None) -> AIProvider:
    """Return a provider instance.

    `name` overrides the configured default (settings.ai_provider). A real
    provider with no API key raises ProviderConfigError; configure a free key
    or set AI_PROVIDER=mock to use the offline provider on purpose.
    """
    selected = (name or settings.ai_provider).lower()
    return _build(selected)
