"""Provider abstraction.

Every AI backend (Groq, Mock, and later OpenAI/Claude/Ollama) implements the
same tiny contract: turn a (system, user) message pair into a text completion.
Prompt construction lives in the service layer, so providers stay thin and
interchangeable.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ProviderError(RuntimeError):
    """A provider failed at request time (network, API error, bad response)."""


class ProviderConfigError(ProviderError):
    """A provider is missing required configuration (e.g. an API key)."""


class AIProvider(ABC):
    #: Stable identifier used for selection and reporting (e.g. "groq").
    name: str = "base"

    def __init__(self, model: str) -> None:
        self.model = model

    @abstractmethod
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
        """Return the model's text completion.

        `context` is optional structured info (platform, topic, tone) that
        offline providers like Mock can use to fake plausible output. Real
        network providers ignore it and rely solely on the prompt.
        """
        raise NotImplementedError
