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


async def generate_posts(req: GeneratePostRequest) -> GeneratePostResponse:
    """Generate optimized post(s). One platform, or all when none specified."""
    provider = get_provider(req.provider)

    targets = [req.platform] if req.platform else list(Platform)

    # Fan out across platforms concurrently — fast and cheap.
    posts = await asyncio.gather(
        *(_generate_one(provider, req, p) for p in targets)
    )

    return GeneratePostResponse(
        provider=provider.name,
        model=provider.model,
        results=list(posts),
    )


async def _generate_one(
    provider: AIProvider, req: GeneratePostRequest, platform: Platform
) -> GeneratedPost:
    spec = PLATFORM_SPECS[platform]
    system = build_system_prompt()
    user = build_user_prompt(req, platform)

    raw = await provider.complete(
        system=system,
        user=user,
        max_tokens=settings.ai_max_tokens,
        temperature=settings.ai_temperature,
        json_mode=True,
        context={
            "platform": platform.value,
            "topic": req.topic,
            "tone": req.tone.value,
            "variants": req.variants,
            "include_hashtags": req.include_hashtags,
        },
    )

    data = _parse_json(raw)
    text = str(data.get("text", "")).strip()

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
