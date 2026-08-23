"""Request and response shapes for Video Studio.

Two rules shape what is and is not in here:

  * **The server decides derived values.** `duration_seconds`, `revision`,
    `status` and the canvas dimensions come back on every read and are absent
    from every write. A client that could set its own duration could get past
    the render limit; one that could set its own revision could defeat the
    conflict check.
  * **Every write field is optional.** The editor autosaves a partial patch —
    just the timeline, just the name — and requiring the whole object would
    mean every save races every other field.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Presets and capabilities
# ---------------------------------------------------------------------------


class PlatformPresetRead(BaseModel):
    key: str
    label: str
    family: str
    aspect_ratio: str
    width: int
    height: int
    fps: int
    platform_max_seconds: int
    description: str


class StudioLimits(BaseModel):
    max_duration_seconds: int
    max_resolution_height: int
    max_upload_mb: int
    max_concurrent_renders: int
    reason: str


class StudioCapabilities(BaseModel):
    """What this deployment can actually do right now.

    The UI reads this instead of assuming. A studio that offers a voice-over
    button on a deployment with no TTS provider configured is a dead end the
    user only discovers after writing a script.
    """

    presets: list[PlatformPresetRead]
    aspect_ratios: dict[str, list[int]]
    limits: StudioLimits
    storage_backend: str
    storage_is_persistent: bool
    ffmpeg_available: bool
    project_types: list[str]

    # ---- Editor ----------------------------------------------------------
    # The vocabularies the timeline editor's controls are built from, served
    # rather than duplicated in JavaScript. The renderer has to understand
    # every value the editor can produce, so a dropdown offering an animation
    # the compositor has never heard of is a title that looks right in the
    # browser and is missing from the export.
    editor: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


class TemplateRead(BaseModel):
    """One template in the picker.

    Carries `preview` — the colours and sample line the card draws itself from
    — rather than an image URL. A template stores configuration, not a rendered
    video, so there is no frame to show; generating the card from the same
    definition the project will be built from is the only preview that cannot
    lie about what you are about to get.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    name: str
    description: str | None = None
    category: str
    category_label: str = ""
    platform: str
    aspect_ratio: str
    width: int
    height: int
    fps: int
    is_system: bool
    scene_count: int = 0
    # Total of the scene durations, so a card can say "≈ 32s" — the single
    # most useful thing to know before picking a template for a 30-second slot.
    estimated_seconds: float = 0.0
    preview: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class TemplateDetail(TemplateRead):
    """A template opened for preview, before committing to it.

    The scene skeleton and the caption style are what somebody is actually
    deciding between, so "Preview" shows them rather than a bigger version of
    the card.
    """

    scenes: list[dict] = Field(default_factory=list)
    subtitle_style: dict = Field(default_factory=dict)
    layout: dict = Field(default_factory=dict)
    export_settings: dict = Field(default_factory=dict)


class TemplateCategory(BaseModel):
    """One tab in the template library's filter row."""

    key: str
    label: str
    count: int
    # Surfaces (YouTube, Shorts, TikTok, Reels) sort ahead of subjects. See
    # TEMPLATE_CATEGORIES in app/models/video_template.py.
    is_surface: bool = False


class TemplateLibrary(BaseModel):
    templates: list[TemplateRead]
    categories: list[TemplateCategory]


class TemplateSave(BaseModel):
    """Save a project's setup as a reusable template of your own."""

    project_id: int
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None, max_length=40)
    # The scene skeleton — titles, durations, transitions — but never the
    # scenes' text. See `templates.save_user_template`.
    include_scenes: bool = True


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


class ProjectCreate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    project_type: str = "blank"
    platform: str | None = None
    aspect_ratio: str | None = None
    # Only meaningful with platform="custom"; otherwise the preset wins.
    width: int | None = Field(default=None, ge=64, le=7680)
    height: int | None = Field(default=None, ge=64, le=7680)
    fps: int | None = Field(default=None, ge=1, le=60)
    template_key: str | None = None
    apply_brand: bool = True


class ProjectUpdate(BaseModel):
    """A partial save. Every field optional — see the module docstring."""

    name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    project_type: str | None = None
    platform: str | None = None
    aspect_ratio: str | None = None
    width: int | None = Field(default=None, ge=64, le=7680)
    height: int | None = Field(default=None, ge=64, le=7680)
    fps: int | None = Field(default=None, ge=1, le=60)
    status: str | None = None
    script: dict | None = None
    timeline: dict | None = None
    brand: dict | None = None
    template_key: str | None = None
    export_settings: dict | None = None
    thumbnail_asset_id: int | None = None
    notes: str | None = None

    # The revision the client loaded. Sending it makes the save a
    # compare-and-set; omitting it is a deliberate force, which is what a
    # rename from the projects list does.
    expected_revision: int | None = None
    # Marks this as an editor autosave rather than an explicit save, which
    # stamps `last_autosave_at` and lets the version throttle collapse a run of
    # them into one snapshot.
    autosave: bool = False


class ProjectRename(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    project_type: str
    platform: str
    aspect_ratio: str
    width: int
    height: int
    fps: int
    duration_seconds: float
    status: str
    template_key: str | None = None
    thumbnail_asset_id: int | None = None
    thumbnail_url: str | None = None
    revision: int
    created_at: datetime
    updated_at: datetime
    last_autosave_at: datetime | None = None

    # Counts rather than the rows themselves. The projects grid shows "6 scenes
    # · 2 audio tracks" and would otherwise download every cue in every project
    # to render a card.
    scene_count: int = 0
    audio_count: int = 0
    subtitle_count: int = 0


class ProjectDetail(ProjectRead):
    """One project, opened. Carries the documents the list deliberately omits."""

    script: dict = Field(default_factory=dict)
    timeline: dict = Field(default_factory=dict)
    brand: dict = Field(default_factory=dict)
    export_settings: dict = Field(default_factory=dict)
    notes: str | None = None


class ProjectList(BaseModel):
    """A page of projects plus the total, so the UI can say "12 of 48"."""

    projects: list[ProjectRead]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------


class AssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None = None
    kind: str
    title: str
    filename: str | None = None
    content_type: str
    size_bytes: int
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    url: str
    created_at: datetime
