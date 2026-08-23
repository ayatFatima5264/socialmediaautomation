"""Video Studio endpoints — presets, templates, projects and asset reads.

Thin wrappers over `app/services/video/*`. Every rule that matters lives in the
service layer, so a background renderer and a request obey the same one; these
functions translate typed domain errors into HTTP and nothing more.

**Authentication is required on everything except one route.**
`GET /api/storage/o/{token}` is public, deliberately and for the same reason
`GET /api/media/{token}` already is: Instagram, Facebook and Pinterest publish a
video by fetching a URL from *their* servers, carrying none of our credentials.
The unguessable token is the boundary there. Every other route takes the user
from the bearer token and scopes its query to them — there is no endpoint that
accepts a user id.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.video_asset import VideoAsset
from app.models.video_audio import VideoAudio
from app.models.video_project import PROJECT_TYPES, VideoProject
from app.models.video_scene import VideoScene
from app.models.video_subtitle import VideoSubtitle
from app.schemas.video import (
    AssetRead,
    ProjectCreate,
    ProjectDetail,
    ProjectList,
    ProjectRead,
    ProjectRename,
    ProjectUpdate,
    StudioCapabilities,
    TemplateCategory,
    TemplateDetail,
    TemplateLibrary,
    TemplateRead,
    TemplateSave,
)
from app.services.storage import get_storage
from app.services.storage.base import ObjectNotFound, StorageError
from app.services.storage.ranges import ranged_response
from app.services.video import assets as asset_service
from app.services.video import presets as preset_service
from app.services.video import projects as project_service
from app.services.video import templates as template_service
from app.services.video import versions as version_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video", tags=["video-studio"])

# The public object read lives outside /api/video: it is addressed by token, it
# takes no session, and grouping it with the authenticated routes would invite
# somebody to "tidy up" by adding a dependency to the whole router.
storage_router = APIRouter(prefix="/api/storage", tags=["video-studio"])


# ---------------------------------------------------------------------------
# Error translation
# ---------------------------------------------------------------------------


def _http(exc: Exception) -> HTTPException:
    """Map a service error onto a status code.

    `ProjectNotFound` and `AssetNotFound` are 404 rather than 403 on purpose:
    the service cannot tell "does not exist" from "belongs to someone else",
    because distinguishing them is what makes an id space enumerable.
    """
    if isinstance(exc, (project_service.ProjectNotFound, asset_service.AssetNotFound)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, project_service.RevisionConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, StorageError):
        return HTTPException(
            status_code=502,
            detail="The file store could not be reached. Try again in a moment.",
        )
    return HTTPException(status_code=422, detail=str(exc))


def _owned(db: Session, user: User, project_id: int) -> VideoProject:
    try:
        return project_service.get_project(db, user_id=user.id, project_id=project_id)
    except project_service.ProjectError as exc:
        raise _http(exc) from exc


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def _asset_url(asset: VideoAsset) -> str:
    """The durable address of an asset.

    Always our own URL, never the bucket's. A presigned R2 URL expires and a
    public one pins the row to whichever backend produced it; this one survives
    the bucket being rotated, going public, or moving vendor.
    """
    return f"{settings.backend_url}/api/storage/o/{asset.token}"


def _asset_read(asset: VideoAsset) -> AssetRead:
    """One asset, with the URL the client should use.

    Built field by field rather than through `model_validate`: `url` is derived
    and has no column behind it, so validating from the ORM row fails on a
    missing required field.
    """
    return AssetRead(
        id=asset.id,
        project_id=asset.project_id,
        kind=asset.kind,
        title=asset.title,
        filename=asset.filename,
        content_type=asset.content_type,
        size_bytes=asset.size_bytes,
        duration_seconds=asset.duration_seconds,
        width=asset.width,
        height=asset.height,
        url=_asset_url(asset),
        created_at=asset.created_at,
    )


def _child_counts(db: Session, project_ids: list[int]) -> dict[int, dict[str, int]]:
    """Scene / audio / subtitle counts for a page of projects, in three queries.

    Grouped rather than counted per project: the projects grid shows twenty
    cards, and a count per card per table is sixty round trips to render one
    screen.
    """
    counts: dict[int, dict[str, int]] = {
        pid: {"scene_count": 0, "audio_count": 0, "subtitle_count": 0}
        for pid in project_ids
    }
    if not project_ids:
        return counts

    for model, field in (
        (VideoScene, "scene_count"),
        (VideoAudio, "audio_count"),
        (VideoSubtitle, "subtitle_count"),
    ):
        rows = db.execute(
            select(model.project_id, func.count(model.id))
            .where(model.project_id.in_(project_ids))
            .group_by(model.project_id)
        ).all()
        for project_id, total in rows:
            counts[project_id][field] = int(total or 0)

    return counts


def _project_read(
    db: Session, project: VideoProject, counts: dict | None = None
) -> ProjectRead:
    data = ProjectRead.model_validate(project)
    if counts:
        data.scene_count = counts.get("scene_count", 0)
        data.audio_count = counts.get("audio_count", 0)
        data.subtitle_count = counts.get("subtitle_count", 0)
    if project.thumbnail_asset_id:
        thumbnail = db.get(VideoAsset, project.thumbnail_asset_id)
        if thumbnail is not None:
            data.thumbnail_url = _asset_url(thumbnail)
    return data


def _project_detail(db: Session, project: VideoProject) -> ProjectDetail:
    counts = _child_counts(db, [project.id])[project.id]
    base = _project_read(db, project, counts)
    return ProjectDetail(
        **base.model_dump(),
        script=project.script or {},
        timeline=project.timeline or {},
        brand=project.brand or {},
        export_settings=project.export_settings or {},
        notes=project.notes,
    )


# ---------------------------------------------------------------------------
# Presets and capabilities
# ---------------------------------------------------------------------------


@router.get("/capabilities", response_model=StudioCapabilities)
def capabilities(user: User = Depends(get_current_user)) -> StudioCapabilities:
    """What this deployment can do — read by the UI instead of assumed.

    `storage_is_persistent` is the one worth watching: it is False when the
    app has fallen back to keeping bytes in Postgres, which is a development
    configuration. The UI says so rather than letting someone build a video
    library on it.
    """
    from app.services.video.ffmpeg import FFmpegError, ffmpeg_path

    try:
        ffmpeg_path()
        ffmpeg_available = True
    except FFmpegError:
        ffmpeg_available = False

    try:
        backend = get_storage().name
    except StorageError:
        backend = "unavailable"

    from app.services.video import renderer as render_worker
    from app.services.video import timeline as timeline_service
    from app.services.video.subtitles import SUBTITLE_FONTS

    return StudioCapabilities(
        presets=preset_service.as_dicts(),
        aspect_ratios={k: list(v) for k, v in preset_service.ASPECT_RATIOS.items()},
        limits=preset_service.limits(),
        storage_backend=backend,
        storage_is_persistent=(backend == "r2"),
        ffmpeg_available=ffmpeg_available,
        project_types=list(PROJECT_TYPES),
        editor={
            "tracks": [dict(track) for track in timeline_service.TRACKS],
            "clip_kinds": {
                key: list(value)
                for key, value in timeline_service.TRACK_CLIP_KINDS.items()
            },
            "sequential_tracks": sorted(timeline_service.SEQUENTIAL_TRACKS),
            "text_animations": list(timeline_service.TEXT_ANIMATIONS),
            "text_positions": list(timeline_service.TEXT_POSITIONS),
            "text_alignments": list(timeline_service.TEXT_ALIGNMENTS),
            "fonts": list(SUBTITLE_FONTS),
            "fit_modes": list(timeline_service.FIT_MODES),
            "audio_roles": list(timeline_service.AUDIO_ROLES),
            "speed_range": [timeline_service.MIN_SPEED, timeline_service.MAX_SPEED],
            "min_clip_seconds": timeline_service.MIN_CLIP_SECONDS,
            # False when the server has no font installed, so the editor can
            # say so instead of letting somebody write a title that will not
            # export. See `compositor.font_available`.
            **render_worker.render_capabilities(),
        },
    )


def _template_read(row) -> TemplateRead:
    """One template, with the derived fields the card needs.

    Built on top of `model_validate` rather than instead of it: everything with
    a column behind it comes from the row, and only the three values computed
    from `definition` are set here.
    """
    definition = row.definition or {}
    scenes = definition.get("scenes") or []

    item = TemplateRead.model_validate(row)
    item.category_label = template_service.CATEGORY_LABELS.get(
        row.category, (row.category or "").replace("_", " ").title()
    )
    item.scene_count = len(scenes)
    item.estimated_seconds = round(
        sum(float(scene.get("duration_seconds") or 0) for scene in scenes), 1
    )
    item.preview = definition.get("preview") or {}
    return item


@router.get("/templates", response_model=TemplateLibrary)
def list_templates(
    category: str | None = None,
    platform: str | None = None,
    search: str | None = Query(default=None, max_length=200),
    owned_only: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TemplateLibrary:
    """The template library, with its category tabs.

    The categories come back alongside the templates rather than from a second
    endpoint: the tab row and the grid have to agree, and two requests is two
    chances for them to be rendered from different snapshots. The counts are of
    the *unfiltered* library, so filtering to "TikTok" does not zero out every
    other tab and strand the user there.
    """
    rows = template_service.list_templates(
        db,
        user_id=user.id,
        category=category,
        platform=platform,
        search=search,
        owned_only=owned_only,
    )
    return TemplateLibrary(
        templates=[_template_read(row) for row in rows],
        categories=[
            TemplateCategory(**entry)
            for entry in template_service.category_counts(db, user_id=user.id)
        ],
    )


@router.get("/templates/{key}", response_model=TemplateDetail)
def get_template(
    key: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TemplateDetail:
    """One template, opened for preview before it is used."""
    try:
        row = template_service.get_template(db, user_id=user.id, key=key)
    except template_service.TemplateError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    definition = row.definition or {}
    base = _template_read(row)
    return TemplateDetail(
        **base.model_dump(),
        scenes=definition.get("scenes") or [],
        subtitle_style=definition.get("subtitle_style") or {},
        layout=definition.get("layout") or {},
        export_settings=definition.get("export_settings") or {},
    )


@router.post("/templates", response_model=TemplateDetail, status_code=201)
def save_template(
    body: TemplateSave,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TemplateDetail:
    """Save a project's setup as a template of your own.

    Configuration only — the canvas, the caption style, the layout and the
    shape of the scenes. Never the script, never the media. See
    `templates.save_user_template` for why.
    """
    project = _owned(db, user, body.project_id)
    try:
        row = template_service.save_user_template(
            db,
            user_id=user.id,
            project=project,
            name=body.name,
            description=body.description,
            category=body.category,
            include_scenes=body.include_scenes,
        )
    except template_service.TemplateError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    definition = row.definition or {}
    base = _template_read(row)
    return TemplateDetail(
        **base.model_dump(),
        scenes=definition.get("scenes") or [],
        subtitle_style=definition.get("subtitle_style") or {},
        layout=definition.get("layout") or {},
        export_settings=definition.get("export_settings") or {},
    )


@router.delete("/templates/{key}", status_code=204)
def delete_template(
    key: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Delete one of your own templates. Built-in templates are refused.

    422 rather than 403 for a system template: it is not a permission the user
    could be granted, it is a thing that does not happen.
    """
    try:
        template_service.delete_user_template(db, user_id=user.id, key=key)
    except template_service.TemplateError as exc:
        message = str(exc)
        status = 404 if "does not exist" in message else 422
        raise HTTPException(status_code=status, detail=message) from exc
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


@router.get("/projects", response_model=ProjectList)
def list_projects(
    search: str | None = Query(default=None, max_length=200),
    platform: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectList:
    """A page of the signed-in user's projects. Never anybody else's."""
    rows = project_service.list_projects(
        db,
        user_id=user.id,
        search=search,
        platform=platform,
        status=status,
        limit=limit,
        offset=offset,
    )
    counts = _child_counts(db, [row.id for row in rows])
    return ProjectList(
        projects=[_project_read(db, row, counts.get(row.id)) for row in rows],
        total=project_service.count_projects(db, user_id=user.id),
        limit=limit,
        offset=offset,
    )


@router.post("/projects", response_model=ProjectDetail, status_code=201)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectDetail:
    template = None
    if body.template_key:
        try:
            template = template_service.get_template(
                db, user_id=user.id, key=body.template_key
            )
        except template_service.TemplateError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        project = project_service.create_project(
            db,
            user_id=user.id,
            name=body.name,
            description=body.description,
            project_type=body.project_type,
            platform=body.platform,
            aspect_ratio=body.aspect_ratio,
            width=body.width,
            height=body.height,
            fps=body.fps,
            template=template,
            apply_brand=body.apply_brand,
        )
    except project_service.ProjectError as exc:
        raise _http(exc) from exc

    return _project_detail(db, project)


@router.get("/projects/{project_id}", response_model=ProjectDetail)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectDetail:
    return _project_detail(db, _owned(db, user, project_id))


@router.patch("/projects/{project_id}", response_model=ProjectDetail)
def update_project(
    project_id: int,
    body: ProjectUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectDetail:
    """Save a project. A stale `expected_revision` comes back as 409.

    `exclude_unset` matters: the editor sends only what changed, and treating
    an absent field as an explicit null would blank the rest of the project on
    every keystroke.
    """
    project = _owned(db, user, project_id)
    patch = body.model_dump(exclude_unset=True, exclude={"expected_revision", "autosave"})

    try:
        # Written before the change, so the snapshot is of what is about to be
        # overwritten. The throttle inside decides whether it is worth keeping.
        version_service.snapshot(
            db,
            project=project,
            reason="autosave" if body.autosave else "manual",
            commit=False,
        )
        project_service.update_project(
            db,
            project=project,
            patch=patch,
            expected_revision=body.expected_revision,
            autosave=body.autosave,
        )
    except project_service.ProjectError as exc:
        db.rollback()
        raise _http(exc) from exc

    return _project_detail(db, project)


@router.post("/projects/{project_id}/rename", response_model=ProjectRead)
def rename_project(
    project_id: int,
    body: ProjectRename,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectRead:
    """Rename from the projects list, where no revision has been loaded."""
    project = _owned(db, user, project_id)
    try:
        project_service.rename_project(db, project=project, name=body.name)
    except project_service.ProjectError as exc:
        raise _http(exc) from exc
    return _project_read(db, project)


@router.post("/projects/{project_id}/duplicate", response_model=ProjectDetail, status_code=201)
def duplicate_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectDetail:
    project = _owned(db, user, project_id)
    copy = project_service.duplicate_project(db, project=project)
    return _project_detail(db, copy)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Delete a project. Its assets survive, detached and still in the library."""
    project = _owned(db, user, project_id)
    project_service.delete_project(db, project=project)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------


@router.get("/assets", response_model=list[AssetRead])
def list_assets(
    kind: str | None = None,
    project_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AssetRead]:
    rows = asset_service.user_assets(
        db, user_id=user.id, kind=kind, project_id=project_id, limit=limit
    )
    return [_asset_read(row) for row in rows]


@router.delete("/assets/{asset_id}", status_code=204)
def delete_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    try:
        asset = asset_service.get_asset(db, user_id=user.id, asset_id=asset_id)
    except asset_service.AssetError as exc:
        raise _http(exc) from exc
    asset_service.delete_asset(db, asset)
    return Response(status_code=204)


@storage_router.get("/o/{token}")
def read_object(token: str, request: Request, db: Session = Depends(get_db)):
    """Serve an asset by its unguessable token. PUBLIC — no session.

    Two paths, decided by the backend rather than by the caller:

      * R2 — redirect to a URL the bucket serves, so tens of megabytes of video
        never pass through this process. The redirect also hands range requests
        and resumable downloads to R2, which does them properly.
      * database (development) — serve the bytes here, honouring Range.

    **Range support is not optional for media.** A browser opens an audio or
    video file with `Range: bytes=0-` and seeks by asking for byte ranges; a
    route that answers every one of those with a plain 200 leaves Chrome's
    media pipeline stalled at `HAVE_NOTHING` and the file never plays. See
    app/services/storage/ranges.py.
    """
    try:
        asset = asset_service.get_asset_by_token(db, token)
    except asset_service.AssetError as exc:
        raise HTTPException(status_code=404, detail="File not found.") from exc

    storage = get_storage()

    if storage.name == "database":
        try:
            data, content_type = asset_service.read_asset(asset)
        except asset_service.AssetError as exc:
            raise HTTPException(status_code=404, detail="File not found.") from exc
        return ranged_response(
            data,
            content_type=content_type,
            range_header=request.headers.get("range"),
            filename=asset.filename,
        )

    try:
        url = storage.url_for(asset.storage_key)
    except ObjectNotFound as exc:
        raise HTTPException(status_code=404, detail="File not found.") from exc
    except StorageError as exc:
        logger.exception("Could not resolve a URL for asset %s", asset.id)
        raise HTTPException(
            status_code=502, detail="The file store could not be reached."
        ) from exc

    # 307, not 301: a presigned URL expires, and a permanent redirect would be
    # cached by the browser long after the signature stopped working.
    return RedirectResponse(url, status_code=307)
