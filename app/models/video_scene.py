"""VideoScene ORM model — one beat of a project's storyboard.

A scene is the unit the *script* is broken into: a line of narration, a note
about what should be on screen, and eventually the asset that ended up there.
It sits between the script and the timeline, and it is a row rather than an
entry in a JSON blob because scenes are addressed individually all the time —
"regenerate this scene's visual", "re-record this line", "swap scene 4's clip",
"delete scene 2". Each of those is an update to one row instead of a
read-modify-write of the whole project document, which is what makes two of
them running at once safe.

**Scenes are not the timeline.** The timeline (JSON on the project) is what the
editor manipulates and the renderer compiles, and it can hold things no scene
describes — a b-roll cutaway, a logo sting, a trimmed clip. Scenes are the
narrative outline the timeline is first *built from*, and they stay editable
afterwards so "regenerate scene 3" still means something once the user has
started editing. `projects.rebuild_timeline_from_scenes()` is the one direction
that is automatic; nothing writes back the other way.

Ordering is an explicit `position` integer, not the primary key: scenes get
reordered, and a list whose order depends on insertion order cannot be.
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

# How a scene hands over to the next one. The renderer maps these onto ffmpeg
# xfade transitions; "cut" means no transition at all and is the default,
# because a transition on every scene is the look of a template, not an edit.
SCENE_TRANSITIONS = ("cut", "fade", "slide", "zoom", "wipe", "dissolve")

# Where a scene's visual comes from. Recorded so "regenerate" knows what to do
# again, and so the UI can show why a scene has no picture yet.
SCENE_SOURCES = ("pending", "ai_image", "stock", "upload", "color", "asset")


class VideoScene(Base):
    __tablename__ = "video_scenes"
    __table_args__ = {"info": {"alembic_only": True}}

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("video_projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # 0-based, dense after any reorder. Not unique-constrained: reordering a
    # list under a unique index means a temporary collision on every swap.
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    title: Mapped[str | None] = mapped_column(String(200), default=None)
    # What is said over this scene — the narration line the voice-over reads.
    text: Mapped[str | None] = mapped_column(Text, default=None)
    # What should be on screen, in words. The prompt an image is generated
    # from, or the query a stock clip is searched with. Kept after the asset
    # is chosen so the scene can be regenerated without re-deriving it.
    visual_prompt: Mapped[str | None] = mapped_column(Text, default=None)

    source: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # The visual actually in use. SET NULL, not CASCADE: deleting an image from
    # the library empties the scene rather than destroying the writing in it.
    asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("video_assets.id", ondelete="SET NULL"), index=True, default=None
    )
    # The narration audio for this scene, when it was generated per-scene
    # rather than as one voice-over for the whole project.
    voice_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("video_assets.id", ondelete="SET NULL"), default=None
    )

    # Seconds. `start_seconds` is derived from the durations before it and is
    # stored so the editor can lay scenes out without walking the whole list.
    start_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)

    transition: Mapped[str] = mapped_column(String(20), default="cut", nullable=False)

    # Ken Burns direction, text overlay, filter, crop — anything the renderer
    # needs that is specific to how this one scene is shot.
    settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

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
            f"<VideoScene project={self.project_id} #{self.position} "
            f"{self.duration_seconds}s source={self.source}>"
        )
