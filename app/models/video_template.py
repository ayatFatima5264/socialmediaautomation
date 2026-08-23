"""VideoTemplate ORM model — a starting point a project is created from.

A template is a *project shaped like an example*: a canvas, a subtitle style, a
set of scene placeholders and some brand defaults. Applying one fills in a new
project's documents; it does not link the two. That is deliberate — a template
edited or withdrawn later must not reach back into a video someone already
published from it.

Two kinds of row live here, told apart by `user_id`:

  * **System templates** (`user_id` NULL, `is_system` True) ship with the app
    and are visible to everyone. They are seeded by
    `app/services/video/templates.py` and re-seeded on every boot, so editing
    the code is how they change.
  * **User templates** (`user_id` set) are somebody's own saved project
    settings, visible only to them.

`definition` is one JSON document rather than a column per setting because it
is written by the seeder and read by the project factory, and nothing queries
inside it. What IS queried — category, platform, dimensions — are columns.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# How the template library groups its tabs. Mirrors the categories the
# Templates screen shows; a value outside this list is still stored, so adding
# a category is a seeder change rather than a migration.
#
# Two kinds of category sit in one list, deliberately. The first four are
# *surfaces* — where the video is going, which decides the canvas. The rest are
# *subjects* — what the video is about, which decides the storyboard. People
# arrive at this screen from both directions ("I need a TikTok" and "I need an
# explainer"), and splitting them into two filter rows makes the user answer
# two questions to reach one grid.
TEMPLATE_CATEGORIES = (
    # surfaces
    "youtube",
    "shorts",
    "tiktok",
    "reels",
    # subjects
    "educational",
    "business",
    "motivation",
    "facts",
    "product",
    "documentary",
    "storytelling",
    "animated",
    "other",
)

# Which of the above name a destination rather than a subject. Used by the UI
# to order the filter row so the surfaces come first; not a storage rule.
SURFACE_CATEGORIES = ("youtube", "shorts", "tiktok", "reels")


class VideoTemplate(Base):
    __tablename__ = "video_templates"
    __table_args__ = {"info": {"alembic_only": True}}

    id: Mapped[int] = mapped_column(primary_key=True)

    # Stable identifier used by the seeder and by `template_key` on a project.
    # Unique across system and user templates so one namespace addresses both.
    key: Mapped[str] = mapped_column(
        String(80), unique=True, index=True, nullable=False
    )

    # NULL means a system template, visible to every account. A template with
    # an owner is private to them.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, default=None
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[str] = mapped_column(String(40), index=True, default="other", nullable=False)

    # The canvas a project made from this template starts on.
    platform: Mapped[str] = mapped_column(String(40), default="youtube_shorts", nullable=False)
    aspect_ratio: Mapped[str] = mapped_column(String(12), default="9:16", nullable=False)
    width: Mapped[int] = mapped_column(Integer, default=1080, nullable=False)
    height: Mapped[int] = mapped_column(Integer, default=1920, nullable=False)
    fps: Mapped[int] = mapped_column(Integer, default=30, nullable=False)

    # {"timeline": {...}, "scenes": [...], "subtitle_style": {...},
    #  "brand": {...}, "export_settings": {...}} — whatever the factory copies.
    definition: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # The card image in the template picker. An asset id rather than a URL, for
    # the same reason the project's thumbnail is: assets are addressed through
    # the storage layer. NULL until artwork exists, which is the state every
    # seeded template starts in.
    preview_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("video_assets.id", ondelete="SET NULL"), default=None
    )

    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Position in the library. Lower sorts first; ties fall back to name.
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

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
        owner = "system" if self.user_id is None else f"user={self.user_id}"
        return f"<VideoTemplate key={self.key!r} {owner} platform={self.platform}>"
