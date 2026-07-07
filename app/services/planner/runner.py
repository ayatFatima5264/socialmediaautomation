"""Planner Service — orchestrates per-post generation as a background job.

Reuses `ai_service.generate_posts` (content), the scheduling service (timing),
and writes standard `Post` rows linked to the plan. Runs with its own DB session
(like the scheduler) so it survives the request that kicked it off, commits per
topic for live progress, and degrades gracefully on partial failures.

Diversity: an accumulating "avoid list" of already-used hashtags is fed into
each subsequent generation, and the model is told to vary CTAs — satisfying the
no-repeat requirement across the whole plan.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from sqlalchemy import select

from app.database import SessionLocal
from app.models.content_plan import ContentPlan
from app.models.post import Post
from app.schemas.post import GeneratePostRequest, Platform, PostStatus, Tone
from app.services import business_profile_service
from app.services.ai_service import generate_posts
from app.services.planner.scheduling import schedule_time

logger = logging.getLogger(__name__)

# Map a planned content type to the closest generation tone.
_TONE_BY_TYPE: dict[str, Tone] = {
    "Educational": Tone.informative,
    "Tips": Tone.informative,
    "Industry News": Tone.informative,
    "Case Study": Tone.professional,
    "Promotional": Tone.promotional,
    "Product Update": Tone.promotional,
    "Engagement": Tone.casual,
    "Story": Tone.casual,
    "Behind the Scenes": Tone.friendly,
    "Testimonial": Tone.friendly,
    "Inspirational": Tone.inspirational,
}


def _tone_for(content_type: str | None) -> Tone:
    return _TONE_BY_TYPE.get(content_type or "", Tone.professional)


def _avoid_instructions(used_hashtags: set[str]) -> str | None:
    if not used_hashtags:
        return (
            "This post is part of a larger content plan. Use a fresh call-to-action "
            "and avoid generic repeated phrasing."
        )
    sample = ", ".join(f"#{h}" for h in list(used_hashtags)[:25])
    return (
        "This post is part of a larger content plan. To keep it diverse: do NOT "
        f"reuse these hashtags already used elsewhere in the plan: {sample}. "
        "Also vary the call-to-action and opening hook so posts don't feel repetitive."
    )


async def run_generation(plan_id: int) -> None:
    """Generate + schedule every post for a plan. Safe to call as a background task."""
    db = SessionLocal()
    try:
        plan = db.get(ContentPlan, plan_id)
        if plan is None:
            return

        # Idempotent (re)generation: clear this plan's not-yet-published posts.
        existing = db.scalars(
            select(Post).where(
                Post.plan_id == plan.id,
                Post.status.in_([PostStatus.draft.value, PostStatus.scheduled.value]),
            )
        ).all()
        for p in existing:
            db.delete(p)

        plan.status = "generating"
        plan.generated_posts = 0
        plan.error = None
        topics = list(plan.topics or [])
        try:
            platforms = [Platform(p) for p in plan.platforms]
        except ValueError:
            platforms = []
        plan.total_posts = len(topics) * len(platforms)
        db.commit()

        business_context = business_profile_service.context_for_user(db, plan.user_id)
        used_hashtags: set[str] = set()

        for topic in topics:
            try:
                local_date = date.fromisoformat(str(topic["date"]))
            except (KeyError, ValueError):
                continue
            tone = _tone_for(topic.get("content_type"))
            avoid = _avoid_instructions(used_hashtags)

            # Generate all selected platforms for this topic concurrently.
            results = await asyncio.gather(
                *(
                    generate_posts(
                        GeneratePostRequest(
                            topic=topic["topic"], tone=tone, platform=p,
                            include_hashtags=True,
                        ),
                        business_context,
                        avoid,
                    )
                    for p in platforms
                ),
                return_exceptions=True,
            )

            for slot, (platform, res) in enumerate(zip(platforms, results)):
                if isinstance(res, Exception) or not getattr(res, "results", None):
                    logger.warning(
                        "Planner: generation failed for %s / %r",
                        platform.value, topic.get("topic"),
                    )
                    continue
                gp = res.results[0]
                sched = schedule_time(
                    platform=platform, local_date=local_date,
                    tzname=plan.timezone, slot=slot,
                )
                db.add(
                    Post(
                        user_id=plan.user_id,
                        plan_id=plan.id,
                        platform=platform.value,
                        content=gp.text,
                        hashtags=gp.hashtags,
                        status=PostStatus.draft.value,
                        approval_status="pending",
                        content_type=topic.get("content_type"),
                        topic=topic.get("topic"),
                        scheduled_time=sched,
                    )
                )
                used_hashtags.update(h.lower() for h in gp.hashtags)
                plan.generated_posts += 1

            db.commit()  # commit per topic so progress polling sees live counts

        plan.status = "ready"
        db.commit()
    except Exception as exc:  # noqa: BLE001 — never crash the background task
        logger.exception("Planner generation failed for plan %s", plan_id)
        try:
            plan = db.get(ContentPlan, plan_id)
            if plan is not None:
                plan.status = "failed"
                plan.error = str(exc)
                db.commit()
        except Exception:  # noqa: BLE001
            pass
    finally:
        db.close()


async def regenerate_post(db, post: Post) -> Post:
    """Regenerate a single planner post's copy in place (keeps schedule/approval)."""
    business_context = business_profile_service.context_for_user(db, post.user_id)
    req = GeneratePostRequest(
        topic=post.topic or post.content[:200],
        tone=_tone_for(post.content_type),
        platform=Platform(post.platform),
        include_hashtags=True,
    )
    res = await generate_posts(req, business_context)
    if res.results:
        gp = res.results[0]
        post.content = gp.text
        post.hashtags = gp.hashtags
        db.commit()
        db.refresh(post)
    return post
