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

from app.core.limits import MAX_SCRIPT_CHARACTERS

#: The most cues a track can carry. `MAX_SCRIPT_CHARACTERS` of narration splits
#: into a few thousand at the shortest sensible cue length, so this is well
#: clear of any real track while still bounding the work an edit does.
MAX_CUES = 10_000

#: One cue is a line or two of subtitle. This is generous for that and still
#: stops a single cue carrying a megabyte into an SRT and then a drawtext
#: argument.
MAX_CUE_CHARACTERS = 4_000


class Cue(BaseModel):
    """A cue as it is *returned*.

    Deliberately unbounded. An imported SRT is read back as whatever it says,
    and a response model that refuses a long line would turn somebody else's
    unusual subtitle file into a 500 instead of something they can edit. The
    bound belongs on the way in, where it stops the input growing — see
    `CueIn`.
    """

    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str


class CueIn(Cue):
    """A cue as it is *accepted*.

    Same shape, with a ceiling on the text. A cue is a line or two of subtitle;
    this is generous for that and still stops one carrying a megabyte into an
    SRT line and then a drawtext argument at render time.
    """

    text: str = Field(max_length=MAX_CUE_CHARACTERS)


class CueList(BaseModel):
    """Every editing request carries the whole track.

    Deliberately not a per-cue patch API. A subtitle track is a few hundred
    cues at most, editing is interactive, and a split or a merge changes the
    index of everything after it — so an endpoint that took "cue 14" would be
    describing a track the client no longer has.

    That the whole track arrives every time is also why it is bounded: the
    request is the unit of work, so an unbounded one is an unbounded amount of
    work per call.
    """

    cues: list[CueIn] = Field(default_factory=list, max_length=MAX_CUES)


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------


class ScriptRequest(BaseModel):
    """Cues from a written script — the input with no audio behind it."""

    text: str = Field(min_length=1, max_length=MAX_SCRIPT_CHARACTERS)
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


class DocumentResult(ScriptResult):
    """Cues from an uploaded TXT, DOCX or PDF.

    Carries the extracted `text` as well as the cues, because a document is
    two different inputs depending on what else the user supplied: on its own
    it is a script to be timed, and alongside a recording it is a *reference*
    to align the transcript against. Returning both means the combined
    workflow reads the file once rather than uploading it twice.
    """

    text: str
    #: What it was read as — "pdf", "docx", "text", "rtf".
    kind: str
    filename: str
    word_count: int
    character_count: int
    #: True when the document was longer than the reader's ceiling and the tail
    #: was dropped. Said out loud rather than silently truncated.
    truncated: bool = False


class AlignmentReport(BaseModel):
    """What comparing a script against the spoken audio actually changed.

    Returned rather than logged because the difference between "your script was
    used" and "your script did not match this recording" is something the user
    has to be told — otherwise a subtitle track that ignored their document
    looks like a bug.
    """

    #: False when the script was not used at all: it did not match the
    #: recording, or one side was empty. The cues are then the transcription,
    #: untouched.
    applied: bool
    #: "aligned" | "partial" | "unmatched" | "empty".
    status: str
    #: How alike the two texts are overall, 0–1.
    similarity: float
    #: The share of the spoken words the script accounts for, 0–1. This, not
    #: `similarity`, is what decides whether the script was usable: a long
    #: script recorded one section at a time is a correct pairing with low
    #: similarity and high coverage.
    coverage: float = 0.0
    matched_words: int = 0
    #: Words whose spelling came from the script.
    corrected_words: int = 0
    #: Words where the speaker said something else and the audio won.
    kept_words: int = 0
    #: Script words that were never spoken. They do not become subtitles.
    skipped_words: int = 0
    #: Spoken words absent from the script. They stay.
    added_words: int = 0
    message: str | None = None
    #: Set when the delivery diverged from the script enough to be worth
    #: saying. Non-blocking — the track is still usable.
    warning: str | None = None


class AlignRequest(CueList):
    """Correct a transcribed track against the script it was read from."""

    script: str = Field(min_length=1, max_length=MAX_SCRIPT_CHARACTERS)
    style_key: str | None = None


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


class AlignResult(EditResult):
    """An aligned track, plus what the alignment did to it."""

    alignment: AlignmentReport


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
