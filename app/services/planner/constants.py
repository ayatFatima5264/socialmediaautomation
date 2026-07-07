"""Shared Content Planner vocabulary and the scheduling heuristic.

Kept in one place so the strategy engine, scheduling engine, and API validation
all agree — and so the frontend can mirror these lists. Extend freely; adding a
content type or a platform's best-times is a one-line change.
"""
from __future__ import annotations

from app.schemas.post import Platform

# The healthy content mix the AI balances across a plan.
CONTENT_TYPES: list[str] = [
    "Educational",
    "Promotional",
    "Tips",
    "Engagement",
    "Industry News",
    "Case Study",
    "Behind the Scenes",
    "Testimonial",
    "Product Update",
    "Story",
    "Inspirational",
]

# Business goals the plan optimizes toward (mirrors onboarding goals).
CONTENT_GOALS: list[str] = [
    "Generate Leads",
    "Increase Sales",
    "Brand Awareness",
    "Grow Followers",
    "Drive Website Traffic",
    "Educate Audience",
    "Build Community",
]

# Posting frequency -> posts per week (custom uses the user's number).
FREQUENCY_PER_WEEK: dict[str, int] = {
    "daily": 7,
    "3_week": 3,
    "5_week": 5,
    "custom": 0,  # resolved from posts_per_week
}

FREQUENCIES: list[str] = list(FREQUENCY_PER_WEEK.keys())
DURATIONS: list[int] = [7, 14, 30]

# Best local hours to post per platform (24h), simple industry heuristic. This
# is intentionally a static table for v1; it can later be replaced by
# data-driven, per-account recommendations without changing call sites.
BEST_HOURS: dict[Platform, list[int]] = {
    Platform.instagram: [11, 14, 19],
    Platform.facebook: [9, 13, 15],
    Platform.twitter: [8, 12, 17],
    Platform.linkedin: [8, 10, 12],
    Platform.threads: [9, 12, 20],
    Platform.pinterest: [14, 20, 21],
}

# Fallback if a platform isn't in the table.
DEFAULT_HOURS: list[int] = [9, 13, 18]
