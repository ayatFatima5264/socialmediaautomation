"""Shared implementation for any OpenAI-compatible Chat Completions API.

Groq, Google Gemini (via its OpenAI-compatibility endpoint), OpenRouter,
Cerebras, Together, and local Ollama/vLLM servers all speak the same protocol.
Each concrete provider only supplies a name, base_url, model and API key — the
request/response handling lives here once.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.services.providers.base import (
    AIProvider,
    ProviderConfigError,
    ProviderError,
)


class OpenAICompatibleProvider(AIProvider):
    #: Subclasses override these. `key_hint` names the env var in error messages.
    name: str = "openai-compatible"
    key_hint: str = "API key"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        base_url: str,
        timeout: float,
        supports_json_mode: bool = True,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        if not api_key:
            raise ProviderConfigError(
                f"{self.key_hint} is not set. Add it to your .env."
            )
        super().__init__(model)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.supports_json_mode = supports_json_mode
        self.extra_headers = extra_headers or {}

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
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode and self.supports_json_mode:
            # Forces strict JSON output on providers that support it.
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.extra_headers,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
        except httpx.HTTPError as exc:  # network/timeout/DNS
            raise ProviderError(f"{self.name} request failed: {exc}") from exc

        if resp.status_code != 200:
            detail = _safe_error_detail(resp)
            raise ProviderError(f"{self.name} API error {resp.status_code}: {detail}")

        try:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise ProviderError(
                f"Unexpected {self.name} response shape: {exc}"
            ) from exc


def _safe_error_detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        if isinstance(body, dict) and "error" in body:
            err = body["error"]
            return err.get("message", str(err)) if isinstance(err, dict) else str(err)
        return str(body)
    except ValueError:
        return resp.text[:300]
