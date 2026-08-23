"""Smart Repurpose — one long video into several shorts.

    a 10-minute recording
        │
        ├─ transcribe ──▶ timed segments
        │
        ├─ find moments ─▶ candidate clips (hook, start, end, why)
        │                   ← the user reviews and edits these
        │
        └─ for each moment × each platform:
               a NEW project, with a timeline that trims the SAME source asset,
               framed vertically, hooked, captioned and signed off with a CTA
                   │
                   └─▶ the ordinary Video Editor, and the ordinary export

**The source is never modified, and never copied.** A short's timeline
references the original `VideoAsset` and trims it with `trim_start`/`trim_end`
— the clip arithmetic Task 6's timeline already does. Ten shorts from one
recording is one file in storage, and the original project (if there was one)
is not touched at any point: repurposing only ever *creates*.

**Vertical framing is real, not a promise.** A 16:9 source on a 9:16 canvas
with `fit="cover"` is scaled to fill and centre-cropped by the compositor's own
`place()`. The `focus_x` on a moment shifts that crop when the speaker is not
centred, and it is the same `x` offset the editor's inspector exposes — so a
generated framing can be nudged by hand afterwards.

**Nothing is published and nothing is rendered automatically.** The moments are
returned for review first; creating the projects is a second, explicit call;
exporting is the user pressing Export in the editor. Three deliberate steps,
because a tool that turns one upload into nine published videos on its own is a
tool nobody can trust.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.models.video_asset import VideoAsset
from app.models.video_project import VideoProject
from app.services.providers.base import AIProvider, ProviderError
from app.services.video import metering
from app.services.video import projects as project_service
from app.services.video import subtitles as subtitle_engine
from app.services.video import timeline as tl

logger = logging.getLogger(__name__)


class RepurposeError(RuntimeError):
    """A repurpose operation was refused. The message is user-facing."""


# The surfaces a long video is cut down for. Each names a platform preset, so
# the canvas comes from the same place every other project's does.
TARGETS: tuple[dict, ...] = (
    {
        "key": "youtube_shorts",
        "label": "YouTube Shorts",
        "platform": "youtube_shorts",
        "max_seconds": 60,
        "subtitle_style": "shorts",
    },
    {
        "key": "tiktok",
        "label": "TikTok",
        "platform": "tiktok",
        "max_seconds": 60,
        "subtitle_style": "tiktok",
    },
    {
        "key": "instagram_reels",
        "label": "Instagram Reels",
        "platform": "instagram_reels",
        "max_seconds": 90,
        "subtitle_style": "shorts",
    },
)

TARGETS_BY_KEY = {entry["key"]: entry for entry in TARGETS}

# What a clip has to be to be worth cutting. Under fifteen seconds there is no
# room for a hook and a payoff; over ninety it is not a short.
MIN_CLIP_SECONDS = 15.0
MAX_CLIP_SECONDS = 90.0

# How many candidates to ask for. More than a handful and the user is doing
# review work rather than choosing.
DEFAULT_MOMENT_COUNT = 5


# ---------------------------------------------------------------------------
# Finding the moments
# ---------------------------------------------------------------------------

_SYSTEM = (
    "You find the moments in a long video that work on their own as a short. "
    "A good moment is a complete thought: it makes one point and finishes it. "
    "You never invent content — every moment must correspond to timestamps in "
    "the transcript you are given. Return only the JSON object requested."
)


def _transcript_lines(segments: list[dict], *, limit: int = 400) -> str:
    """The transcript as timestamped lines the model can point at.

    Timestamps on every line, because the whole output is a set of time ranges
    and a model that has not seen the clock cannot produce them. Truncated for
    a very long recording — the alternative is a prompt that does not fit.
    """
    lines = []
    for segment in segments[:limit]:
        start = float(segment.get("start") or 0)
        lines.append(f"[{int(start // 60):02d}:{int(start % 60):02d}] {segment.get('text', '')}")
    return "\n".join(lines)


def _clamp_to_segments(
    start: float, end: float, segments: list[dict]
) -> tuple[float, float]:
    """Snap a time range out to the sentence boundaries around it.

    A model returns round numbers; speech does not start on them. Extending to
    the enclosing segments is what stops every short opening on half a word,
    which is the single most obvious way an auto-cut clip looks auto-cut.
    """
    if not segments:
        return start, end

    opening = None
    closing = None
    for segment in segments:
        seg_start = float(segment.get("start") or 0)
        seg_end = float(segment.get("end") or seg_start)
        # Half-open comparisons. `seg_start <= start <= seg_end` would match
        # the segment that *ends* exactly where the clip begins, dragging the
        # opening a whole sentence earlier for no reason — and, across a set of
        # evenly spaced clips, making every one of them overlap its neighbour.
        if seg_start <= start < seg_end or (opening is None and seg_start >= start):
            opening = opening if opening is not None else seg_start
        if seg_start < end <= seg_end:
            closing = seg_end
        elif seg_end <= end:
            closing = seg_end

    return (
        opening if opening is not None else start,
        closing if closing is not None and closing > (opening or start) else end,
    )


def _fallback_moments(
    segments: list[dict], *, count: int, duration: float
) -> list[dict]:
    """Evenly spaced clips, used when the model is unavailable.

    Not a placeholder: a recording cut into five complete, sentence-aligned
    chunks is a usable starting point that the user can retime. Returning
    nothing because a model was down would be worse.
    """
    if duration <= 0:
        return []

    span = min(MAX_CLIP_SECONDS, max(MIN_CLIP_SECONDS, duration / max(count, 1)))
    moments = []
    for index in range(count):
        start = index * (duration / max(count, 1))
        end = min(duration, start + span)
        if end - start < MIN_CLIP_SECONDS:
            break
        start, end = _clamp_to_segments(start, end, segments)
        text = _text_between(segments, start, end)
        moments.append(
            {
                "start": round(start, 2),
                "end": round(end, 2),
                "title": f"Clip {index + 1}",
                "hook": _first_sentence(text) or f"Part {index + 1}",
                "reason": "Evenly spaced — the transcript could not be analysed.",
                "cta": "Follow for the full video",
            }
        )
    return moments


def _first_sentence(text: str, limit: int = 90) -> str:
    sentence = re.split(r"(?<=[.!?])\s+", (text or "").strip())[0] if text else ""
    return sentence[:limit].strip()


def _text_between(segments: list[dict], start: float, end: float) -> str:
    return " ".join(
        str(segment.get("text") or "")
        for segment in segments
        if float(segment.get("start") or 0) >= start - 0.01
        and float(segment.get("end") or 0) <= end + 0.01
    ).strip()


async def find_moments(
    *,
    segments: list[dict],
    duration: float,
    count: int = DEFAULT_MOMENT_COUNT,
    provider: AIProvider | None = None,
) -> list[dict]:
    """Pick the sections of a recording worth cutting into shorts.

    Returns moments with a hook and a reason. Never raises for a model failure
    — it falls back to evenly spaced, sentence-aligned clips, because a list
    the user can retime beats an error message.
    """
    if not segments:
        raise RepurposeError(
            "There is no transcript to work from. Transcribe the video first."
        )

    from app.config import settings
    from app.services.providers.factory import get_provider

    client = provider or get_provider()
    wanted = max(1, min(count, 10))

    user = (
        f"This is the transcript of a {duration / 60:.1f}-minute video, with "
        f"timestamps.\n\n{_transcript_lines(segments)}\n\n"
        f"Find the {wanted} best sections to cut into standalone short videos. "
        f"Each must be between {MIN_CLIP_SECONDS:.0f} and {MAX_CLIP_SECONDS:.0f} "
        f"seconds long, and must be a complete thought.\n\n"
        f'Return ONLY: {{"moments": [{{"start_seconds": 0, "end_seconds": 30, '
        f'"title": "a short label", "hook": "the opening line to put on screen", '
        f'"reason": "why this works alone", "cta": "a short call to action"}}]}}'
    )

    try:
        raw = await client.complete(
            system=_SYSTEM,
            user=user,
            max_tokens=settings.ai_max_tokens,
            temperature=0.6,
            json_mode=True,
            context={"feature": "video_repurpose", "moments": wanted},
        )
    except ProviderError as exc:
        logger.warning("Moment detection unavailable, spacing evenly: %s", exc)
        return _fallback_moments(segments, count=wanted, duration=duration)

    from app.services.ai_service import _parse_json

    data = _parse_json(raw)
    raw_moments = data.get("moments") if isinstance(data, dict) else None
    if not isinstance(raw_moments, list) or not raw_moments:
        logger.warning("Moment detection returned nothing usable; spacing evenly")
        return _fallback_moments(segments, count=wanted, duration=duration)

    moments = []
    for index, entry in enumerate(raw_moments):
        if not isinstance(entry, dict):
            continue
        try:
            start = max(0.0, float(entry.get("start_seconds") or 0))
            end = float(entry.get("end_seconds") or 0)
        except (TypeError, ValueError):
            continue

        end = min(end, duration)
        if end - start < MIN_CLIP_SECONDS:
            # Extend rather than drop: a model that returned a ten-second span
            # found something there, it just under-cut it.
            end = min(duration, start + MIN_CLIP_SECONDS)
        if end - start > MAX_CLIP_SECONDS:
            end = start + MAX_CLIP_SECONDS
        if end - start < MIN_CLIP_SECONDS:
            continue

        start, end = _clamp_to_segments(start, end, segments)
        if end - start > MAX_CLIP_SECONDS:
            end = start + MAX_CLIP_SECONDS

        text = _text_between(segments, start, end)
        moments.append(
            {
                "start": round(start, 2),
                "end": round(end, 2),
                "title": str(entry.get("title") or f"Clip {index + 1}")[:120],
                "hook": str(entry.get("hook") or _first_sentence(text))[:120],
                "reason": str(entry.get("reason") or "")[:300],
                "cta": str(entry.get("cta") or "Follow for more")[:80],
                # The transcript of this span, so the short's captions come
                # from the recording rather than being transcribed again.
                "transcript": text[:5000],
                # Centre framing by default; the reviewer can shift it.
                "focus_x": 0.0,
            }
        )

    moments.sort(key=lambda item: item["start"])
    return moments or _fallback_moments(segments, count=wanted, duration=duration)


def overlaps(moments: list[dict]) -> list[tuple[int, int]]:
    """Pairs of moments that cover the same footage.

    Reported rather than silently merged: two shorts from overlapping spans is
    sometimes exactly what somebody wants (a long answer and the punchline
    inside it), and sometimes a mistake. The reviewer decides.
    """
    found = []
    ordered = sorted(range(len(moments)), key=lambda i: moments[i]["start"])
    for position, index in enumerate(ordered[:-1]):
        nxt = ordered[position + 1]
        if moments[nxt]["start"] < moments[index]["end"] - 0.5:
            found.append((index, nxt))
    return found


# ---------------------------------------------------------------------------
# Moments → projects
# ---------------------------------------------------------------------------


def _cues_for(moment: dict, segments: list[dict], style: dict) -> list[dict]:
    """Captions for a short, re-timed to start at zero.

    Taken from the original transcript rather than transcribed again: the words
    and their timings are already known, and re-running speech recognition on a
    slice of audio would cost money to produce a worse answer.
    """
    start = float(moment["start"])
    end = float(moment["end"])

    cues = []
    for segment in segments:
        seg_start = float(segment.get("start") or 0)
        seg_end = float(segment.get("end") or seg_start)
        if seg_end <= start or seg_start >= end:
            continue
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        cues.append(
            {
                "start": round(max(0.0, seg_start - start), 3),
                "end": round(min(end, seg_end) - start, 3),
                "text": text,
            }
        )

    if not cues:
        return []
    # Through the engine's own segment splitter, so a repurposed caption obeys
    # the same reading limits a transcribed one does. The limits come from the
    # style rather than the defaults — a TikTok caption wraps much shorter than
    # a YouTube one, and using the default here would produce lines that
    # overflow the frame they were styled for.
    return subtitle_engine.cues_from_segments(
        cues,
        max_chars_per_line=int(
            style.get("max_chars_per_line", subtitle_engine.DEFAULT_MAX_CHARS_PER_LINE)
        ),
        max_lines=int(style.get("max_lines", subtitle_engine.DEFAULT_MAX_LINES)),
    )


def build_short_timeline(
    *,
    moment: dict,
    source_asset: VideoAsset,
    project: VideoProject,
    include_hook: bool = True,
    include_cta: bool = True,
) -> dict:
    """The timeline for one short: a trimmed slice of the source, framed.

    One video clip referencing the original asset — not a copy — plus a hook
    at the top and a call to action at the end. Ordinary clips on the ordinary
    three tracks, so the editor can move, trim and restyle every one of them.
    """
    start = float(moment["start"])
    end = float(moment["end"])
    length = round(max(1.0, end - start), 3)

    short_side = min(project.width, project.height)

    video_clips = [
        {
            "kind": "video",
            "asset_id": source_asset.id,
            "start": 0.0,
            "duration": length,
            # The trim is what makes this a slice rather than a copy.
            "trim_start": round(start, 3),
            "trim_end": round(end, 3),
            # Fill the vertical canvas and centre-crop — real reframing, done
            # by the compositor's own placement maths.
            "fit": "cover",
            "x": float(moment.get("focus_x") or 0.0),
            "label": moment.get("title") or "Clip",
        }
    ]

    text_clips = []
    if include_hook and (moment.get("hook") or "").strip():
        text_clips.append(
            {
                "kind": "text",
                "text": moment["hook"],
                "start": 0.0,
                # Long enough to read, short enough to get out of the way.
                "duration": round(min(3.5, length / 2), 2),
                "position": "top",
                "animation": "slide-up",
                "font_size": max(20, int(short_side * 0.062)),
                "uppercase": True,
            }
        )

    if include_cta and (moment.get("cta") or "").strip() and length > 6:
        cta_length = round(min(3.0, length / 4), 2)
        text_clips.append(
            {
                "kind": "text",
                "text": moment["cta"],
                "start": round(length - cta_length, 2),
                "duration": cta_length,
                "position": "bottom",
                "animation": "fade",
                "font_size": max(16, int(short_side * 0.045)),
            }
        )

    return tl.normalize(
        {
            "version": tl.TIMELINE_VERSION,
            "tracks": [
                {"id": "video", "kind": "video", "label": "Video", "clips": video_clips},
                # The source's own audio rides with the video clip, so the
                # audio track starts empty — music is the user's choice.
                {"id": "audio", "kind": "audio", "label": "Audio", "clips": []},
                {"id": "text", "kind": "text", "label": "Text", "clips": text_clips},
            ],
        }
    )


def create_short(
    db: Session,
    *,
    user_id: int,
    moment: dict,
    target: str,
    source_asset: VideoAsset,
    segments: list[dict],
    source_project: VideoProject | None = None,
    name: str | None = None,
) -> VideoProject:
    """Make one short as a **new project**. Nothing existing is modified.

    The source project, if there is one, is only read — for its name. The
    source *asset* is shared by reference, which is both correct (it is the
    same footage) and the reason ten shorts cost one file of storage.
    """
    spec = TARGETS_BY_KEY.get(target)
    if spec is None:
        raise RepurposeError(f"{target} is not a platform this can cut for.")

    length = float(moment["end"]) - float(moment["start"])
    if length > spec["max_seconds"]:
        raise RepurposeError(
            f"{spec['label']} allows {spec['max_seconds']} seconds; this clip is "
            f"{length:.0f}. Shorten it before creating."
        )

    label = (
        name
        or f"{moment.get('title') or 'Clip'} — {spec['label']}"
    )[:200]

    project = project_service.create_project(
        db,
        user_id=user_id,
        name=label,
        project_type="repurpose",
        platform=spec["platform"],
        apply_brand=True,
    )

    timeline = build_short_timeline(
        moment=moment, source_asset=source_asset, project=project
    )

    # Where this came from, recorded on the project so the editor can show it
    # and so a second pass can tell a repurposed project from an original.
    provenance = {
        "kind": "repurpose",
        "source_asset_id": source_asset.id,
        "source_project_id": source_project.id if source_project else None,
        "source_name": (source_project.name if source_project else source_asset.title),
        "moment": {
            key: moment.get(key)
            for key in ("start", "end", "title", "hook", "reason", "cta", "focus_x")
        },
        "target": target,
    }

    project_service.update_project(
        db,
        project=project,
        patch={"timeline": timeline, "script": provenance},
    )

    # Captions, from the transcript we already have.
    style = subtitle_engine.preset(spec["subtitle_style"])
    cues = _cues_for(moment, segments, style)
    if cues:
        from sqlalchemy import select

        from app.models.video_subtitle import VideoSubtitle

        track = db.scalars(
            select(VideoSubtitle)
            .where(VideoSubtitle.project_id == project.id)
            .order_by(VideoSubtitle.id)
        ).first()
        if track is None:
            track = VideoSubtitle(project_id=project.id, is_primary=True)
            db.add(track)
        track.source = "repurpose"
        track.cues = cues
        track.style = style
        track.cue_count = len(cues)
        track.duration_seconds = subtitle_engine.total_duration(cues)
        db.commit()

    # One row per clip actually produced. Metered here rather than at analysis
    # time because analysing is cheap and reversible — what a plan would charge
    # for is the shorts somebody kept.
    metering.record(
        db,
        user_id=user_id,
        metric="repurpose_clips",
        quantity=1,
        source="repurpose",
        project_id=project.id,
        meta={
            "target": target,
            "source_asset_id": source_asset.id,
            "seconds": round(float(moment["end"]) - float(moment["start"]), 2),
        },
    )

    logger.info(
        "Repurposed asset %s [%.1f-%.1f] into project %s for %s",
        source_asset.id, moment["start"], moment["end"], project.id, target,
    )
    return project


def targets() -> list[dict]:
    return [dict(entry) for entry in TARGETS]
