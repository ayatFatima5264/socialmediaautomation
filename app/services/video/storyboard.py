"""Script → scenes → the real timeline.

This is the middle of the AI pipeline and the part that makes the rest of it
honest:

    script ──▶ SCENES ──▶ (voice, visuals, subtitles, music) ──▶ TIMELINE
                                                                    │
                                             the same editor a human ┘
                                             would have built by hand

**Scenes are rows, not a rendering.** `scenes_from_script` produces
`VideoScene` records — the same table a template writes and the same one the
scene editor edits. There is no parallel "AI project" representation. Changing
a generated scene is changing a scene.

**The timeline is built from those rows by `build_timeline`, and it is an
ordinary timeline.** It goes through `timeline.normalize` like any other, the
editor loads it with no idea it was generated, and the compositor renders it
with no special case. That is what "populate the real Video Project, not create
a separate uneditable output" means in code: after generation there is nothing
left that knows the project came from AI except a note in `script`.

**Regeneration is per stage and per scene.** Because each step writes to its
own field — `text` from the script, `visual_prompt` and `asset_id` from the
visual step, `voice_asset_id` from the voice step — redoing one leaves the
others alone. Rewriting a scene's narration does not throw away the image
somebody picked for it.

**Durations are arithmetic, not a model's guess.** Each scene gets time in
proportion to how many words are said over it, then the whole thing is scaled
to the requested length. A model asked to assign seconds returns numbers that
neither add up nor match the narration.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.video_project import VideoProject
from app.models.video_scene import SCENE_SOURCES, SCENE_TRANSITIONS, VideoScene
from app.services.providers.base import AIProvider, ProviderError
from app.services.video import scripting
from app.services.video import timeline as tl

logger = logging.getLogger(__name__)


class StoryboardError(RuntimeError):
    """A storyboard operation was refused. The message is user-facing."""


# The shortest a scene may be. Below about a second and a half a viewer cannot
# read on-screen text or register a cut, so a "scene" that short is really a
# glitch in the pacing.
MIN_SCENE_SECONDS = 1.5
MAX_SCENE_SECONDS = 30.0

# Which scene roles exist, in order. The role is kept in `settings` so the
# editor can label a scene ("Hook", "Point 2") and so regeneration knows which
# part of the script a scene came from.
SCENE_ROLES = ("hook", "introduction", "point", "ending", "cta")


# ---------------------------------------------------------------------------
# Script → scenes
# ---------------------------------------------------------------------------


def _beats(script: dict) -> list[dict]:
    """The script's parts, flattened into the order they are spoken.

    A part with no text is dropped rather than becoming an empty scene: a user
    who deleted the CTA gets a video without one, not a silent two seconds at
    the end.
    """
    beats: list[dict] = []

    def add(role: str, title: str, text: str) -> None:
        if (text or "").strip():
            beats.append({"role": role, "title": title, "text": text.strip()})

    add("hook", "Hook", script.get("hook", ""))
    add("introduction", "Introduction", script.get("introduction", ""))

    for index, point in enumerate(script.get("main_points") or []):
        add(
            "point",
            (point.get("heading") or f"Point {index + 1}")[:200],
            point.get("text", ""),
        )

    add("ending", "Ending", script.get("ending", ""))
    add("cta", "Call to action", script.get("cta", ""))
    return beats


def _split_long(beat: dict, budget_seconds: float, language: str) -> list[dict]:
    """Break a beat that would overrun `MAX_SCENE_SECONDS` into sentences.

    A single main point can be forty seconds of narration, and one static shot
    held that long is the difference between a video and a slideshow. Split at
    sentence boundaries so each piece is still a complete thought.
    """
    if budget_seconds <= MAX_SCENE_SECONDS:
        return [beat]

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", beat["text"]) if s.strip()]
    if len(sentences) < 2:
        return [beat]

    pieces = max(2, int(budget_seconds / MAX_SCENE_SECONDS) + 1)
    per = max(1, len(sentences) // pieces)

    out = []
    for index in range(0, len(sentences), per):
        chunk = " ".join(sentences[index : index + per])
        if not chunk:
            continue
        out.append(
            {
                "role": beat["role"],
                "title": beat["title"] if index == 0 else f"{beat['title']} (cont.)",
                "text": chunk,
            }
        )
    return out or [beat]


def allocate_durations(
    beats: list[dict], *, total_seconds: float, language: str
) -> list[float]:
    """Give each beat time in proportion to what is said over it.

    Then scale the whole set so it adds up to the requested length, and clamp
    each one to something watchable. Clamping happens *after* scaling and the
    result is rescaled once more, so a floor applied to one short beat does not
    silently make the video longer than asked for.
    """
    if not beats:
        return []

    rate = scripting.words_per_second(language)
    natural = [max(0.5, scripting.count_words(beat["text"]) / rate) for beat in beats]
    spoken = sum(natural)
    if spoken <= 0:
        return [round(total_seconds / len(beats), 2)] * len(beats)

    # Scale so the scenes cover the requested length. If the script came in
    # under budget the scenes stretch a little, which reads as breathing room
    # rather than as dead air.
    factor = total_seconds / spoken
    scaled = [value * factor for value in natural]

    clamped = [max(MIN_SCENE_SECONDS, min(value, MAX_SCENE_SECONDS)) for value in scaled]

    # One correction pass: clamping moved the total, so pull it back onto the
    # target across the scenes that still have room to move.
    drift = sum(clamped) - total_seconds
    if abs(drift) > 0.05:
        movable = [
            index
            for index, value in enumerate(clamped)
            if MIN_SCENE_SECONDS < value < MAX_SCENE_SECONDS
        ]
        if movable:
            share = drift / len(movable)
            for index in movable:
                clamped[index] = max(
                    MIN_SCENE_SECONDS, min(clamped[index] - share, MAX_SCENE_SECONDS)
                )

    return [round(value, 2) for value in clamped]


def _overlay_text(beat: dict, visual_mode: str) -> str:
    """What goes on screen for this scene, as opposed to what is said.

    In **animated** mode there is no footage, so the words *are* the video: the
    narration goes on screen, trimmed to something readable at a glance.

    In **natural** mode the footage carries it and a full transcript on top
    would fight the picture — so only the hook and the call to action get text,
    which are the two beats that have to land whether or not the sound is on.
    """
    if visual_mode == "animated":
        words = beat["text"].split()
        return " ".join(words[:14]) + ("…" if len(words) > 14 else "")

    if beat["role"] in ("hook", "cta"):
        words = beat["text"].split()
        return " ".join(words[:10]) + ("…" if len(words) > 10 else "")

    return ""


def _default_source(visual_mode: str) -> str:
    """What kind of visual a scene starts out wanting.

    `pending` for natural mode — the visual step has not run yet and the scene
    honestly has no picture. `color` for animated, because a kinetic-typography
    scene's background is a generated card and nothing needs searching for.
    """
    return "color" if visual_mode == "animated" else "pending"


def scenes_from_script(script: dict, *, total_seconds: float | None = None) -> list[dict]:
    """Turn a script into scene dicts. Pure — no database, no model call.

    Deterministic on purpose: the same script always produces the same
    storyboard, so "regenerate scenes" after editing one line of narration
    changes that scene and nothing else.
    """
    brief = script.get("brief") or {}
    language = brief.get("language") or "en-US"
    visual_mode = brief.get("visual_mode") or "natural"
    target = float(total_seconds or brief.get("duration_seconds") or 30.0)

    beats = _beats(script)
    if not beats:
        raise StoryboardError(
            "This script has no narration in it yet. Write or generate one first."
        )

    # A first pass to find beats that are too long to hold as one shot, then a
    # second allocation over the split list.
    rough = allocate_durations(beats, total_seconds=target, language=language)
    expanded: list[dict] = []
    for beat, seconds in zip(beats, rough):
        expanded.extend(_split_long(beat, seconds, language))

    durations = allocate_durations(expanded, total_seconds=target, language=language)

    keywords = script.get("keywords") or [brief.get("topic", "")]

    scenes: list[dict] = []
    start = 0.0
    for index, (beat, seconds) in enumerate(zip(expanded, durations)):
        scenes.append(
            {
                "position": index,
                "title": beat["title"],
                # The narration. This is what the voice reads and what the
                # subtitles are built from.
                "text": beat["text"],
                # Filled in properly by `describe_visuals`; this is the
                # deterministic fallback so a scene is never left with nothing
                # to search for.
                "visual_prompt": _fallback_prompt(beat, keywords),
                "source": _default_source(visual_mode),
                "start_seconds": round(start, 2),
                "duration_seconds": seconds,
                # No transition on the first scene — a fade from black at the
                # top of a short video wastes the only second that matters.
                "transition": "cut" if index == 0 else "fade",
                "settings": {
                    "role": beat["role"],
                    "visual_mode": visual_mode,
                    "overlay_text": _overlay_text(beat, visual_mode),
                },
            }
        )
        start += seconds

    return scenes


def _fallback_prompt(beat: dict, keywords: list[str]) -> str:
    """A visual description derived from the scene itself.

    Used when the model is unavailable or returns nothing for a scene. Not a
    placeholder — it is a real search query built from the subject keywords and
    the beat's own heading, which is enough to find usable stock.
    """
    subject = ", ".join(word for word in keywords[:3] if word)
    return f"{subject}, {beat['title'].lower()}".strip(", ") or beat["title"]


# ---------------------------------------------------------------------------
# Visual descriptions
# ---------------------------------------------------------------------------

_VISUAL_SYSTEM = (
    "You describe the single image that should be on screen while a line of "
    "narration is spoken. You write search-engine style descriptions of a "
    "photograph: subject, setting, lighting. Never describe text, logos, "
    "watermarks, split screens or collages. Never mention the narration. "
    "Return only the JSON object you are asked for."
)


async def describe_visuals(
    scenes: list[dict],
    *,
    script: dict,
    provider: AIProvider | None = None,
) -> list[dict]:
    """Give each scene a visual prompt, in one model call for the whole set.

    One call rather than one per scene: a twelve-scene video would otherwise be
    twelve round trips, and the model does a visibly better job when it can see
    the whole arc and avoid describing the same office desk twelve times.

    Best-effort. A failure leaves the deterministic prompts in place, because a
    storyboard with workable search queries is far better than no storyboard.
    """
    if not scenes:
        return scenes

    brief = script.get("brief") or {}
    if brief.get("visual_mode") == "animated":
        # Animated scenes are text on a generated background — there is nothing
        # to search for, and asking a model for photo descriptions here would
        # produce prompts nothing will ever use.
        return scenes

    from app.services.providers.factory import get_provider

    client = provider or get_provider()

    listing = "\n".join(
        f"{index + 1}. [{scene['settings'].get('role', 'scene')}] {scene['text'][:220]}"
        for index, scene in enumerate(scenes)
    )
    user = (
        f"TOPIC: {brief.get('topic', '')}\n"
        f"AUDIENCE: {brief.get('audience', '')}\n"
        f"TONE: {brief.get('tone', '')}\n\n"
        f"Here are {len(scenes)} scenes of narration:\n{listing}\n\n"
        f"For each one, describe the photograph that should be on screen. "
        f"Vary the subjects and settings across the list — do not describe the "
        f"same scene twice.\n\n"
        f'Return ONLY: {{"visuals": ["description for scene 1", '
        f'"description for scene 2", ...]}} with exactly {len(scenes)} entries.'
    )

    try:
        from app.config import settings as app_settings

        raw = await client.complete(
            system=_VISUAL_SYSTEM,
            user=user,
            max_tokens=app_settings.ai_max_tokens,
            temperature=0.8,
            json_mode=True,
            context={"feature": "video_visual_prompts", "scenes": len(scenes)},
        )
    except ProviderError as exc:
        logger.warning("Visual prompts unavailable, keeping fallbacks: %s", exc)
        return scenes

    from app.services.ai_service import _parse_json

    data = _parse_json(raw)
    visuals = data.get("visuals") if isinstance(data, dict) else None
    if not isinstance(visuals, list):
        logger.warning("Visual prompt response was not a list; keeping fallbacks")
        return scenes

    for scene, description in zip(scenes, visuals):
        text = re.sub(r"\s+", " ", str(description or "")).strip()[:500]
        if text:
            scene["visual_prompt"] = text
            # It now has something worth searching for.
            if scene["source"] == "pending":
                scene["source"] = "pending"

    return scenes


# ---------------------------------------------------------------------------
# Scenes → rows
# ---------------------------------------------------------------------------


def apply_scenes(
    db: Session,
    *,
    project: VideoProject,
    scenes: list[dict],
    commit: bool = True,
) -> list[VideoScene]:
    """Replace a project's storyboard with these scenes.

    A replace rather than a merge. Regenerating a storyboard from a changed
    script produces a different number of scenes in different places, and
    trying to reconcile that against the old rows produces neither the old
    storyboard nor the new one.

    Assets are deliberately **not** carried over, for the same reason: scene 3
    of the new script is not scene 3 of the old one, and silently inheriting a
    picture chosen for different words is worse than an empty scene.
    """
    db.execute(delete(VideoScene).where(VideoScene.project_id == project.id))

    rows: list[VideoScene] = []
    start = 0.0
    for position, scene in enumerate(scenes):
        duration = max(
            MIN_SCENE_SECONDS,
            min(float(scene.get("duration_seconds") or 5.0), MAX_SCENE_SECONDS),
        )
        source = scene.get("source")
        transition = scene.get("transition")

        row = VideoScene(
            project_id=project.id,
            position=position,
            title=(scene.get("title") or f"Scene {position + 1}")[:200],
            text=scene.get("text") or None,
            visual_prompt=scene.get("visual_prompt") or None,
            source=source if source in SCENE_SOURCES else "pending",
            asset_id=scene.get("asset_id"),
            voice_asset_id=scene.get("voice_asset_id"),
            start_seconds=round(start, 3),
            duration_seconds=round(duration, 3),
            transition=transition if transition in SCENE_TRANSITIONS else "cut",
            settings=dict(scene.get("settings") or {}),
        )
        db.add(row)
        rows.append(row)
        start += duration

    if commit:
        db.commit()
        for row in rows:
            db.refresh(row)
    else:
        db.flush()

    return rows


def load_scenes(db: Session, project_id: int) -> list[VideoScene]:
    return list(
        db.scalars(
            select(VideoScene)
            .where(VideoScene.project_id == project_id)
            .order_by(VideoScene.position, VideoScene.id)
        ).all()
    )


def resequence(db: Session, project_id: int, *, commit: bool = True) -> float:
    """Recompute every scene's `start_seconds` from the durations before it.

    Called after any edit that changes a duration or an order. `start_seconds`
    is stored rather than derived so the editor can lay scenes out without
    walking the list, which means it has to be maintained — and one function
    that does it is the only way it stays right.
    """
    start = 0.0
    for row in load_scenes(db, project_id):
        row.start_seconds = round(start, 3)
        start += row.duration_seconds
    if commit:
        db.commit()
    return round(start, 3)


# ---------------------------------------------------------------------------
# Scenes → the timeline
# ---------------------------------------------------------------------------


def build_timeline(
    db: Session,
    *,
    project: VideoProject,
    include_voice: bool = True,
    include_text: bool = True,
) -> dict:
    """Assemble the project's scenes into a real timeline document.

    **This is the join between the AI pipeline and the editor.** What comes out
    is an ordinary timeline — the same shape a person dragging clips would have
    produced, normalized by the same function, rendered by the same compositor.
    Nothing downstream can tell it was generated.

    Mapping, per scene:

      * its visual becomes a **video-track clip** (an image clip for a still, a
        video clip for footage), positioned at the scene's start and lasting
        the scene's duration. A scene with no visual yet leaves a gap, which
        renders as black — visible, obviously unfinished, and fixable in the
        editor rather than silently skipped.
      * its narration becomes an **audio-track clip**, when the voice step has
        run for that scene.
      * its on-screen text becomes a **text-track clip**.

    Existing music on the audio track is preserved: it was not put there by
    this pipeline, and rebuilding the visuals is not a reason to throw away a
    track somebody chose.
    """
    from app.models.video_asset import VideoAsset

    scenes = load_scenes(db, project.id)
    if not scenes:
        raise StoryboardError("This project has no scenes to build a timeline from.")

    previous = tl.normalize(project.timeline)
    # Music survives a rebuild; scene-derived narration does not, because it is
    # about to be regenerated from the scenes themselves.
    kept_audio = [
        clip
        for clip in tl.get_track(previous, "audio")["clips"]
        if clip.get("role") == "music"
    ]
    kept_audio.extend(_music_layers(db, project=project, already=kept_audio))

    asset_ids = [
        row.asset_id for row in scenes if row.asset_id
    ] + [row.voice_asset_id for row in scenes if row.voice_asset_id]
    assets = {
        asset.id: asset
        for asset in db.scalars(
            select(VideoAsset).where(
                VideoAsset.id.in_(asset_ids or [-1]),
                VideoAsset.user_id == project.user_id,
            )
        ).all()
    }

    video_clips: list[dict] = []
    audio_clips: list[dict] = list(kept_audio)
    text_clips: list[dict] = []

    for row in scenes:
        start = float(row.start_seconds)
        duration = float(row.duration_seconds)

        asset = assets.get(row.asset_id) if row.asset_id else None
        if asset is not None:
            is_video = asset.content_type.startswith("video/")
            video_clips.append(
                {
                    "kind": "video" if is_video else "image",
                    "asset_id": asset.id,
                    "start": start,
                    "duration": duration,
                    "label": row.title or "",
                    # `cover` so a source of any shape fills a vertical canvas
                    # rather than sitting in bars — which is what a generated
                    # video should look like without anyone adjusting it.
                    "fit": "cover",
                }
            )

        voice = assets.get(row.voice_asset_id) if row.voice_asset_id else None
        if include_voice and voice is not None:
            audio_clips.append(
                {
                    "kind": "audio",
                    "asset_id": voice.id,
                    "start": start,
                    # The narration's own length, not the scene's: a scene
                    # padded to a round number must not stretch or cut the
                    # voice-over that plays over it.
                    "duration": float(voice.duration_seconds or duration),
                    "role": "voiceover",
                    "label": row.title or "",
                }
            )

        overlay = (row.settings or {}).get("overlay_text")
        if include_text and (overlay or "").strip():
            text_clips.append(
                {
                    "kind": "text",
                    "text": overlay,
                    "start": start,
                    "duration": duration,
                    "position": "center"
                    if (row.settings or {}).get("visual_mode") == "animated"
                    else "bottom",
                    "animation": "fade",
                    "font_size": _text_size(project, row),
                }
            )

    document = {
        "version": tl.TIMELINE_VERSION,
        "tracks": [
            {"id": "video", "kind": "video", "label": "Video", "clips": video_clips},
            {"id": "audio", "kind": "audio", "label": "Audio", "clips": audio_clips},
            {"id": "text", "kind": "text", "label": "Text", "clips": text_clips},
        ],
    }

    # Through the same normalizer everything else uses — so a generated
    # timeline is subject to exactly the rules a hand-made one is.
    return tl.normalize(document)


def _music_layers(
    db: Session, *, project: VideoProject, already: list[dict]
) -> list[dict]:
    """Music added through the Music Library, as timeline clips.

    **This is a bridge between two places audio can legitimately live**, and it
    exists because they were built for different moments:

      * `VideoAudio` rows are the "attached but not placed" inbox. The Music
        Library's *Add to project* writes one, and it has to work before a
        timeline exists — you can pick a track for a project the moment it is
        created.
      * timeline clips are what the compositor renders.

    Without this, a track added from the library would be attached to the
    project, visible in its audio layers, and silently absent from the export.
    So the build folds those rows in, carrying their volume, fades and looping
    across, and records `audio_layer_id` on the clip so a second build
    recognises what it already imported rather than stacking a duplicate.

    A layer whose asset has gone is skipped: the row survives a deleted file by
    design (see `VideoAudio.asset_id`), but there is nothing to render.
    """
    from app.models.video_asset import VideoAsset
    from app.models.video_audio import VideoAudio

    imported = {
        clip.get("meta", {}).get("audio_layer_id")
        for clip in already
        if isinstance(clip.get("meta"), dict)
    }
    # Clips written before `meta` carried the id are matched on the asset, so
    # an older project does not gain a duplicate on its next build.
    imported_assets = {clip.get("asset_id") for clip in already}

    rows = db.scalars(
        select(VideoAudio)
        .where(VideoAudio.project_id == project.id, VideoAudio.role == "music")
        .order_by(VideoAudio.position, VideoAudio.id)
    ).all()

    out: list[dict] = []
    for row in rows:
        if row.id in imported or row.asset_id in imported_assets:
            continue
        if row.asset_id is None:
            # A catalogue track that streams from its source. The renderer
            # pulls its inputs from object storage, so there is nothing here it
            # could use — the track has to be uploaded or downloaded first.
            logger.info(
                "Skipping music layer %s on project %s: no stored audio",
                row.id, project.id,
            )
            continue
        asset = db.get(VideoAsset, row.asset_id)
        if asset is None or asset.user_id != project.user_id:
            continue

        out.append(
            {
                "kind": "audio",
                "asset_id": asset.id,
                "start": float(row.start_seconds or 0.0),
                "duration": float(
                    row.duration_seconds or asset.duration_seconds or 30.0
                ),
                "volume": float(row.volume),
                "fade_in": float(row.fade_in),
                "fade_out": float(row.fade_out),
                "muted": bool(row.muted),
                "role": "music",
                "label": row.label or "Music",
                "meta": {"audio_layer_id": row.id},
            }
        )

    return out


def _text_size(project: VideoProject, scene: VideoScene) -> int:
    """A readable caption size for this canvas.

    Proportional to the frame's short side rather than fixed: 48px is a title
    on a 1080-wide canvas and unreadable on a 4K one. Animated scenes go
    bigger, because there the text is the content.
    """
    short_side = min(project.width, project.height)
    fraction = 0.075 if (scene.settings or {}).get("visual_mode") == "animated" else 0.05
    return max(18, int(round(short_side * fraction)))


def storyboard_summary(db: Session, project: VideoProject) -> dict:
    """What the generation screen shows about progress.

    Counts rather than a percentage: "6 of 8 scenes have a visual" tells the
    user what to do next, where "75%" does not.
    """
    scenes = load_scenes(db, project.id)
    return {
        "scene_count": len(scenes),
        "with_visual": sum(1 for row in scenes if row.asset_id),
        "with_voice": sum(1 for row in scenes if row.voice_asset_id),
        "with_text": sum(
            1 for row in scenes if ((row.settings or {}).get("overlay_text") or "").strip()
        ),
        "duration_seconds": round(
            sum(float(row.duration_seconds) for row in scenes), 2
        ),
    }
