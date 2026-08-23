"""VideoSubtitle ORM model — one subtitle track on a project.

A track is a language: the English captions and the Urdu translation of the
same video are two rows, each with its own cues and its own style, and exactly
one of them is `is_primary` — the one that gets burned in if burn-in is on.

**Why the cues are a JSON column and not a `video_subtitle_cues` table.** A
three-minute video is 60–90 cues, and they are never addressed individually:
Subtitle Studio loads the whole track, the user edits it, and the whole track is
saved. Splitting that into rows would turn one read and one write into ninety of
each, and would need a diffing layer to work out which cue moved — for data
that has no meaning outside its track. Cue rows would buy per-cue queries that
nothing in the product performs.

The cue shape is fixed and shared with `app/services/video/subtitles.py`:

    [{"start": 0.0, "end": 2.4, "text": "Hello"}, ...]

Seconds from the start of the media. That one shape is what Subtitle Studio
edits, what SRT and VTT are written from, and what the renderer burns in — so
there is never a conversion step where timing can drift.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Where the cues came from. Kept because it decides what "regenerate" does and
# because a machine transcript deserves a "check this" hint that hand-typed
# cues do not.
SUBTITLE_SOURCES = ("transcription", "script", "upload", "manual", "translation")


class VideoSubtitle(Base):
    __tablename__ = "video_subtitles"
    __table_args__ = {"info": {"alembic_only": True}}

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("video_projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # BCP-47 ("en-US", "ur-PK"). Not constrained to a list: a translation can
    # target any language the text provider handles.
    language: Mapped[str] = mapped_column(String(20), default="en-US", nullable=False)
    label: Mapped[str | None] = mapped_column(String(120), default=None)
    source: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)

    # The track burned in when burn-in is enabled, and the one shown in the
    # editor's subtitle row. Enforced in the service, not by a partial unique
    # index — the constraint syntax differs between SQLite and Postgres, and
    # the rule is "the service sets it", not "the database refuses it".
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # [{"start": float, "end": float, "text": str}] — see the module docstring.
    cues: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # Font, size, position, colours, animation: one of the Subtitle Studio
    # presets or a customised copy of one.
    style: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Denormalised so the subtitle list can show "72 cues · 2:58" without
    # loading every cue array. Recomputed by the service on every write.
    cue_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # The last exported .srt / .vtt file, when one has been made. The cues here
    # stay the source of truth; the asset is a copy the user downloaded, and it
    # goes stale the moment they edit a cue. SET NULL so deleting the file does
    # not take the track with it.
    asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("video_assets.id", ondelete="SET NULL"), default=None
    )

    # Provider, model and detected language of a transcription; the source
    # track of a translation.
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<VideoSubtitle project={self.project_id} {self.language} "
            f"cues={self.cue_count} primary={self.is_primary}>"
        )
