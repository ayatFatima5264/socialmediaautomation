"""Mock provider — zero-cost, offline fallback.

Requires no API key and no network, so the whole generation flow (and the
React frontend wired to it) works out of the box for local development and
tests. It produces valid, platform-flavoured JSON using the structured
`context` passed by the service layer.
"""
from __future__ import annotations

import json
from typing import Any

from app.services.providers.base import AIProvider

# Light, platform-appropriate flavour for the faked output.
_PLATFORM_FLAVOUR: dict[str, dict[str, str]] = {
    "twitter":   {"emoji": "🚀", "cta": "Thoughts?"},
    "instagram": {"emoji": "✨", "cta": "Save this for later 👇"},
    "facebook":  {"emoji": "💬", "cta": "What do you think?"},
    "linkedin":  {"emoji": "📈", "cta": "Curious how others approach this."},
    "threads":   {"emoji": "🧵", "cta": "real talk."},
}


class MockProvider(AIProvider):
    name = "mock"

    def __init__(self, model: str = "mock-1") -> None:
        super().__init__(model)

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
        ctx = context or {}
        platform = str(ctx.get("platform", "twitter"))
        topic = str(ctx.get("topic", "your topic"))
        tone = str(ctx.get("tone", "professional"))
        flavour = _PLATFORM_FLAVOUR.get(platform, _PLATFORM_FLAVOUR["twitter"])

        text = (
            f"{flavour['emoji']} [{tone.title()} · {platform.title()} · MOCK]\n\n"
            f"Here's a take on {topic} crafted for {platform.title()}.\n"
            f"{flavour['cta']}"
        )

        result: dict[str, Any] = {"text": text}
        if ctx.get("variants"):
            result["short_version"] = f"{flavour['emoji']} {topic} — in short. {flavour['cta']}"
            result["long_version"] = (
                f"{text}\n\nThe longer version expands on {topic} with more "
                f"detail, examples and a {tone} framing tailored to the audience."
            )
        if ctx.get("include_hashtags", True):
            slug = "".join(w.capitalize() for w in topic.split()[:3] if w.isalnum())
            result["hashtags"] = [t for t in (slug or "Topic", platform.title(), "SocialMedia") if t]
        else:
            result["hashtags"] = []

        return json.dumps(result)
