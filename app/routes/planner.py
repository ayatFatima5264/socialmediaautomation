"""AI Content Planner endpoints (all user-scoped).

Thin API over the planner services. Flow:
  POST /strategy         -> create a plan + AI content calendar (fast, sync)
  PATCH /{id}/topics     -> edit the calendar before generating
  POST /{id}/generate    -> generate every post in the background
  GET  /{id}             -> poll status + generated posts (live progress)
  POST /{id}/approve     -> promote approved posts to scheduled (scheduler publishes)
  POST /quick-generate   -> one-click: use saved settings, strategy + generate
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.timeutils import to_naive_utc, utcnow
from app.database import get_db
from app.models.content_plan import ContentPlan, PlannerSettings
from app.models.post import Post
from app.models.user import User
from app.schemas.content_plan import (
    ApproveRequest,
    GenerateRequest,
    PlannerPostRead,
    PlannerPostUpdate,
    PlannerSettingsRead,
    PlannerSettingsUpdate,
    PlannerSetup,
    PlanRead,
    PlanSummary,
    RegenerateTopicRequest,
    TopicsUpdate,
)
from app.schemas.post import Platform, PostStatus
from app.services import business_profile_service
from app.services.planner import scheduling, signals, strategy
from app.services.planner.runner import regenerate_post, run_generation

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/planner", tags=["planner"])

# Hold references to fire-and-forget background jobs so they aren't GC'd.
_JOBS: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _JOBS.add(task)
    task.add_done_callback(_JOBS.discard)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _owned_plan(db: Session, plan_id: int, user: User) -> ContentPlan:
    plan = db.get(ContentPlan, plan_id)
    if plan is None or plan.user_id != user.id:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


def _owned_planner_post(db: Session, post_id: int, user: User) -> Post:
    post = db.get(Post, post_id)
    if post is None or post.user_id != user.id or post.plan_id is None:
        raise HTTPException(status_code=404, detail="Planner post not found")
    return post


def _slots_for(setup: PlannerSetup, tzname: str) -> list[dict]:
    dates = scheduling.plan_dates(
        duration_days=setup.duration_days,
        frequency=setup.frequency,
        posts_per_week=setup.posts_per_week,
        tzname=tzname,
    )
    return [{"date": d.isoformat(), "weekday": d.strftime("%A")} for d in dates]


def _post_read(p: Post) -> PlannerPostRead:
    r = PlannerPostRead.model_validate(p)
    r.character_count = len(p.content or "")
    return r


def _plan_read(db: Session, plan: ContentPlan) -> PlanRead:
    posts = db.scalars(
        select(Post)
        .where(Post.plan_id == plan.id)
        .order_by(Post.scheduled_time.asc(), Post.id.asc())
    ).all()
    data = PlanRead.model_validate(plan)
    data.posts = [_post_read(p) for p in posts]
    return data


def _get_or_create_settings(db: Session, user: User) -> PlannerSettings:
    s = db.scalars(
        select(PlannerSettings).where(PlannerSettings.user_id == user.id)
    ).first()
    if s is None:
        s = PlannerSettings(user_id=user.id)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
@router.get("/settings", response_model=PlannerSettingsRead)
def get_settings(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> PlannerSettingsRead:
    s = _get_or_create_settings(db, user)
    return PlannerSettingsRead(
        default_duration_days=s.default_duration_days,
        default_frequency=s.default_frequency,
        default_posts_per_week=s.default_posts_per_week,
        default_platforms=s.default_platforms,
        default_goals=s.default_goals,
        default_content_mix=s.default_content_mix,
        auto_mode=s.auto_mode,
        timezone=user.timezone,
    )


@router.put("/settings", response_model=PlannerSettingsRead)
def update_settings(
    data: PlannerSettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlannerSettingsRead:
    s = _get_or_create_settings(db, user)
    s.default_duration_days = data.default_duration_days
    s.default_frequency = data.default_frequency
    s.default_posts_per_week = data.default_posts_per_week
    s.default_platforms = [p.value for p in data.default_platforms]
    s.default_goals = data.default_goals
    s.default_content_mix = data.default_content_mix
    s.auto_mode = data.auto_mode
    user.timezone = data.timezone or "UTC"
    db.commit()
    return get_settings(db, user)


# ---------------------------------------------------------------------------
# Strategy (create a plan)
# ---------------------------------------------------------------------------
async def _build_plan(db: Session, user: User, setup: PlannerSetup, source: str) -> ContentPlan:
    slots = _slots_for(setup, user.timezone)

    # Assemble strategy context from the pluggable signal providers (Business
    # Profile today; Seasonal/Trending/Competitor/Performance/Learning later).
    planner_ctx = signals.PlannerContext(
        db=db,
        user_id=user.id,
        platforms=[p.value for p in setup.platforms],
        goals=setup.goals,
        content_mix=setup.content_mix,
        duration_days=setup.duration_days,
        user_prompt=setup.user_prompt,
    )
    gathered = await signals.gather_signals(planner_ctx)
    context, guidance = signals.assemble_context(gathered)

    result = await strategy.generate_strategy(
        slots=slots,
        goals=setup.goals,
        content_mix=setup.content_mix,
        platforms=[p.value for p in setup.platforms],
        user_prompt=setup.user_prompt,
        business_context=context,
        extra_guidance=guidance,
    )
    plan = ContentPlan(
        user_id=user.id,
        name=setup.name or f"{setup.duration_days}-Day Content Plan",
        source=source,
        duration_days=setup.duration_days,
        frequency=setup.frequency,
        posts_per_week=setup.posts_per_week,
        platforms=[p.value for p in setup.platforms],
        goals=setup.goals,
        content_mix=setup.content_mix,
        user_prompt=setup.user_prompt,
        timezone=user.timezone,
        auto_mode=False,  # Auto Mode publishing is deferred; always require approval
        theme=result.get("theme"),
        summary=result.get("summary"),
        topics=result.get("topics", []),
        status="strategy",
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.post("/strategy", response_model=PlanRead, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    setup: PlannerSetup,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlanRead:
    plan = await _build_plan(db, user, setup, source="wizard")
    return _plan_read(db, plan)


@router.post("/quick-generate", response_model=PlanRead, status_code=status.HTTP_201_CREATED)
async def quick_generate(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> PlanRead:
    """One-click: build a plan from saved settings and start generating."""
    s = _get_or_create_settings(db, user)
    if not s.default_platforms:
        raise HTTPException(
            status_code=422,
            detail="Set your default platforms in Planner Settings first.",
        )
    setup = PlannerSetup(
        duration_days=s.default_duration_days,
        frequency=s.default_frequency,
        posts_per_week=s.default_posts_per_week,
        platforms=[Platform(p) for p in s.default_platforms],
        goals=s.default_goals,
        content_mix=s.default_content_mix,
    )
    plan = await _build_plan(db, user, setup, source="quick")
    plan.status = "generating"
    db.commit()
    _spawn(run_generation(plan.id))
    return _plan_read(db, plan)


# ---------------------------------------------------------------------------
# Read / list
# ---------------------------------------------------------------------------
@router.get("", response_model=list[PlanSummary])
def list_plans(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[ContentPlan]:
    return list(
        db.scalars(
            select(ContentPlan)
            .where(ContentPlan.user_id == user.id)
            .order_by(ContentPlan.created_at.desc())
        ).all()
    )


@router.get("/{plan_id}", response_model=PlanRead)
def get_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlanRead:
    return _plan_read(db, _owned_plan(db, plan_id, user))


# ---------------------------------------------------------------------------
# Edit topics (Step 2)
# ---------------------------------------------------------------------------
@router.patch("/{plan_id}/topics", response_model=PlanRead)
def update_topics(
    plan_id: int,
    data: TopicsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlanRead:
    plan = _owned_plan(db, plan_id, user)
    if plan.status not in ("strategy", "ready", "failed"):
        raise HTTPException(status_code=409, detail="Plan is currently generating")
    plan.topics = [
        {
            "id": t.id,
            "date": t.date.isoformat(),
            "weekday": t.weekday,
            "content_type": t.content_type,
            "topic": t.topic,
        }
        for t in data.topics
    ]
    db.commit()
    return _plan_read(db, plan)


@router.post("/{plan_id}/topics/regenerate", response_model=PlanRead)
async def regenerate_one_topic(
    plan_id: int,
    body: RegenerateTopicRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlanRead:
    plan = _owned_plan(db, plan_id, user)
    topics = list(plan.topics or [])
    idx = next((i for i, t in enumerate(topics) if t.get("id") == body.topic_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Topic not found")

    target = topics[idx]
    business_context = business_profile_service.context_for_user(db, user.id)
    fresh = await strategy.regenerate_topic(
        slot={"date": target["date"], "weekday": target["weekday"]},
        content_type=target.get("content_type", ""),
        content_mix=plan.content_mix,
        existing_topics=[t["topic"] for i, t in enumerate(topics) if i != idx],
        goals=plan.goals,
        business_context=business_context,
    )
    topics[idx] = {**target, **fresh}
    plan.topics = topics
    db.commit()
    return _plan_read(db, plan)


# ---------------------------------------------------------------------------
# Generate (Step 3) — background job
# ---------------------------------------------------------------------------
@router.post("/{plan_id}/generate", response_model=PlanRead)
async def generate_plan(
    plan_id: int,
    _body: GenerateRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlanRead:
    plan = _owned_plan(db, plan_id, user)
    if plan.status == "generating":
        raise HTTPException(status_code=409, detail="Generation already in progress")
    if not plan.topics:
        raise HTTPException(status_code=422, detail="Plan has no topics to generate")
    plan.status = "generating"
    plan.generated_posts = 0
    db.commit()
    _spawn(run_generation(plan.id))
    return _plan_read(db, plan)


# ---------------------------------------------------------------------------
# Per-post actions (Step 3/5)
# ---------------------------------------------------------------------------
@router.patch("/posts/{post_id}", response_model=PlannerPostRead)
def update_planner_post(
    post_id: int,
    data: PlannerPostUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlannerPostRead:
    post = _owned_planner_post(db, post_id, user)
    if post.status == PostStatus.published.value:
        raise HTTPException(status_code=409, detail="Post already published")
    if data.content is not None:
        post.content = data.content
    if data.hashtags is not None:
        post.hashtags = data.hashtags
    if data.scheduled_time is not None:
        sched = to_naive_utc(data.scheduled_time)
        if sched <= utcnow():
            raise HTTPException(status_code=422, detail="scheduled_time must be in the future")
        post.scheduled_time = sched
    db.commit()
    db.refresh(post)
    return _post_read(post)


@router.post("/posts/{post_id}/regenerate", response_model=PlannerPostRead)
async def regenerate_planner_post(
    post_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlannerPostRead:
    post = _owned_planner_post(db, post_id, user)
    if post.status == PostStatus.published.value:
        raise HTTPException(status_code=409, detail="Post already published")
    post = await regenerate_post(db, post)
    return _post_read(post)


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_planner_post(
    post_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    post = _owned_planner_post(db, post_id, user)
    db.delete(post)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Approval (Step 6)
# ---------------------------------------------------------------------------
@router.post("/{plan_id}/approve", response_model=PlanRead)
def approve_posts(
    plan_id: int,
    body: ApproveRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlanRead:
    """Promote pending posts to scheduled. The background scheduler publishes
    them at their scheduled_time — nothing publishes without this approval."""
    plan = _owned_plan(db, plan_id, user)
    query = select(Post).where(
        Post.plan_id == plan.id, Post.approval_status == "pending"
    )
    if not body.all:
        if not body.post_ids:
            raise HTTPException(status_code=422, detail="No posts selected")
        query = query.where(Post.id.in_(body.post_ids))

    pending = db.scalars(query).all()
    now = utcnow()
    from datetime import timedelta

    for post in pending:
        if post.scheduled_time is None or post.scheduled_time <= now:
            post.scheduled_time = now + timedelta(hours=1)
        post.status = PostStatus.scheduled.value
        post.approval_status = "approved"

    # Flush so the "any pending left?" query sees these updates (autoflush=False).
    db.flush()
    # If nothing is left pending, the whole plan is scheduled.
    remaining = db.scalars(
        select(Post).where(
            Post.plan_id == plan.id, Post.approval_status == "pending"
        )
    ).first()
    if remaining is None and plan.status == "ready":
        plan.status = "scheduled"
    db.commit()
    return _plan_read(db, plan)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Delete a plan. Its unpublished posts cascade; published posts are kept."""
    plan = _owned_plan(db, plan_id, user)
    # Detach already-published posts so history is preserved.
    published = db.scalars(
        select(Post).where(
            Post.plan_id == plan.id, Post.status == PostStatus.published.value
        )
    ).all()
    for p in published:
        p.plan_id = None
    db.delete(plan)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
