"""Strategy signal providers — the extensibility backbone of the planner's brain.

The AI Marketing Manager builds its strategy from a stack of *signals*. Each
signal contributes (a) context injected into the strategy prompt and (b) optional
guidance rules. New capabilities — Seasonal campaigns, Trending topics,
Competitor inspiration, Performance-based recommendations, Learning from user
edits — are added by writing a new provider and registering it. The strategy
engine never changes.

Only the Business Profile provider is active today; the rest are documented,
registered stubs that return `None` until implemented, so the plug points are
real and visible rather than hypothetical.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from app.services import business_profile_service


@dataclass
class PlannerContext:
    """Inputs available to every signal provider when building a strategy."""
    db: Session
    user_id: int
    platforms: list[str]
    goals: list[str]
    content_mix: list[str]
    duration_days: int
    user_prompt: str | None


@dataclass
class Signal:
    """A provider's contribution to the strategy prompt."""
    key: str
    # Freeform context block (facts the AI should use), rendered under a heading.
    context: str | None = None
    # Extra rules/instructions appended to the strategy prompt.
    guidance: str | None = None


class SignalProvider(Protocol):
    key: str
    enabled: bool

    async def gather(self, ctx: PlannerContext) -> Signal | None: ...


# ---------------------------------------------------------------------------
# Active provider — Business Profile
# ---------------------------------------------------------------------------
class BusinessProfileProvider:
    """Grounds the whole plan in the user's saved business profile."""
    key = "business_profile"
    enabled = True

    async def gather(self, ctx: PlannerContext) -> Signal | None:
        context = business_profile_service.context_for_user(ctx.db, ctx.user_id)
        if not context:
            return None
        return Signal(
            key=self.key,
            context=context,
            guidance=(
                "Ground every topic in this business — reference its industry, "
                "audience and offering so the plan feels bespoke, not generic."
            ),
        )


# ---------------------------------------------------------------------------
# Future providers — registered but inactive. Flip `enabled = True` and fill in
# `gather` to ship each capability; the strategy engine picks it up automatically.
# ---------------------------------------------------------------------------
class SeasonalProvider:
    """Seasonal / holiday campaigns (Ramadan, Eid, Black Friday, New Year…).

    TODO: given the plan's date window + region, surface upcoming events and
    tell the AI to weave in timely, on-brand campaign moments.
    """
    key = "seasonal"
    enabled = False

    async def gather(self, ctx: PlannerContext) -> Signal | None:
        return None


class TrendingProvider:
    """Trending industry topics.

    TODO: pull current trends for the business's industry (news/search/social
    APIs) and offer them as optional angles the AI can build fresh takes on.
    """
    key = "trending"
    enabled = False

    async def gather(self, ctx: PlannerContext) -> Signal | None:
        return None


class CompetitorProvider:
    """Competitor inspiration (without copying).

    TODO: summarize themes competitors post about so the AI can differentiate —
    explicitly instructed to inspire, never replicate.
    """
    key = "competitor"
    enabled = False

    async def gather(self, ctx: PlannerContext) -> Signal | None:
        return None


class PerformanceProvider:
    """Performance-based recommendations.

    TODO: read this user's historical post performance (once analytics exists)
    and bias the mix toward content types/topics that performed well.
    """
    key = "performance"
    enabled = False

    async def gather(self, ctx: PlannerContext) -> Signal | None:
        return None


class PreferenceLearningProvider:
    """AI learning from the user's edits and preferences.

    TODO: consume recorded planner edits (topics rewritten, posts regenerated,
    types deleted) to learn tone/topic preferences over time and steer the plan.
    See `record_edit` below for the capture hook.
    """
    key = "preference_learning"
    enabled = False

    async def gather(self, ctx: PlannerContext) -> Signal | None:
        return None


# Order matters: earlier providers appear first in the assembled context.
_PROVIDERS: list[SignalProvider] = [
    BusinessProfileProvider(),
    PerformanceProvider(),
    PreferenceLearningProvider(),
    SeasonalProvider(),
    TrendingProvider(),
    CompetitorProvider(),
]


async def gather_signals(ctx: PlannerContext) -> list[Signal]:
    """Run every enabled provider and collect its non-empty signal."""
    out: list[Signal] = []
    for provider in _PROVIDERS:
        if not getattr(provider, "enabled", False):
            continue
        try:
            sig = await provider.gather(ctx)
        except Exception:  # noqa: BLE001 — a bad provider must never break planning
            sig = None
        if sig is not None:
            out.append(sig)
    return out


def assemble_context(signals: list[Signal]) -> tuple[str | None, str | None]:
    """Merge signals into (context_block, guidance_block) for the prompt."""
    contexts = [s.context.strip() for s in signals if s.context]
    guidance = [s.guidance.strip() for s in signals if s.guidance]
    return (
        "\n\n".join(contexts) or None,
        " ".join(guidance) or None,
    )


def record_edit(db: Session, user_id: int, kind: str, detail: dict) -> None:
    """Capture hook for the AI-learning loop (topics/posts the user changes).

    Intentionally a no-op today — this is the seam where the future
    PreferenceLearningProvider will read from. Wire it to a `planner_events`
    table when learning ships; keeping the call sites in place now means no
    refactor later.
    """
    return None
