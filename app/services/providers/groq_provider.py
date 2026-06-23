"""Groq provider — the primary FREE option.

Groq exposes an OpenAI-compatible Chat Completions API, so this provider also
serves as the template for any OpenAI-compatible backend (OpenAI, Together,
OpenRouter, a local Ollama/vLLM server, ...): just change base_url + model.

Free API keys: https://console.groq.com/keys
"""
from __future__ import annotations

from typing import Any

import httpx

from app.services.providers.base import (
    AIProvider,
    ProviderConfigError,
    ProviderError,
)


class GroqProvider(AIProvider):
    name = "groq"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        base_url: str,
        timeout: float,
    ) -> None:
        if not api_key:
            raise ProviderConfigError(
                "GROQ_API_KEY is not set. Add it to your .env or use AI_PROVIDER=mock."
            )
        super().__init__(model)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

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
        if json_mode:
            # Supported by Groq's Llama models; forces strict JSON output.
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
        except httpx.HTTPError as exc:  # network/timeout/DNS
            raise ProviderError(f"Groq request failed: {exc}") from exc

        if resp.status_code != 200:
            detail = _safe_error_detail(resp)
            raise ProviderError(f"Groq API error {resp.status_code}: {detail}")

        try:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise ProviderError(f"Unexpected Groq response shape: {exc}") from exc


def _safe_error_detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        if isinstance(body, dict) and "error" in body:
            err = body["error"]
            return err.get("message", str(err)) if isinstance(err, dict) else str(err)
        return str(body)
    except ValueError:
        return resp.text[:300]
