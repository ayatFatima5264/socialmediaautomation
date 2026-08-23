"""Handing a finished video over to AutoSocial's publishing pipeline.

Video Studio does not grow a second publisher. A finished render becomes a
**draft `Post`** — the same row the composer, the scheduler and every platform
adapter already work with — carrying the video's public URL, a caption and the
target platform. From that point it is an ordinary post: the user reviews it,
schedules it, and the existing scheduler publishes it.

**Nothing is published here.** `prepare_post` creates a draft, and a draft is
inert: the scheduler only picks up rows in `scheduled` with a time in the past.
That is the requirement — no automatic publishing without confirmation — made
structural rather than promised, because there is no code path in this module
that can reach a platform API.

**What "where supported" honestly means.** Two separate questions, and the UI
is told both:

  * *Is there an account?* — a connected `SocialAccount` for the platform.
  * *Can the adapter upload video?* — today, **no adapter can**. Every
    publisher in `app/services/publisher` handles text and images; none
    implements the video upload flow (Meta's Reels container, and so on). A
    draft is still worth creating — it carries the caption, the hashtags and a
    fetchable URL — but the last step is currently the user downloading the MP4
    and uploading it themselves, and saying so is better than producing a post
    that fails at publish time.

YouTube and TikTok have no adapter at all, so they are export-only and reported
as such rather than offered and then refused.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.post import Post
from app.models.social_account import SocialAccount
from app.models.video_asset import VideoAsset
from app.models.video_project import VideoProject
from app.schemas.post import Platform, PostStatus
from app.services.video import exports

logger = logging.getLogger(__name__)


class PublishError(RuntimeError):
    """A publishing hand-off was refused. The message is user-facing."""


# Which social platform a video project's canvas is aimed at. `None` means the
# app has no adapter for it — YouTube and TikTok are export-only, and offering
# them as publish targets would be offering something that cannot happen.
PLATFORM_FOR: dict[str, Platform | None] = {
    "youtube": None,
    "youtube_shorts": None,
    "tiktok": None,
    "instagram_reels": Platform.instagram,
    "instagram_post": Platform.instagram,
    "facebook": Platform.facebook,
    "facebook_reels": Platform.facebook,
    # A custom canvas is not aimed anywhere in particular, so the user chooses.
    "custom": None,
}

# Platforms whose adapter can currently upload a *video*. Empty, and that is
# the honest state of the code rather than an oversight — see the module
# docstring. A platform added here without the adapter work would produce
# drafts that fail at publish time.
VIDEO_UPLOAD_SUPPORTED: frozenset[Platform] = frozenset()

EXPORT_ONLY_NOTE = (
    "Download the MP4 and upload it in the app — AutoSocial has no publishing "
    "connection for this platform."
)
NO_VIDEO_ADAPTER_NOTE = (
    "The draft is ready with its caption and the video attached, but the last "
    "step is manual: this platform's connection can post text and images, not "
    "video."
)


def _connected(db: Session, user_id: int) -> dict[str, SocialAccount]:
    rows = db.scalars(
        select(SocialAccount).where(SocialAccount.user_id == user_id)
    ).all()
    return {row.platform: row for row in rows}


def targets(db: Session, *, user_id: int, project: VideoProject) -> list[dict]:
    """Where this video could go, and what stands in the way of each.

    Returns every platform the app knows, not only the reachable ones. A user
    whose Instagram is disconnected needs to see Instagram with "connect it
    first" — hiding it makes the feature look like it does not support
    Instagram at all.
    """
    accounts = _connected(db, user_id)
    suggested = PLATFORM_FOR.get(project.platform)

    out = []
    for platform in Platform:
        account = accounts.get(platform.value)
        supported = platform in VIDEO_UPLOAD_SUPPORTED

        if account is None:
            reason = f"Connect {platform.value.capitalize()} in Social Accounts first."
        elif not supported:
            reason = NO_VIDEO_ADAPTER_NOTE
        else:
            reason = None

        out.append(
            {
                "platform": platform.value,
                "label": platform.value.capitalize(),
                "connected": account is not None,
                "video_upload_supported": supported,
                "reason": reason,
                # The one this project's canvas was made for, so the UI can
                # preselect it rather than making the user work it out.
                "suggested": suggested is not None and platform is suggested,
            }
        )

    return out


def export_only_platforms(project: VideoProject) -> list[str]:
    """Surfaces this video is sized for that the app cannot publish to.

    Reported alongside the targets so a Shorts project says plainly that
    YouTube is a download, rather than showing six platforms none of which is
    the one it was made for.
    """
    if PLATFORM_FOR.get(project.platform) is None and project.platform != "custom":
        return [project.platform]
    return []


def default_caption(project: VideoProject) -> tuple[str, list[str]]:
    """A caption and hashtags drawn from whatever the project already knows.

    An AI project has a script with a hook and a CTA, which is a far better
    starting caption than the project's name; a hand-built one has only a name.
    Either way the user edits it before anything is posted.
    """
    script = project.script or {}
    parts: list[str] = []

    for key in ("hook", "introduction"):
        value = str(script.get(key) or "").strip()
        if value:
            parts.append(value)
    cta = str(script.get("cta") or "").strip()
    if cta:
        parts.append(cta)

    caption = "\n\n".join(parts).strip() or (project.name or "").strip()

    hashtags = [
        f"#{str(word).strip().lstrip('#').replace(' ', '')}"
        for word in (script.get("keywords") or [])
        if str(word).strip()
    ][:5]

    return caption[:2000], hashtags


def prepare_post(
    db: Session,
    *,
    user_id: int,
    project: VideoProject,
    platform: Platform,
    caption: str | None = None,
    hashtags: list[str] | None = None,
    scheduled_time: datetime | None = None,
) -> Post:
    """Create a **draft** post carrying this project's finished video.

    Deliberately never `scheduled`, even when a time is given: the time is
    stored so the composer opens with it filled in, and the user presses
    Schedule. A function that could produce a `scheduled` row would be a
    function that can cause a publish without anybody confirming it.
    """
    render = exports.latest_completed_render(db, project.id)
    if render is None:
        raise PublishError("Render the video before publishing it.")

    asset = db.get(VideoAsset, render.output_asset_id)
    if asset is None or asset.user_id != user_id:
        raise PublishError("The rendered video is no longer available.")

    text, tags = default_caption(project)
    content = (caption if caption is not None else text).strip()
    if not content:
        raise PublishError("Write a caption before creating the post.")

    # The public, unguessable URL — the one a platform's servers can fetch with
    # none of our credentials. Same construction every other asset uses.
    video_url = f"{settings.backend_url}/api/storage/o/{asset.token}"

    post = Post(
        user_id=user_id,
        platform=platform.value,
        content=content[:63206],
        hashtags=list(hashtags if hashtags is not None else tags),
        status=PostStatus.draft.value,
        media=[video_url],
        scheduled_time=scheduled_time,
        content_type="video",
        topic=(project.name or "")[:300] or None,
        platform_options={
            "source": "video_studio",
            "video_project_id": project.id,
            "render_id": render.id,
            "aspect_ratio": project.aspect_ratio,
            "duration_seconds": render.duration_seconds,
        },
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    logger.info(
        "Prepared %s draft post %s from video project %s",
        platform.value, post.id, project.id,
    )
    return post
