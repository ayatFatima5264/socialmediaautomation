"""VideoRender ORM model — one attempt at turning a project into a file.

Rendering is the one operation in Video Studio that cannot be a request/response
cycle: a 60-second 1080p encode outlives any sensible HTTP timeout. So a render
is a row. The client posts a job, gets an id, and polls it; the work happens
elsewhere and reports progress by updating this row.

That indirection is also the answer to "move rendering to a worker later". The
API contract is this table, not a function call — a queue consumer on another
machine writes the same columns, and the frontend never learns the difference.

Two product rules are enforced by the shape:

  * **A failed render must never destroy the project.** The job holds the
    failure — status, message, the stage it died in — and the project is
    untouched. Retrying creates a new job rather than mutating this one, so the
    history of what was attempted survives.
  * **Progress must be real.** `progress` and `stage` are written by the
    renderer as it works, from ffmpeg's own reported position. Nothing may set
    them on a timer; a bar that moves while nothing happens is worse than no
    bar at all.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# The lifecycle of one attempt.
#
# Note there is no "draft" here, though a *project* has one. A render row only
# exists because somebody pressed Export, so its first state is `queued` —
# waiting for a worker slot. A job that has not been requested is not a row.
RENDER_STATUSES = ("queued", "processing", "completed", "failed", "cancelled")

# States from which nothing further happens. Used to decide whether a job can
# still be cancelled and whether the worker may claim it.
TERMINAL_RENDER_STATUSES = ("completed", "failed", "cancelled")

# The stages a render reports, in order. Named here so the API, the renderer
# and the progress UI agree on the vocabulary instead of passing free text.
RENDER_STAGES = (
    "queued",
    "preparing",     # validating the timeline, resolving assets
    "downloading",   # pulling source objects out of the bucket
    "scenes",        # compositing the visual track
    "audio",         # mixing voice-over and music
    "subtitles",     # generating and burning in captions
    "encoding",      # the ffmpeg pass — where the real time goes
    "uploading",     # writing the finished file back to storage
    "done",
)

# Why a render failed, in a form the UI can branch on. The human-readable
# message stays in `error`; this is for deciding whether to offer "try again",
# "shorten the video" or "reconnect storage".
RENDER_ERROR_CODES = (
    "invalid_timeline",
    "missing_asset",
    "storage_error",
    "ffmpeg_error",
    "timeout",
    "cancelled",
    "limit_exceeded",
    "interrupted",   # the process died mid-render (deploy, OOM, restart)
    "unknown",
)


# The phases a person is shown, as opposed to the stages the worker writes.
#
# `stage` is engineering detail — "downloading", "scenes", "uploading" — and
# there are nine of them. What somebody watching an export needs is the shorter
# vocabulary below, and it is *derived* from the real stage rather than tracked
# separately: there is no second field to drift, and nothing can report
# "Rendering" while the worker is actually still downloading.
RENDER_PHASES = (
    "queued",
    "processing",
    "rendering",
    "finalizing",
    "completed",
    "failed",
    "cancelled",
)

# Which stages belong to which phase. Every stage in RENDER_STAGES appears
# exactly once, so a stage added later without updating this map is a visible
# omission rather than a silent fallback.
_PHASE_BY_STAGE = {
    "queued": "queued",
    "preparing": "processing",
    "downloading": "processing",
    "scenes": "rendering",
    "audio": "rendering",
    "subtitles": "rendering",
    "encoding": "rendering",
    "uploading": "finalizing",
    "done": "completed",
}

PHASE_LABELS = {
    "queued": "Queued",
    "processing": "Processing",
    "rendering": "Rendering",
    "finalizing": "Finalizing",
    "completed": "Completed",
    "failed": "Failed",
    "cancelled": "Cancelled",
}


def phase_of(status: str, stage: str) -> str:
    """The phase to show for a render, from its real status and stage.

    Terminal statuses win: a job that failed while encoding is "failed", not
    "rendering". Everything else is decided by the stage the worker last
    reported, so the phase moves only when actual work has moved.
    """
    if status in ("completed", "failed", "cancelled"):
        return status
    if status == "queued":
        return "queued"
    return _PHASE_BY_STAGE.get(stage, "processing")


class VideoRender(Base):
    __tablename__ = "video_renders"
    __table_args__ = {"info": {"alembic_only": True}}

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("video_projects.id", ondelete="CASCADE"), index=True, nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(20), default="queued", index=True, nullable=False
    )
    stage: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    # 0.0 – 1.0. Written by the renderer only when it has actually advanced.
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # What was asked for: format, resolution, fps, quality, burn_subtitles.
    # Frozen onto the job so a re-read of a finished render reports the settings
    # it was made with, not whatever the project's defaults say today.
    settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # A snapshot of the timeline as it was when the job was queued. Editing the
    # project mid-render must not change what is being encoded, and a retry
    # must reproduce the same file.
    timeline_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # The finished file. NULL until the render completes.
    output_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("video_assets.id", ondelete="SET NULL"), default=None
    )

    # Kept in full: a render fails for reasons the user cannot see (a codec, a
    # missing asset, an out-of-memory kill), and a one-line "render failed"
    # makes that unsupportable.
    error: Mapped[str | None] = mapped_column(Text, default=None)
    error_code: Mapped[str | None] = mapped_column(String(30), default=None)
    # The stage the failure happened in, kept separately from `stage` so the
    # job can be left showing where it got to rather than being rewound.
    error_stage: Mapped[str | None] = mapped_column(String(20), default=None)

    # Which retry this is, for the same project. Not a counter on the project:
    # each attempt is its own row with its own outcome.
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Measured, not estimated — used to meter render_seconds honestly and to
    # tell the user roughly how long the next one will take.
    duration_seconds: Mapped[float | None] = mapped_column(Float, default=None)

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    @property
    def is_terminal(self) -> bool:
        """Has this attempt finished, one way or another?"""
        return self.status in TERMINAL_RENDER_STATUSES

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<VideoRender id={self.id} project={self.project_id} "
            f"status={self.status} stage={self.stage} progress={self.progress:.2f}>"
        )
