"""Subtitle cues: building them, editing them, and writing the file formats.

A *cue* is `{"start": float, "end": float, "text": str}` — seconds from the
start of the media, and the words shown between them. That shape is the whole
contract: it is what Subtitle Studio edits, what `video_projects.subtitles`
stores, what SRT and VTT are written from, and what the renderer will burn in.
One shape, so there is never a conversion step where timing can drift.

Everything here is pure. No database, no network, no provider — which is what
makes it directly testable and what lets the same functions serve the
independent Subtitle Studio and a subtitle track inside a project.

**Why cues are rebuilt from segments rather than used as-is.** A speech model
returns whatever length of segment it felt like: sometimes two words, sometimes
a 14-second paragraph. Neither is a subtitle. `cues_from_transcript` re-splits
on reading limits — characters per line, lines per cue, minimum and maximum
duration — which is the difference between a transcript and a subtitle track.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Reading-speed limits. The defaults are the broadcast conventions most
# platforms converge on, and they are what the presets vary.
DEFAULT_MAX_CHARS_PER_LINE = 42
DEFAULT_MAX_LINES = 2
DEFAULT_MIN_DURATION = 0.7
DEFAULT_MAX_DURATION = 6.0
# A gap this small between two cues reads as a flicker, so the first is
# extended to meet the second instead.
MIN_GAP = 0.04


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str

    def as_dict(self) -> dict:
        return {"start": self.start, "end": self.end, "text": self.text}


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------
# Styling AND reading limits together, because they are not independent: TikTok
# captions are big and central, which means fewer characters fit on a line, and
# a preset that changed the font without changing the wrap would overflow.
#
# `word_highlight` marks the presets that need word-level timings. Subtitle
# Studio disables those when the provider returned none, rather than animating
# to interpolated positions and calling it karaoke.
SUBTITLE_PRESETS: dict[str, dict] = {
    "clean": {
        "label": "Clean",
        "description": "Neutral white text with a soft shadow. Reads anywhere.",
        "font_family": "Inter",
        "font_size": 42,
        "font_weight": 600,
        "color": "#FFFFFF",
        "background": "transparent",
        "outline": "#000000",
        "outline_width": 2,
        "shadow": True,
        "position": "bottom",
        "align": "center",
        "uppercase": False,
        "animation": "none",
        "word_highlight": False,
        "max_chars_per_line": 42,
        "max_lines": 2,
    },
    "youtube": {
        "label": "YouTube",
        "description": "Boxed captions in YouTube's own style.",
        "font_family": "Roboto",
        "font_size": 40,
        "font_weight": 500,
        "color": "#FFFFFF",
        "background": "rgba(0,0,0,0.75)",
        "outline": "none",
        "outline_width": 0,
        "shadow": False,
        "position": "bottom",
        "align": "center",
        "uppercase": False,
        "animation": "none",
        "word_highlight": False,
        "max_chars_per_line": 42,
        "max_lines": 2,
    },
    "shorts": {
        "label": "Shorts",
        "description": "Large centred text for vertical video.",
        "font_family": "Inter",
        "font_size": 60,
        "font_weight": 800,
        "color": "#FFFFFF",
        "background": "transparent",
        "outline": "#000000",
        "outline_width": 4,
        "shadow": True,
        "position": "center",
        "align": "center",
        "uppercase": False,
        "animation": "pop",
        "word_highlight": False,
        # Bigger text, so fewer characters fit before it wraps off screen.
        "max_chars_per_line": 24,
        "max_lines": 2,
    },
    "tiktok": {
        "label": "TikTok",
        "description": "Bold, tight phrases in the TikTok caption style.",
        "font_family": "Inter",
        "font_size": 58,
        "font_weight": 800,
        "color": "#FFFFFF",
        "background": "rgba(0,0,0,0.35)",
        "outline": "none",
        "outline_width": 0,
        "shadow": True,
        "position": "center",
        "align": "center",
        "uppercase": False,
        "animation": "pop",
        "word_highlight": False,
        "max_chars_per_line": 22,
        "max_lines": 2,
    },
    "karaoke": {
        "label": "Karaoke",
        "description": "Each word lights up as it is spoken. Needs word timings.",
        "font_family": "Inter",
        "font_size": 56,
        "font_weight": 800,
        "color": "#FFFFFF",
        "highlight_color": "#22C55E",
        "background": "transparent",
        "outline": "#000000",
        "outline_width": 3,
        "shadow": True,
        "position": "center",
        "align": "center",
        "uppercase": False,
        "animation": "none",
        "word_highlight": True,
        "max_chars_per_line": 24,
        "max_lines": 2,
    },
    "highlight": {
        "label": "Highlight",
        "description": "The spoken word sits on a coloured block.",
        "font_family": "Inter",
        "font_size": 54,
        "font_weight": 800,
        "color": "#FFFFFF",
        "highlight_color": "#159A68",
        "background": "transparent",
        "outline": "#000000",
        "outline_width": 2,
        "shadow": True,
        "position": "center",
        "align": "center",
        "uppercase": True,
        "animation": "none",
        "word_highlight": True,
        "max_chars_per_line": 20,
        "max_lines": 1,
    },
    "minimal": {
        "label": "Minimal",
        "description": "Small, low-contrast text that stays out of the way.",
        "font_family": "Inter",
        "font_size": 32,
        "font_weight": 500,
        "color": "#F5F5F5",
        "background": "transparent",
        "outline": "none",
        "outline_width": 0,
        "shadow": True,
        "position": "bottom",
        "align": "center",
        "uppercase": False,
        "animation": "fade",
        "word_highlight": False,
        "max_chars_per_line": 48,
        "max_lines": 1,
    },
}

DEFAULT_PRESET = "clean"

# ---------------------------------------------------------------------------
# Style vocabularies
# ---------------------------------------------------------------------------
# What the style panel is allowed to offer. Served to the UI rather than
# duplicated in JavaScript, because the renderer has to understand every value
# the editor can produce — a dropdown offering an animation the burn-in step
# has never heard of is a subtitle track that looks right in the browser and
# wrong in the exported video.

# Kept to faces that are actually available to the renderer. Adding one here
# means adding it to the render step too, which is the point of the list.
SUBTITLE_FONTS = ("Inter", "Roboto", "Montserrat", "Poppins", "Open Sans", "Arial")

# Vertical placement within the safe area.
SUBTITLE_POSITIONS = ("top", "center", "bottom")

SUBTITLE_ALIGNMENTS = ("left", "center", "right")

# How a cue enters. "none" is first because it is the right answer for most
# long-form video; the rest suit short-form, where motion holds attention.
SUBTITLE_ANIMATIONS = ("none", "fade", "pop", "slide-up", "typewriter")


def style_vocabularies() -> dict:
    """Everything the style panel needs beyond the presets themselves."""
    return {
        "fonts": list(SUBTITLE_FONTS),
        "positions": list(SUBTITLE_POSITIONS),
        "alignments": list(SUBTITLE_ALIGNMENTS),
        "animations": list(SUBTITLE_ANIMATIONS),
    }


# Every field a style carries, with the fallback used when a client omits it.
# A partial style from an older build therefore still renders, rather than
# producing a cue with no colour.
STYLE_DEFAULTS: dict = {
    "key": DEFAULT_PRESET,
    "font_family": "Inter",
    "font_size": 44,
    "font_weight": 700,
    "color": "#FFFFFF",
    "background": "rgba(0,0,0,0.35)",
    "outline": "#000000",
    "outline_width": 2,
    "shadow": True,
    "position": "bottom",
    "align": "center",
    "uppercase": False,
    "animation": "none",
    "word_highlight": False,
    "highlight_color": "#159A68",
    "max_chars_per_line": DEFAULT_MAX_CHARS_PER_LINE,
    "max_lines": DEFAULT_MAX_LINES,
}


def clean_style(style: dict | None) -> dict:
    """Fill in a style and drop anything the renderer cannot honour.

    Validated on the way in rather than trusted: a `position` of "diagonal" or
    a `max_lines` of 40 is not a style, it is a subtitle track nobody can read,
    and the burn-in step would have to guess what was meant.
    """
    merged = {**STYLE_DEFAULTS, **(style or {})}

    if merged.get("position") not in SUBTITLE_POSITIONS:
        merged["position"] = STYLE_DEFAULTS["position"]
    if merged.get("align") not in SUBTITLE_ALIGNMENTS:
        merged["align"] = STYLE_DEFAULTS["align"]
    if merged.get("animation") not in SUBTITLE_ANIMATIONS:
        merged["animation"] = STYLE_DEFAULTS["animation"]
    if merged.get("font_family") not in SUBTITLE_FONTS:
        merged["font_family"] = STYLE_DEFAULTS["font_family"]

    # Numeric bounds. The font size ceiling is generous — short-form captions
    # are genuinely huge — but a size of 4000 is a bug, not a choice.
    def _bounded(field: str, low: int, high: int) -> None:
        try:
            merged[field] = max(low, min(high, int(merged.get(field))))
        except (TypeError, ValueError):
            merged[field] = STYLE_DEFAULTS[field]

    _bounded("font_size", 12, 200)
    _bounded("font_weight", 100, 900)
    _bounded("outline_width", 0, 12)
    _bounded("max_chars_per_line", 12, 80)
    _bounded("max_lines", 1, 4)

    merged["shadow"] = bool(merged.get("shadow"))
    merged["uppercase"] = bool(merged.get("uppercase"))
    merged["word_highlight"] = bool(merged.get("word_highlight"))

    return merged


def preset(key: str | None) -> dict:
    """A style preset by key, with its own key included. Falls back to Clean."""
    chosen = SUBTITLE_PRESETS.get((key or "").lower(), SUBTITLE_PRESETS[DEFAULT_PRESET])
    return {"key": key if key in SUBTITLE_PRESETS else DEFAULT_PRESET, **chosen}


# ---------------------------------------------------------------------------
# Building cues
# ---------------------------------------------------------------------------

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def _wrap(text: str, max_chars: int, max_lines: int) -> str:
    """Break a cue's text onto lines at word boundaries.

    Words are never split. A single word longer than the line limit is left
    over-long rather than hyphenated — a broken word is harder to read than a
    wide line, and this is the case where the limit is the wrong rule.
    """
    words = text.split()
    if not words:
        return ""

    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)

    if len(lines) <= max_lines:
        return "\n".join(lines)

    # Too many lines: keep the first `max_lines - 1` and let the last absorb
    # the rest. Dropping the overflow would silently lose the user's words.
    head = lines[: max_lines - 1]
    tail = " ".join(lines[max_lines - 1 :])
    return "\n".join([*head, tail])


def _split_long_segment(
    start: float,
    end: float,
    text: str,
    *,
    max_chars: int,
    max_lines: int,
    max_duration: float,
) -> list[Cue]:
    """Cut one over-long segment into readable cues.

    Split points are sentence boundaries first, because a cue that ends
    mid-sentence reads badly. When a single sentence is still too long it is
    split on word count, and timing is apportioned by *character* share rather
    than evenly: "OK." and a 30-word clause are not the same length of speech.
    """
    capacity = max_chars * max_lines
    duration = max(0.0, end - start)

    if len(text) <= capacity and duration <= max_duration:
        return [Cue(start, end, _wrap(text, max_chars, max_lines))]

    pieces = [part for part in _SENTENCE_END.split(text) if part.strip()]

    # Sentences that are themselves too long get chopped on word boundaries.
    chunks: list[str] = []
    for piece in pieces:
        if len(piece) <= capacity:
            chunks.append(piece.strip())
            continue
        words, current = piece.split(), ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) > capacity and current:
                chunks.append(current)
                current = word
            else:
                current = candidate
        if current:
            chunks.append(current)

    if not chunks:
        return [Cue(start, end, _wrap(text, max_chars, max_lines))]

    total_chars = sum(len(chunk) for chunk in chunks) or 1
    cues: list[Cue] = []
    cursor = start
    for index, chunk in enumerate(chunks):
        share = duration * (len(chunk) / total_chars)
        # The last cue lands exactly on `end` rather than on an accumulated
        # float, so a track can never finish a few milliseconds past its audio.
        chunk_end = end if index == len(chunks) - 1 else cursor + share
        cues.append(Cue(cursor, chunk_end, _wrap(chunk, max_chars, max_lines)))
        cursor = chunk_end
    return cues


def cues_from_segments(
    segments,
    *,
    max_chars_per_line: int = DEFAULT_MAX_CHARS_PER_LINE,
    max_lines: int = DEFAULT_MAX_LINES,
    min_duration: float = DEFAULT_MIN_DURATION,
    max_duration: float = DEFAULT_MAX_DURATION,
) -> list[dict]:
    """Turn transcript segments into subtitle cues.

    `segments` is anything with `.start`, `.end` and `.text` — the
    TranscriptSegment dataclass, or dicts with those keys.
    """
    cues: list[Cue] = []

    for segment in segments:
        if isinstance(segment, dict):
            start = float(segment.get("start", 0.0))
            end = float(segment.get("end", 0.0))
            text = (segment.get("text") or "").strip()
        else:
            start, end, text = float(segment.start), float(segment.end), segment.text.strip()

        if not text:
            continue
        if end <= start:
            # A zero-length segment still has words in it. Give it the minimum
            # readable duration rather than dropping the line.
            end = start + min_duration

        cues.extend(
            _split_long_segment(
                start,
                end,
                text,
                max_chars=max_chars_per_line,
                max_lines=max_lines,
                max_duration=max_duration,
            )
        )

    return normalize([cue.as_dict() for cue in cues], min_duration=min_duration)


def cues_from_transcript(transcript, *, style: dict | None = None) -> list[dict]:
    """Cues from a Transcript, using a style preset's reading limits."""
    style = style or preset(DEFAULT_PRESET)
    return cues_from_segments(
        transcript.segments,
        max_chars_per_line=int(style.get("max_chars_per_line", DEFAULT_MAX_CHARS_PER_LINE)),
        max_lines=int(style.get("max_lines", DEFAULT_MAX_LINES)),
    )


def normalize(cues: list[dict], *, min_duration: float = DEFAULT_MIN_DURATION) -> list[dict]:
    """Sort, de-overlap and clean a cue list. Safe to run on user edits.

    This is what runs after every edit in the Subtitle Studio, so it must be
    conservative: it fixes what is unambiguously broken (negative durations,
    overlaps, empty cues, flickers) and touches nothing else. It never merges
    or rewrites text.
    """
    cleaned: list[dict] = []
    for cue in cues or []:
        text = (cue.get("text") or "").strip()
        if not text:
            continue
        start = max(0.0, float(cue.get("start") or 0.0))
        end = float(cue.get("end") or 0.0)
        if end <= start:
            end = start + min_duration
        cleaned.append({"start": round(start, 3), "end": round(end, 3), "text": text})

    cleaned.sort(key=lambda c: (c["start"], c["end"]))

    for index in range(len(cleaned) - 1):
        current, following = cleaned[index], cleaned[index + 1]
        if current["end"] > following["start"]:
            # Trim the earlier cue rather than pushing the later one: the later
            # cue's start is tied to speech that actually begins then.
            current["end"] = max(current["start"] + 0.05, following["start"] - MIN_GAP)
            current["end"] = round(current["end"], 3)

    return cleaned


# ---------------------------------------------------------------------------
# File formats
# ---------------------------------------------------------------------------


def _timestamp(seconds: float, *, separator: str) -> str:
    """HH:MM:SS,mmm (SRT) or HH:MM:SS.mmm (VTT)."""
    seconds = max(0.0, seconds)
    total_ms = int(round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def to_srt(cues: list[dict]) -> str:
    """SubRip. Numbered from 1, comma decimal separator, blank line between."""
    blocks = []
    for index, cue in enumerate(cues or [], start=1):
        blocks.append(
            f"{index}\n"
            f"{_timestamp(cue['start'], separator=',')} --> "
            f"{_timestamp(cue['end'], separator=',')}\n"
            f"{cue['text']}"
        )
    # SRT players are happier with a trailing newline than without one.
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def to_vtt(cues: list[dict]) -> str:
    """WebVTT. Same timings, dot separator, and the required header."""
    blocks = ["WEBVTT", ""]
    for cue in cues or []:
        blocks.append(
            f"{_timestamp(cue['start'], separator='.')} --> "
            f"{_timestamp(cue['end'], separator='.')}\n"
            f"{cue['text']}"
        )
        blocks.append("")
    return "\n".join(blocks)


def to_txt(cues: list[dict]) -> str:
    """A plain reading transcript: no timings, line breaks flattened."""
    return "\n".join(
        " ".join((cue.get("text") or "").split()) for cue in cues or []
    ) + ("\n" if cues else "")


_SRT_TIME = re.compile(
    r"(\d{1,3}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*"
    r"(\d{1,3}):(\d{2}):(\d{2})[,.](\d{1,3})"
)


def parse(text: str) -> list[dict]:
    """Read an SRT or VTT file back into cues.

    One parser for both: they differ in a header, a decimal separator and cue
    numbering, and all three are things a tolerant reader can simply skip. This
    is what lets a user upload subtitles they already have and edit them.
    """
    cues: list[dict] = []
    current: dict | None = None
    lines: list[str] = []

    for raw in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.strip("﻿")
        match = _SRT_TIME.search(line)

        if match:
            if current is not None:
                current["text"] = "\n".join(lines).strip()
                if current["text"]:
                    cues.append(current)
            numbers = [int(value) for value in match.groups()]
            # A 2-digit millisecond field means centiseconds, not milliseconds.
            start = numbers[0] * 3600 + numbers[1] * 60 + numbers[2] + numbers[3] / 1000
            end = numbers[4] * 3600 + numbers[5] * 60 + numbers[6] + numbers[7] / 1000
            current = {"start": start, "end": end, "text": ""}
            lines = []
            continue

        if current is None:
            # Header, cue number or blank line before the first timestamp.
            continue

        if not line.strip():
            current["text"] = "\n".join(lines).strip()
            if current["text"]:
                cues.append(current)
            current, lines = None, []
            continue

        lines.append(line)

    if current is not None:
        current["text"] = "\n".join(lines).strip()
        if current["text"]:
            cues.append(current)

    return normalize(cues)


def shift(cues: list[dict], offset: float) -> list[dict]:
    """Move every cue by `offset` seconds. Negative shifts clamp at zero."""
    return normalize(
        [
            {
                "start": max(0.0, cue["start"] + offset),
                "end": max(0.0, cue["end"] + offset),
                "text": cue["text"],
            }
            for cue in cues or []
        ]
    )


def total_duration(cues: list[dict]) -> float:
    """When the last cue ends. 0.0 for an empty track."""
    return max((float(cue.get("end") or 0.0) for cue in cues or []), default=0.0)


# ---------------------------------------------------------------------------
# Editing
# ---------------------------------------------------------------------------
# The operations the Subtitle Studio's cue list offers. All pure, all taking
# and returning a cue list, all running the result through `normalize` — so an
# edit can never leave the track overlapping, out of order or negative-length,
# whatever order the user performs them in.
#
# They live here rather than in the frontend because the same operations have
# to be available to a future generator and to any repair of an imported file,
# and because "what does splitting a cue do to its timing" is a decision that
# must have exactly one answer.


class SubtitleEditError(ValueError):
    """An edit was refused. The message is user-facing."""


def _cue_list(cues: list[dict] | None) -> list[dict]:
    """A mutable copy with the three fields guaranteed present."""
    return [
        {
            "start": float(cue.get("start") or 0.0),
            "end": float(cue.get("end") or 0.0),
            "text": str(cue.get("text") or ""),
        }
        for cue in cues or []
    ]


def _require_index(cues: list[dict], index: int) -> None:
    if not 0 <= index < len(cues):
        raise SubtitleEditError(f"There is no cue {index + 1} to edit.")


def update_cue(
    cues: list[dict],
    index: int,
    *,
    start: float | None = None,
    end: float | None = None,
    text: str | None = None,
) -> list[dict]:
    """Change one cue's timing or wording."""
    working = _cue_list(cues)
    _require_index(working, index)

    cue = working[index]
    if start is not None:
        cue["start"] = max(0.0, float(start))
    if end is not None:
        cue["end"] = max(0.0, float(end))
    if text is not None:
        cue["text"] = str(text)

    if not cue["text"].strip():
        raise SubtitleEditError(
            "A cue needs some text. Delete it instead of emptying it."
        )
    return normalize(working)


def insert_cue(
    cues: list[dict],
    *,
    index: int | None = None,
    text: str = "New subtitle",
    start: float | None = None,
    end: float | None = None,
    gap: float = MIN_GAP,
    default_duration: float = 2.0,
) -> list[dict]:
    """Add a cue, by default straight after `index`.

    Making the user type two timestamps to add a line they are about to
    reposition anyway is the kind of friction that stops people fixing
    subtitles at all — so the timing is worked out for them.

    **Where the time comes from matters**, because a transcribed track is
    usually contiguous and has no gap to insert into:

      * If there is a real gap after the chosen cue, the new one sits in it.
      * If there is not, the time is borrowed from the *start of the next cue*,
        which is shortened to make room. Nothing after that moves, so the rest
        of the track stays in sync with its audio.
      * If the next cue is too short to spare any, the insert is refused with
        a reason rather than producing a cue that lands out of order.

    That last case is why this cannot simply append and let `normalize` sort it
    out: `normalize` orders by start time, so a new cue starting after the next
    one's start would silently appear in the wrong place in the list.
    """
    working = _cue_list(cues)

    if index is None:
        position = len(working)
    else:
        _require_index(working, index)
        position = index + 1

    explicit = start is not None and end is not None
    following = working[position] if position < len(working) else None

    if start is None:
        start = (working[position - 1]["end"] if position > 0 else 0.0) + gap

    if end is None:
        end = start + default_duration
        if following is not None:
            room = following["start"] - gap - start
            if room >= DEFAULT_MIN_DURATION:
                # A real gap: take what is there, up to the default length.
                end = start + min(default_duration, room)
            else:
                # No gap. Borrow from the next cue, leaving it readable.
                spare = (following["end"] - following["start"]) - DEFAULT_MIN_DURATION
                borrow = min(default_duration, max(0.0, spare))
                if borrow < DEFAULT_MIN_DURATION:
                    raise SubtitleEditError(
                        "There is no room to add a cue here. Shorten a "
                        "neighbouring cue first, or add it at the end."
                    )
                end = start + borrow
                following["start"] = end + gap

    if end <= start:
        end = start + DEFAULT_MIN_DURATION

    if explicit and following is not None and start > following["start"]:
        # An explicit timing that lands after the next cue is not an insert at
        # this position — it is a different position, and silently reordering
        # would be a surprise.
        raise SubtitleEditError(
            "That start time is after the following cue. Add the cue there "
            "instead, or change the timing afterwards."
        )

    working.insert(position, {"start": float(start), "end": float(end), "text": text})
    return normalize(working)


def delete_cue(cues: list[dict], index: int) -> list[dict]:
    """Remove one cue.

    The rest keep their timing — deleting a line is not a reason to move the
    lines around it.
    """
    working = _cue_list(cues)
    _require_index(working, index)
    working.pop(index)
    return normalize(working)


def split_cue(
    cues: list[dict],
    index: int,
    *,
    at_seconds: float | None = None,
    at_character: int | None = None,
) -> list[dict]:
    """Break one cue into two.

    The split point can be given as a time or as an offset into the text; one
    is derived from the other so the halves stay in step. Splitting purely by
    time would cut a word in half, so a time split snaps to the nearest word
    boundary, and the duration is then apportioned by character share — the
    same rule `_split_long_segment` uses, and for the same reason: "OK." and a
    30-word clause are not the same length of speech.
    """
    working = _cue_list(cues)
    _require_index(working, index)

    cue = working[index]
    text = cue["text"]
    duration = cue["end"] - cue["start"]

    if len(text.split()) < 2:
        raise SubtitleEditError("This cue has only one word — there is nothing to split.")
    if duration <= DEFAULT_MIN_DURATION:
        raise SubtitleEditError("This cue is too short to split into two readable ones.")

    if at_character is None:
        fraction = 0.5
        if at_seconds is not None:
            if not cue["start"] < at_seconds < cue["end"]:
                raise SubtitleEditError("Choose a split point inside this cue.")
            fraction = (at_seconds - cue["start"]) / duration
        at_character = int(len(text) * fraction)

    # Snap to the nearest whitespace so a word is never cut in half. Both
    # directions are searched and the closer one wins, so the split stays near
    # where the user asked rather than always drifting left.
    left = max(text.rfind(" ", 0, at_character), text.rfind("\n", 0, at_character))
    right = min(
        [pos for pos in (text.find(" ", at_character), text.find("\n", at_character)) if pos != -1],
        default=-1,
    )

    if left == -1 and right == -1:
        raise SubtitleEditError("There is no word boundary to split on.")
    if left == -1:
        boundary = right
    elif right == -1:
        boundary = left
    else:
        boundary = left if (at_character - left) <= (right - at_character) else right

    head = text[:boundary].strip()
    tail = text[boundary:].strip()
    if not head or not tail:
        raise SubtitleEditError("A split has to leave text on both sides.")

    share = len(head) / max(1, len(head) + len(tail))
    seam = cue["start"] + duration * share

    working[index : index + 1] = [
        {"start": cue["start"], "end": seam, "text": head},
        {"start": seam, "end": cue["end"], "text": tail},
    ]
    return normalize(working)


def merge_cues(
    cues: list[dict],
    indices: list[int],
    *,
    separator: str = " ",
    max_chars_per_line: int = DEFAULT_MAX_CHARS_PER_LINE,
    max_lines: int = DEFAULT_MAX_LINES,
) -> list[dict]:
    """Join two or more cues into one.

    The merged cue runs from the first start to the last end, so the words stay
    over the audio they belong to. Only *adjacent* cues can be merged: joining
    cue 2 to cue 9 would either swallow everything between them or produce a
    cue whose text does not match its timing, and neither is what anyone means
    by "merge".

    **The result is re-wrapped to the reading limits.** Two cues of 40
    characters merge into 80, and simply concatenating them would produce a
    line nothing else in the studio would ever emit — the editor flags exactly
    that state as too long to read. Re-wrapping also makes a merge the precise
    inverse of a split, so the pair can be used to reshape a track without
    degrading it.
    """
    working = _cue_list(cues)
    if len(indices or []) < 2:
        raise SubtitleEditError("Select at least two cues to merge.")

    ordered = sorted(set(indices))
    for index in ordered:
        _require_index(working, index)
    if ordered != list(range(ordered[0], ordered[-1] + 1)):
        raise SubtitleEditError("Only cues next to each other can be merged.")

    chosen = [working[i] for i in ordered]

    # Line breaks inside the merged cues collapse to spaces first: keeping them
    # would preserve the shape of cues that no longer exist.
    joined = separator.join(
        " ".join(cue["text"].split()) for cue in chosen if cue["text"].strip()
    )

    merged = {
        "start": chosen[0]["start"],
        "end": chosen[-1]["end"],
        # Then re-wrapped to the reading limits — which is what the arguments
        # above are for, and what makes a merge the inverse of a split. Without
        # this the two cues a split produced merged back into one *unwrapped*
        # line, so splitting and re-merging a wrapped cue silently rewrote it,
        # and the result was a line longer than the editor itself flags as
        # unreadable.
        "text": _wrap(joined, max_chars_per_line, max_lines),
    }

    working[ordered[0] : ordered[-1] + 1] = [merged]
    return normalize(working)


def search_replace(
    cues: list[dict],
    *,
    find: str,
    replace: str = "",
    case_sensitive: bool = False,
    whole_word: bool = False,
) -> tuple[list[dict], int]:
    """Replace text across every cue. Returns (cues, replacements made).

    The count is returned rather than logged because "replaced 14 occurrences"
    is the only way the user can tell a working find from a silent no-match —
    and a subtitle track is long enough that scrolling to check is not an
    answer.

    Timing is never touched. A find-and-replace that re-timed the track would
    be unusable on the one job it exists for: fixing a name the model spelled
    wrong in forty places.
    """
    if not find:
        raise SubtitleEditError("Enter something to find.")

    pattern = re.escape(find)
    if whole_word:
        pattern = rf"\b{pattern}\b"
    compiled = re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)

    working = _cue_list(cues)
    total = 0
    for cue in working:
        text, count = compiled.subn(replace, cue["text"])
        if count:
            cue["text"] = text
            total += count

    # Replacing a cue's whole text with nothing is a legitimate way to drop a
    # line, but it must not leave a wordless cue in the track.
    working = [cue for cue in working if cue["text"].strip()]

    return normalize(working), total


# ---------------------------------------------------------------------------
# Cues from a written script
# ---------------------------------------------------------------------------

# Words per minute for a script with no audio behind it. 150 is the middle of
# the range broadcast guidance gives for clear narration — fast enough not to
# feel padded, slow enough to be readable.
DEFAULT_WPM = 150.0


def cues_from_script(
    text: str,
    *,
    duration_seconds: float | None = None,
    wpm: float = DEFAULT_WPM,
    style: dict | None = None,
    start_at: float = 0.0,
) -> list[dict]:
    """Time a written script into cues, with no audio and no transcription.

    This is the third input the Subtitle Studio takes, and the honest thing to
    say about it is that the timing is *estimated*: there is no recording to
    measure against, so each cue gets a share of the total proportional to how
    much text it holds.

    `duration_seconds` is used when it is known — the length of the voice-over
    the script was written for, say — and the script is fitted to it exactly.
    Without it the length comes from a reading speed, which is a guess, and the
    UI says so rather than presenting estimated timings as measured ones.
    """
    style = style or preset(DEFAULT_PRESET)
    max_chars = int(style.get("max_chars_per_line", DEFAULT_MAX_CHARS_PER_LINE))
    max_lines = int(style.get("max_lines", DEFAULT_MAX_LINES))

    if not text or not text.strip():
        return []

    # Sentences first, then over-long ones broken on the reading limits — the
    # same path a transcript segment takes, so a script-timed track and a
    # transcribed one are wrapped identically.
    blocks: list[str] = []
    for paragraph in re.split(r"\n\s*\n+", text):
        for sentence in _SENTENCE_END.split(paragraph.strip()):
            sentence = " ".join(sentence.split())
            if sentence:
                blocks.append(sentence)

    if not blocks:
        return []

    if duration_seconds and duration_seconds > 0:
        total = float(duration_seconds)
    else:
        words = sum(len(block.split()) for block in blocks)
        total = (words / max(1.0, wpm)) * 60.0

    total_chars = sum(len(block) for block in blocks) or 1
    cues: list[Cue] = []
    cursor = float(start_at)

    for index, block in enumerate(blocks):
        share = total * (len(block) / total_chars)
        # The last cue lands exactly on the end rather than on an accumulated
        # float, so a fitted track finishes precisely with its audio.
        end = (start_at + total) if index == len(blocks) - 1 else cursor + share
        cues.extend(
            _split_long_segment(
                cursor,
                end,
                block,
                max_chars=max_chars,
                max_lines=max_lines,
                max_duration=DEFAULT_MAX_DURATION,
            )
        )
        cursor = end

    return normalize([cue.as_dict() for cue in cues])
