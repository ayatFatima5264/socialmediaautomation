"""VideoAudio ORM model — one audio layer attached to a project.

A finished video usually has two or three audio layers running at once: the
voice-over, a music bed under it, and occasionally a sound effect. They are
mixed, not sequenced, so they cannot be positions in one list — each needs its
own gain, fades, offset and looping, and the music needs to know it should duck
under the speech.

That is what this table is: one row per layer, referencing a `VideoAsset` for
the actual audio. The bytes live in object storage like every other asset; this
row is only how the project uses them.

**Why not a track in the timeline JSON.** Audio is the one thing produced
*outside* the editor — Voice Studio makes a voice-over with no project open,
the music library adds a bed from a different screen. Both need somewhere to
attach to a project before a timeline exists, and both need to survive the
timeline being rebuilt from a changed script. A row does that; a clip in a
document that gets regenerated does not.
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

# What this layer is for. The role decides mixing behaviour, not just a label:
# `voiceover` is what music ducks under, and only one of them is primary.
AUDIO_ROLES = ("voiceover", "music", "sfx", "original")


class VideoAudio(Base):
    __tablename__ = "video_audio"
    __table_args__ = {"info": {"alembic_only": True}}

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("video_projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # SET NULL rather than CASCADE. Deleting a music track from the library
    # should silence the layer, not delete the layer's settings — the user
    # picked a volume and a fade, and those are worth keeping while they
    # choose a replacement.
    asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("video_assets.id", ondelete="SET NULL"), index=True, default=None
    )

    role: Mapped[str] = mapped_column(String(20), default="music", index=True, nullable=False)
    label: Mapped[str | None] = mapped_column(String(200), default=None)
    # Stacking order within a role, for the rare case of two music beds.
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ---- Placement -------------------------------------------------------
    # Where the layer starts on the project's clock, and how much of the source
    # is used. `duration_seconds` NULL means "as long as the source is", which
    # is what a voice-over almost always wants.
    start_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    trim_start: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    trim_end: Mapped[float | None] = mapped_column(Float, default=None)

    # ---- Mixing ----------------------------------------------------------
    # 0.0–1.0 linear gain. Music defaults well below speech because a bed at
    # full volume is the single most common way an auto-assembled video comes
    # out unusable.
    volume: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    fade_in: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    fade_out: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Automatically drop this layer while the voice-over is speaking.
    ducking: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Repeat the source to cover `duration_seconds` — how a 30-second music
    # loop scores a two-minute video.
    loop: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    muted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Licence and attribution for a stock track, the voice and language of a
    # voice-over — whatever has to travel with the layer.
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
            f"<VideoAudio project={self.project_id} role={self.role} "
            f"asset={self.asset_id} volume={self.volume}>"
        )
