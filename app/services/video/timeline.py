"""The timeline document — the single thing the editor, the preview and the
renderer all read.

This module is the reason the editor is not a mock. There is exactly one
representation of what a video contains, it lives in `VideoProject.timeline`,
and everything downstream is a pure function of it:

    editor  ──edits──▶  timeline  ──▶  preview  (frontend reads the same doc)
                            └────────▶  compositor  ──▶  ffmpeg  ──▶  the file

`queue_render` snapshots this document, so what is encoded is what was on the
screen. No separate preview model exists to drift from it, and there is nowhere
for one to be introduced: the compositor takes a normalized timeline and
nothing else.

**The MVP shape: three tracks, and what each one means.**

    video   a *sequence*. Clips never overlap — one video track can only show
            one thing at a time, so an edit that would overlap is refused or
            rippled. Gaps render as black.
    audio   a *mix*. Voice-over and music are both here and are supposed to
            play together, so overlap is not only allowed, it is the point.
    text    *overlays*. Titles and captions drawn over the composited video,
            stacked in list order. Overlap is allowed.

That difference is not cosmetic — it is why `_settle` treats the tracks
differently, and it is exactly what the ffmpeg graph does downstream
(concat-by-overlay for video, `amix` for audio, chained `drawtext` for text).

**Every operation is pure.** `add_clip`, `move_clip`, `trim_clip`,
`split_clip`, `delete_clip`, `reorder_clips` and `update_clip` take a timeline
and return a new one. They never touch the database. That is what makes them
testable in milliseconds, what lets the undo stack be a list of documents, and
what lets the same code run in a request and in a background worker.

**Normalization is not optional.** Anything read from the database goes through
`normalize` first: it repairs a legacy document, fills in defaults so an older
client's clip still renders, coerces every number, and sorts. The renderer can
then assume a clean document instead of defending against every field being
absent — which is how a renderer ends up with a different idea of the video
than the editor has.
"""
from __future__ import annotations

import secrets
from copy import deepcopy

# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------

TIMELINE_VERSION = 2

# The three tracks, in the order the editor stacks them top to bottom. Fixed
# for the MVP on purpose: "one video, one audio, one text track that work
# reliably" is a shippable editor, and an arbitrary number of tracks is a
# different and much larger compositor.
TRACKS: tuple[dict, ...] = (
    {"id": "video", "kind": "video", "label": "Video"},
    {"id": "audio", "kind": "audio", "label": "Audio"},
    {"id": "text", "kind": "text", "label": "Text"},
)

TRACK_IDS = tuple(track["id"] for track in TRACKS)

# What may sit on each track. An image and a video clip share the video track
# because they occupy the same role — something visible for a stretch of time —
# and separating them would make "replace this photo with the clip I shot" a
# cross-track move for no reason.
TRACK_CLIP_KINDS: dict[str, tuple[str, ...]] = {
    "video": ("video", "image"),
    "audio": ("audio",),
    "text": ("text",),
}

CLIP_KINDS = tuple(kind for kinds in TRACK_CLIP_KINDS.values() for kind in kinds)

# Tracks whose clips must not overlap. See the module docstring.
SEQUENTIAL_TRACKS = frozenset({"video"})

# Bounds. These are not style preferences — they are what keeps a hand-written
# API call from producing a filter graph that hangs ffmpeg or an export that
# blows the duration cap.
MIN_CLIP_SECONDS = 0.05
MAX_CLIP_SECONDS = 3600.0
# Nothing else bounds how many clips a track may hold, and both the stored
# document and the render command grow with it. A 500-clip track is already far
# past any edit this MVP is for.
MAX_CLIPS_PER_TRACK = 500
MIN_SPEED = 0.25
MAX_SPEED = 4.0

# How a text clip can enter. Deliberately the same vocabulary Subtitle Studio
# offers (see `subtitles.SUBTITLE_ANIMATIONS`), minus the two that need
# word-level timings, which a hand-typed title does not have. A shared list is
# what stops the editor offering an animation the renderer cannot draw.
TEXT_ANIMATIONS = ("none", "fade", "pop", "slide-up")

TEXT_POSITIONS = ("top", "center", "bottom")
TEXT_ALIGNMENTS = ("left", "center", "right")

# How a clip fills a canvas of a different shape.
FIT_MODES = ("cover", "contain")


class TimelineError(ValueError):
    """An edit was refused. The message is shown to the user."""


def new_clip_id() -> str:
    """An id unique within a document, and stable across a save.

    Random rather than sequential: the undo stack, the preview and the renderer
    all address clips by id, and an id derived from a position would change
    meaning the moment anything moved.
    """
    return f"c_{secrets.token_urlsafe(8)}"


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
# Every field a clip can carry, with the value used when it is absent. A clip
# written by an older build therefore still renders — it does not arrive at the
# compositor with no scale and no volume.

_COMMON_DEFAULTS: dict = {
    "start": 0.0,
    "duration": 5.0,
    # The in/out points inside the source. `trim_end` None means "to the end of
    # the source", which is what a freshly added clip wants before anything is
    # known about how long it will stay.
    "trim_start": 0.0,
    "trim_end": None,
    "label": "",
    "locked": False,
    # Provenance — where this clip came from, when something else needs to
    # recognise it later. The music bridge in storyboard.py stamps the
    # `VideoAudio` row id here so a rebuild can tell an already-imported track
    # from a new one. Not client-editable (see `_EDITABLE`): a client that
    # could rewrite this could make a rebuild duplicate every music layer.
    "meta": {},
}

_VISUAL_DEFAULTS: dict = {
    # Transform. `scale` multiplies the fitted size, so 1.0 is "as the fit mode
    # decided" and the user's zoom is relative to something sensible.
    "scale": 1.0,
    # Offset from centre, as a fraction of the canvas. Fractions rather than
    # pixels so a project resized from 1080p to 720p keeps its composition.
    "x": 0.0,
    "y": 0.0,
    "rotation": 0.0,
    "opacity": 1.0,
    # Fractions of the source cropped away from each edge.
    "crop": {"left": 0.0, "top": 0.0, "right": 0.0, "bottom": 0.0},
    "fit": "cover",
    "speed": 1.0,
    # A video clip carries its own audio; an image has none and ignores this.
    "volume": 1.0,
    "muted": False,
}

_AUDIO_DEFAULTS: dict = {
    "volume": 1.0,
    "fade_in": 0.0,
    "fade_out": 0.0,
    "muted": False,
    "speed": 1.0,
    # Which of the two things on this track it is. Not a separate track (the
    # MVP has one), but the renderer still needs to know what to duck under
    # what, and the editor colours them differently.
    "role": "music",
}

_TEXT_DEFAULTS: dict = {
    "text": "",
    "font_family": "Inter",
    "font_size": 48,
    "font_weight": 700,
    "color": "#FFFFFF",
    "background": "transparent",
    "outline": "#000000",
    "outline_width": 2,
    "position": "center",
    "align": "center",
    # Fine offset from the named position, as canvas fractions.
    "x": 0.0,
    "y": 0.0,
    "animation": "none",
    "uppercase": False,
}

AUDIO_ROLES = ("voiceover", "music", "sfx")


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------
# Every value that reaches the renderer goes through one of these. A string
# "1.5" from a form, a None from an older client and a NaN from a broken client
# all have to become a number the filter graph can be built from — the
# alternative is an ffmpeg command with the word "None" in it.


def _number(value, fallback: float, low: float, high: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return fallback
    if result != result:  # NaN — never equal to itself
        return fallback
    return max(low, min(result, high))


def _boolean(value, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    if value is None:
        return fallback
    return bool(value)


def _choice(value, allowed: tuple[str, ...], fallback: str) -> str:
    text = str(value or "").strip().lower()
    return text if text in allowed else fallback


def _colour(value, fallback: str) -> str:
    """A colour the filter graph can use, or the fallback.

    Accepts `#rgb`, `#rrggbb`, `#rrggbbaa` and the literal "transparent".
    Anything else is refused rather than passed through: an unvalidated string
    here lands inside an ffmpeg filter argument, where a stray quote or colon
    changes the meaning of the whole graph.
    """
    text = str(value or "").strip()
    if text.lower() == "transparent":
        return "transparent"
    if text.startswith("#"):
        body = text[1:]
        if len(body) in (3, 6, 8) and all(
            character in "0123456789abcdefABCDEF" for character in body
        ):
            return f"#{body.upper()}"
    # rgba(...) is what the subtitle presets use, so it has to survive.
    lowered = text.lower().replace(" ", "")
    if lowered.startswith("rgba(") and lowered.endswith(")"):
        parts = lowered[5:-1].split(",")
        if len(parts) == 4:
            try:
                red, green, blue = (max(0, min(255, int(float(p)))) for p in parts[:3])
                alpha = max(0.0, min(1.0, float(parts[3])))
            except ValueError:
                return fallback
            return f"#{red:02X}{green:02X}{blue:02X}{round(alpha * 255):02X}"
    return fallback


def _crop(value) -> dict:
    """Crop fractions, clamped so opposite edges cannot meet.

    Left+right below 1.0 (and top+bottom likewise) is the invariant: a crop
    that removes the whole frame produces a zero-width scale filter, which
    ffmpeg rejects with an error nobody can act on.
    """
    source = value if isinstance(value, dict) else {}
    box = {
        edge: _number(source.get(edge), 0.0, 0.0, 0.95)
        for edge in ("left", "top", "right", "bottom")
    }
    for a, b in (("left", "right"), ("top", "bottom")):
        if box[a] + box[b] > 0.95:
            # Scale both back proportionally rather than zeroing them, so a
            # crop dragged too far settles at the limit instead of jumping
            # back to nothing.
            excess = 0.95 / (box[a] + box[b])
            box[a] = round(box[a] * excess, 4)
            box[b] = round(box[b] * excess, 4)
    return box


# ---------------------------------------------------------------------------
# Clip normalization
# ---------------------------------------------------------------------------


def normalize_clip(raw: dict, *, track_id: str) -> dict:
    """One clip, complete and in range, whatever arrived.

    The returned dict is what the compositor is entitled to assume: every key
    present, every number finite and clamped, ids assigned. It is also what the
    frontend preview reads, so the two cannot disagree about a default.
    """
    if not isinstance(raw, dict):
        raise TimelineError("A clip must be an object.")

    allowed = TRACK_CLIP_KINDS.get(track_id, ())
    kind = _choice(raw.get("kind"), allowed, allowed[0] if allowed else "video")

    clip: dict = {
        "id": str(raw.get("id") or "").strip() or new_clip_id(),
        "kind": kind,
        "track": track_id,
        # None is legitimate: a text clip has no asset, and a clip whose asset
        # was deleted keeps its place on the timeline rather than vanishing.
        "asset_id": _asset_id(raw.get("asset_id")),
    }

    for field, fallback in _COMMON_DEFAULTS.items():
        clip[field] = raw.get(field, fallback)

    clip["start"] = _number(clip["start"], 0.0, 0.0, MAX_CLIP_SECONDS)
    clip["duration"] = _number(
        clip["duration"], 5.0, MIN_CLIP_SECONDS, MAX_CLIP_SECONDS
    )
    clip["trim_start"] = _number(clip["trim_start"], 0.0, 0.0, MAX_CLIP_SECONDS)
    clip["trim_end"] = (
        None
        if clip["trim_end"] is None
        else _number(clip["trim_end"], 0.0, 0.0, MAX_CLIP_SECONDS)
    )
    # An inverted trim is not a clamp away from being valid — it is a bug in
    # whatever sent it, and honouring it would ask ffmpeg for negative frames.
    if clip["trim_end"] is not None and clip["trim_end"] <= clip["trim_start"]:
        clip["trim_end"] = None
    clip["label"] = str(clip.get("label") or "")[:120]
    clip["locked"] = _boolean(clip.get("locked"))
    clip["meta"] = clip["meta"] if isinstance(clip.get("meta"), dict) else {}

    if kind in ("video", "image"):
        _apply_visual(clip, raw)
    elif kind == "audio":
        _apply_audio(clip, raw)
    elif kind == "text":
        _apply_text(clip, raw)

    return clip


def _asset_id(value) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _apply_visual(clip: dict, raw: dict) -> None:
    for field, fallback in _VISUAL_DEFAULTS.items():
        clip[field] = raw.get(field, fallback)

    clip["scale"] = _number(clip["scale"], 1.0, 0.05, 10.0)
    clip["x"] = _number(clip["x"], 0.0, -2.0, 2.0)
    clip["y"] = _number(clip["y"], 0.0, -2.0, 2.0)
    clip["rotation"] = _number(clip["rotation"], 0.0, -360.0, 360.0)
    clip["opacity"] = _number(clip["opacity"], 1.0, 0.0, 1.0)
    clip["crop"] = _crop(clip["crop"])
    clip["fit"] = _choice(clip["fit"], FIT_MODES, "cover")
    clip["speed"] = _number(clip["speed"], 1.0, MIN_SPEED, MAX_SPEED)
    clip["volume"] = _number(clip["volume"], 1.0, 0.0, 4.0)
    clip["muted"] = _boolean(clip["muted"])

    # A still has no timebase, so speed means nothing to it. Forced to 1.0
    # rather than ignored downstream, so the editor and the renderer agree
    # about what an image clip's duration means.
    if clip["kind"] == "image":
        clip["speed"] = 1.0
        clip["volume"] = 0.0
        clip["muted"] = True


def _apply_audio(clip: dict, raw: dict) -> None:
    for field, fallback in _AUDIO_DEFAULTS.items():
        clip[field] = raw.get(field, fallback)

    clip["volume"] = _number(clip["volume"], 1.0, 0.0, 4.0)
    clip["speed"] = _number(clip["speed"], 1.0, MIN_SPEED, MAX_SPEED)
    clip["muted"] = _boolean(clip["muted"])
    clip["role"] = _choice(clip["role"], AUDIO_ROLES, "music")

    # Fades are clamped to the clip. A two-second fade on a one-second clip is
    # not a fade, and `afade` given one produces silence.
    half = max(MIN_CLIP_SECONDS, clip["duration"] / 2)
    clip["fade_in"] = _number(clip["fade_in"], 0.0, 0.0, half)
    clip["fade_out"] = _number(clip["fade_out"], 0.0, 0.0, half)


def _apply_text(clip: dict, raw: dict) -> None:
    for field, fallback in _TEXT_DEFAULTS.items():
        clip[field] = raw.get(field, fallback)

    # Newlines survive (a title card is often two lines); control characters do
    # not, because they reach a drawtext argument.
    text = str(clip.get("text") or "")
    clip["text"] = "".join(
        character
        for character in text
        if character == "\n" or character >= " "
    )[:500]

    clip["font_size"] = int(_number(clip["font_size"], 48, 8, 400))
    clip["font_weight"] = int(_number(clip["font_weight"], 700, 100, 900))
    clip["color"] = _colour(clip["color"], "#FFFFFF")
    clip["background"] = _colour(clip["background"], "transparent")
    clip["outline"] = _colour(clip["outline"], "#000000")
    clip["outline_width"] = int(_number(clip["outline_width"], 2, 0, 20))
    clip["position"] = _choice(clip["position"], TEXT_POSITIONS, "center")
    clip["align"] = _choice(clip["align"], TEXT_ALIGNMENTS, "center")
    clip["x"] = _number(clip["x"], 0.0, -1.0, 1.0)
    clip["y"] = _number(clip["y"], 0.0, -1.0, 1.0)
    clip["animation"] = _choice(clip["animation"], TEXT_ANIMATIONS, "none")
    clip["uppercase"] = _boolean(clip["uppercase"])

    font = str(clip.get("font_family") or "").strip()
    clip["font_family"] = font[:60] or "Inter"


# ---------------------------------------------------------------------------
# Document normalization
# ---------------------------------------------------------------------------


def empty_timeline() -> dict:
    """A new, valid, empty document."""
    return {
        "version": TIMELINE_VERSION,
        "tracks": [{**track, "clips": []} for track in TRACKS],
    }


def normalize(timeline: dict | None) -> dict:
    """A complete, ordered, in-range document — whatever came in.

    Handles three cases that all reach this function in practice:

      * `None` or `{}` — a project that has never been edited.
      * A **version 1 document**, which had four tracks: text, video, audio and
        subtitles. Subtitle clips are folded into the text track, because the
        MVP editor has one text track and dropping them would silently delete
        somebody's captions.
      * A version 2 document with fields missing, from an older client.

    Unknown tracks are discarded, not preserved. Keeping them would mean the
    renderer receiving clips it has no filter for, and a document that grows a
    track nobody can see or delete.
    """
    source = timeline if isinstance(timeline, dict) else {}
    incoming = source.get("tracks")
    incoming = incoming if isinstance(incoming, list) else []

    by_id: dict[str, list] = {track_id: [] for track_id in TRACK_IDS}

    for track in incoming:
        if not isinstance(track, dict):
            continue
        track_id = str(track.get("id") or "").strip().lower()
        # v1's "subtitles" track becomes text. See the docstring.
        if track_id == "subtitles":
            track_id = "text"
        if track_id not in by_id:
            continue
        clips = track.get("clips")
        if isinstance(clips, list):
            by_id[track_id].extend(clip for clip in clips if isinstance(clip, dict))

    tracks = []
    seen_ids: set[str] = set()
    for spec in TRACKS:
        clips = []
        # Whole documents arrive here too — a PUT of the timeline, or a
        # migration of an older one — so the cap `add_clip` enforces has to hold
        # on this path as well, or it is one endpoint away from meaningless.
        for raw in by_id[spec["id"]][:MAX_CLIPS_PER_TRACK]:
            clip = normalize_clip(raw, track_id=spec["id"])
            # Two clips with the same id would make every edit ambiguous —
            # `move_clip` would move whichever the search hit first.
            if clip["id"] in seen_ids:
                clip["id"] = new_clip_id()
            seen_ids.add(clip["id"])
            clips.append(clip)
        tracks.append({**spec, "clips": clips})

    document = {"version": TIMELINE_VERSION, "tracks": tracks}
    return _settle(document)


def _settle(timeline: dict) -> dict:
    """Order the clips, and make the sequential tracks actually sequential.

    Sorting is by start, then by id — the id tiebreak matters because two clips
    at the same start would otherwise swap places on every save, which shows up
    as a timeline that reshuffles when nothing was edited.

    On the video track, overlaps are removed by pushing later clips right. That
    is a *repair* of an already-invalid document (a bad import, a concurrent
    edit), not the normal path: `move_clip` refuses an overlapping move up
    front so the user gets told, rather than having their clip silently slide
    somewhere they did not put it.
    """
    for track in timeline["tracks"]:
        clips = sorted(track["clips"], key=lambda clip: (clip["start"], clip["id"]))

        if track["id"] in SEQUENTIAL_TRACKS:
            cursor = 0.0
            for clip in clips:
                if clip["start"] < cursor - 1e-6:
                    clip["start"] = round(cursor, 3)
                cursor = clip["start"] + clip["duration"]

        for clip in clips:
            clip["start"] = round(clip["start"], 3)
            clip["duration"] = round(clip["duration"], 3)

        track["clips"] = clips

    return timeline


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def get_track(timeline: dict, track_id: str) -> dict:
    for track in timeline["tracks"]:
        if track["id"] == track_id:
            return track
    raise TimelineError(f"There is no {track_id!r} track.")


def find_clip(timeline: dict, clip_id: str) -> tuple[dict, dict]:
    """`(track, clip)` for an id, or a refusal naming what was not found."""
    for track in timeline["tracks"]:
        for clip in track["clips"]:
            if clip["id"] == clip_id:
                return track, clip
    raise TimelineError("That clip is no longer on the timeline.")


def duration(timeline: dict) -> float:
    """Where the last clip on any track ends."""
    longest = 0.0
    for track in timeline["tracks"]:
        for clip in track["clips"]:
            longest = max(longest, clip["start"] + clip["duration"])
    return round(longest, 3)


def asset_ids(timeline: dict) -> list[int]:
    """Every asset the timeline references, once each, in timeline order.

    The renderer resolves these to files up front so a missing one is reported
    as `missing_asset` before any encoding starts, rather than as an ffmpeg
    error eight minutes in.
    """
    found: list[int] = []
    for track in timeline["tracks"]:
        for clip in track["clips"]:
            if clip["asset_id"] and clip["asset_id"] not in found:
                found.append(clip["asset_id"])
    return found


def is_empty(timeline: dict) -> bool:
    return not any(track["clips"] for track in timeline["tracks"])


def summary(timeline: dict) -> dict:
    """Counts and length, for the projects list and the export dialog."""
    counts = {track["id"]: len(track["clips"]) for track in timeline["tracks"]}
    return {
        "duration_seconds": duration(timeline),
        "clip_counts": counts,
        "total_clips": sum(counts.values()),
        "has_video": counts.get("video", 0) > 0,
        "has_audio": counts.get("audio", 0) > 0,
        "has_text": counts.get("text", 0) > 0,
    }


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------
# All pure: timeline in, new timeline out. The caller decides whether to save.


def _overlap(clips: list[dict], *, start: float, end: float, ignore: str | None) -> dict | None:
    """The first clip covering any of `[start, end)`, or None."""
    for clip in clips:
        if clip["id"] == ignore:
            continue
        clip_end = clip["start"] + clip["duration"]
        if start < clip_end - 1e-6 and clip["start"] < end - 1e-6:
            return clip
    return None


def _append_position(track: dict) -> float:
    """Where a new clip goes when no position was given: after the last one."""
    if not track["clips"]:
        return 0.0
    last = track["clips"][-1]
    return round(last["start"] + last["duration"], 3)


def add_clip(
    timeline: dict,
    *,
    track_id: str,
    clip: dict,
    at: float | None = None,
) -> tuple[dict, dict]:
    """Put a clip on a track. Returns the new timeline and the clip added.

    `at` None means "after the last clip on this track", which is what dropping
    a file into the editor should do — appending is the overwhelmingly common
    intent, and making the caller compute the end itself invites two callers to
    compute it differently.

    On the video track a position that would overlap is refused rather than
    nudged. The user picked a spot; silently moving their clip somewhere else
    is worse than saying it will not fit.
    """
    document = deepcopy(timeline)
    track = get_track(document, track_id)

    # The timeline is stored as JSON on the project row and becomes one ffmpeg
    # filter chain at render time, so an unbounded track is both a row that
    # grows without limit and a command that eventually will not run. This cap
    # is far above any real edit; it exists so there is a limit at all.
    if len(track["clips"]) >= MAX_CLIPS_PER_TRACK:
        raise TimelineError(
            f"A track holds at most {MAX_CLIPS_PER_TRACK} clips. "
            "Delete something before adding more."
        )

    prepared = normalize_clip({**clip, "id": clip.get("id") or new_clip_id()}, track_id=track_id)
    prepared["start"] = (
        _append_position(track)
        if at is None
        else _number(at, 0.0, 0.0, MAX_CLIP_SECONDS)
    )

    if track_id in SEQUENTIAL_TRACKS:
        end = prepared["start"] + prepared["duration"]
        clash = _overlap(track["clips"], start=prepared["start"], end=end, ignore=None)
        if clash is not None:
            raise TimelineError(
                "There is already a clip there. Move it, or drop this one after it."
            )

    track["clips"].append(prepared)
    return _settle(document), prepared


def move_clip(timeline: dict, *, clip_id: str, start: float) -> dict:
    """Slide a clip along its own track.

    Cross-track moves are not offered: with one track per kind there is nowhere
    else for a clip to go, and pretending otherwise would mean an audio clip
    could be dropped on the video track.
    """
    document = deepcopy(timeline)
    track, clip = find_clip(document, clip_id)

    if clip["locked"]:
        raise TimelineError(f"“{clip['label'] or 'That clip'}” is locked.")

    new_start = _number(start, clip["start"], 0.0, MAX_CLIP_SECONDS)

    if track["id"] in SEQUENTIAL_TRACKS:
        clash = _overlap(
            track["clips"],
            start=new_start,
            end=new_start + clip["duration"],
            ignore=clip_id,
        )
        if clash is not None:
            raise TimelineError(
                "That would overlap another clip. Video clips play one at a time."
            )

    clip["start"] = new_start
    return _settle(document)


def trim_clip(
    timeline: dict,
    *,
    clip_id: str,
    edge: str,
    to: float,
) -> dict:
    """Drag one end of a clip. `edge` is "start" or "end"; `to` is on the
    project clock.

    The two edges do different things, and conflating them is the classic way a
    trim goes wrong:

      * dragging the **end** changes how much of the source is used, keeping
        the in-point;
      * dragging the **start** moves the clip *and* its in-point together, so
        the frames under the playhead do not slide.

    Speed is accounted for in both: a clip at 2× consumes two seconds of source
    for every second of timeline, so trimming one second off the timeline
    advances the source in-point by two.
    """
    if edge not in ("start", "end"):
        raise TimelineError("A clip can only be trimmed at its start or its end.")

    document = deepcopy(timeline)
    track, clip = find_clip(document, clip_id)

    if clip["locked"]:
        raise TimelineError(f"“{clip['label'] or 'That clip'}” is locked.")

    speed = clip.get("speed", 1.0) or 1.0
    target = _number(to, clip["start"], 0.0, MAX_CLIP_SECONDS)
    clip_end = clip["start"] + clip["duration"]

    if edge == "end":
        new_duration = target - clip["start"]
        if new_duration < MIN_CLIP_SECONDS:
            raise TimelineError("A clip cannot be trimmed away entirely.")
        clip["duration"] = round(new_duration, 3)
        # The out-point follows the new length, in source time.
        clip["trim_end"] = round(clip["trim_start"] + new_duration * speed, 3)
    else:
        new_duration = clip_end - target
        if new_duration < MIN_CLIP_SECONDS:
            raise TimelineError("A clip cannot be trimmed away entirely.")
        consumed = (target - clip["start"]) * speed
        new_trim_start = clip["trim_start"] + consumed
        if new_trim_start < 0:
            # Dragging left past the head of the source: the clip can start
            # earlier on the timeline, but there are no frames before frame
            # zero, so the in-point stops there.
            raise TimelineError("There is no more of this clip before that point.")
        clip["trim_start"] = round(new_trim_start, 3)
        if clip["trim_end"] is not None:
            clip["trim_end"] = round(clip["trim_start"] + new_duration * speed, 3)
        clip["start"] = round(target, 3)
        clip["duration"] = round(new_duration, 3)

    if track["id"] in SEQUENTIAL_TRACKS:
        clash = _overlap(
            track["clips"],
            start=clip["start"],
            end=clip["start"] + clip["duration"],
            ignore=clip_id,
        )
        if clash is not None:
            raise TimelineError("That would overlap the next clip.")

    return _settle(document)


def split_clip(timeline: dict, *, clip_id: str, at: float) -> tuple[dict, list[str]]:
    """Cut a clip in two at a point on the project clock.

    Returns the new timeline and the two resulting clip ids, left first. The
    left half keeps the original id so anything holding a selection still has
    something to point at.

    The right half's in-point is advanced by however much source the left half
    consumed, which is where speed matters again — splitting a 2× clip halfway
    along the timeline advances the source by twice that.
    """
    document = deepcopy(timeline)
    _track, clip = find_clip(document, clip_id)

    if clip["locked"]:
        raise TimelineError(f"“{clip['label'] or 'That clip'}” is locked.")

    point = _number(at, 0.0, 0.0, MAX_CLIP_SECONDS)
    offset = point - clip["start"]

    if offset < MIN_CLIP_SECONDS or offset > clip["duration"] - MIN_CLIP_SECONDS:
        raise TimelineError(
            "Move the playhead further into the clip before splitting it."
        )

    speed = clip.get("speed", 1.0) or 1.0
    consumed = offset * speed

    right = deepcopy(clip)
    right["id"] = new_clip_id()
    right["start"] = round(point, 3)
    right["duration"] = round(clip["duration"] - offset, 3)
    right["trim_start"] = round(clip["trim_start"] + consumed, 3)
    # `trim_end` unchanged: the right half runs to wherever the original did.

    clip["duration"] = round(offset, 3)
    clip["trim_end"] = round(clip["trim_start"] + consumed, 3)

    # A fade-out belongs to the end of the original, which is now the right
    # half's end; a fade-in belongs to the left. Splitting without this gives
    # both halves both fades, which is audible.
    if clip["kind"] == "audio":
        clip["fade_out"] = 0.0
        right["fade_in"] = 0.0

    track = get_track(document, clip["track"])
    track["clips"].append(right)

    return _settle(document), [clip["id"], right["id"]]


def delete_clip(timeline: dict, *, clip_id: str, ripple: bool = False) -> dict:
    """Remove a clip.

    `ripple` closes the gap by pulling later clips on the same track back. Off
    by default: leaving a hole is what most edits want, and silently resyncing
    everything after the deletion point is a surprising amount of movement for
    one keystroke.
    """
    document = deepcopy(timeline)
    track, clip = find_clip(document, clip_id)

    if clip["locked"]:
        raise TimelineError(f"“{clip['label'] or 'That clip'}” is locked.")

    gap_start = clip["start"]
    gap = clip["duration"]

    track["clips"] = [row for row in track["clips"] if row["id"] != clip_id]

    if ripple:
        for row in track["clips"]:
            if row["start"] >= gap_start:
                row["start"] = round(max(0.0, row["start"] - gap), 3)

    return _settle(document)


def reorder_clips(timeline: dict, *, track_id: str, clip_ids: list[str]) -> dict:
    """Lay a sequential track's clips out in a given order, back to back.

    Only meaningful for the video track, which is a sequence — reordering a mix
    means nothing, because the clips are not in a queue. Every clip currently
    on the track must appear exactly once, so a partial list cannot silently
    drop the clips it forgot to mention.
    """
    if track_id not in SEQUENTIAL_TRACKS:
        raise TimelineError("Only the video track can be reordered.")

    document = deepcopy(timeline)
    track = get_track(document, track_id)

    existing = {clip["id"]: clip for clip in track["clips"]}
    if sorted(clip_ids) != sorted(existing):
        raise TimelineError(
            "The new order must list every clip on the track exactly once."
        )

    cursor = 0.0
    ordered = []
    for clip_id in clip_ids:
        clip = existing[clip_id]
        clip["start"] = round(cursor, 3)
        cursor += clip["duration"]
        ordered.append(clip)

    track["clips"] = ordered
    return _settle(document)


# Fields a client may change through `update_clip`. A whitelist rather than a
# blacklist: `id`, `track` and `kind` decide what a clip *is*, and letting a
# patch change them turns an update into an undetectable replace.
_EDITABLE = frozenset(
    set(_COMMON_DEFAULTS)
    | set(_VISUAL_DEFAULTS)
    | set(_AUDIO_DEFAULTS)
    | set(_TEXT_DEFAULTS)
    | {"asset_id"}
) - {"start", "meta"}


def update_clip(timeline: dict, *, clip_id: str, patch: dict) -> dict:
    """Change a clip's properties — the inspector panel's one endpoint.

    `start` is deliberately not editable here: moving is `move_clip`, which
    knows about overlaps. A patch that could set `start` would be a way around
    that check.

    Unknown keys are ignored rather than rejected, so a newer client sending a
    field this build does not have yet still gets its other changes applied.
    """
    document = deepcopy(timeline)
    track, clip = find_clip(document, clip_id)

    if clip["locked"] and not (len(patch) == 1 and "locked" in patch):
        raise TimelineError(f"“{clip['label'] or 'That clip'}” is locked.")

    merged = {**clip, **{k: v for k, v in (patch or {}).items() if k in _EDITABLE}}
    updated = normalize_clip(merged, track_id=track["id"])
    # Identity is never taken from the patch.
    updated["id"] = clip["id"]
    updated["kind"] = clip["kind"]
    updated["start"] = clip["start"]

    if track["id"] in SEQUENTIAL_TRACKS:
        clash = _overlap(
            [row for row in track["clips"] if row["id"] != clip_id],
            start=updated["start"],
            end=updated["start"] + updated["duration"],
            ignore=None,
        )
        if clash is not None:
            raise TimelineError(
                "That length would overlap the next clip. Move it first."
            )

    track["clips"] = [
        updated if row["id"] == clip_id else row for row in track["clips"]
    ]
    return _settle(document)
