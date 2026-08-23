"""Project version history — snapshots, restore, and pruning.

An autosaving editor has to be able to answer "undo that" after a reload. This
module writes the snapshots that make it possible and reads them back.

Three rules shape it:

  * **Snapshots are throttled, not written on every save.** The editor saves as
    the user types; a version per keystroke is a table that grows without limit
    for something nobody scrolls past the last handful of. `MIN_SECONDS_BETWEEN`
    collapses a working session into a version every couple of minutes, while
    anything explicit (a manual save point, the moment before an AI rewrite)
    always writes.
  * **Restoring is itself undoable.** A `pre_restore` snapshot is written first,
    so a restore the user regrets is one more restore away rather than a
    permanent loss.
  * **A snapshot holds the whole document, not a diff.** A project is tens of
    kilobytes of JSON; a diff would need a merge implementation to read one
    back, and a half-applied restore is worse than none.
"""
from __future__ import annotations

import logging
from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutils import utcnow
from app.models.video_audio import VideoAudio
from app.models.video_project import VideoProject
from app.models.video_project_version import (
    MAX_VERSIONS_PER_PROJECT,
    VERSION_REASONS,
    VideoProjectVersion,
)
from app.models.video_scene import VideoScene
from app.models.video_subtitle import VideoSubtitle

logger = logging.getLogger(__name__)

# How long an ordinary autosave waits before it earns a snapshot. Explicit
# reasons bypass it entirely.
MIN_SECONDS_BETWEEN = 120.0


class VersionError(RuntimeError):
    """A version operation was refused. The message is user-facing."""


def _serialise(db: Session, project: VideoProject) -> dict:
    """The whole project as one JSON document, children included."""
    scenes = db.scalars(
        select(VideoScene)
        .where(VideoScene.project_id == project.id)
        .order_by(VideoScene.position)
    ).all()
    layers = db.scalars(
        select(VideoAudio)
        .where(VideoAudio.project_id == project.id)
        .order_by(VideoAudio.position)
    ).all()
    tracks = db.scalars(
        select(VideoSubtitle).where(VideoSubtitle.project_id == project.id)
    ).all()

    return {
        "project": {
            "name": project.name,
            "description": project.description,
            "project_type": project.project_type,
            "platform": project.platform,
            "aspect_ratio": project.aspect_ratio,
            "width": project.width,
            "height": project.height,
            "fps": project.fps,
            "script": deepcopy(project.script or {}),
            "timeline": deepcopy(project.timeline or {}),
            "brand": deepcopy(project.brand or {}),
            "export_settings": deepcopy(project.export_settings or {}),
            "template_key": project.template_key,
            "notes": project.notes,
            "thumbnail_asset_id": project.thumbnail_asset_id,
        },
        "scenes": [
            {
                "position": s.position,
                "title": s.title,
                "text": s.text,
                "visual_prompt": s.visual_prompt,
                "source": s.source,
                "asset_id": s.asset_id,
                "voice_asset_id": s.voice_asset_id,
                "start_seconds": s.start_seconds,
                "duration_seconds": s.duration_seconds,
                "transition": s.transition,
                "settings": deepcopy(s.settings or {}),
            }
            for s in scenes
        ],
        "audio": [
            {
                "asset_id": a.asset_id,
                "role": a.role,
                "label": a.label,
                "position": a.position,
                "start_seconds": a.start_seconds,
                "duration_seconds": a.duration_seconds,
                "trim_start": a.trim_start,
                "trim_end": a.trim_end,
                "volume": a.volume,
                "fade_in": a.fade_in,
                "fade_out": a.fade_out,
                "ducking": a.ducking,
                "loop": a.loop,
                "muted": a.muted,
                "meta": deepcopy(a.meta or {}),
            }
            for a in layers
        ],
        "subtitles": [
            {
                "language": t.language,
                "label": t.label,
                "source": t.source,
                "is_primary": t.is_primary,
                "cues": deepcopy(t.cues or []),
                "style": deepcopy(t.style or {}),
                "cue_count": t.cue_count,
                "duration_seconds": t.duration_seconds,
                "meta": deepcopy(t.meta or {}),
            }
            for t in tracks
        ],
    }


def should_snapshot(db: Session, *, project: VideoProject, reason: str) -> bool:
    """Has enough happened since the last snapshot to justify another?

    Anything other than a plain autosave always qualifies — those reasons exist
    precisely because something is about to be overwritten.
    """
    if reason != "autosave":
        return True

    latest = db.scalars(
        select(VideoProjectVersion)
        .where(VideoProjectVersion.project_id == project.id)
        .order_by(VideoProjectVersion.created_at.desc())
        .limit(1)
    ).first()
    if latest is None or latest.created_at is None:
        return True

    return (utcnow() - latest.created_at).total_seconds() >= MIN_SECONDS_BETWEEN


def snapshot(
    db: Session,
    *,
    project: VideoProject,
    reason: str = "autosave",
    label: str | None = None,
    force: bool = False,
    commit: bool = True,
) -> VideoProjectVersion | None:
    """Write a version, unless the throttle says this one is not worth keeping.

    Returns the row, or None when it was skipped. Callers treat None as
    success — a skipped snapshot is the normal outcome of a fast autosave, not
    a failure of the save it accompanied.
    """
    if reason not in VERSION_REASONS:
        raise VersionError(f"Unknown version reason {reason!r}.")

    if not force and not should_snapshot(db, project=project, reason=reason):
        return None

    version = VideoProjectVersion(
        project_id=project.id,
        revision=project.revision,
        reason=reason,
        label=label,
        snapshot=_serialise(db, project),
    )
    db.add(version)
    db.flush()

    _prune(db, project_id=project.id)

    if commit:
        db.commit()
        db.refresh(version)
    return version


def _prune(db: Session, *, project_id: int) -> int:
    """Drop the oldest versions beyond the cap. Returns how many went.

    Deleted one at a time through the session rather than with a subquery
    DELETE, because `DELETE ... WHERE id IN (SELECT ... LIMIT)` is not portable
    between SQLite and Postgres — MySQL-style LIMIT in a subquery is rejected by
    one of them whichever way it is written. The list is at most a handful of
    rows, so the loop costs nothing.
    """
    surplus = list(
        db.scalars(
            select(VideoProjectVersion)
            .where(VideoProjectVersion.project_id == project_id)
            .order_by(VideoProjectVersion.created_at.desc(), VideoProjectVersion.id.desc())
            .offset(MAX_VERSIONS_PER_PROJECT)
        ).all()
    )
    for version in surplus:
        db.delete(version)
    return len(surplus)


def list_versions(
    db: Session, *, project: VideoProject, limit: int = MAX_VERSIONS_PER_PROJECT
) -> list[VideoProjectVersion]:
    """A project's history, newest first."""
    return list(
        db.scalars(
            select(VideoProjectVersion)
            .where(VideoProjectVersion.project_id == project.id)
            .order_by(VideoProjectVersion.created_at.desc(), VideoProjectVersion.id.desc())
            .limit(max(1, limit))
        ).all()
    )


def get_version(
    db: Session, *, project: VideoProject, version_id: int
) -> VideoProjectVersion:
    """One version of one project.

    Scoped by project, and the project was already scoped by user — so a
    version id from another account resolves to nothing.
    """
    version = db.scalars(
        select(VideoProjectVersion).where(
            VideoProjectVersion.id == version_id,
            VideoProjectVersion.project_id == project.id,
        )
    ).first()
    if version is None:
        raise VersionError("That version does not exist.")
    return version


def restore(
    db: Session,
    *,
    project: VideoProject,
    version: VideoProjectVersion,
    commit: bool = True,
) -> VideoProject:
    """Write a snapshot back over the project, in one transaction.

    A `pre_restore` snapshot of the current state is taken first, so this is
    reversible. The project's `revision` moves forward rather than back to what
    the snapshot held: any editor tab still open is now out of date, and that
    is exactly what the revision check exists to tell it.
    """
    snapshot(db, project=project, reason="pre_restore", force=True, commit=False)

    document = version.snapshot or {}
    fields = document.get("project") or {}

    for field in (
        "name", "description", "project_type", "platform", "aspect_ratio",
        "width", "height", "fps", "script", "timeline", "brand",
        "export_settings", "template_key", "notes", "thumbnail_asset_id",
    ):
        if field in fields:
            setattr(project, field, deepcopy(fields[field]))

    # Children are replaced wholesale. Merging them would mean deciding what a
    # scene "is" across two versions — there is no stable identity to match on
    # once positions have changed, and a wrong match silently corrupts an edit.
    for model in (VideoScene, VideoAudio, VideoSubtitle):
        for row in db.scalars(
            select(model).where(model.project_id == project.id)
        ).all():
            db.delete(row)
    db.flush()

    for scene in document.get("scenes") or []:
        db.add(VideoScene(project_id=project.id, **_clean(scene, VideoScene)))
    for layer in document.get("audio") or []:
        db.add(VideoAudio(project_id=project.id, **_clean(layer, VideoAudio)))
    for track in document.get("subtitles") or []:
        db.add(VideoSubtitle(project_id=project.id, **_clean(track, VideoSubtitle)))

    project.revision += 1

    if commit:
        db.commit()
        db.refresh(project)
    return project


def _clean(payload: dict, model) -> dict:
    """Keep only keys that are real columns on `model`.

    A snapshot written by an older release can carry a field this one has
    dropped. Passing it to the constructor would raise, turning "restore an old
    version" into an error the user cannot do anything about — so unknown keys
    are discarded instead.
    """
    columns = {c.name for c in model.__table__.columns} - {"id", "project_id"}
    return {k: deepcopy(v) for k, v in (payload or {}).items() if k in columns}
