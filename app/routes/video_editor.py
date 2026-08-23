"""Timeline editor and render endpoints.

    GET    /api/video/projects/{id}/timeline        the document, normalized
    PUT    /api/video/projects/{id}/timeline        replace it (autosave/undo)
    POST   /api/video/projects/{id}/timeline/op     one edit, applied server-side
    POST   /api/video/projects/{id}/render          queue an export
    GET    /api/video/projects/{id}/renders         this project's attempts
    GET    /api/video/renders/{id}                  poll one
    POST   /api/video/renders/{id}/cancel
    POST   /api/video/renders/{id}/retry

**Edits are applied by the server.** `/timeline/op` takes an operation and
returns the whole new document. The editor does not compute the result of a
trim and tell us what it decided — there is one implementation of the rules
(`services/video/timeline.py`), it is the one the renderer reads, and that is
the entire reason the preview and the export cannot drift apart.

**Saving is a compare-and-set.** `expected_revision` makes a save fail with 409
if the project moved underneath it, which is what stops a second tab's autosave
silently reverting the tab you are working in.

**Rendering runs in the background and reports through its row.** The response
to POST /render is a job id; everything after that is polling. The worker is
started as a FastAPI background task here, and the same function would be a
queue consumer on another machine without the client noticing — see the note
on `VideoRender`.
"""
from __future__ import annotations

import logging

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Response,
)
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user
from app.database import SessionLocal, get_db
from app.models.user import User
from app.models.video_asset import VideoAsset
from app.models.video_project import VideoProject
from app.models.video_render import VideoRender
from app.schemas.video_editor import (
    RenderList,
    RenderRead,
    RenderRequest,
    TimelineOperation,
    TimelineOperationResult,
    TimelineRead,
    TimelineSave,
    TimelineSummary,
)
from app.services.video import assets as asset_service
from app.services.video import compositor
from app.services.video import projects as project_service
from app.services.video import renderer as render_worker
from app.services.video import renders as render_service
from app.services.video import timeline as tl
from app.services.video import versions as version_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video", tags=["video-editor"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _owned(db: Session, user: User, project_id: int) -> VideoProject:
    try:
        return project_service.get_project(db, user_id=user.id, project_id=project_id)
    except project_service.ProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _asset_url(asset: VideoAsset) -> str:
    return f"{settings.backend_url}/api/storage/o/{asset.token}"


def _timeline_assets(db: Session, *, user_id: int, document: dict) -> list[dict]:
    """The assets this timeline references, with playable URLs.

    Sent with the document so the preview can load its media immediately. A
    clip whose asset has been deleted is simply absent from this list — the
    clip keeps its place on the timeline and the editor draws it as missing,
    which is recoverable, where dropping the clip would not be.
    """
    ids = tl.asset_ids(document)
    if not ids:
        return []

    out = []
    for asset_id in ids:
        try:
            asset = asset_service.get_asset(db, user_id=user_id, asset_id=asset_id)
        except asset_service.AssetError:
            continue
        out.append(
            {
                "id": asset.id,
                "kind": asset.kind,
                "title": asset.title,
                "content_type": asset.content_type,
                "url": _asset_url(asset),
                "duration_seconds": asset.duration_seconds,
                "width": asset.width,
                "height": asset.height,
            }
        )
    return out


def _placements(project: VideoProject, document: dict, assets: list[dict]) -> dict:
    """Where every visual clip lands on the canvas, in pixels.

    Computed with `compositor.place` — **the renderer's own function**, not a
    reimplementation. This is what makes the preview honest: the browser does
    not do its own crop-and-fit arithmetic and hope it agrees with the export,
    it draws the numbers the encoder will use.

    Keyed by clip id and sent with the document, because the geometry only
    changes when a clip changes — recomputing it per frame in the browser is
    both wasteful and the very place a second implementation would appear.
    """
    by_id = {asset["id"]: asset for asset in assets}
    out: dict[str, dict] = {}

    for clip in tl.get_track(document, "video")["clips"]:
        asset = by_id.get(clip["asset_id"])
        if asset is None:
            continue
        source = compositor.Source(
            path="",
            width=asset.get("width"),
            height=asset.get("height"),
            duration=asset.get("duration_seconds") or 0.0,
            has_video=True,
        )
        placement = compositor.place(
            clip, source, canvas_w=project.width, canvas_h=project.height
        )
        out[clip["id"]] = {
            "crop_x": placement.crop_x,
            "crop_y": placement.crop_y,
            "crop_w": placement.crop_w,
            "crop_h": placement.crop_h,
            "width": placement.scaled_w,
            "height": placement.scaled_h,
            "x": placement.pos_x,
            "y": placement.pos_y,
            "source_width": source.width,
            "source_height": source.height,
        }

    return out


def _read(db: Session, project: VideoProject, document: dict) -> dict:
    """The payload every timeline endpoint returns."""
    assets = _timeline_assets(db, user_id=project.user_id, document=document)
    return {
        "project_id": project.id,
        "revision": project.revision,
        "timeline": document,
        "summary": TimelineSummary(**tl.summary(document)),
        "width": project.width,
        "height": project.height,
        "fps": project.fps,
        "aspect_ratio": project.aspect_ratio,
        "assets": assets,
        "placements": _placements(project, document, assets),
    }


def _save(
    db: Session,
    *,
    project: VideoProject,
    document: dict,
    expected_revision: int | None,
    autosave: bool,
) -> None:
    """Write a timeline through the project service, with a version snapshot.

    The snapshot is taken *before* the change, so what it holds is the state
    about to be overwritten — which is what makes version history useful after
    an edit somebody regrets. The throttle inside decides whether a run of
    autosaves is worth more than one snapshot.
    """
    try:
        version_service.snapshot(
            db,
            project=project,
            reason="autosave" if autosave else "manual",
            commit=False,
        )
        project_service.update_project(
            db,
            project=project,
            patch={"timeline": document},
            expected_revision=expected_revision,
            autosave=autosave,
        )
    except project_service.RevisionConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except project_service.ProjectError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# The timeline
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/timeline", response_model=TimelineRead)
def get_timeline(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TimelineRead:
    """The project's timeline, normalized.

    Normalization happens on read as well as write, so a project last saved by
    an older build — or with the four-track v1 layout — opens in the editor
    already repaired rather than needing a migration pass.
    """
    project = _owned(db, user, project_id)
    document = tl.normalize(project.timeline)
    return TimelineRead(**_read(db, project, document))


@router.put("/projects/{project_id}/timeline", response_model=TimelineRead)
def save_timeline(
    project_id: int,
    body: TimelineSave,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TimelineRead:
    """Replace the timeline wholesale — autosave, undo and redo.

    The incoming document is normalized before it is stored, so an undo to a
    state written by an older build still lands as a valid document, and a
    hand-made request cannot put something the renderer chokes on into the
    database.
    """
    project = _owned(db, user, project_id)
    document = tl.normalize(body.timeline)

    _save(
        db,
        project=project,
        document=document,
        expected_revision=body.expected_revision,
        autosave=body.autosave,
    )
    return TimelineRead(**_read(db, project, document))


@router.post(
    "/projects/{project_id}/timeline/op", response_model=TimelineOperationResult
)
def apply_operation(
    project_id: int,
    body: TimelineOperation,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TimelineOperationResult:
    """Apply one edit and return the new document.

    Every operation goes through the same pure functions the renderer's
    normalization uses. A refused edit — an overlap, a split at the very edge,
    a locked clip — comes back as 422 with the reason, and the timeline is
    left exactly as it was.
    """
    project = _owned(db, user, project_id)
    document = tl.normalize(project.timeline)
    affected: list[str] = []

    try:
        if body.op == "add":
            if not body.track_id or body.clip is None:
                raise tl.TimelineError("Adding a clip needs a track and a clip.")
            document, added = tl.add_clip(
                document, track_id=body.track_id, clip=body.clip, at=body.at
            )
            affected = [added["id"]]

        elif body.op == "move":
            if not body.clip_id or body.start is None:
                raise tl.TimelineError("Moving a clip needs a clip and a position.")
            document = tl.move_clip(document, clip_id=body.clip_id, start=body.start)
            affected = [body.clip_id]

        elif body.op == "trim":
            if not body.clip_id or body.edge is None or body.to is None:
                raise tl.TimelineError("Trimming needs a clip, an edge and a point.")
            document = tl.trim_clip(
                document, clip_id=body.clip_id, edge=body.edge, to=body.to
            )
            affected = [body.clip_id]

        elif body.op == "split":
            if not body.clip_id or body.at is None:
                raise tl.TimelineError("Splitting needs a clip and a point.")
            document, affected = tl.split_clip(
                document, clip_id=body.clip_id, at=body.at
            )

        elif body.op == "delete":
            if not body.clip_id:
                raise tl.TimelineError("Deleting needs a clip.")
            document = tl.delete_clip(
                document, clip_id=body.clip_id, ripple=body.ripple
            )

        elif body.op == "reorder":
            if not body.track_id or not body.clip_ids:
                raise tl.TimelineError("Reordering needs a track and an order.")
            document = tl.reorder_clips(
                document, track_id=body.track_id, clip_ids=body.clip_ids
            )
            affected = list(body.clip_ids)

        elif body.op == "update":
            if not body.clip_id or body.patch is None:
                raise tl.TimelineError("Updating a clip needs a clip and changes.")
            document = tl.update_clip(
                document, clip_id=body.clip_id, patch=body.patch
            )
            affected = [body.clip_id]

    except tl.TimelineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Every operation is an explicit user edit, so it is saved as one — an
    # `autosave` snapshot would let a run of deliberate edits collapse into a
    # single point in version history.
    _save(
        db,
        project=project,
        document=document,
        expected_revision=body.expected_revision,
        autosave=False,
    )

    return TimelineOperationResult(
        **_read(db, project, document), affected_clip_ids=affected
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render_read(db: Session, render: VideoRender) -> RenderRead:
    from app.models.video_render import PHASE_LABELS, phase_of

    data = RenderRead.model_validate(render)
    data.phase = phase_of(render.status, render.stage)
    data.phase_label = PHASE_LABELS[data.phase]
    if render.output_asset_id:
        asset = db.get(VideoAsset, render.output_asset_id)
        if asset is not None:
            data.output_url = _asset_url(asset)
    return data


def run_render_job(render_id: int) -> None:
    """Execute a queued render on its own session.

    Its own session, deliberately: this runs after the response has been sent,
    and the request's session is closed by then. Opening one here is also what
    lets this exact function be a queue consumer in another process later,
    which is the direction `VideoRender` was designed for.

    Nothing is raised out of here. A background task that throws logs a
    traceback nobody sees; `execute` already records every failure on the row
    the client is polling, which is where a failure belongs.
    """
    with SessionLocal() as db:
        pending = render_id
        # Ids this chain has already taken a turn on. `execute` normally moves
        # a job out of `queued` immediately, but if it raises *before* that —
        # a failed `start()`, an unwritable temp directory — the row would
        # still be queued and `next_queued` would hand back the same one
        # forever. Remembering what has been attempted makes the loop
        # terminate whatever goes wrong.
        seen: set[int] = set()

        # A loop, not one job. When this finishes it picks up whatever was
        # waiting for the slot, so a queued job is actually a queue rather than
        # a row that sits there until somebody presses Export again. Bounded by
        # what is queued, and each pass re-reads the row.
        while pending is not None:
            if pending in seen:
                logger.error(
                    "Render %s did not leave the queue; stopping the chain", pending
                )
                return
            seen.add(pending)

            render = db.get(VideoRender, pending)
            if render is None:  # pragma: no cover
                logger.error("Render %s vanished before it could run", pending)
                return
            if render.status != "queued":
                # Already claimed by another chain, or cancelled while waiting.
                return

            if not render_service.slot_available(db):
                # Somebody else is encoding. Leave it queued — the chain that
                # is running will collect it when it finishes, which is what
                # makes the cap a queue instead of a refusal.
                logger.info(
                    "Render %s is waiting for a slot", render.id
                )
                return

            try:
                render_worker.execute(db, render)
            except Exception:  # noqa: BLE001 — see the docstring
                logger.exception("Render %s could not be executed", render.id)

            following = render_service.next_queued(db)
            pending = following.id if following is not None else None


@router.post("/projects/{project_id}/render", response_model=RenderRead, status_code=202)
def start_render(
    project_id: int,
    body: RenderRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RenderRead:
    """Queue an export. 202 — the work has not happened yet.

    The timeline is snapshotted into the job here, so editing the project while
    it exports cannot change what is being encoded.

    Refusals arrive immediately and with a reason (nothing on the timeline, too
    long, already rendering) rather than as a failed job minutes later.
    """
    project = _owned(db, user, project_id)

    options = {}
    if body.quality:
        options["quality"] = body.quality

    try:
        render = render_service.queue_render(db, project=project, settings=options)
    except render_service.RenderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    background.add_task(run_render_job, render.id)
    return _render_read(db, render)


@router.get("/projects/{project_id}/renders", response_model=RenderList)
def list_renders(
    project_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RenderList:
    """Every export attempt for a project, newest first."""
    project = _owned(db, user, project_id)
    rows = render_service.list_renders(
        db, user_id=user.id, project_id=project.id, limit=limit
    )
    active = render_service.unfinished_render(db, project_id=project.id)
    return RenderList(
        renders=[_render_read(db, row) for row in rows],
        active=_render_read(db, active) if active is not None else None,
    )


@router.get("/renders/{render_id}", response_model=RenderRead)
def get_render(
    render_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RenderRead:
    """Poll one job. This is the whole progress API."""
    try:
        render = render_service.get_render(db, user_id=user.id, render_id=render_id)
    except render_service.RenderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _render_read(db, render)


@router.post("/renders/{render_id}/cancel", response_model=RenderRead)
def cancel_render(
    render_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RenderRead:
    """Stop a job. The worker notices the row and terminates the encoder."""
    try:
        render = render_service.get_render(db, user_id=user.id, render_id=render_id)
        render_service.cancel(db, render=render)
    except render_service.RenderNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except render_service.RenderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _render_read(db, render)


@router.post("/renders/{render_id}/retry", response_model=RenderRead, status_code=202)
def retry_render(
    render_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RenderRead:
    """Try a failed export again.

    A **new job**, not a reopened one: `attempt` increments and the previous
    failure survives, so "it failed twice with the same error" is a thing the
    user and the logs can both see.

    The new job snapshots the timeline as it is *now*, which is what makes
    "fix the missing clip, then retry" work.
    """
    try:
        previous = render_service.get_render(db, user_id=user.id, render_id=render_id)
    except render_service.RenderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not previous.is_terminal:
        raise HTTPException(
            status_code=422,
            detail="That export is still running. Wait for it, or cancel it first.",
        )

    project = _owned(db, user, previous.project_id)

    try:
        render = render_service.queue_render(
            db, project=project, settings=previous.settings or {}
        )
    except render_service.RenderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    background.add_task(run_render_job, render.id)
    return _render_read(db, render)


@router.get("/renders/{render_id}/download")
def download_render(
    render_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Download a finished export under a filename a human chose.

    Requires a session, unlike the public asset route: this is a download for
    the person who made it, not a URL a social platform fetches.
    """
    try:
        render = render_service.get_render(db, user_id=user.id, render_id=render_id)
    except render_service.RenderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if render.status != "completed" or not render.output_asset_id:
        raise HTTPException(status_code=422, detail="That export has not finished.")

    try:
        asset = asset_service.get_asset(
            db, user_id=user.id, asset_id=render.output_asset_id
        )
        data, content_type = asset_service.read_asset(asset)
    except asset_service.AssetError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{asset.filename or "video.mp4"}"',
            "Content-Length": str(len(data)),
            "Cache-Control": "private, max-age=0, no-store",
        },
    )
