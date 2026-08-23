"""Everything a finished project can be handed over as.

One project produces several deliverables, and they come from different places:

    mp4        the completed render's output asset
    srt / vtt  the project's subtitle track, formatted by the subtitle engine
    mp3 / wav  the render's audio, extracted with ffmpeg on demand
    png / jpg  the project's thumbnail, redrawn from its design where there is
               one so a JPG is not a recompression of a PNG

**The manifest says what is available and why not.** `manifest()` returns every
kind with an `available` flag and, when it is false, the reason — "render the
video first", "this project has no captions". A download screen that lists six
buttons and fails on four of them is worse than one that explains.

**Nothing is produced until it is asked for.** Extracting an MP3 from a render
costs an ffmpeg pass, and most exports are never downloaded. The manifest is
cheap metadata; `produce()` is where the work happens.

**Derived files are not stored.** An MP3 of a render is a pure function of that
render, so keeping a copy would be a second object to pay for, to keep in step,
and to clean up when the render is replaced. The exception is the MP4 itself,
which the renderer already stored because it is the expensive artefact.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.video_asset import VideoAsset
from app.models.video_project import VideoProject
from app.models.video_render import VideoRender
from app.models.video_subtitle import VideoSubtitle
from app.services.video import assets as asset_service
from app.services.video import subtitles as subtitle_engine
from app.services.video.ffmpeg import FFmpegError, transcode_audio

logger = logging.getLogger(__name__)


class ExportError(RuntimeError):
    """An export could not be produced. The message is user-facing."""


class ExportUnavailable(ExportError):
    """The project is not in a state where this export exists yet."""


# What a project can be exported as. `needs` is what has to exist first, and it
# is what the manifest turns into a reason rather than a dead button.
EXPORT_KINDS: tuple[dict, ...] = (
    {
        "kind": "mp4",
        "label": "Video (MP4)",
        "content_type": "video/mp4",
        "group": "video",
        "needs": "render",
        "description": "The finished video, H.264 in an MP4.",
    },
    {
        "kind": "srt",
        "label": "Subtitles (SRT)",
        "content_type": "application/x-subrip",
        "group": "subtitles",
        "needs": "subtitles",
        "description": "Timed captions for YouTube and most editors.",
    },
    {
        "kind": "vtt",
        "label": "Subtitles (VTT)",
        "content_type": "text/vtt",
        "group": "subtitles",
        "needs": "subtitles",
        "description": "WebVTT, for the web and HTML5 players.",
    },
    {
        "kind": "mp3",
        "label": "Audio (MP3)",
        "content_type": "audio/mpeg",
        "group": "audio",
        "needs": "render_audio",
        "description": "The soundtrack on its own, 192 kbps.",
    },
    {
        "kind": "wav",
        "label": "Audio (WAV)",
        "content_type": "audio/wav",
        "group": "audio",
        "needs": "render_audio",
        "description": "Uncompressed 16-bit audio, for re-editing.",
    },
    {
        "kind": "png",
        "label": "Thumbnail (PNG)",
        "content_type": "image/png",
        "group": "thumbnail",
        "needs": "thumbnail",
        "description": "The project's cover image, lossless.",
    },
    {
        "kind": "jpg",
        "label": "Thumbnail (JPG)",
        "content_type": "image/jpeg",
        "group": "thumbnail",
        "needs": "thumbnail",
        "description": "The cover image as a smaller JPEG.",
    },
)

KINDS_BY_NAME = {entry["kind"]: entry for entry in EXPORT_KINDS}


# ---------------------------------------------------------------------------
# What the project has
# ---------------------------------------------------------------------------


def latest_completed_render(db: Session, project_id: int) -> VideoRender | None:
    """The newest finished export, which is what every file derives from.

    Newest rather than first: a project rendered three times should hand over
    the current cut, not the one from before the edits.
    """
    return db.scalars(
        select(VideoRender)
        .where(
            VideoRender.project_id == project_id,
            VideoRender.status == "completed",
            VideoRender.output_asset_id.is_not(None),
        )
        .order_by(VideoRender.created_at.desc(), VideoRender.id.desc())
    ).first()


def primary_subtitles(db: Session, project_id: int) -> VideoSubtitle | None:
    """The track that would be burned in — the one worth exporting.

    Falls back to any track with cues: a project whose primary flag was never
    set still has captions somebody wants, and refusing to export them over a
    bookkeeping detail would be absurd.
    """
    tracks = list(
        db.scalars(
            select(VideoSubtitle)
            .where(VideoSubtitle.project_id == project_id)
            .order_by(VideoSubtitle.id)
        ).all()
    )
    with_cues = [track for track in tracks if track.cue_count]
    if not with_cues:
        return None
    return next((track for track in with_cues if track.is_primary), with_cues[0])


def manifest(db: Session, project: VideoProject) -> list[dict]:
    """Every export kind, with whether it is available and why not.

    Cheap — it reads three rows and produces no files. The reasons are written
    as the next action to take, not as a statement of what is missing: "Render
    the video first" tells somebody what to do, "no render" does not.
    """
    render = latest_completed_render(db, project.id)
    track = primary_subtitles(db, project.id)

    thumbnail = None
    if project.thumbnail_asset_id:
        thumbnail = db.get(VideoAsset, project.thumbnail_asset_id)
        if thumbnail is not None and thumbnail.user_id != project.user_id:
            thumbnail = None

    output = db.get(VideoAsset, render.output_asset_id) if render else None

    out = []
    for entry in EXPORT_KINDS:
        available = False
        reason = None
        size = None

        if entry["needs"] == "render":
            available = output is not None
            reason = None if available else "Render the video first."
            size = output.size_bytes if output else None
        elif entry["needs"] == "render_audio":
            available = output is not None
            reason = None if available else "Render the video first."
        elif entry["needs"] == "subtitles":
            available = track is not None
            reason = None if available else "This project has no captions yet."
        elif entry["needs"] == "thumbnail":
            available = thumbnail is not None
            reason = (
                None if available else "Set a thumbnail in Thumbnail Studio first."
            )
            size = thumbnail.size_bytes if thumbnail and entry["kind"] == "png" else None

        out.append(
            {
                **{k: v for k, v in entry.items() if k != "needs"},
                "available": available,
                "reason": reason,
                "size_bytes": size,
            }
        )

    return out


# ---------------------------------------------------------------------------
# Producing a file
# ---------------------------------------------------------------------------


def _safe_stem(name: str | None, fallback: str = "video") -> str:
    stem = "".join(
        character if character.isalnum() or character in " -_" else ""
        for character in (name or "")
    ).strip()
    return (stem or fallback)[:60]


def produce(
    db: Session, *, project: VideoProject, kind: str
) -> tuple[bytes, str, str]:
    """One export, as `(bytes, content_type, filename)`.

    Raises `ExportUnavailable` when the project is not ready for that kind —
    which the route turns into a 422 carrying the same sentence the manifest
    would have shown.
    """
    spec = KINDS_BY_NAME.get((kind or "").lower())
    if spec is None:
        raise ExportError(f"{kind!r} is not something this can export.")

    stem = _safe_stem(project.name)

    if spec["group"] == "subtitles":
        return _subtitles(db, project, kind, stem)
    if spec["group"] == "thumbnail":
        return _thumbnail(db, project, kind, stem)
    return _from_render(db, project, kind, stem)


def _subtitles(
    db: Session, project: VideoProject, kind: str, stem: str
) -> tuple[bytes, str, str]:
    track = primary_subtitles(db, project.id)
    if track is None:
        raise ExportUnavailable("This project has no captions yet.")

    cues = track.cues or []
    text = subtitle_engine.to_srt(cues) if kind == "srt" else subtitle_engine.to_vtt(cues)
    content_type = KINDS_BY_NAME[kind]["content_type"]
    # UTF-8 without a BOM. A BOM is what makes an SRT show a stray character on
    # the first cue in several players.
    return text.encode("utf-8"), content_type, f"{stem}.{kind}"


def _thumbnail(
    db: Session, project: VideoProject, kind: str, stem: str
) -> tuple[bytes, str, str]:
    if not project.thumbnail_asset_id:
        raise ExportUnavailable("Set a thumbnail in Thumbnail Studio first.")

    try:
        asset = asset_service.get_asset(
            db, user_id=project.user_id, asset_id=project.thumbnail_asset_id
        )
    except asset_service.AssetError as exc:
        raise ExportUnavailable("That thumbnail is no longer in your library.") from exc

    wanted = KINDS_BY_NAME[kind]["content_type"]
    design = (asset.meta or {}).get("design")

    # Redrawn from the design when the format differs, so a JPG of a PNG
    # thumbnail is a fresh render rather than a recompression of an already
    # compressed image. Same reasoning as the Thumbnail Studio's own download.
    if design and asset.content_type != wanted:
        from app.services.video import thumbnails as studio

        try:
            data = studio.render(design, fmt="png" if kind == "png" else "jpg")
        except studio.ThumbnailError as exc:
            raise ExportError(str(exc)) from exc
        return data, wanted, f"{stem}.{kind}"

    try:
        data, content_type = asset_service.read_asset(asset)
    except asset_service.AssetError as exc:
        raise ExportUnavailable(str(exc)) from exc

    # A thumbnail stored as a PNG and asked for as a PNG (or the reverse) is
    # handed over as-is; a mismatch with no design behind it is converted.
    if content_type != wanted:
        from io import BytesIO

        from PIL import Image

        try:
            image = Image.open(BytesIO(data))
            buffer = BytesIO()
            if kind == "jpg":
                image.convert("RGB").save(buffer, format="JPEG", quality=90)
            else:
                image.save(buffer, format="PNG", optimize=True)
            data = buffer.getvalue()
        except Exception as exc:  # noqa: BLE001 — Pillow raises broadly
            raise ExportError("That thumbnail could not be converted.") from exc

    return data, wanted, f"{stem}.{kind}"


def _from_render(
    db: Session, project: VideoProject, kind: str, stem: str
) -> tuple[bytes, str, str]:
    render = latest_completed_render(db, project.id)
    if render is None:
        raise ExportUnavailable("Render the video first.")

    try:
        asset = asset_service.get_asset(
            db, user_id=project.user_id, asset_id=render.output_asset_id
        )
        data, _content_type = asset_service.read_asset(asset)
    except asset_service.AssetError as exc:
        raise ExportUnavailable("The rendered video is no longer available.") from exc

    if kind == "mp4":
        return data, "video/mp4", f"{stem}.mp4"

    # mp3 / wav — extracted on demand. See the module docstring for why this is
    # not stored.
    try:
        converted = transcode_audio(data, source_suffix="mp4", target=kind)
    except FFmpegError as exc:
        logger.exception("Could not extract %s from render %s", kind, render.id)
        raise ExportError(
            f"The audio could not be extracted as {kind.upper()}. "
            f"The MP4 is still available to download."
        ) from exc

    if not converted:
        raise ExportError("The extracted audio was empty.")

    return converted, KINDS_BY_NAME[kind]["content_type"], f"{stem}.{kind}"
