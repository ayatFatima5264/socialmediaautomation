"""Converting a project to another platform's format.

One edit, several surfaces: a 16:9 YouTube cut becomes a 9:16 Short and a 1:1
in-feed post. The rule that makes this safe is the same one Smart Repurpose
follows —

    **the original is never modified.** Convert only ever *creates*. It reads
    the source project's timeline, scenes and captions, and writes a new
    project with a new canvas. Nothing about the source changes, including its
    revision.

**Reframing is real.** Every visual clip is set to `fit="cover"` so it fills
the new canvas and is centre-cropped by the compositor's own `place()` — the
same maths the preview draws. A clip's `x` offset survives, so a framing the
user nudged by hand is carried over rather than reset.

**What does not carry over, and why.** Renders do not: a finished 16:9 file is
not a 9:16 file, and copying the row would leave a project claiming an export
that does not match it. Text sizes are *rescaled* rather than copied, because a
font size is a fraction of the canvas and the canvas changed shape.
"""
from __future__ import annotations

import logging
from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.video_project import VideoProject
from app.models.video_scene import VideoScene
from app.models.video_subtitle import VideoSubtitle
from app.services.video import presets
from app.services.video import projects as project_service
from app.services.video import subtitles as subtitle_engine
from app.services.video import timeline as tl

logger = logging.getLogger(__name__)


class FormatError(RuntimeError):
    """A conversion was refused. The message is user-facing."""


# Which caption style suits which surface. A vertical short wants big centred
# captions; a landscape video wants the quieter default. Applied on conversion
# because carrying a `shorts` style onto a 16:9 canvas produces text that
# occupies a third of the frame.
_SUBTITLE_STYLE_FOR = {
    "youtube": "youtube",
    "youtube_shorts": "shorts",
    "tiktok": "tiktok",
    "instagram_reels": "shorts",
    "instagram_post": "clean",
    "facebook": "clean",
    "facebook_reels": "shorts",
}


def targets_for(project: VideoProject) -> list[dict]:
    """The formats this project can be converted to — everything but its own.

    `custom` is excluded: converting to "custom" means nothing without
    dimensions, and the format picker on the project page already covers
    changing a canvas by hand.
    """
    out = []
    for preset in presets.PRESETS:
        if preset.key in ("custom", project.platform):
            continue
        width, height = presets.clamp_resolution(preset.width, preset.height)
        out.append(
            {
                "key": preset.key,
                "label": preset.label,
                "aspect_ratio": preset.aspect_ratio,
                "width": width,
                "height": height,
                "max_seconds": preset.platform_max_seconds,
                "description": preset.description,
            }
        )
    return out


def _rescale_text(clip: dict, *, source: VideoProject, target_short: int) -> dict:
    """Keep a text clip the same size *relative to the frame*.

    `font_size` is stored in pixels on a timeline clip, so a title set for a
    1080-wide canvas is illegibly small on a 1920-wide one and overflows going
    the other way. Rescaling by the ratio of the short sides preserves what the
    user actually chose, which was a size relative to the picture.
    """
    source_short = max(1, min(source.width, source.height))
    factor = target_short / source_short
    updated = deepcopy(clip)
    updated["font_size"] = max(8, int(round(clip.get("font_size", 48) * factor)))
    return updated


def reframe_timeline(
    timeline: dict, *, source: VideoProject, target: VideoProject
) -> dict:
    """The source timeline, laid out for a different canvas.

    Clip timings are untouched — a conversion changes the shape of the picture,
    not the edit. What changes is how each clip fills the frame and how big the
    text is.
    """
    document = tl.normalize(timeline)
    target_short = min(target.width, target.height)

    video = tl.get_track(document, "video")
    video["clips"] = [
        {
            **clip,
            # Fill the new shape. `contain` on a converted clip means bars on
            # every side, which is what "converted" should never look like.
            "fit": "cover",
        }
        for clip in video["clips"]
    ]

    text = tl.get_track(document, "text")
    text["clips"] = [
        _rescale_text(clip, source=source, target_short=target_short)
        for clip in text["clips"]
    ]

    # Audio is unchanged: a soundtrack has no aspect ratio.
    return tl.normalize(document)


def convert_project(
    db: Session,
    *,
    user_id: int,
    project: VideoProject,
    target: str,
    name: str | None = None,
    copy_scenes: bool = True,
    copy_subtitles: bool = True,
) -> VideoProject:
    """Create a new project in another format from this one.

    Returns the new project. The source is read and not written — asserted by
    the tests, because "we do not mean to change it" is not a guarantee.
    """
    if project.user_id != user_id:
        raise FormatError("That project belongs to a different account.")

    preset = presets.get_preset(target)
    if preset.key == "custom":
        raise FormatError(
            "Pick a platform to convert to. For a custom size, change the "
            "canvas on the project itself."
        )
    if preset.key == project.platform:
        raise FormatError(f"This project is already a {preset.label} project.")

    duration = project_service.project_duration(db, project)
    if duration > preset.platform_max_seconds:
        raise FormatError(
            f"{preset.label} allows {preset.platform_max_seconds // 60 or 1} "
            f"minute{'s' if preset.platform_max_seconds >= 120 else ''}; this "
            f"project is {duration / 60:.1f} minutes. Shorten it first."
        )

    copy = project_service.create_project(
        db,
        user_id=user_id,
        name=(name or f"{project.name} — {preset.label}")[:200],
        description=project.description,
        project_type=project.project_type,
        platform=preset.key,
        apply_brand=False,
    )

    # ---- the timeline ---------------------------------------------------
    timeline = reframe_timeline(
        project.timeline or {}, source=project, target=copy
    )

    provenance = {
        **deepcopy(project.script or {}),
        "converted_from": {
            "project_id": project.id,
            "name": project.name,
            "platform": project.platform,
            "aspect_ratio": project.aspect_ratio,
        },
    }

    project_service.update_project(
        db,
        project=copy,
        patch={
            "timeline": timeline,
            "script": provenance,
            "brand": deepcopy(project.brand or {}),
            "export_settings": deepcopy(project.export_settings or {}),
        },
    )

    # ---- scenes ----------------------------------------------------------
    if copy_scenes:
        rows = db.scalars(
            select(VideoScene)
            .where(VideoScene.project_id == project.id)
            .order_by(VideoScene.position, VideoScene.id)
        ).all()
        for row in rows:
            db.add(
                VideoScene(
                    project_id=copy.id,
                    position=row.position,
                    title=row.title,
                    text=row.text,
                    visual_prompt=row.visual_prompt,
                    source=row.source,
                    # The same assets, by reference. A conversion is a second
                    # framing of one video, not a second copy of its media.
                    asset_id=row.asset_id,
                    voice_asset_id=row.voice_asset_id,
                    start_seconds=row.start_seconds,
                    duration_seconds=row.duration_seconds,
                    transition=row.transition,
                    settings=deepcopy(row.settings or {}),
                )
            )

    # ---- captions --------------------------------------------------------
    if copy_subtitles:
        source_track = db.scalars(
            select(VideoSubtitle)
            .where(VideoSubtitle.project_id == project.id)
            .order_by(VideoSubtitle.id)
        ).first()

        target_track = db.scalars(
            select(VideoSubtitle)
            .where(VideoSubtitle.project_id == copy.id)
            .order_by(VideoSubtitle.id)
        ).first()

        if source_track is not None and source_track.cue_count:
            style = subtitle_engine.preset(
                _SUBTITLE_STYLE_FOR.get(preset.key, subtitle_engine.DEFAULT_PRESET)
            )
            if target_track is None:
                target_track = VideoSubtitle(project_id=copy.id, is_primary=True)
                db.add(target_track)
            target_track.language = source_track.language
            target_track.source = source_track.source
            target_track.cues = deepcopy(source_track.cues or [])
            target_track.style = style
            target_track.cue_count = source_track.cue_count
            target_track.duration_seconds = source_track.duration_seconds

    db.commit()
    db.refresh(copy)

    logger.info(
        "Converted project %s (%s) into %s (%s)",
        project.id, project.platform, copy.id, preset.key,
    )
    return copy
