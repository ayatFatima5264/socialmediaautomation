"""Google Gemini provider — generous free tier, no credit card.

Uses Gemini's OpenAI-compatibility endpoint
(https://generativelanguage.googleapis.com/v1beta/openai), so it reuses the
shared OpenAI-compatible request handling. Bearer auth with the API key and
`response_format: json_object` are both supported by that endpoint.

Free API keys: https://aistudio.google.com/apikey
"""
from __future__ import annotations

from app.services.providers.openai_compatible import OpenAICompatibleProvider


class GeminiProvider(OpenAICompatibleProvider):
    name = "gemini"
    key_hint = "GEMINI_API_KEY"
