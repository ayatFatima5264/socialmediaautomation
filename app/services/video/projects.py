"""Video project lifecycle: create, read, autosave, rename, duplicate, delete.

The rules that make a project trustworthy live here rather than in the route, so
that an autosave from the editor, a "save" from Voice Studio's Add to Project,
and a future background job all obey the same ones:

  * **Ownership is part of the lookup.** Every read takes a `user_id` and folds
    it into the WHERE clause. A project belonging to someone else is
    indistinguishable from one that does not exist, which is what stops the id
    space being enumerable. There is no "fetch then check" path, because that is
    the shape the check eventually gets forgotten in.
  * **A save never silently loses another save.** Every write bumps `revision`,
    and a client that sends the revision it loaded gets a conflict instead of
    overwriting a newer one. Two tabs on the same project is not an exotic case
    — it is what happens when a user opens a project from their phone.
  * **Duration is derived, never sent.** The client could claim any length; the
    render limit and the timeline layout both depend on the real one, so it is
    recomputed on every save.
  * **Deleting a project keeps its assets.** A voice-over the user also
    downloaded outlives the project it was attached to. Its scenes, audio
    layers, subtitle tracks and version history do not — those are parts of the
    project, not files the user owns.
"""
from __future__ import annotations

import logging
from copy import deepcopy

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.timeutils import utcnow
from app.models.video_asset import VideoAsset
from app.models.video_audio import VideoAudio
from app.models.video_project import (
    EMPTY_TIMELINE,
    PROJECT_STATUSES,
    PROJECT_TYPES,
    VideoProject,
)
from app.models.video_project_version import VideoProjectVersion
from app.models.video_scene import VideoScene
from app.models.video_subtitle import VideoSubtitle
from app.services.video import presets, subtitles as subtitle_engine

logger = logging.getLogger(__name__)


class ProjectError(RuntimeError):
    """A project operation was refused. The message is user-facing."""


class ProjectNotFound(ProjectError):
    """No such project — or it belongs to somebody else.

    Deliberately one exception for both. Telling the two apart would confirm
    that an id exists, which is exactly what an enumeration attack is looking
    for. The route maps this to 404.
    """


class RevisionConflict(ProjectError):
    """The project changed since the client loaded it."""

    def __init__(self, expected: int, actual: int) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(
            "This project was changed somewhere else — another tab or device. "
            "Reload to get the latest version before saving again."
        )


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def get_project(db: Session, *, user_id: int, project_id: int) -> VideoProject:
    """One project, or a refusal. Never leaks another user's row."""
    project = db.scalars(
        select(VideoProject).where(
            VideoProject.id == project_id, VideoProject.user_id == user_id
        )
    ).first()
    if project is None:
        raise ProjectNotFound("That project does not exist.")
    return project


def list_projects(
    db: Session,
    *,
    user_id: int,
    search: str | None = None,
    platform: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[VideoProject]:
    """A user's projects, most recently edited first.

    Filtering happens in SQL rather than in the client: the projects list is
    the one screen that grows without bound, and a full download it would
    outgrow is the same mistake `listCampaigns` already avoids.
    """
    query = select(VideoProject).where(VideoProject.user_id == user_id)

    if search:
        query = query.where(VideoProject.name.ilike(f"%{search.strip()}%"))
    if platform:
        query = query.where(VideoProject.platform == platform)
    if status:
        query = query.where(VideoProject.status == status)

    query = (
        query.order_by(VideoProject.updated_at.desc())
        .limit(min(max(1, limit), 200))
        .offset(max(0, offset))
    )
    return list(db.scalars(query).all())


def count_projects(db: Session, *, user_id: int) -> int:
    return int(
        db.scalar(
            select(func.count(VideoProject.id)).where(VideoProject.user_id == user_id)
        )
        or 0
    )


# ---------------------------------------------------------------------------
# Timeline arithmetic
# ---------------------------------------------------------------------------


def timeline_duration(timeline: dict | None) -> float:
    """Where the last clip on any track ends.

    A clip is `{"start": s, "duration": d, ...}`. `end` is honoured when
    present so a trimmed clip does not have to restate its length, which is the
    shape the editor writes.
    """
    longest = 0.0
    for track in (timeline or {}).get("tracks", []) or []:
        for clip in track.get("clips", []) or []:
            try:
                start = float(clip.get("start") or 0.0)
                end = clip.get("end")
                end = float(end) if end is not None else start + float(clip.get("duration") or 0.0)
            except (TypeError, ValueError):
                continue
            longest = max(longest, end)
    return round(longest, 3)


def project_duration(db: Session, project: VideoProject) -> float:
    """The project's real length, in seconds.

    Three sources, whichever runs longest: the timeline, the scene list, and
    the subtitle tracks. All three are consulted because a project can
    legitimately have only one of them — Subtitle Studio's "Add to Project"
    produces captions before any media exists, and the AI flow produces scenes
    before a timeline is built. Reporting 0:00 for either would be wrong on the
    projects list and would let a too-long project past the render check.
    """
    if project.id is None:
        return timeline_duration(project.timeline)

    scene_end = float(
        db.scalar(
            select(
                func.coalesce(
                    func.max(VideoScene.start_seconds + VideoScene.duration_seconds), 0.0
                )
            ).where(VideoScene.project_id == project.id)
        )
        or 0.0
    )
    subtitle_end = float(
        db.scalar(
            select(func.coalesce(func.max(VideoSubtitle.duration_seconds), 0.0)).where(
                VideoSubtitle.project_id == project.id
            )
        )
        or 0.0
    )
    return round(max(timeline_duration(project.timeline), scene_end, subtitle_end), 3)


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

# Fields a client may set. Anything not listed — id, user_id, revision,
# timestamps, duration — is derived or owned by the server, and a patch that
# names one is ignored rather than honoured.
PATCHABLE = {
    "name",
    "description",
    "project_type",
    "platform",
    "aspect_ratio",
    "width",
    "height",
    "fps",
    "status",
    "script",
    "timeline",
    "brand",
    "template_key",
    "export_settings",
    "thumbnail_asset_id",
    "notes",
}


def create_project(
    db: Session,
    *,
    user_id: int,
    name: str | None = None,
    description: str | None = None,
    project_type: str = "blank",
    platform: str | None = None,
    aspect_ratio: str | None = None,
    width: int | None = None,
    height: int | None = None,
    fps: int | None = None,
    template=None,
    apply_brand: bool = True,
    commit: bool = True,
) -> VideoProject:
    """Start a project from a platform preset, optionally on a template.

    The preset supplies the canvas; a template overrides it; explicit
    dimensions override both, which is what "Custom" on the Create Video screen
    sends. Whatever is chosen is then clamped to the MVP resolution cap, so a
    project can never be created that the renderer would have to refuse later.
    """
    if project_type not in PROJECT_TYPES:
        raise ProjectError(f"Unknown project type {project_type!r}.")

    preset = presets.get_preset(platform or (template.platform if template else None))
    definition = dict(getattr(template, "definition", None) or {})

    canvas_width, canvas_height = presets.clamp_resolution(
        int(width or (template.width if template else 0) or preset.width),
        int(height or (template.height if template else 0) or preset.height),
    )
    canvas_fps = int(fps or (template.fps if template else 0) or preset.fps)

    project = VideoProject(
        user_id=user_id,
        name=(name or "Untitled project").strip()[:200] or "Untitled project",
        description=(description or None),
        project_type=project_type,
        platform=preset.key,
        aspect_ratio=(
            aspect_ratio or (template.aspect_ratio if template else None) or preset.aspect_ratio
        ),
        width=canvas_width,
        height=canvas_height,
        fps=canvas_fps,
        duration_seconds=0.0,
        status="draft",
        script=deepcopy(definition.get("script") or {}),
        # A deep copy: the constant is module-level and a shallow one would let
        # the first project's edits reach into every project created after it.
        timeline=deepcopy(definition.get("timeline") or EMPTY_TIMELINE),
        brand={"apply": bool(apply_brand), **(definition.get("brand") or {})},
        template_id=(template.id if template else None),
        template_key=(template.key if template else None),
        export_settings=deepcopy(definition.get("export_settings"))
        or {
            "format": "mp4",
            "resolution": presets.resolution_label(canvas_width, canvas_height),
            "fps": canvas_fps,
            "quality": "high",
            "burn_subtitles": False,
        },
        revision=0,
    )

    db.add(project)
    db.flush()  # assigns project.id, which the child rows below need

    # A template's scenes become real scene rows straight away, so the project
    # opens on a storyboard rather than on an empty screen the user has to
    # work out how to fill.
    start = 0.0
    for position, scene in enumerate(definition.get("scenes") or []):
        if not isinstance(scene, dict):
            continue
        duration = float(scene.get("duration_seconds") or scene.get("duration") or 5.0)
        db.add(
            VideoScene(
                project_id=project.id,
                position=position,
                title=scene.get("title"),
                text=scene.get("text"),
                visual_prompt=scene.get("visual_prompt"),
                source="pending",
                start_seconds=start,
                duration_seconds=duration,
                transition=scene.get("transition") or "cut",
                # The template's guidance for this beat travels in `settings`,
                # never in `text`. `text` is what the voice reads, what the
                # subtitles are built from and what the renderer draws — a
                # prompt left there would be narrated and published verbatim by
                # anyone who did not notice it. Nothing renders from `settings`.
                settings={
                    **deepcopy(scene.get("settings") or {}),
                    **{
                        key: scene[key]
                        for key in ("role", "prompt", "media", "animation", "layout")
                        if scene.get(key)
                    },
                },
            )
        )
        start += duration

    # Every project gets one subtitle track, empty. Subtitle Studio then has
    # somewhere to write into without having to decide whether to create one,
    # and the editor always has a subtitles row to draw.
    db.add(
        VideoSubtitle(
            project_id=project.id,
            language="en-US",
            source="manual",
            is_primary=True,
            cues=[],
            style=deepcopy(
                definition.get("subtitle_style")
                or subtitle_engine.preset(subtitle_engine.DEFAULT_PRESET)
            ),
            cue_count=0,
            duration_seconds=0.0,
        )
    )

    project.duration_seconds = project_duration(db, project)

    if commit:
        db.commit()
        db.refresh(project)
    return project


def update_project(
    db: Session,
    *,
    project: VideoProject,
    patch: dict,
    expected_revision: int | None = None,
    autosave: bool = False,
    commit: bool = True,
) -> VideoProject:
    """Apply a patch, with optimistic concurrency and derived fields.

    `expected_revision` is what the client loaded. Sending it turns a save into
    a compare-and-set; omitting it is a deliberate force, which is what a
    rename from the projects list does — it touches one field and cannot
    conflict meaningfully.
    """
    if expected_revision is not None and expected_revision != project.revision:
        raise RevisionConflict(expected_revision, project.revision)

    for field, value in (patch or {}).items():
        if field not in PATCHABLE or value is None:
            continue

        if field == "name":
            value = str(value).strip()[:200] or "Untitled project"
        elif field == "status" and value not in PROJECT_STATUSES:
            continue
        elif field == "project_type" and value not in PROJECT_TYPES:
            continue
        elif field in {"width", "height"}:
            value = int(value)
        elif field == "fps":
            value = max(1, min(60, int(value)))

        setattr(project, field, value)

    # Dimensions are re-clamped after the patch, not before: a client may have
    # changed both, and the cap applies to the result.
    project.width, project.height = presets.clamp_resolution(
        project.width, project.height
    )

    project.duration_seconds = project_duration(db, project)
    project.revision += 1
    if autosave:
        project.last_autosave_at = utcnow()

    if commit:
        db.commit()
        db.refresh(project)
    return project


def rename_project(
    db: Session, *, project: VideoProject, name: str, commit: bool = True
) -> VideoProject:
    """Rename, and nothing else.

    Its own function rather than a patch because a rename comes from the
    projects list, where the client has not loaded the project and has no
    revision to send. Routing it through `update_project` would mean either
    passing no revision (making the general save path look like it tolerates
    that) or inventing one.
    """
    cleaned = (name or "").strip()[:200]
    if not cleaned:
        raise ProjectError("A project needs a name.")

    project.name = cleaned
    project.revision += 1
    if commit:
        db.commit()
        db.refresh(project)
    return project


def set_status(
    db: Session, *, project: VideoProject, status: str, commit: bool = True
) -> VideoProject:
    """Move a project between draft / processing / completed / failed.

    Called by the render pipeline as a job progresses, so the projects list can
    show state without joining every render. Does NOT bump `revision`: the
    editor's document has not changed, and bumping it would make a render
    invalidate the tab the user is editing in.
    """
    if status not in PROJECT_STATUSES:
        raise ProjectError(f"Unknown project status {status!r}.")
    project.status = status
    if commit:
        db.commit()
    return project


def duplicate_project(
    db: Session, *, project: VideoProject, name: str | None = None
) -> VideoProject:
    """Copy a project, including its scenes, audio layers and subtitle tracks.

    Assets are **referenced, not copied**. The duplicate points at the same
    asset rows, which is right: duplicating a project to try a different edit
    must not double the storage bill, and the assets are immutable anyway.

    The copy always starts as a draft with no render history and no version
    history. It has not been rendered — presenting it as though it had would
    offer a download of the original's file.
    """
    copy = VideoProject(
        user_id=project.user_id,
        name=(name or f"{project.name} (copy)")[:200],
        description=project.description,
        project_type=project.project_type,
        platform=project.platform,
        aspect_ratio=project.aspect_ratio,
        width=project.width,
        height=project.height,
        fps=project.fps,
        duration_seconds=project.duration_seconds,
        status="draft",
        script=deepcopy(project.script or {}),
        timeline=deepcopy(project.timeline or {}),
        brand=deepcopy(project.brand or {}),
        template_id=project.template_id,
        template_key=project.template_key,
        export_settings=deepcopy(project.export_settings or {}),
        thumbnail_asset_id=project.thumbnail_asset_id,
        notes=project.notes,
        revision=0,
    )
    db.add(copy)
    db.flush()

    for scene in db.scalars(
        select(VideoScene)
        .where(VideoScene.project_id == project.id)
        .order_by(VideoScene.position)
    ).all():
        db.add(
            VideoScene(
                project_id=copy.id,
                position=scene.position,
                title=scene.title,
                text=scene.text,
                visual_prompt=scene.visual_prompt,
                source=scene.source,
                asset_id=scene.asset_id,
                voice_asset_id=scene.voice_asset_id,
                start_seconds=scene.start_seconds,
                duration_seconds=scene.duration_seconds,
                transition=scene.transition,
                settings=deepcopy(scene.settings or {}),
            )
        )

    for layer in db.scalars(
        select(VideoAudio).where(VideoAudio.project_id == project.id)
    ).all():
        db.add(
            VideoAudio(
                project_id=copy.id,
                asset_id=layer.asset_id,
                role=layer.role,
                label=layer.label,
                position=layer.position,
                start_seconds=layer.start_seconds,
                duration_seconds=layer.duration_seconds,
                trim_start=layer.trim_start,
                trim_end=layer.trim_end,
                volume=layer.volume,
                fade_in=layer.fade_in,
                fade_out=layer.fade_out,
                ducking=layer.ducking,
                loop=layer.loop,
                muted=layer.muted,
                meta=deepcopy(layer.meta or {}),
            )
        )

    for track in db.scalars(
        select(VideoSubtitle).where(VideoSubtitle.project_id == project.id)
    ).all():
        db.add(
            VideoSubtitle(
                project_id=copy.id,
                language=track.language,
                label=track.label,
                source=track.source,
                is_primary=track.is_primary,
                cues=deepcopy(track.cues or []),
                style=deepcopy(track.style or {}),
                cue_count=track.cue_count,
                duration_seconds=track.duration_seconds,
                # Deliberately not copied: the exported .srt belongs to the
                # original. The copy exports its own when asked.
                asset_id=None,
                meta=deepcopy(track.meta or {}),
            )
        )

    db.commit()
    db.refresh(copy)
    return copy


def delete_project(db: Session, *, project: VideoProject) -> None:
    """Delete a project and its parts. Its assets survive, detached.

    `video_assets.project_id` is ON DELETE SET NULL, so a voice-over made in
    Voice Studio and attached to a project belongs to the user, not to the
    project. Scenes, audio layers, subtitle tracks and versions are ON DELETE
    CASCADE — they have no meaning without the project.

    The child rows are also deleted explicitly rather than left to the
    database. SQLite does not enforce foreign keys unless the connection asks
    it to, so on a developer's machine and in the test suite the cascade would
    silently not happen.
    """
    project_id = project.id
    for model in (VideoProjectVersion, VideoScene, VideoAudio, VideoSubtitle):
        db.execute(delete(model).where(model.project_id == project_id))

    # Assets are detached, not deleted — the database would do this on
    # Postgres, but see the note above about SQLite.
    db.execute(
        VideoAsset.__table__.update()
        .where(VideoAsset.project_id == project_id)
        .values(project_id=None)
    )

    db.delete(project)
    db.commit()


def attach_asset(
    db: Session, *, project: VideoProject, asset: VideoAsset, commit: bool = True
) -> VideoAsset:
    """Connect a standalone asset to a project — the "Add to Project" action.

    Deliberately does NOT place the asset on the timeline. Adding a voice-over
    to a project makes it available there; where it sits is an editing decision
    the user makes in the editor, and silently dropping a clip onto their
    timeline would be an edit they did not ask for.
    """
    if asset.user_id != project.user_id:
        raise ProjectError("That asset belongs to a different account.")

    asset.project_id = project.id
    if commit:
        db.commit()
        db.refresh(asset)
    return asset


def render_refusal(db: Session, project: VideoProject) -> str | None:
    """Why this project cannot be rendered right now, or None.

    Checked before a render job is created so the refusal arrives immediately
    with a reason, rather than as a failed job minutes later. It lives here
    because the limits are a property of the project.
    """
    duration = project_duration(db, project)
    if duration <= 0:
        return "This project has nothing on its timeline yet."

    cap = settings.video_max_duration_seconds
    if duration > cap:
        return (
            f"This project is {duration / 60:.1f} minutes long. Rendering is "
            f"currently limited to {cap // 60} minutes while it runs on the "
            f"API server."
        )

    # The short side, not the height — see `presets.clamp_resolution`. Checking
    # height here would refuse every vertical project, which is most of them.
    if min(project.width, project.height) > settings.video_max_resolution_height:
        return (
            f"{presets.resolution_label(project.width, project.height)} is above "
            f"the current render limit of {settings.video_max_resolution_height}p."
        )
    return None
