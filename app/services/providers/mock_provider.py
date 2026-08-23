"""Mock provider — zero-cost, offline fallback.

Requires no API key and no network, so the whole generation flow (and the
React frontend wired to it) works out of the box for local development and
tests. It produces valid, platform-flavoured JSON using the structured
`context` passed by the service layer.
"""
from __future__ import annotations

import json
import re
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

        # Video Studio asks for different shapes, and a mock that answered a
        # script request with post JSON would make the AI video flow fail
        # exactly where this provider exists to let it work.
        feature = str(ctx.get("feature", ""))
        if feature == "video_script":
            return _mock_script(topic, tone, user)
        if feature == "video_script_section":
            return _mock_section(str(ctx.get("section") or "hook"), topic)
        if feature == "video_visual_prompts":
            return _mock_visuals(topic, int(ctx.get("scenes") or 1))
        if feature == "video_repurpose":
            return _mock_moments(user, int(ctx.get("moments") or 3))

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


# ---------------------------------------------------------------------------
# Video Studio shapes
# ---------------------------------------------------------------------------
# Kept as functions rather than inline so the class stays readable, and so a
# test can assert against them directly.


def _mock_script(topic: str, tone: str, user_prompt: str) -> str:
    """A script in the shape `scripting.normalize_script` expects.

    The point count is read back out of the prompt so the mock honours the
    length the caller asked for — a mock that always returned three points
    would make the duration arithmetic untestable.
    """
    match = re.search(r"exactly (\d+) main point", user_prompt)
    points = int(match.group(1)) if match else 2

    return json.dumps(
        {
            "title": f"{topic} — explained",
            "hook": f"Most people get {topic} wrong.",
            "introduction": f"Here is what actually matters about {topic}.",
            "main_points": [
                {
                    "heading": f"Point {index + 1}",
                    "text": (
                        f"This is point {index + 1} about {topic}. "
                        f"It is written in a {tone} tone and says something "
                        f"concrete the viewer can use."
                    ),
                }
                for index in range(points)
            ],
            "ending": f"That is {topic} in short.",
            "cta": "Follow for more like this.",
            "keywords": [word for word in topic.split()[:4] if word] or [topic],
        }
    )


def _mock_section(section: str, topic: str) -> str:
    """One rewritten section, in the shape `regenerate_section` parses.

    Worded differently from `_mock_script` on purpose: a test that asserts the
    section actually changed cannot do so if the mock hands back the same
    sentence the original generator produced.
    """
    text = {
        "title": f"{topic}, rewritten",
        "hook": f"Here is the part of {topic} nobody mentions.",
        "introduction": f"A second look at {topic}, from a different angle.",
        "ending": f"That is the other side of {topic}.",
        "cta": "Save this one for later.",
    }.get(section, f"A reworked line about {topic}.")
    return json.dumps({"heading": "Reworked point", "text": text})


def _mock_visuals(topic: str, scenes: int) -> str:
    """One visual description per scene, varied enough to be distinguishable."""
    settings = (
        "a bright modern workspace",
        "a city street at golden hour",
        "hands writing in a notebook",
        "an open laptop on a wooden desk",
        "a person walking through a park",
        "a quiet cafe interior",
    )
    return json.dumps(
        {
            "visuals": [
                f"{settings[index % len(settings)]}, related to {topic}, "
                f"natural light, shallow depth of field"
                for index in range(scenes)
            ]
        }
    )


def _mock_moments(user_prompt: str, count: int) -> str:
    """Candidate clips, spaced across whatever transcript was described.

    The video's length is read back out of the prompt so the mock proposes
    moments that actually fit inside it — a mock returning timestamps past the
    end of the recording would make the clamping untestable.
    """
    match = re.search(r"([0-9.]+)-minute video", user_prompt)
    duration = float(match.group(1)) * 60 if match else 300.0

    span = min(45.0, max(15.0, duration / max(count, 1)))
    moments = []
    for index in range(count):
        start = round(index * (duration / max(count, 1)), 2)
        end = round(min(duration, start + span), 2)
        if end - start < 15:
            break
        moments.append(
            {
                "start_seconds": start,
                "end_seconds": end,
                "title": f"Moment {index + 1}",
                "hook": f"The part about number {index + 1}",
                "reason": "It makes one point and finishes it.",
                "cta": "Follow for the full video",
            }
        )
    return json.dumps({"moments": moments})
