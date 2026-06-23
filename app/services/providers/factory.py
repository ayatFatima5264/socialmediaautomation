"""Provider registry + selection.

This is the single switch point for the AI backend. Pick a provider via:
  * AI_PROVIDER in .env (default), or
  * a per-request `provider` override.

If "groq" is requested but no key is configured, we transparently fall back to
the mock provider and log a warning, so the app never hard-fails on a missing
key during development.
"""
from __future__ import annotations

import logging

from app.config import settings
from app.services.providers.base import AIProvider
from app.services.providers.groq_provider import GroqProvider
from app.services.providers.mock_provider import MockProvider

logger = logging.getLogger(__name__)

#: Provider identifiers the API advertises to clients.
available_providers: list[str] = ["groq", "mock"]


def _build(name: str) -> AIProvider:
    name = name.lower()
    if name == "mock":
        return MockProvider()
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

    `name` overrides the configured default (settings.ai_provider). A "groq"
    selection with no API key gracefully degrades to the mock provider.
    """
    selected = (name or settings.ai_provider).lower()

    if selected == "groq" and not settings.groq_api_key:
        logger.warning(
            "AI_PROVIDER=groq but GROQ_API_KEY is not set — falling back to mock provider."
        )
        return MockProvider()

    return _build(selected)
