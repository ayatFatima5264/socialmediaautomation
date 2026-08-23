"""Request and response shapes for Smart Repurpose.

The shape of this API is the product rule: **analyse, review, then create.**

`POST /analyze` returns moments and changes nothing. The client shows them, the
user edits the times, hooks and CTAs, and only then does `POST /create` make
projects. There is no endpoint that goes from an upload to finished videos, and
that is deliberate — a tool that turns one file into nine videos without a
human looking at them is a tool that produces nine videos nobody wants.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RepurposeTarget(BaseModel):
    key: str
    label: str
    platform: str
    max_seconds: int
    subtitle_style: str


class RepurposeOptions(BaseModel):
    targets: list[RepurposeTarget]
    min_clip_seconds: float
    max_clip_seconds: float
    default_moment_count: int
    # False when no transcription provider is configured. The UI says so
    # instead of offering an analyse button that always 503s.
    transcription_available: bool = True


class Moment(BaseModel):
    """One candidate clip. Every field editable before anything is created."""

    start: float = Field(ge=0)
    end: float = Field(gt=0)
    title: str = Field(default="", max_length=120)
    # What goes on screen for the first few seconds.
    hook: str = Field(default="", max_length=120)
    # Why the model thought this stands alone. Shown, not used — it is what
    # lets a reviewer disagree with a suggestion for a reason.
    reason: str = Field(default="", max_length=300)
    cta: str = Field(default="", max_length=80)
    # Horizontal framing when the subject is not centred, as a fraction of the
    # canvas. The same offset the editor's inspector exposes, so a generated
    # framing can be nudged by hand afterwards.
    focus_x: float = Field(default=0.0, ge=-1.0, le=1.0)
    transcript: str = ""


class AnalyzeRequest(BaseModel):
    """Find the moments in a long video.

    `asset_id` is a video already in the library — uploaded through the Media
    Library, or the finished export of another project. Repurpose never takes
    an upload directly: the file has to exist as an asset first so the shorts
    can reference it rather than copying it.
    """

    asset_id: int
    count: int = Field(default=5, ge=1, le=10)
    language: str | None = None
    # Re-transcribe even if this asset has been analysed before. Off by
    # default because transcription costs money and the words do not change.
    force: bool = False


class AnalyzeResult(BaseModel):
    asset_id: int
    duration_seconds: float
    language: str = ""
    moments: list[Moment]
    # Pairs of indices covering the same footage. Surfaced rather than merged —
    # overlapping shorts are sometimes exactly what somebody wants.
    overlaps: list[list[int]] = Field(default_factory=list)
    segment_count: int = 0
    analyzed_at: datetime | None = None
    # True when this came from a stored analysis rather than a fresh one.
    cached: bool = False


class CreateShortsRequest(BaseModel):
    """Turn reviewed moments into projects.

    One project per moment per target: three moments for two platforms is six
    projects, each with its own canvas and caption style.
    """

    asset_id: int
    moments: list[Moment] = Field(min_length=1, max_length=20)
    targets: list[str] = Field(min_length=1, max_length=3)
    # Recorded on each short so the editor can show where it came from. Never
    # modified — see the module docstring in services/video/repurpose.py.
    source_project_id: int | None = None


class ShortRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: int
    name: str
    platform: str
    aspect_ratio: str
    width: int
    height: int
    duration_seconds: float
    target: str
    moment: dict = Field(default_factory=dict)
    # Where to open it. The pipeline ends in the ordinary editor.
    editor_path: str


class CreateShortsResult(BaseModel):
    shorts: list[ShortRead]
    # Moments that could not be made, with the reason — a clip too long for
    # the platform it was aimed at, most often.
    skipped: list[dict] = Field(default_factory=list)
    source_project_unchanged: bool = True
