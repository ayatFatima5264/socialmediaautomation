"""VideoProjectVersion ORM model — a snapshot of a project at one revision.

An editor that autosaves has to answer "undo that" after a reload, after a
crash, and after the user changed their mind an hour later. `revision` on the
project tells you *that* it changed; this table is what lets you go back.

A version is written on meaningful saves, not on every keystroke — see
`app/services/video/versions.py` for the throttle. Each row holds the whole
document rather than a diff: a project is tens of kilobytes of JSON, diffing
would need a merge implementation to read one back, and the point of a restore
is that it cannot half-apply.

The history is **capped** (`MAX_VERSIONS_PER_PROJECT`). Unbounded snapshots of
an autosaving editor is a table that grows without limit for a feature nobody
uses past the last handful of states, and the oldest rows are pruned on write.

`label` is set when a version is worth naming — "before AI rebuild", "restored
from 14:02". An unlabelled row is an ordinary autosave.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# How many snapshots one project keeps. Enough to cover a working session;
# small enough that a thousand projects is megabytes, not gigabytes.
MAX_VERSIONS_PER_PROJECT = 20

# What made this version. `autosave` is the editor saving as the user works;
# `manual` is an explicit save point; `pre_restore` is written just before a
# restore so restoring is itself undoable; `pre_ai` is written before a
# generator rewrites the timeline.
VERSION_REASONS = ("autosave", "manual", "pre_restore", "pre_ai", "pre_render")


class VideoProjectVersion(Base):
    __tablename__ = "video_project_versions"
    __table_args__ = {"info": {"alembic_only": True}}

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("video_projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # The project's `revision` at the moment of the snapshot. Not unique: a
    # pre_restore row and an autosave row can share one, and a unique index
    # would make writing the safety snapshot fail exactly when it matters.
    revision: Mapped[int] = mapped_column(Integer, default=0, index=True, nullable=False)
    reason: Mapped[str] = mapped_column(String(20), default="autosave", nullable=False)
    label: Mapped[str | None] = mapped_column(String(120), default=None)

    # The whole project document: name, format, script, timeline, brand,
    # export settings, plus the scenes / audio / subtitle rows serialised.
    # Restoring writes all of it back inside one transaction.
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<VideoProjectVersion project={self.project_id} "
            f"rev={self.revision} reason={self.reason}>"
        )
