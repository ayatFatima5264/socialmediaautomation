"""Prompt Builder for the Content Planner strategy step.

Provider-agnostic string construction only — no network calls here. Produces
the (system, user) messages that ask the LLM to design a diverse content
calendar grounded in the user's business profile, goals, and content mix.
"""
from __future__ import annotations

import json

from app.services.planner.constants import CONTENT_TYPES

STRATEGY_SYSTEM = (
    "You are an expert social media strategist and content planner. You design "
    "balanced, non-repetitive content calendars that mix formats (educational, "
    "engagement, promotional, stories, tips, etc.) to grow an audience. You "
    "ALWAYS return only valid JSON matching the requested schema — no markdown, "
    "no code fences, no commentary."
)


def _mix(content_mix: list[str]) -> list[str]:
    return content_mix or CONTENT_TYPES


def build_strategy_user_prompt(
    *,
    slots: list[dict],
    goals: list[str],
    content_mix: list[str],
    platforms: list[str],
    user_prompt: str | None,
    business_context: str | None,
    extra_guidance: str | None = None,
) -> str:
    """Ask for a plan theme, a short rationale, and one topic per calendar day."""
    allowed = _mix(content_mix)
    slot_lines = "\n".join(
        f'- slot {i}: {s["weekday"]} {s["date"]}' for i, s in enumerate(slots)
    )
    lines = [
        "You are acting as this brand's social media manager. Design a "
        f"{len(slots)}-post content calendar with an intentional, cohesive "
        "strategy — not a random list of posts.",
        "",
        "CALENDAR SLOTS (produce exactly one topic per slot, in order):",
        slot_lines,
        "",
        f"ALLOWED CONTENT TYPES (use a healthy, varied mix): {', '.join(allowed)}",
    ]
    if platforms:
        lines.append(f"TARGET PLATFORMS: {', '.join(platforms)}")
    if goals:
        lines.append(f"BUSINESS GOALS: {', '.join(goals)}")
    if business_context:
        lines += [
            "",
            "BUSINESS CONTEXT (make topics specific and on-brand; ignore missing "
            "fields):",
            business_context,
        ]
    if user_prompt:
        lines += ["", f"EXTRA DIRECTION FROM THE USER: {user_prompt}"]

    lines += [
        "",
        "RULES:",
        "- Give the plan a clear THEME and a one-paragraph rationale explaining "
        "the strategy and how it serves the goals.",
        "- Balance the content_type across the calendar; don't over-use any one "
        "type (especially Promotional).",
        "- Every topic must be DISTINCT — no duplicate or near-duplicate ideas.",
        "- Each topic is a short, specific, compelling title (max ~70 chars).",
        "- content_type must be one of the allowed types above.",
    ]
    if extra_guidance:
        lines.append(f"- {extra_guidance}")

    lines += [
        "",
        "Return ONLY a JSON object of the form:",
        json.dumps(
            {
                "theme": "A short strategy theme/title",
                "summary": "One paragraph explaining the plan and why it works",
                "topics": [
                    {"content_type": "Educational", "topic": "A specific title"}
                ],
            },
            indent=2,
        ),
        f"with exactly {len(slots)} items in the topics array, in slot order.",
    ]
    return "\n".join(lines)


def build_regenerate_user_prompt(
    *,
    slot: dict,
    content_type: str,
    content_mix: list[str],
    existing_topics: list[str],
    goals: list[str],
    business_context: str | None,
) -> str:
    """Ask for ONE fresh topic that doesn't collide with the rest of the plan."""
    allowed = _mix(content_mix)
    lines = [
        f"Suggest ONE fresh {content_type} social media topic for "
        f'{slot["weekday"]} {slot["date"]}.',
        f"It must be a {content_type} post (one of: {', '.join(allowed)}).",
    ]
    if goals:
        lines.append(f"BUSINESS GOALS: {', '.join(goals)}")
    if business_context:
        lines += ["", "BUSINESS CONTEXT:", business_context]
    if existing_topics:
        lines += [
            "",
            "AVOID overlapping with these existing topics in the plan:",
            "; ".join(existing_topics[:40]),
        ]
    lines += [
        "",
        "The topic must be distinct from all of the above, specific and "
        "compelling (max ~70 chars).",
        "",
        'Return ONLY a JSON object: {"content_type": "...", "topic": "..."}',
    ]
    return "\n".join(lines)
