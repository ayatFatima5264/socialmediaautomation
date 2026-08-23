"""Request and response shapes for the Media Library.

Same two rules the rest of Video Studio's schemas follow: the server owns every
derived value, and every write field is optional unless leaving it out would be
meaningless.

One addition specific to this screen — **`usage` is on the read model**. The
library's whole job is to let somebody delete a file without breaking a video,
and that decision cannot be made from a filename. So every asset comes back
knowing which projects reference it and how, and the delete endpoint refuses
unless the client has been told.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AssetUsage(BaseModel):
    """One place an asset is referenced from."""

    project_id: int
    project_name: str
    # "visual", "voice-over", "audio layer", "subtitle track", "thumbnail".
    role: str


class MediaItem(BaseModel):
    """One file in the library."""

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

    # Where this file is used. Empty when nothing references it, which is what
    # makes it safe to delete — and the UI says exactly that rather than
    # showing an unexplained enabled/disabled button.
    usage: list[AssetUsage] = Field(default_factory=list)


class MediaFilter(BaseModel):
    """One tab in the filter bar, with a live count."""

    key: str
    label: str
    count: int


class MediaList(BaseModel):
    """A page of the library.

    `total` is the count *after* filtering, so "24 of 310" is honest about what
    the current filters match rather than about how many files exist.
    `storage_bytes` is the whole library regardless of filter — it answers "how
    much am I using", which no filter changes.
    """

    items: list[MediaItem]
    total: int
    limit: int
    offset: int
    filters: list[MediaFilter] = Field(default_factory=list)
    storage_bytes: int = 0


class UploadItem(BaseModel):
    """One image from the post composer's media library.

    A different shape from `MediaItem` on purpose: these live in `media_assets`
    and are not Video Studio assets. Flattening them into one list would make
    "delete" and "add to project" mean two different things depending on the
    row, which is exactly the confusion this separation avoids.
    """

    id: int
    token: str
    url: str
    filename: str | None = None
    content_type: str
    size_bytes: int
    created_at: datetime
    # The studio asset this image was already imported as, if any. Set means
    # the button reads "In your library" instead of offering the import again.
    imported_asset_id: int | None = None


class UploadList(BaseModel):
    items: list[UploadItem]
    total: int
    limit: int
    offset: int


class MediaRename(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class MediaImport(BaseModel):
    """Bring a composer upload into Video Studio."""

    media_id: int
    # Optional: import straight into a project, which is what the picker inside
    # the editor does. Omitted, the file lands in the library unattached.
    project_id: int | None = None


class MediaAttach(BaseModel):
    project_id: int
