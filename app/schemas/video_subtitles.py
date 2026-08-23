"""Request and response shapes for Subtitle Studio.

A *cue* is `{"start": float, "end": float, "text": str}` — seconds from the
start of the media, and the words shown between them. That one shape is what
the editor sends, what `video_subtitles.cues` stores, what SRT and VTT are
written from, and what the renderer will burn in. Keeping it identical
everywhere is what stops timing drifting through a conversion step.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Cue(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str


class CueList(BaseModel):
    """Every editing request carries the whole track.

    Deliberately not a per-cue patch API. A subtitle track is a few hundred
    cues at most, editing is interactive, and a split or a merge changes the
    index of everything after it — so an endpoint that took "cue 14" would be
    describing a track the client no longer has.
    """

    cues: list[Cue] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------


class ScriptRequest(BaseModel):
    """Cues from a written script — the input with no audio behind it."""

    text: str = Field(min_length=1)
    #: The length to fit the script to, when it is known (the voice-over it was
    #: written for). Without it the timing comes from a reading speed, which is
    #: an estimate, and the response says so.
    duration_seconds: float | None = Field(default=None, gt=0)
    words_per_minute: float = Field(default=150.0, ge=60, le=400)
    style_key: str | None = None


class TranscribeResult(BaseModel):
    cues: list[Cue]
    text: str
    #: What the model detected. A name ("English"), not a code — passed through
    #: rather than guessed at.
    language: str
    duration_seconds: float
    provider: str
    model: str
    word_count: int
    #: Per-word timings, when the provider returns them. These are what make
    #: the karaoke and word-highlight presets honest rather than interpolated.
    words: list[dict] = Field(default_factory=list)
    #: The stored upload, so the editor can play it back while checking timing.
    source_asset_id: int | None = None
    source_url: str | None = None
    translated: bool = False


class ScriptResult(BaseModel):
    cues: list[Cue]
    duration_seconds: float
    #: True when the timing came from a reading speed rather than from audio.
    #: The UI says so; presenting an estimate as a measurement is the one thing
    #: this path must not do.
    estimated: bool


# ---------------------------------------------------------------------------
# Editing
# ---------------------------------------------------------------------------


class CueUpdate(CueList):
    index: int = Field(ge=0)
    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, ge=0)
    text: str | None = None


class CueInsert(CueList):
    #: Insert after this cue. None appends to the end.
    index: int | None = Field(default=None, ge=0)
    text: str = "New subtitle"
    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, ge=0)


class CueDelete(CueList):
    index: int = Field(ge=0)


class CueSplit(CueList):
    index: int = Field(ge=0)
    #: Split at a time, or at an offset into the text. One is derived from the
    #: other, so either is enough.
    at_seconds: float | None = Field(default=None, ge=0)
    at_character: int | None = Field(default=None, ge=0)


class CueMerge(CueList):
    indices: list[int] = Field(min_length=2)


class CueShift(CueList):
    """Move the whole track. For audio that starts late, or a trimmed intro."""

    offset_seconds: float


class SearchReplace(CueList):
    find: str = Field(min_length=1)
    replace: str = ""
    case_sensitive: bool = False
    whole_word: bool = False


class NormalizeRequest(CueList):
    style_key: str | None = None


class EditResult(BaseModel):
    cues: list[Cue]
    duration_seconds: float
    cue_count: int
    #: Only set by search/replace — "replaced 14 occurrences" is the only way
    #: to tell a working find from a silent no-match.
    replacements: int | None = None


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------


class StylePreset(BaseModel):
    key: str
    label: str
    description: str
    font_family: str
    font_size: int
    font_weight: int
    color: str
    background: str
    outline: str
    outline_width: int
    shadow: bool
    position: str
    align: str
    uppercase: bool
    animation: str
    word_highlight: bool
    highlight_color: str | None = None
    max_chars_per_line: int
    max_lines: int


class StyleOptions(BaseModel):
    """The vocabularies the style panel builds its controls from.

    Served rather than hardcoded in the frontend so the renderer and the editor
    cannot disagree about which animations exist.
    """

    presets: list[StylePreset]
    default_preset: str
    fonts: list[str]
    positions: list[str]
    alignments: list[str]
    animations: list[str]


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


class ExportFormat(BaseModel):
    key: str
    label: str
    extension: str
    content_type: str


class ExportRequest(CueList):
    format: str = Field(default="srt", pattern="^(srt|vtt|txt)$")
    title: str | None = Field(default=None, max_length=200)
    language: str | None = None
    project_id: int | None = None


class SubtitleFile(BaseModel):
    """An exported subtitle file, stored in object storage."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None = None
    title: str
    filename: str | None = None
    content_type: str
    size_bytes: int
    url: str
    created_at: datetime
    format: str
    cue_count: int
    duration_seconds: float
    language: str | None = None


# ---------------------------------------------------------------------------
# Tracks on a project
# ---------------------------------------------------------------------------


class AttachRequest(CueList):
    project_id: int
    language: str = "en-US"
    label: str | None = Field(default=None, max_length=120)
    style: dict = Field(default_factory=dict)
    source: str = "transcription"
    #: Replace this track instead of adding another. The studio sends it when
    #: re-attaching a track it already created, so editing and re-adding does
    #: not leave two copies on the project.
    track_id: int | None = None


class SubtitleTrack(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    language: str
    label: str | None = None
    source: str
    is_primary: bool
    cue_count: int
    duration_seconds: float
    style: dict = Field(default_factory=dict)
    cues: list[Cue] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
