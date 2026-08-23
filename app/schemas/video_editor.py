"""Request and response shapes for the timeline editor and the renderer.

One design decision runs through this file: **the client sends operations, not
opinions.** There is a single `TimelineOperation` covering add/move/trim/split/
delete/reorder/update, it is applied by `services/video/timeline.py`, and the
response is the whole new document. The editor never computes the result of an
edit and tells the server what it decided.

That is what keeps the promise that the preview and the export are the same
video. A client that applied its own trim arithmetic would be a second
implementation of the rules, and the two would disagree the first time either
changed — which is exactly the "visual-only mock editor" failure mode.

The cost is a round trip per edit, and it is paid deliberately. Dragging stays
smooth because the editor shows the drag locally and commits on release; what
it never does is *keep* a locally-computed document.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# The document
# ---------------------------------------------------------------------------


class TimelineSummary(BaseModel):
    """Counts and length — what the header and the export dialog read."""

    duration_seconds: float
    clip_counts: dict[str, int]
    total_clips: int
    has_video: bool
    has_audio: bool
    has_text: bool


class TimelineRead(BaseModel):
    """The whole timeline, normalized, plus what the editor needs around it.

    `revision` is the project's, and it comes back on every response so the
    client can send it with the next save and be told about a conflicting edit
    from another tab rather than silently overwriting it.

    The canvas travels with the document because every position in it is a
    fraction of the canvas — a preview that guessed the dimensions would frame
    every clip differently from the export.
    """

    project_id: int
    revision: int
    timeline: dict
    summary: TimelineSummary
    width: int
    height: int
    fps: int
    aspect_ratio: str
    # Assets the timeline references, resolved to playable URLs. Sent with the
    # document so the preview can draw the first frame without a second
    # request per clip.
    assets: list[dict] = Field(default_factory=list)

    # Where each visual clip lands on the canvas, in pixels, keyed by clip id
    # — computed by the *compositor's own* `place()`. The preview draws these
    # numbers rather than doing its own crop-and-fit arithmetic, which is what
    # stops the browser and the encoder disagreeing about framing.
    placements: dict[str, dict] = Field(default_factory=dict)


class TimelineSave(BaseModel):
    """A full replacement. Used by autosave, undo and redo.

    Undo is a document swap rather than an inverse operation: reversing a
    split, a ripple delete and a reorder correctly is three more rule
    implementations to keep in step, and a stack of documents cannot drift.
    """

    timeline: dict
    # The revision the client loaded. Omitting it forces the save, which is
    # what a first write after opening does.
    expected_revision: int | None = None
    autosave: bool = True


class TimelineOperation(BaseModel):
    """One edit.

    Fields are optional because each `op` uses a different subset; which ones
    are required is enforced in the service, where the rule already lives, so
    the two cannot disagree about what a valid split is.
    """

    op: Literal[
        "add", "move", "trim", "split", "delete", "reorder", "update"
    ]

    # add
    track_id: str | None = None
    clip: dict | None = None
    at: float | None = None

    # move / trim / split / delete / update
    clip_id: str | None = None
    start: float | None = None
    edge: Literal["start", "end"] | None = None
    to: float | None = None
    ripple: bool = False
    patch: dict | None = None

    # reorder
    clip_ids: list[str] | None = None

    expected_revision: int | None = None


class TimelineOperationResult(TimelineRead):
    """The new document, plus what the operation touched.

    `affected_clip_ids` lets the editor keep a selection through an edit that
    changed which clips exist — a split leaves two clips where one was, and an
    editor that dropped the selection on every split would be exhausting.
    """

    affected_clip_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


class RenderRequest(BaseModel):
    quality: Literal["draft", "standard", "high"] | None = None


class RenderRead(BaseModel):
    """One export attempt.

    Carries `error_code` as well as `error` on purpose: the message is for the
    person, the code is what the UI branches on to offer the right next step —
    "open the project" for a missing clip, "try again" for storage.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    status: str
    stage: str
    # The shorter vocabulary a person is shown — Queued, Processing,
    # Rendering, Finalizing, Completed, Failed, Cancelled — *derived* from the
    # real status and stage rather than tracked separately, so nothing can
    # report "Rendering" while the worker is still downloading.
    phase: str = "queued"
    phase_label: str = "Queued"
    progress: float
    attempt: int
    settings: dict = Field(default_factory=dict)
    error: str | None = None
    error_code: str | None = None
    error_stage: str | None = None
    duration_seconds: float | None = None
    output_asset_id: int | None = None
    # Where to watch or download the finished file. None until it exists.
    output_url: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RenderList(BaseModel):
    renders: list[RenderRead]
    # The one still running, if any — so the editor can reattach its progress
    # bar after a reload without scanning the list itself.
    active: RenderRead | None = None
