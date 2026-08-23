"""Export, format conversion and the publishing hand-off.

    GET  /api/video/projects/{id}/exports            what can be downloaded
    GET  /api/video/projects/{id}/exports/{kind}     the file itself
    GET  /api/video/projects/{id}/formats            what it can be converted to
    POST /api/video/projects/{id}/convert            -> a NEW project
    GET  /api/video/projects/{id}/publish/targets    where it could go
    POST /api/video/projects/{id}/publish            -> a DRAFT post

**Converting creates; it never modifies.** The source project's timeline, name
and revision are untouched — the new format is a new project, which is what
lets somebody keep the 16:9 cut and the 9:16 cut side by side.

**Publishing prepares; it never posts.** `POST /publish` produces a draft
`Post` and nothing else. The scheduler only picks up `scheduled` rows, and
nothing in this router can create one — so "no automatic publishing" is a
property of the code rather than a promise in a docstring.

Downloads are authenticated and `no-store`: these are somebody's files, not
URLs a platform fetches. The public, token-addressed route for that is
`GET /api/storage/o/{token}`.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.video_project import VideoProject
from app.schemas.post import Platform
from app.schemas.video_exports import (
    ConvertRequest,
    ConvertResult,
    ExportItem,
    ExportManifest,
    FormatOption,
    FormatOptions,
    PreparedPost,
    PublishRequest,
    PublishTarget,
    PublishTargets,
)
from app.services.video import exports as export_service
from app.services.video import formats as format_service
from app.services.video import metering
from app.services.video import projects as project_service
from app.services.video import publishing as publish_service
from app.services.video import timeline as tl

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video", tags=["video-export"])


def _owned(db: Session, user: User, project_id: int) -> VideoProject:
    try:
        return project_service.get_project(db, user_id=user.id, project_id=project_id)
    except project_service.ProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/exports", response_model=ExportManifest)
def manifest(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExportManifest:
    """Every deliverable, with whether it is ready and what to do if not.

    Cheap: it reads three rows and produces no files. The reasons are the next
    action to take, so a download screen never shows a button that fails.
    """
    project = _owned(db, user, project_id)
    render = export_service.latest_completed_render(db, project.id)

    return ExportManifest(
        project_id=project.id,
        project_name=project.name,
        platform=project.platform,
        aspect_ratio=project.aspect_ratio,
        width=project.width,
        height=project.height,
        fps=project.fps,
        duration_seconds=tl.duration(tl.normalize(project.timeline)),
        render_id=render.id if render else None,
        items=[ExportItem(**entry) for entry in export_service.manifest(db, project)],
    )


@router.get("/projects/{project_id}/exports/{kind}")
def download(
    project_id: int,
    kind: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """One export, as a download.

    422 with the manifest's own sentence when the project is not ready for that
    kind — so the message the user sees is the same one the button explained.
    """
    project = _owned(db, user, project_id)

    try:
        data, content_type, filename = export_service.produce(
            db, project=project, kind=kind
        )
    except export_service.ExportUnavailable as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except export_service.ExportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Counted as one export handed over. The `exports` metric existed from the
    # start and nothing wrote to it — a plan that priced deliverables would
    # have had no history to price from.
    metering.record(
        db,
        user_id=user.id,
        metric="exports",
        quantity=1,
        source="export",
        project_id=project.id,
        meta={"kind": kind, "bytes": len(data)},
    )

    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(data)),
            # Somebody's own file, behind their session — nothing in front of
            # the API may cache it.
            "Cache-Control": "private, max-age=0, no-store",
        },
    )


# ---------------------------------------------------------------------------
# Formats
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/formats", response_model=FormatOptions)
def formats(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FormatOptions:
    """The platforms this project can be converted to."""
    project = _owned(db, user, project_id)
    duration = project_service.project_duration(db, project)

    options = []
    for entry in format_service.targets_for(project):
        fits = duration <= entry["max_seconds"]
        options.append(
            FormatOption(
                **entry,
                fits=fits,
                reason=None
                if fits
                else (
                    f"This project is {duration / 60:.1f} minutes; "
                    f"{entry['label']} allows "
                    f"{max(1, entry['max_seconds'] // 60)}."
                ),
            )
        )

    return FormatOptions(
        project_id=project.id,
        current=project.platform,
        duration_seconds=round(duration, 2),
        formats=options,
    )


@router.post("/projects/{project_id}/convert", response_model=ConvertResult, status_code=201)
def convert(
    project_id: int,
    body: ConvertRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConvertResult:
    """Create a new project in another format. The original is untouched.

    A conversion reframes — every visual clip fills the new canvas and text is
    rescaled to it — but it does not re-cut: the timings are the edit, and the
    edit did not change.
    """
    project = _owned(db, user, project_id)

    try:
        copy = format_service.convert_project(
            db,
            user_id=user.id,
            project=project,
            target=body.target,
            name=body.name,
            copy_scenes=body.copy_scenes,
            copy_subtitles=body.copy_subtitles,
        )
    except format_service.FormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except project_service.ProjectError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return ConvertResult(
        project_id=copy.id,
        name=copy.name,
        platform=copy.platform,
        aspect_ratio=copy.aspect_ratio,
        width=copy.width,
        height=copy.height,
        source_project_id=project.id,
        editor_path=f"/video/projects/{copy.id}/edit",
    )


# ---------------------------------------------------------------------------
# Publishing
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/publish/targets", response_model=PublishTargets)
def publish_targets(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PublishTargets:
    """Where this video could go, and what stands in the way of each.

    Reports two separate things per platform — whether an account is connected,
    and whether that platform's adapter can upload video — because they are
    fixed in different places and conflating them tells the user the wrong
    thing to do.
    """
    project = _owned(db, user, project_id)
    render = export_service.latest_completed_render(db, project.id)

    return PublishTargets(
        project_id=project.id,
        ready=render is not None,
        reason=None if render else "Render the video before publishing it.",
        targets=[
            PublishTarget(**entry)
            for entry in publish_service.targets(db, user_id=user.id, project=project)
        ],
        export_only=publish_service.export_only_platforms(project),
        export_only_note=publish_service.EXPORT_ONLY_NOTE,
    )


@router.post("/projects/{project_id}/publish", response_model=PreparedPost, status_code=201)
def prepare(
    project_id: int,
    body: PublishRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PreparedPost:
    """Create a **draft** post carrying this video. It is not published.

    The draft opens in the composer, where the user edits the caption and
    presses Schedule or Publish. Nothing in this router can reach a platform.
    """
    project = _owned(db, user, project_id)

    try:
        platform = Platform(body.platform)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"{body.platform} is not a platform this can post to."
        ) from exc

    try:
        post = publish_service.prepare_post(
            db,
            user_id=user.id,
            project=project,
            platform=platform,
            caption=body.caption,
            hashtags=body.hashtags,
            scheduled_time=body.scheduled_time,
        )
    except publish_service.PublishError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return PreparedPost(
        post_id=post.id,
        platform=post.platform,
        status=post.status,
        content=post.content,
        hashtags=list(post.hashtags or []),
        media=list(post.media or []),
        scheduled_time=post.scheduled_time,
        # Where to go to confirm it. The hand-off ends in the composer, which
        # is where publishing decisions are made in this app.
        review_path=f"/posts/{post.id}",
    )
