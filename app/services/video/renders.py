"""Render job lifecycle — the state machine, without the rendering.

This module owns every transition a `VideoRender` row can make. The thing that
actually encodes video is not here and does not exist yet; what exists is the
contract it will be driven through, because that contract is also what the API
polls and what the projects list reads.

Keeping the two apart is deliberate. A renderer is a subprocess, a temp
directory and a filter graph — none of which can be unit-tested quickly. A
state machine is pure bookkeeping over one row, and it is where the rules that
actually matter live:

  * **A job only moves forward.** queued → processing → completed | failed |
    cancelled. Nothing re-opens a terminal job; a retry is a new row with
    `attempt + 1`, so what was tried survives.
  * **Progress only increases, and only when something happened.** `progress`
    is clamped and never allowed to go backwards. Nothing here sets it on a
    timer — the caller passes a fraction it measured.
  * **A failure explains itself.** Status, a machine-readable code, the stage
    it died in, and the full error text. "Render failed" on its own is
    unsupportable.
  * **The project mirrors the newest job, and is never damaged by it.** A
    failed render leaves the project's documents untouched and its status
    `failed`; the next successful one clears it.
"""
from __future__ import annotations

import logging
from copy import deepcopy

from sqlalchemy import func, select
from sqlalchemy.orm import Session

# Aliased: `queue_render` takes a `settings` argument (the export options),
# and an unaliased import would be shadowed inside it.
from app.config import settings as app_settings
from app.core.timeutils import utcnow
from app.models.video_project import VideoProject
from app.models.video_render import (
    RENDER_ERROR_CODES,
    RENDER_STAGES,
    RENDER_STATUSES,
    TERMINAL_RENDER_STATUSES,
    VideoRender,
)
from app.services.video import metering, projects as project_service

logger = logging.getLogger(__name__)


class RenderError(RuntimeError):
    """A render operation was refused. The message is user-facing."""


class RenderNotFound(RenderError):
    """No such render job — or it belongs to somebody else."""


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def get_render(db: Session, *, user_id: int, render_id: int) -> VideoRender:
    """One job, scoped to its owner. Same rule as projects: the ownership
    check is part of the query, not a separate `if` afterwards."""
    render = db.scalars(
        select(VideoRender).where(
            VideoRender.id == render_id, VideoRender.user_id == user_id
        )
    ).first()
    if render is None:
        raise RenderNotFound("That render does not exist.")
    return render


def list_renders(
    db: Session,
    *,
    user_id: int,
    project_id: int | None = None,
    limit: int = 20,
) -> list[VideoRender]:
    """A user's render attempts, newest first."""
    query = select(VideoRender).where(VideoRender.user_id == user_id)
    if project_id is not None:
        query = query.where(VideoRender.project_id == project_id)
    query = query.order_by(VideoRender.created_at.desc()).limit(min(max(1, limit), 100))
    return list(db.scalars(query).all())


def latest_render(db: Session, *, user_id: int, project_id: int) -> VideoRender | None:
    jobs = list_renders(db, user_id=user_id, project_id=project_id, limit=1)
    return jobs[0] if jobs else None


def active_render_count(db: Session) -> int:
    """How many jobs are running right now, across every user.

    Global rather than per-user because the limit it feeds
    (`VIDEO_MAX_CONCURRENT_RENDERS`) is about one shared CPU, not about
    fairness between accounts.
    """
    return int(
        db.scalar(
            select(func.count(VideoRender.id)).where(VideoRender.status == "processing")
        )
        or 0
    )


def slot_available(db: Session) -> bool:
    """Whether another render may start right now.

    The cap exists because rendering shares one small CPU with every other
    request in the process — a second concurrent ffmpeg does not make two
    videos faster, it makes every API call slower and both videos late.
    """
    return active_render_count(db) < app_settings.video_max_concurrent_renders


def next_queued(db: Session) -> VideoRender | None:
    """The oldest job waiting for a slot.

    Oldest first, so a queue is a queue. This is what the worker calls when it
    finishes: a job that had to wait is picked up by the chain rather than
    sitting `queued` until somebody presses Export again.
    """
    return db.scalars(
        select(VideoRender)
        .where(VideoRender.status == "queued")
        .order_by(VideoRender.created_at, VideoRender.id)
    ).first()


# ---------------------------------------------------------------------------
# Creating
# ---------------------------------------------------------------------------


def queue_render(
    db: Session,
    *,
    project: VideoProject,
    settings: dict | None = None,
    commit: bool = True,
) -> VideoRender:
    """Create a queued job for a project, or refuse with a reason.

    The timeline is snapshotted here, not when a worker picks the job up.
    Editing the project while it renders must not change what is being
    encoded, and a retry must reproduce the same file.
    """
    refusal = project_service.render_refusal(db, project)
    if refusal:
        raise RenderError(refusal)

    if unfinished_render(db, project_id=project.id) is not None:
        raise RenderError(
            "This project is already being rendered. Wait for that export to "
            "finish, or cancel it first."
        )

    previous = int(
        db.scalar(
            select(func.count(VideoRender.id)).where(
                VideoRender.project_id == project.id
            )
        )
        or 0
    )

    render = VideoRender(
        user_id=project.user_id,
        project_id=project.id,
        status="queued",
        stage="queued",
        progress=0.0,
        # The project's export settings are the default; whatever the export
        # dialog sent wins. Frozen either way — a re-read of a finished render
        # reports what it was made with.
        settings={**(project.export_settings or {}), **(settings or {})},
        timeline_snapshot=deepcopy(project.timeline or {}),
        attempt=previous + 1,
    )
    db.add(render)

    project_service.set_status(db, project=project, status="processing", commit=False)

    if commit:
        db.commit()
        db.refresh(render)
    return render


def unfinished_render(db: Session, *, project_id: int) -> VideoRender | None:
    """The job for this project that has not finished, if there is one."""
    return db.scalars(
        select(VideoRender)
        .where(
            VideoRender.project_id == project_id,
            VideoRender.status.notin_(TERMINAL_RENDER_STATUSES),
        )
        .order_by(VideoRender.created_at.desc())
    ).first()


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------


def start(db: Session, *, render: VideoRender, commit: bool = True) -> VideoRender:
    """Mark a queued job as running. Called by the worker when it claims it."""
    if render.status != "queued":
        raise RenderError(f"A {render.status} render cannot be started.")

    render.status = "processing"
    render.stage = "preparing"
    render.progress = 0.0
    render.started_at = utcnow()
    if commit:
        db.commit()
    return render


def report_progress(
    db: Session,
    *,
    render: VideoRender,
    stage: str | None = None,
    progress: float | None = None,
    commit: bool = True,
) -> VideoRender:
    """Record real forward movement.

    Progress is clamped to 0–1 and never allowed to decrease. A renderer that
    restarts a pass would otherwise make the bar jump backwards, which reads as
    a bug even when the render is fine.

    A job that has already finished is left alone rather than raising: a late
    progress report from a subprocess that was cancelled is a race, not an
    error, and failing the worker over it would be worse than ignoring it.
    """
    if render.is_terminal:
        logger.debug("Ignoring progress on a %s render %s", render.status, render.id)
        return render

    if stage:
        if stage not in RENDER_STAGES:
            raise RenderError(f"Unknown render stage {stage!r}.")
        render.stage = stage

    if progress is not None:
        clamped = max(0.0, min(1.0, float(progress)))
        render.progress = max(render.progress, clamped)

    if commit:
        db.commit()
    return render


def complete(
    db: Session,
    *,
    render: VideoRender,
    output_asset_id: int | None = None,
    thumbnail_asset_id: int | None = None,
    duration_seconds: float | None = None,
    commit: bool = True,
) -> VideoRender:
    """Mark a job finished and hand its output to the project.

    `thumbnail_asset_id` is the poster frame the worker extracted, kept separate
    from `output_asset_id` on purpose. The two used to be the same field — the
    MP4 was assigned to `project.thumbnail_asset_id` — and that made the project
    carry a "thumbnail" that was a video, so every PNG/JPG export failed when it
    tried to decode it. A thumbnail is an image or it is not a thumbnail.
    """
    if render.is_terminal:
        raise RenderError(f"This render is already {render.status}.")

    render.status = "completed"
    render.stage = "done"
    render.progress = 1.0
    render.output_asset_id = output_asset_id
    render.duration_seconds = duration_seconds
    render.finished_at = utcnow()

    project = db.get(VideoProject, render.project_id)
    if project is not None:
        project.status = "completed"
        # The render's poster frame becomes the project's thumbnail, unless the
        # user picked one — which is a decision we must not overwrite.
        if project.thumbnail_asset_id is None and thumbnail_asset_id is not None:
            project.thumbnail_asset_id = thumbnail_asset_id

    if duration_seconds:
        metering.record(
            db,
            user_id=render.user_id,
            metric="render_seconds",
            quantity=duration_seconds,
            source="render",
            project_id=render.project_id,
            meta={"render_id": render.id, "attempt": render.attempt},
            commit=False,
        )

    if commit:
        db.commit()
        db.refresh(render)
    return render


def fail(
    db: Session,
    *,
    render: VideoRender,
    error: str,
    error_code: str = "unknown",
    commit: bool = True,
) -> VideoRender:
    """Record a failure, in full, without touching the project's content.

    `stage` is left where it was: the user needs to see how far it got, and
    rewinding it to some "failed" pseudo-stage throws that away.
    """
    if render.is_terminal:
        raise RenderError(f"This render is already {render.status}.")

    render.status = "failed"
    render.error = (error or "The render failed for an unknown reason.")[:20000]
    render.error_code = error_code if error_code in RENDER_ERROR_CODES else "unknown"
    render.error_stage = render.stage
    render.finished_at = utcnow()

    project = db.get(VideoProject, render.project_id)
    if project is not None:
        project.status = "failed"

    logger.warning(
        "Render %s failed at stage %s (%s): %s",
        render.id, render.error_stage, render.error_code, render.error[:200],
    )

    if commit:
        db.commit()
        db.refresh(render)
    return render


def cancel(db: Session, *, render: VideoRender, commit: bool = True) -> VideoRender:
    """Stop a job the user no longer wants.

    The project goes back to `draft`, not `cancelled`: a project is never in a
    cancelled condition — one attempt at exporting it was. Stopping the actual
    subprocess is the worker's job; it sees this row and terminates.
    """
    if render.is_terminal:
        raise RenderError(f"This render has already {render.status}.")

    render.status = "cancelled"
    render.error_code = "cancelled"
    render.error_stage = render.stage
    render.finished_at = utcnow()

    project = db.get(VideoProject, render.project_id)
    if project is not None:
        project.status = "draft"

    if commit:
        db.commit()
        db.refresh(render)
    return render


def recover_interrupted(db: Session, *, commit: bool = True) -> int:
    """Fail every job left `processing` by a process that died. Returns how many.

    Called on startup. A render running when the container was replaced — a
    deploy, an out-of-memory kill, a restart — has no worker any more and
    nothing will ever move it. Without this the project sits at 40% forever and
    cannot be re-rendered, because `queue_render` refuses while one is
    unfinished.

    Safe to run on every boot precisely because the deployment is single
    instance: there is no other worker whose live job this could steal. That
    assumption is written down in the Dockerfile and render.yaml too, and this
    function is one of the places it would have to change first.
    """
    stale = list(
        db.scalars(
            select(VideoRender).where(VideoRender.status.in_(("queued", "processing")))
        ).all()
    )
    for render in stale:
        render.status = "failed"
        render.error = (
            "The render was interrupted by a server restart. Nothing was lost "
            "— open the project and export again."
        )
        render.error_code = "interrupted"
        render.error_stage = render.stage
        render.finished_at = utcnow()

        project = db.get(VideoProject, render.project_id)
        if project is not None and project.status == "processing":
            project.status = "draft"

    if stale and commit:
        db.commit()
    if stale:
        logger.info("Recovered %d interrupted render job(s) on startup", len(stale))
    return len(stale)


def as_dict(render: VideoRender) -> dict:
    """The job, shaped for the polling endpoint.

    A plain function rather than a Pydantic schema because the worker logs it
    too, and the two must not be able to disagree about what a job looks like.
    """
    return {
        "id": render.id,
        "project_id": render.project_id,
        "status": render.status,
        "stage": render.stage,
        "progress": round(render.progress, 4),
        "attempt": render.attempt,
        "settings": render.settings or {},
        "output_asset_id": render.output_asset_id,
        "duration_seconds": render.duration_seconds,
        "error": render.error,
        "error_code": render.error_code,
        "error_stage": render.error_stage,
        "started_at": render.started_at.isoformat() if render.started_at else None,
        "finished_at": render.finished_at.isoformat() if render.finished_at else None,
        "created_at": render.created_at.isoformat() if render.created_at else None,
    }


__all__ = [
    "RenderError",
    "RenderNotFound",
    "RENDER_STATUSES",
    "RENDER_STAGES",
    "get_render",
    "list_renders",
    "latest_render",
    "active_render_count",
    "slot_available",
    "next_queued",
    "queue_render",
    "unfinished_render",
    "start",
    "report_progress",
    "complete",
    "fail",
    "cancel",
    "recover_interrupted",
    "as_dict",
]
