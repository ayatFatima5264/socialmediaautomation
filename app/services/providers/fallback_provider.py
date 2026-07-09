"""Fallback chain over several providers.

Wraps an ordered list of real providers and serves each request from the first
one that succeeds. If the primary (e.g. Groq) errors at request time — rate
limit, timeout, network, bad response — the next provider (e.g. Gemini) is
tried automatically, so a single flaky backend never fails a user's request.

Only *request-time* failures (ProviderError) trigger a fallback. Providers that
can't even be constructed (missing API key) are filtered out earlier in the
factory, so this class only ever holds usable backends.
"""
from __future__ import annotations

import logging
from typing import Any

from app.services.providers.base import AIProvider, ProviderError

logger = logging.getLogger(__name__)


class FallbackProvider(AIProvider):
    name = "fallback"

    def __init__(self, providers: list[AIProvider]) -> None:
        if not providers:
            raise ValueError("FallbackProvider requires at least one provider")
        self._providers = providers
        primary = providers[0]
        super().__init__(primary.model)
        # `name`/`model` reflect the primary until a request is served, then the
        # provider that actually answered — so response metadata is truthful.
        self.name = primary.name

    async def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
        json_mode: bool = True,
        context: dict[str, Any] | None = None,
    ) -> str:
        last_exc: ProviderError | None = None
        for index, provider in enumerate(self._providers):
            try:
                result = await provider.complete(
                    system=system,
                    user=user,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    json_mode=json_mode,
                    context=context,
                )
            except ProviderError as exc:
                last_exc = exc
                logger.warning(
                    "AI provider %r failed (%s); falling back to next in chain",
                    provider.name,
                    exc,
                )
                continue
            # Record who actually served the request (see note in __init__).
            self.name = provider.name
            self.model = provider.model
            if index > 0:
                logger.info("AI request served by fallback provider %r", provider.name)
            return result

        raise ProviderError(
            f"All AI providers in the fallback chain failed. Last error: {last_exc}"
        ) from last_exc
