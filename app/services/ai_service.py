"""AI service layer.

Orchestrates: request -> per-platform prompt -> provider completion ->
robust JSON parse -> typed GeneratedPost. Platform-agnostic and
provider-agnostic; switching the LLM is a config change, not a code change.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re

from app.config import settings
from app.schemas.post import (
    GeneratedPost,
    GeneratePostRequest,
    GeneratePostResponse,
    Platform,
)
from app.services.prompt_templates import (
    PLATFORM_SPECS,
    build_system_prompt,
    build_user_prompt,
)
from app.services.providers import AIProvider, get_provider

logger = logging.getLogger(__name__)

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


async def generate_posts(
    req: GeneratePostRequest,
    business_context: str | None = None,
    extra_instructions: str | None = None,
) -> GeneratePostResponse:
    """Generate optimized post(s). One platform, or all when none specified.

    `business_context` (from the user's business profile) is woven into each
    prompt when present; it's optional so generation works without a profile.
    `extra_instructions` appends ad-hoc guidance (e.g. the Content Planner's
    "avoid these hashtags/CTAs" diversity rules) — optional and additive.
    """
    provider = get_provider(req.provider)

    targets = [req.platform] if req.platform else list(Platform)

    # Fan out across platforms concurrently — fast and cheap.
    posts = await asyncio.gather(
        *(
            _generate_one(provider, req, p, business_context, extra_instructions)
            for p in targets
        )
    )

    return GeneratePostResponse(
        provider=provider.name,
        model=provider.model,
        results=list(posts),
    )


async def generate_article(
    topic: str,
    *,
    audience: str | None = None,
    tone: str = "professional",
    provider_name: str | None = None,
    business_context: str | None = None,
) -> dict:
    """Generate a LinkedIn article (title, body, tags, SEO keywords, cover prompt).

    Returns a dict the route serializes; reading time is derived from the body.
    Deliberately produces long-form prose — no hashtags or short captions.
    """
    provider = get_provider(provider_name)
    system = (
        "You are an expert LinkedIn ghostwriter who writes engaging, "
        "professional long-form articles. You ALWAYS return only a JSON object "
        "matching the requested schema — no markdown, no code fences, no commentary."
    )
    audience_line = f"\nTARGET AUDIENCE: {audience}" if audience else ""
    context_line = (
        f"\nBUSINESS CONTEXT (make it relevant and on-brand; ignore missing "
        f"fields):\n{business_context}"
        if business_context
        else ""
    )
    user = (
        f"Write a {tone} LinkedIn article about this topic:\n"
        f"TOPIC: {topic}{audience_line}{context_line}\n\n"
        "Requirements:\n"
        "- A compelling, specific title (max ~80 characters).\n"
        "- A body of roughly 400-800 words in clear paragraphs separated by "
        "blank lines. Use a few short plain-text subheadings. Professional, "
        "insight-driven, with a strong opening hook and a closing takeaway.\n"
        "- 3-6 topical tags (no # symbol).\n"
        "- 4-8 SEO keywords/phrases.\n"
        "- A short visual description for a 16:9 cover image.\n\n"
        "Return ONLY a JSON object with exactly these keys:\n"
        '{"title": "...", "body": "...", "tags": ["..."], '
        '"seo_keywords": ["..."], "cover_image_prompt": "..."}'
    )
    raw = await provider.complete(
        system=system,
        user=user,
        max_tokens=max(settings.ai_max_tokens, 2048),
        temperature=settings.ai_temperature,
        json_mode=True,
        context={"article": True, "topic": topic},
    )
    data = _parse_json(raw)
    body = str(data.get("body", "")).strip()
    title = str(data.get("title", "")).strip() or topic[:80]
    words = len(body.split())
    return {
        "title": title,
        "body": body,
        "tags": _normalize_hashtags(data.get("tags")),
        "seo_keywords": _normalize_list(data.get("seo_keywords")),
        "cover_image_prompt": str(data.get("cover_image_prompt", "")).strip() or title,
        "reading_time_min": max(1, round(words / 200)),
        "word_count": words,
    }


def _normalize_list(value: object) -> list[str]:
    """Normalize a value into a clean list of strings (keeps phrases intact)."""
    if value is None:
        return []
    if isinstance(value, str):
        value = re.split(r"[,\n]+", value)
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    for item in value:
        s = str(item).strip().lstrip("#").strip()
        if s:
            out.append(s)
    return out


async def generate_carousel_outline(
    topic: str,
    slides: int,
    *,
    platform: Platform | None = None,
    provider_name: str | None = None,
) -> list[str]:
    """Return exactly `slides` short, DISTINCT visual descriptions for a carousel.

    Best-effort: if the LLM provider is unavailable (no API key) or returns
    something unusable, fall back to deterministic per-slide labels so image
    generation still produces visibly different slides — never identical images.
    """
    slides = max(1, min(slides, 10))
    fallback = _fallback_outline(topic, slides)

    try:
        provider = get_provider(provider_name)
    except Exception:  # noqa: BLE001 — provider not configured; use fallback
        logger.info("Carousel outline: provider unavailable, using fallback labels.")
        return fallback

    system = (
        "You design social media carousels. You always return ONLY valid JSON "
        "matching the requested schema — no markdown, no commentary."
    )
    audience = f" for {platform.value}" if platform else ""
    user = (
        f"Create exactly {slides} carousel slides{audience} about this topic:\n"
        f"TOPIC: {topic}\n\n"
        "Each slide must cover a DIFFERENT aspect of the topic (e.g. cover, key "
        "point, example, benefit, summary) so that no two slides look alike.\n"
        'Return ONLY a JSON object: {"slides": ["short visual description", ...]} '
        f"with exactly {slides} items, each 3-10 words, no numbering."
    )
    try:
        raw = await provider.complete(
            system=system,
            user=user,
            max_tokens=settings.ai_max_tokens,
            temperature=0.7,
            json_mode=True,
            context={"carousel": True, "topic": topic, "slides": slides},
        )
        items = _parse_json(raw).get("slides")
        cleaned = (
            [str(s).strip() for s in items if str(s).strip()]
            if isinstance(items, list)
            else []
        )
    except Exception:  # noqa: BLE001 — best effort; keep going with the fallback
        logger.warning("Carousel outline generation failed; using fallback labels.")
        cleaned = []

    if len(cleaned) < slides:
        # Pad with fallback labels so we always return exactly `slides` items.
        cleaned += fallback[len(cleaned):]
    return cleaned[:slides]


# Optional, in-place text edits for the manual composer ("AI Assist"). Each
# transforms the user's existing text rather than generating a new post.
ASSIST_INSTRUCTIONS: dict[str, str] = {
    "improve": "Improve the writing so it is clearer, more engaging and polished. Keep the same meaning and the same language.",
    "rewrite": "Rewrite the text in a fresh way while preserving its meaning and language.",
    "shorten": "Make the text shorter and more concise while keeping the key message.",
    "expand": "Expand the text with more relevant detail and depth, keeping the same voice.",
    "grammar": "Correct all spelling, grammar and punctuation mistakes. Keep the wording and language otherwise unchanged.",
    "tone": "Rewrite the text in a {tone} tone.",
    "hashtags": "Generate 5 to 10 relevant hashtags (a mix of popular and niche) for the text. Each must start with # and be separated by spaces. Return only the hashtags.",
    "cta": "Write one short, compelling call-to-action line for the text. Return only that line.",
    "translate": "Translate the text into {language}. Return only the translation.",
}


async def assist_text(
    text: str,
    action: str,
    *,
    tone: str | None = None,
    language: str | None = None,
    provider_name: str | None = None,
) -> str:
    """Apply an in-place AI edit (improve/rewrite/translate/…) to `text`."""
    instruction = ASSIST_INSTRUCTIONS.get(action)
    if instruction is None:
        raise ValueError(f"Unknown assist action: {action!r}")
    if action == "tone":
        instruction = instruction.format(tone=tone or "professional")
    if action == "translate":
        instruction = instruction.format(language=language or "English")

    provider = get_provider(provider_name)
    system = (
        "You are an expert social media copy editor. You ALWAYS return only a "
        'JSON object {"result": "..."} with no markdown, no code fences and no '
        "commentary."
    )
    user = (
        f"{instruction}\n\nTEXT:\n{text}\n\n"
        'Return ONLY a JSON object: {"result": "the edited text"}.'
    )
    raw = await provider.complete(
        system=system,
        user=user,
        max_tokens=settings.ai_max_tokens,
        temperature=0.7,
        json_mode=True,
        context={"assist": action},
    )
    result = str(_parse_json(raw).get("result", "")).strip()
    return result or text


def _fallback_outline(topic: str, slides: int) -> list[str]:
    """Deterministic distinct slide labels when the LLM can't be used."""
    roles = [
        "cover", "introduction", "key point", "example", "benefit",
        "how it works", "pro tip", "common mistake", "insight", "summary",
    ]
    return [
        f"{topic} — {roles[i] if i < len(roles) else f'point {i + 1}'}"
        for i in range(slides)
    ]


async def _generate_one(
    provider: AIProvider,
    req: GeneratePostRequest,
    platform: Platform,
    business_context: str | None = None,
    extra_instructions: str | None = None,
) -> GeneratedPost:
    spec = PLATFORM_SPECS[platform]
    system = build_system_prompt()
    user = build_user_prompt(req, platform, business_context, extra_instructions)

    context = {
        "platform": platform.value,
        "topic": req.topic,
        "tone": req.tone.value,
        "variants": req.variants,
        "include_hashtags": req.include_hashtags,
    }

    raw = await provider.complete(
        system=system,
        user=user,
        max_tokens=settings.ai_max_tokens,
        temperature=settings.ai_temperature,
        json_mode=True,
        context=context,
    )

    data = _parse_json(raw)
    text = str(data.get("text", "")).strip()

    # Some models (e.g. llama-3.3-70b) ignore a stated length floor and return a
    # bare one-line slogan. If the draft is well under the platform minimum, do
    # one expand pass that feeds the draft back and asks for a fuller post.
    if len(text) < spec.min_chars:
        expanded = await _expand(provider, req, platform, text, context)
        if len(expanded) > len(text):
            data["text"] = expanded
            text = expanded

    hashtags: list[str] = []
    if req.include_hashtags:
        hashtags = _normalize_hashtags(data.get("hashtags"))

    return GeneratedPost(
        platform=platform,
        text=text,
        short_version=_opt_str(data.get("short_version")) if req.variants else None,
        long_version=_opt_str(data.get("long_version")) if req.variants else None,
        hashtags=hashtags,
        character_count=len(text),
        char_limit=spec.char_limit,
        within_limit=len(text) <= spec.char_limit,
    )


async def _expand(
    provider: AIProvider,
    req: GeneratePostRequest,
    platform: Platform,
    draft: str,
    context: dict,
) -> str:
    """Rewrite an over-short draft into a fuller, platform-native post.

    Returns the expanded text, or the original draft if the rewrite fails or
    doesn't actually grow it.
    """
    spec = PLATFORM_SPECS[platform]
    system = build_system_prompt()
    user = (
        f"Rewrite the following {spec.label} post so it is more developed and "
        f"engaging. It is currently too short.\n\n"
        f"DRAFT: {draft or '(empty)'}\n\n"
        f"TOPIC: {req.topic}\n"
        f"VOICE: {spec.voice}\n"
        f"REQUIRED LENGTH: between {spec.min_chars} and {spec.char_limit} "
        f"characters. Keep the same core idea and tone, but expand it into "
        f"full sentences — add a concrete benefit, detail or call-to-action. "
        f"Never return just a headline.\n\n"
        'Return ONLY a JSON object: {"text": "the rewritten post"}'
    )
    try:
        raw = await provider.complete(
            system=system,
            user=user,
            max_tokens=settings.ai_max_tokens,
            temperature=settings.ai_temperature,
            json_mode=True,
            context={**context, "expand": True},
        )
    except Exception:  # noqa: BLE001 — expansion is best-effort; keep the draft
        logger.warning("Expand pass failed for %s; keeping short draft.", platform.value)
        return draft

    expanded = str(_parse_json(raw).get("text", "")).strip()
    return expanded or draft


def _parse_json(raw: str) -> dict:
    """Best-effort JSON extraction from a model response.

    Handles clean JSON, ```json fenced blocks, and stray prose around the
    object. Falls back to treating the whole response as plain post text.
    """
    if not raw:
        return {"text": ""}

    cleaned = raw.strip()
    # Strip a leading/trailing markdown code fence if present.
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = _JSON_OBJECT_RE.search(cleaned)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse JSON from model output; using raw text.")
    return {"text": cleaned}


def _normalize_hashtags(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        # Accept "#a #b" or "a, b" strings as well as arrays.
        value = re.split(r"[\s,]+", value)
    if not isinstance(value, (list, tuple)):
        return []
    tags: list[str] = []
    for item in value:
        tag = str(item).strip().lstrip("#").strip()
        if tag:
            tags.append(tag)
    return tags


def _opt_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
