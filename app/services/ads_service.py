"""AI Ads Studio — generation.

Everything here runs on the providers the app already has: the configured AI
provider (groq by default) for text, and image_service for creatives. Nothing
new is bolted on, so the Studio inherits the existing fallback chain, the
provider override, and the same image pipeline the Generator uses.

---- What can and cannot be generated today -------------------------------

Text — ad copy, headlines, CTAs, and the SCRIPT for a video — is a language
model's job, and the configured provider does all of it.

Creatives — product ads, banners, carousel slides — go through image_service,
the same path the AI Generator uses.

Video is the exception. No video model is configured, and a text provider
cannot render an MP4. Rather than refuse the video tools outright, they
generate the part that IS a language task: a shot-by-shot plan with timings,
on-screen copy, and camera direction. That is genuinely useful — it is what a
person would write before opening an editor — and `renderable=False` on the
response says plainly that the file itself still needs a video provider.
Callers must not present a plan as a finished video.
"""
from __future__ import annotations

import logging

from app.config import settings
from app.services.ai_service import _parse_json  # shared best-effort JSON reader
from app.services.image_service import compose_prompt, dimensions_for, generate_with_fallback
from app.services.providers import get_provider

logger = logging.getLogger(__name__)

# Ad headlines live under a much tighter ceiling than captions do; every major
# ad platform sits at or under this, so it is the number worth writing to.
HEADLINE_LIMIT = 40


def _system(role: str) -> str:
    """A shared system prompt. Every call returns JSON and nothing else."""
    return (
        f"You are {role} You write for paid advertising, where every word is "
        "bought. Be specific and concrete; never use filler, hype, or claims "
        "the brief does not support. You ALWAYS return only a JSON object with "
        "no markdown, no code fences and no commentary."
    )


def _brief(**fields: object) -> str:
    """Render the non-empty parts of a brief as labelled lines."""
    lines = [f"{k}: {v}" for k, v in fields.items() if v not in (None, "", [], {})]
    return "\n".join(lines) if lines else "(no additional detail supplied)"


async def _complete_json(
    system: str,
    user: str,
    *,
    provider_name: str | None = None,
    temperature: float = 0.8,
    context: dict | None = None,
) -> dict:
    provider = get_provider(provider_name)
    raw = await provider.complete(
        system=system,
        user=user,
        max_tokens=settings.ai_max_tokens,
        temperature=temperature,
        json_mode=True,
        context=context or {},
    )
    return _parse_json(raw)


def _as_list(value: object) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    return []


# ---------------------------------------------------------------------------
# Ad copy
# ---------------------------------------------------------------------------


async def generate_ad_copy(
    *,
    product: str,
    audience: str | None = None,
    offer: str | None = None,
    platform: str = "instagram",
    tone: str = "Professional",
    cta: str = "Shop Now",
    char_limit: int = 2200,
    variants: int = 3,
    provider_name: str | None = None,
) -> list[dict]:
    """Several complete ad copies, each a different angle on the same offer.

    Variants exist so there is something real to test against — one "safe"
    option is not a test. Each carries the angle it takes so a winner says
    something about the audience rather than just about the words.
    """
    system = _system("a direct-response copywriter.")
    user = (
        f"Write {variants} DISTINCT ad copy variants.\n\n"
        f"BRIEF\n{_brief(Product=product, Audience=audience, Offer=offer, Platform=platform, Tone=tone)}\n\n"
        "RULES\n"
        f"- Each variant takes a different angle (e.g. benefit, curiosity, objection, proof, urgency).\n"
        f"- headline: at most {HEADLINE_LIMIT} characters.\n"
        f"- body: at most {char_limit} characters, and far shorter is better.\n"
        f"- cta: use exactly \"{cta}\".\n"
        "- No emoji unless the tone is Playful. No hashtags.\n\n"
        'Return ONLY: {"variants": [{"angle": "...", "headline": "...", '
        '"body": "...", "cta": "..."}]}'
    )

    data = await _complete_json(
        system, user, provider_name=provider_name, context={"ads": "copy"}
    )

    out: list[dict] = []
    for item in _as_list(data.get("variants"))[:variants]:
        if not isinstance(item, dict):
            continue
        headline = str(item.get("headline", "")).strip()
        body = str(item.get("body", "")).strip()
        if not headline and not body:
            continue
        out.append(
            {
                "angle": str(item.get("angle", "")).strip() or "General",
                "headline": headline,
                # Truncation is the caller's contract with the platform, so it
                # is enforced here rather than trusted to the model.
                "body": body[:char_limit],
                "cta": str(item.get("cta", "")).strip() or cta,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Headlines
# ---------------------------------------------------------------------------


async def generate_headlines(
    *,
    product: str,
    offer: str | None = None,
    angles: list[str] | None = None,
    platform: str = "facebook",
    count: int = 6,
    provider_name: str | None = None,
) -> list[dict]:
    """Ranked headlines, each labelled with its angle and its reasoning."""
    system = _system("a direct-response copywriter who tests headlines for a living.")
    wanted = ", ".join(angles) if angles else "benefit, curiosity, proof, objection, urgency"
    user = (
        f"Write {count} headlines for one offer, ranked strongest first.\n\n"
        f"BRIEF\n{_brief(Product=product, Offer=offer, Platform=platform, Angles=wanted)}\n\n"
        "RULES\n"
        f"- At most {HEADLINE_LIMIT} characters each. Count them.\n"
        "- Spread across the requested angles; do not repeat an angle twice in a row.\n"
        "- `why` is one short clause explaining the ranking, not a restatement.\n\n"
        'Return ONLY: {"headlines": [{"text": "...", "angle": "...", "why": "..."}]}'
    )

    data = await _complete_json(
        system, user, provider_name=provider_name, context={"ads": "headlines"}
    )

    out: list[dict] = []
    for item in _as_list(data.get("headlines"))[:count]:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        out.append(
            {
                "text": text,
                "angle": str(item.get("angle", "")).strip() or "General",
                "why": str(item.get("why", "")).strip(),
                # Reported rather than enforced: an over-length headline is
                # still worth showing, flagged, so the user can trim it.
                "over_limit": len(text) > HEADLINE_LIMIT,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Calls to action
# ---------------------------------------------------------------------------

#: The button sets the platforms actually offer. The model may write the line
#: above the button; it may not invent a button the platform will reject.
NATIVE_BUTTONS: dict[str, list[str]] = {
    "facebook": ["Shop Now", "Learn More", "Sign Up", "Get Offer", "Book Now"],
    "instagram": ["Shop Now", "Learn More", "Sign Up", "Contact Us"],
    "linkedin": ["Learn More", "Sign Up", "Register", "Request Demo", "Download"],
    "twitter": ["Shop Now", "Learn More", "Book Now"],
    "pinterest": ["Shop Now", "Learn More", "Visit Site"],
}


async def generate_ctas(
    *,
    offer: str,
    stage: str = "Warm — considering",
    platform: str = "facebook",
    tone: str = "Friendly",
    count: int = 5,
    provider_name: str | None = None,
) -> list[dict]:
    """Supporting lines paired with a button the platform actually supports."""
    buttons = NATIVE_BUTTONS.get(platform, NATIVE_BUTTONS["facebook"])
    system = _system("a conversion copywriter.")
    user = (
        f"Write {count} calls to action.\n\n"
        f"BRIEF\n{_brief(Offer=offer, **{'Funnel stage': stage}, Platform=platform, Tone=tone)}\n\n"
        "RULES\n"
        "- `line` is the short sentence ABOVE the button. At most 60 characters.\n"
        f"- `button` MUST be exactly one of: {', '.join(buttons)}.\n"
        "- Match the funnel stage: a cold audience is asked to learn, not to buy.\n\n"
        'Return ONLY: {"ctas": [{"line": "...", "button": "..."}]}'
    )

    data = await _complete_json(
        system, user, provider_name=provider_name, context={"ads": "cta"}
    )

    out: list[dict] = []
    for item in _as_list(data.get("ctas"))[:count]:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line", "")).strip()
        if not line:
            continue
        button = str(item.get("button", "")).strip()
        # The platform's list is the authority, not the model's answer.
        if button not in buttons:
            button = buttons[0]
        out.append({"line": line, "button": button})
    return out


# ---------------------------------------------------------------------------
# Creatives
# ---------------------------------------------------------------------------


async def generate_creative(
    *,
    subject: str,
    headline: str | None = None,
    background: str | None = None,
    style: str = "corporate",
    aspect_ratio: str = "1:1",
    quality: str = "standard",
    count: int = 1,
) -> list[str]:
    """Ad imagery, through the same pipeline the AI Generator uses.

    Returns image URLs. `count` above one gives alternatives of the same brief
    rather than a sequence — carousel slides pass their own per-slide subject.
    """
    parts = [subject]
    if background:
        parts.append(f"set on {background}")
    if headline:
        # The headline steers the composition (leaving room for text) without
        # asking the model to render the words, which it does badly.
        parts.append(f"composed with clear empty space for the headline '{headline}'")
    parts.append("advertising product photography, professional lighting")

    prompt = compose_prompt(", ".join(parts), style=style)
    width, height = dimensions_for(aspect_ratio)

    urls: list[str] = []
    sources: list[str] = []
    for i in range(max(1, count)):
        # generate_with_fallback verifies each candidate, so `provider` is the
        # source that ACTUALLY produced the image — not the one we asked for.
        url, provider = await generate_with_fallback(
            prompt,
            width=width,
            height=height,
            # A different seed per pass, so "3 versions" are three images and
            # not the same one three times.
            seed=i,
        )
        logger.info("ads: creative %d/%d via %s", i + 1, count, provider)
        if url:
            urls.append(url)
            sources.append(provider)

    # Returned to the caller, not just logged. When the AI host rate-limits, the
    # chain silently substitutes a keyword-matched stock photo — a perfectly
    # good image that is NOT generated. Without this the user cannot tell the
    # two apart, and comes to believe generation is working when it is not.
    return urls, sources


# ---------------------------------------------------------------------------
# Video plans
# ---------------------------------------------------------------------------


async def generate_video_plan(
    *,
    concept: str,
    duration: int = 15,
    platform: str = "instagram",
    style: str = "Modern & Clean",
    motion: str | None = None,
    provider_name: str | None = None,
) -> dict:
    """A shot-by-shot plan for a video ad.

    NOT a video. No video model is configured, so this generates the part that
    is a language task — scenes, timings, on-screen copy, camera direction and
    a voiceover script. The response carries `renderable: False` so no caller
    can mistake a plan for a finished file.
    """
    system = _system("a video ad director who writes tight, shootable briefs.")
    user = (
        f"Plan a {duration}-second video ad.\n\n"
        f"BRIEF\n{_brief(Concept=concept, Platform=platform, Style=style, **{'Camera motion': motion})}\n\n"
        "RULES\n"
        f"- The scene timings must add up to {duration} seconds.\n"
        "- The first scene has to earn the stop; the last one asks for the click.\n"
        "- `on_screen` is the text burned into that scene. Keep it under 8 words.\n"
        "- `voiceover` across all scenes should read in about "
        f"{max(1, duration * 2)} words total.\n\n"
        'Return ONLY: {"hook": "...", "scenes": [{"start": 0, "seconds": 3, '
        '"shot": "...", "on_screen": "...", "voiceover": "..."}], "cta": "..."}'
    )

    data = await _complete_json(
        system, user, provider_name=provider_name, temperature=0.85,
        context={"ads": "video-plan"},
    )

    scenes: list[dict] = []
    clock = 0
    for item in _as_list(data.get("scenes")):
        if not isinstance(item, dict):
            continue
        try:
            seconds = max(1, int(float(item.get("seconds", 3))))
        except (TypeError, ValueError):
            seconds = 3
        scenes.append(
            {
                # Timings are recomputed from the durations rather than trusted:
                # models routinely return overlapping or gapped start times.
                "start": clock,
                "seconds": seconds,
                "shot": str(item.get("shot", "")).strip(),
                "on_screen": str(item.get("on_screen", "")).strip(),
                "voiceover": str(item.get("voiceover", "")).strip(),
            }
        )
        clock += seconds

    return {
        "hook": str(data.get("hook", "")).strip(),
        "scenes": scenes,
        "cta": str(data.get("cta", "")).strip(),
        "total_seconds": clock,
        # The honest part: the plan is real, the file is not.
        "renderable": False,
        "note": (
            "This is a shot plan, not a rendered video. Rendering needs a video "
            "generation provider, which is not configured."
        ),
    }
