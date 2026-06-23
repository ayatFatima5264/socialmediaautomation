"""Groq provider — fast, free Llama inference.

Groq exposes an OpenAI-compatible Chat Completions API, so the request handling
is inherited from OpenAICompatibleProvider; this class only pins the identity.

Free API keys: https://console.groq.com/keys
"""
from __future__ import annotations

from app.services.providers.openai_compatible import OpenAICompatibleProvider


class GroqProvider(OpenAICompatibleProvider):
    name = "groq"
    key_hint = "GROQ_API_KEY"
