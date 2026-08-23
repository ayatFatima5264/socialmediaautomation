"""Request and response shapes for export, conversion and publishing.

Two things run through this file.

**Every "cannot" carries a reason.** `ExportItem.reason`, `FormatOption.reason`,
`PublishTarget.reason` — an unavailable option is returned with the sentence
that explains it rather than omitted. A screen that hides what is not ready
leaves the user unable to tell a missing feature from an unfinished project.

**Publishing prepares a draft and says so.** `PreparedPost.status` is the
post's real status, which is always `draft`. There is no field here that could
express "published", because nothing in this path publishes.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


class ExportItem(BaseModel):
    """One deliverable, and whether it exists yet."""

    kind: str
    label: str
    content_type: str
    group: str
    description: str
    available: bool
    # The next action to take when it is not available — "Render the video
    # first", not "no render".
    reason: str | None = None
    # Known only for files that already exist; a derived export has no size
    # until it is produced, and guessing would be worse than saying nothing.
    size_bytes: int | None = None


class ExportManifest(BaseModel):
    project_id: int
    project_name: str
    platform: str
    aspect_ratio: str
    width: int
    height: int
    fps: int
    duration_seconds: float
    # The render everything derives from, if there is one.
    render_id: int | None = None
    items: list[ExportItem]


# ---------------------------------------------------------------------------
# Formats
# ---------------------------------------------------------------------------


class FormatOption(BaseModel):
    key: str
    label: str
    aspect_ratio: str
    width: int
    height: int
    max_seconds: int
    description: str
    # False when the project is longer than the platform allows. Reported
    # rather than hidden, so "why can I not make a Reel of this" has an answer.
    fits: bool = True
    reason: str | None = None


class FormatOptions(BaseModel):
    project_id: int
    current: str
    duration_seconds: float
    formats: list[FormatOption]


class ConvertRequest(BaseModel):
    """Create a new project in another format. The original is not modified."""

    target: str
    name: str | None = Field(default=None, max_length=200)
    copy_scenes: bool = True
    copy_subtitles: bool = True


class ConvertResult(BaseModel):
    project_id: int
    name: str
    platform: str
    aspect_ratio: str
    width: int
    height: int
    # The project it came from, unchanged.
    source_project_id: int
    editor_path: str


# ---------------------------------------------------------------------------
# Publishing
# ---------------------------------------------------------------------------


class PublishTarget(BaseModel):
    """One platform, and the two separate things that can stand in the way.

    `connected` and `video_upload_supported` are reported apart because they
    are fixed in different places — one by the user in Social Accounts, one by
    the adapter code — and collapsing them into a single "unavailable" would
    tell the user the wrong thing to do.
    """

    platform: str
    label: str
    connected: bool
    video_upload_supported: bool
    reason: str | None = None
    # The platform this project's canvas was made for.
    suggested: bool = False


class PublishTargets(BaseModel):
    project_id: int
    # False until there is a finished render — there is nothing to post yet.
    ready: bool
    reason: str | None = None
    targets: list[PublishTarget]
    # Surfaces this video is sized for that the app has no connection to at
    # all (YouTube, TikTok). Export-only, and named so a Shorts project does
    # not just show six platforms that are not the one it was made for.
    export_only: list[str] = Field(default_factory=list)
    export_only_note: str = ""


class PublishRequest(BaseModel):
    platform: str
    caption: str | None = Field(default=None, max_length=63206)
    hashtags: list[str] | None = None
    # Stored on the draft so the composer opens with it filled in. It does
    # **not** schedule anything — see `publishing.prepare_post`.
    scheduled_time: datetime | None = None


class PreparedPost(BaseModel):
    """The draft that was created. Always `draft`; nothing was published."""

    post_id: int
    platform: str
    status: str
    content: str
    hashtags: list[str] = Field(default_factory=list)
    media: list[str] = Field(default_factory=list)
    scheduled_time: datetime | None = None
    review_path: str
