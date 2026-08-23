"""VideoProject ORM model — the unit of work in Video Studio.

Video Studio's core rule is "independent tools, unified projects": Voice Studio,
Subtitle Studio and the editor each work on their own, and a project is what
they connect to when the user wants one thing rather than three files. This
table is that connection point.

**What is a column, what is JSON, and what is its own table.**

  * *Columns* — anything queried, sorted, filtered or authorised on: owner,
    platform, status, dimensions, duration, timestamps.
  * *JSON documents* — the timeline, the script, brand and export settings.
    The editor reads and writes the whole timeline in one autosave, and the
    renderer must consume exactly the document the preview rendered.
    Normalising a timeline into clip / track / keyframe tables would mean a
    dozen statements per keystroke and a diffing layer to work out which.
  * *Their own tables* — scenes (`video_scenes`), audio layers (`video_audio`)
    and subtitle tracks (`video_subtitles`). Each of those is addressed
    individually all the time ("regenerate scene 3", "mute the music", "export
    the Urdu track"), produced by tools that run with no project open, and
    edited concurrently. Rows, not fields.

Binary is never here. Every asset is a row in `video_assets` pointing at an
object-storage key; the timeline and the scenes reference assets by id.
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# How the project was started. Recorded because the Create Video screen offers
# six routes into the same editor and the UI reopens a project the way it was
# begun — a repurpose project shows its clips, a blank one shows the timeline.
PROJECT_TYPES = (
    "ai",
    "blank",
    "script",
    "existing_video",
    "audio",
    "repurpose",
)

# Lifecycle. `processing`/`completed`/`failed` mirror the newest VideoRender, so
# the projects list can show state without joining every job.
#
# A project has no `cancelled` state, though a render does: cancelling an export
# returns the project to `draft`, because the project itself was never in a
# cancelled condition — one attempt at exporting it was.
PROJECT_STATUSES = ("draft", "processing", "completed", "failed")

# The four tracks the editor shows, in the order it stacks them. Named here so
# a project created today opens in that editor without a backfill.
#
# Text and subtitles are separate tracks on purpose: a title card and a caption
# are edited by different tools, have different styling, and only one of them is
# regenerated when the transcript changes.
EMPTY_TIMELINE: dict = {
    "version": 1,
    "tracks": [
        {"id": "text", "kind": "text", "label": "Text", "clips": []},
        {"id": "video", "kind": "video", "label": "Video", "clips": []},
        {"id": "audio", "kind": "audio", "label": "Audio", "clips": []},
        {"id": "subtitles", "kind": "subtitles", "label": "Subtitles", "clips": []},
    ],
}


class VideoProject(Base):
    __tablename__ = "video_projects"
    __table_args__ = {"info": {"alembic_only": True}}

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    name: Mapped[str] = mapped_column(String(200), default="Untitled project", nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    project_type: Mapped[str] = mapped_column(String(30), default="blank", nullable=False)

    # ---- Format ----------------------------------------------------------
    # Platform is the preset the user picked; the three numbers are what the
    # renderer actually uses. Both are stored because a project can be resized
    # away from its preset, and "YouTube Shorts" must not then be a lie.
    platform: Mapped[str] = mapped_column(String(40), default="youtube_shorts", nullable=False)
    aspect_ratio: Mapped[str] = mapped_column(String(12), default="9:16", nullable=False)
    width: Mapped[int] = mapped_column(Integer, default=1080, nullable=False)
    height: Mapped[int] = mapped_column(Integer, default=1920, nullable=False)
    fps: Mapped[int] = mapped_column(Integer, default=30, nullable=False)

    # Timeline length in seconds, recomputed whenever the timeline is saved.
    # A column rather than a JSON field because the projects list sorts and
    # displays it, and the render limit is checked against it.
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    status: Mapped[str] = mapped_column(
        String(20), default="draft", index=True, nullable=False
    )

    # ---- Content documents ----------------------------------------------
    # Script Studio's output: hook, intro, sections, ending, CTA — plus the
    # plain text the user may have pasted or edited by hand.
    script: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # The editable document both the preview and the renderer read.
    #
    # Scenes, audio layers and subtitle tracks are NOT here — they are rows in
    # video_scenes / video_audio / video_subtitles. See the module docstring.
    timeline: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # ---- Settings --------------------------------------------------------
    # {"apply": bool, ...overrides} — whether the user's Brand Kit is painted
    # onto this project, and anything they changed for this project only.
    brand: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # The template this project was started from, kept for display only. A
    # template supplies a starting document and is then out of the picture —
    # SET NULL so withdrawing one never reaches into a finished video.
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("video_templates.id", ondelete="SET NULL"), default=None
    )
    template_key: Mapped[str | None] = mapped_column(String(80), default=None)
    # Format, resolution, fps, quality, burn-in — remembered per project so the
    # export dialog reopens on the last choice.
    export_settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # The poster frame shown in the projects grid. A VideoAsset id rather than
    # a URL: assets are addressed through the storage layer, and a URL on a row
    # would pin the project to whichever backend produced it.
    thumbnail_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("video_assets.id", ondelete="SET NULL"), default=None
    )

    notes: Mapped[str | None] = mapped_column(Text, default=None)

    # ---- Autosave --------------------------------------------------------
    # Incremented on every save. The editor sends the revision it loaded, and a
    # mismatch means the project changed underneath it — two tabs, or a phone
    # and a laptop. Without this the second tab silently overwrites the first,
    # which is the one bug an autosaving editor must never have.
    revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # When the editor last wrote, as distinct from `updated_at`, which any
    # write touches. Shown as "Saved 14:02" and used to throttle snapshots.
    last_autosave_at: Mapped[datetime | None] = mapped_column(
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

    # ---- Children --------------------------------------------------------
    # Cascades are declared on both sides: `ondelete` above is the database
    # enforcing it (and the only thing that applies to a bulk DELETE), while
    # `cascade="all, delete-orphan"` is the ORM doing the same for a session
    # that has the objects loaded. SQLite does not enforce foreign keys by
    # default, so without the ORM half the test suite would leave orphans that
    # Postgres never would.
    scenes = relationship(
        "VideoScene",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="VideoScene.position",
    )
    audio_layers = relationship(
        "VideoAudio",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="VideoAudio.position",
    )
    subtitle_tracks = relationship(
        "VideoSubtitle",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    versions = relationship(
        "VideoProjectVersion",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="VideoProjectVersion.created_at.desc()",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<VideoProject id={self.id} name={self.name!r} "
            f"platform={self.platform} status={self.status}>"
        )
