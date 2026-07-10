"""Background scheduler + publish logic.

Design: the database is the single source of truth. A lightweight asyncio loop
polls for posts that are due (status=scheduled and scheduled_time <= now) and
publishes them. This survives restarts (state lives in the DB, not the
scheduler) and needs no extra infrastructure like Redis/Celery.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.timeutils import utcnow
from app.database import SessionLocal
from app.models.post import Post
from app.models.social_account import SocialAccount
from app.schemas.post import Platform, PostStatus
from app.services.publisher import PublishResult, get_publisher

logger = logging.getLogger(__name__)


def _media_urls(post: Post) -> list[str]:
    """Ordered public media URLs attached to a post, read from Post.media.

    Post.media items look like {"type": "image", "url": <public URL>, ...} (see
    the planner). Publishers that support media (e.g. X) receive these and decide
    how to use them; text-only publishers ignore them. Malformed/urlless entries
    are skipped.
    """
    items = post.media or []
    return [
        item["url"]
        for item in items
        if isinstance(item, dict) and item.get("url")
    ]


async def publish_post(db: Session, post: Post) -> Post:
    """Publish a single post via its platform adapter and persist the outcome.

    Shared by the scheduler and the manual "publish now" endpoint.
    """
    post.status = PostStatus.publishing.value
    db.commit()

    platform = Platform(post.platform)
    # Use the post owner's connected account for this platform, if any.
    account = db.scalars(
        select(SocialAccount).where(
            SocialAccount.user_id == post.user_id,
            SocialAccount.platform == platform.value,
        )
    ).first()

    publisher = get_publisher(platform, account, db)
    try:
        result = await publisher.publish(
            content=post.content,
            hashtags=post.hashtags or [],
            media_urls=_media_urls(post),
        )
    except Exception as exc:  # adapter blew up — record, don't crash the loop
        logger.exception("Publisher raised for post %s", post.id)
        result = PublishResult(success=False, error=str(exc))

    if result.success:
        post.status = PostStatus.published.value
        post.published_time = utcnow()
        post.external_id = result.external_id
        post.error = None
    else:
        post.status = PostStatus.failed.value
        post.error = result.error

    db.commit()
    db.refresh(post)
    return post


async def process_due_posts() -> int:
    """Publish every post that is due. Returns how many were processed."""
    db = SessionLocal()
    try:
        now = utcnow()
        due = list(
            db.scalars(
                select(Post).where(
                    Post.status == PostStatus.scheduled.value,
                    Post.scheduled_time.is_not(None),
                    Post.scheduled_time <= now,
                )
            ).all()
        )
        if not due:
            return 0
        logger.info("Scheduler: %d post(s) due for publishing", len(due))
        for post in due:
            await publish_post(db, post)
        return len(due)
    finally:
        db.close()


async def scheduler_loop(stop_event: asyncio.Event) -> None:
    interval = settings.scheduler_poll_seconds
    logger.info("Scheduler started (poll every %ss)", interval)
    while not stop_event.is_set():
        try:
            await process_due_posts()
        except Exception:  # never let a bad iteration kill the loop
            logger.exception("Scheduler iteration failed")
        try:
            # Sleep, but wake immediately if asked to stop.
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
    logger.info("Scheduler stopped")
