"""Strategy Service — the AI Content Planning Engine.

One cheap LLM call turns the user's preferences + business profile into a
diverse, dated content calendar (topics). This is fast and synchronous; the
heavy per-post generation happens later in the runner.

Falls back to a deterministic, still-useful calendar if the provider is
unavailable, so the planner never dead-ends.
"""
from __future__ import annotations

import json
import logging
import re
import uuid

from app.config import settings
from app.services.planner.constants import CONTENT_TYPES
from app.services.planner.prompts import (
    STRATEGY_SYSTEM,
    build_regenerate_user_prompt,
    build_strategy_user_prompt,
)
from app.services.providers import get_provider

logger = logging.getLogger(__name__)

_JSON_RE = re.compile(r"[\[{].*[\]}]", re.DOTALL)


def _parse(raw: str) -> dict | list:
    if not raw:
        return {}
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m = _JSON_RE.search(cleaned)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {}


def _topic_id() -> str:
    return uuid.uuid4().hex[:12]


def _fallback_topics(slots: list[dict], content_mix: list[str]) -> list[dict]:
    """Deterministic, varied calendar used when the LLM can't be reached."""
    mix = content_mix or CONTENT_TYPES
    out: list[dict] = []
    for i, s in enumerate(slots):
        ctype = mix[i % len(mix)]
        out.append(
            {
                "id": _topic_id(),
                "date": s["date"],
                "weekday": s["weekday"],
                "content_type": ctype,
                "topic": f"{ctype} post idea for {s['weekday']}",
            }
        )
    return out


def _dedupe(topics: list[dict], content_mix: list[str]) -> list[dict]:
    """Ensure no two topics are identical — nudges variety if the LLM repeats."""
    mix = content_mix or CONTENT_TYPES
    seen: set[str] = set()
    for i, t in enumerate(topics):
        key = t["topic"].strip().lower()
        if key and key not in seen:
            seen.add(key)
            continue
        # Collision (or empty): synthesize a distinct fallback.
        t["topic"] = f"{t['content_type']} idea for {t['weekday']} ({i + 1})"
        seen.add(t["topic"].lower())
    return topics


async def generate_strategy(
    *,
    slots: list[dict],
    goals: list[str],
    content_mix: list[str],
    platforms: list[str],
    user_prompt: str | None,
    business_context: str | None,
    extra_guidance: str | None = None,
    provider_name: str | None = None,
) -> dict:
    """Build a strategy: {theme, summary, topics:[{id,date,weekday,content_type,topic}]}."""
    if not slots:
        return {"theme": "", "summary": "", "topics": []}

    try:
        provider = get_provider(provider_name)
    except Exception:  # noqa: BLE001 — no provider configured; use fallback
        logger.info("Strategy: provider unavailable, using fallback calendar.")
        return {
            "theme": "Balanced content plan",
            "summary": "A varied mix of content across your selected platforms.",
            "topics": _dedupe(_fallback_topics(slots, content_mix), content_mix),
        }

    user = build_strategy_user_prompt(
        slots=slots,
        goals=goals,
        content_mix=content_mix,
        platforms=platforms,
        user_prompt=user_prompt,
        business_context=business_context,
        extra_guidance=extra_guidance,
    )
    theme, summary = "", ""
    try:
        raw = await provider.complete(
            system=STRATEGY_SYSTEM,
            user=user,
            max_tokens=max(settings.ai_max_tokens, 1600),
            temperature=0.8,
            json_mode=True,
            context={"planner": "strategy", "slots": len(slots)},
        )
        parsed = _parse(raw)
        if isinstance(parsed, dict):
            theme = str(parsed.get("theme", "")).strip()
            summary = str(parsed.get("summary", "")).strip()
            items = parsed.get("topics")
        else:
            items = parsed
        items = items if isinstance(items, list) else []
    except Exception:  # noqa: BLE001 — best effort; degrade to fallback
        logger.warning("Strategy generation failed; using fallback calendar.")
        items = []

    mix = content_mix or CONTENT_TYPES
    topics: list[dict] = []
    for i, s in enumerate(slots):
        item = items[i] if i < len(items) and isinstance(items[i], dict) else {}
        ctype = str(item.get("content_type", "")).strip()
        topic = str(item.get("topic", "")).strip()
        topics.append(
            {
                "id": _topic_id(),
                "date": s["date"],
                "weekday": s["weekday"],
                "content_type": ctype or mix[i % len(mix)],
                "topic": topic or f"{mix[i % len(mix)]} post idea for {s['weekday']}",
            }
        )
    return {
        "theme": theme or "Balanced content plan",
        "summary": summary or "A varied, on-brand mix across your platforms.",
        "topics": _dedupe(topics, content_mix),
    }


async def regenerate_topic(
    *,
    slot: dict,
    content_type: str,
    content_mix: list[str],
    existing_topics: list[str],
    goals: list[str],
    business_context: str | None,
    provider_name: str | None = None,
) -> dict:
    """Regenerate a single topic without touching the rest of the plan."""
    try:
        provider = get_provider(provider_name)
    except Exception:  # noqa: BLE001
        return {
            "content_type": content_type,
            "topic": f"{content_type} post idea for {slot['weekday']}",
        }

    user = build_regenerate_user_prompt(
        slot=slot,
        content_type=content_type,
        content_mix=content_mix,
        existing_topics=existing_topics,
        goals=goals,
        business_context=business_context,
    )
    try:
        raw = await provider.complete(
            system=STRATEGY_SYSTEM,
            user=user,
            max_tokens=settings.ai_max_tokens,
            temperature=0.9,
            json_mode=True,
            context={"planner": "regenerate_topic"},
        )
        parsed = _parse(raw)
        data = parsed if isinstance(parsed, dict) else {}
    except Exception:  # noqa: BLE001
        data = {}

    return {
        "content_type": str(data.get("content_type", "")).strip() or content_type,
        "topic": str(data.get("topic", "")).strip()
        or f"{content_type} post idea for {slot['weekday']}",
    }
