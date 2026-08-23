"""Request and response shapes for Thumbnail Studio.

The design document is passed around as a plain `dict` rather than a deeply
typed model, deliberately. A layer's fields differ by type, the set will grow,
and a Pydantic union here would mean every new control needs a schema change in
lockstep with the renderer that draws it. `thumbnails.normalize` is the single
validator — it runs on every path in and every path out, so a malformed design
is repaired in one place instead of rejected in two.

What *is* typed is the boundary: which template, which format, which words.
Those are the things a client can get wrong in a way worth a 422.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ThumbnailOptions(BaseModel):
    """Everything the studio's controls are built from."""

    formats: list[dict]
    templates: list[dict]
    palettes: list[dict]
    anchors: list[str]
    fonts: list[str]
    background_kinds: list[str]
    # False when the server has no font installed — the studio says so rather
    # than rendering every headline in a bitmap fallback without explanation.
    text_rendering_available: bool = True


class DesignRequest(BaseModel):
    """Build a design from a template and some words."""

    template: str = "bold_center"
    headline: str = Field(default="", max_length=200)
    kicker: str = Field(default="", max_length=200)
    format: str = "youtube"
    palette: str = "mint"
    background_asset_id: int | None = None
    logo_asset_id: int | None = None
    # Pull colours and the logo from the user's Brand Kit. On by default: a
    # business that has filled one in almost never wants a generic palette.
    use_brand: bool = True


class DesignDocument(BaseModel):
    """A design, as the studio holds it. Every field editable."""

    version: int = 1
    format: str
    width: int
    height: int
    background: dict
    layers: list[dict]
    template: str | None = None


class RenderRequest(BaseModel):
    """Render a design — preview or download, the same call underneath."""

    design: dict
    format: Literal["png", "jpg"] = "png"
    # A fraction of full size, for a preview that arrives quickly. The
    # composition is identical because every dimension in a design is a
    # proportion of the canvas; only the pixel count changes.
    scale: float = Field(default=1.0, ge=0.1, le=1.0)


class BackgroundRequest(BaseModel):
    """Generate a background image from a prompt.

    The format decides the shape asked of the image provider, so a vertical
    cover does not get a landscape picture cropped to fit.
    """

    prompt: str = Field(min_length=3, max_length=500)
    format: str = "youtube"


class VariationsRequest(BaseModel):
    design: dict
    count: int = Field(default=4, ge=1, le=8)


class VariationsResult(BaseModel):
    designs: list[dict]


class SaveThumbnail(BaseModel):
    """Render a design and keep it as a file in the library."""

    design: dict
    title: str | None = Field(default=None, max_length=200)
    format: Literal["png", "jpg"] = "png"
    # Attach to a project as its thumbnail in the same call — which is what
    # "Add to Project" does, and saves a second round trip.
    project_id: int | None = None


class ThumbnailRead(BaseModel):
    """One saved thumbnail."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    url: str
    content_type: str
    size_bytes: int
    width: int | None = None
    height: int | None = None
    created_at: datetime
    # The design it was rendered from, so it can be reopened and edited rather
    # than only re-downloaded. A thumbnail you cannot get back into the editor
    # is a dead end.
    design: dict = Field(default_factory=dict)
    project_id: int | None = None
