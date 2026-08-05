"""AI Ads Studio request/response schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ---- Ad copy --------------------------------------------------------------


class AdCopyRequest(BaseModel):
    product: str = Field(..., min_length=2, max_length=300)
    audience: str | None = Field(None, max_length=300)
    offer: str | None = Field(None, max_length=300)
    platform: str = "instagram"
    tone: str = "Professional"
    cta: str = "Shop Now"
    variants: int = Field(3, ge=1, le=6)
    provider: str | None = None


class AdCopyVariant(BaseModel):
    angle: str
    headline: str
    body: str
    cta: str


class AdCopyResponse(BaseModel):
    variants: list[AdCopyVariant]


# ---- Headlines ------------------------------------------------------------


class HeadlineRequest(BaseModel):
    product: str = Field(..., min_length=2, max_length=300)
    offer: str | None = Field(None, max_length=300)
    angles: list[str] = Field(default_factory=list)
    platform: str = "facebook"
    count: int = Field(6, ge=1, le=12)
    provider: str | None = None


class Headline(BaseModel):
    text: str
    angle: str
    why: str = ""
    over_limit: bool = False


class HeadlineResponse(BaseModel):
    headlines: list[Headline]
    limit: int


# ---- Calls to action ------------------------------------------------------


class CtaRequest(BaseModel):
    offer: str = Field(..., min_length=2, max_length=300)
    stage: str = "Warm — considering"
    platform: str = "facebook"
    tone: str = "Friendly"
    count: int = Field(5, ge=1, le=10)
    provider: str | None = None


class Cta(BaseModel):
    line: str
    button: str


class CtaResponse(BaseModel):
    ctas: list[Cta]
    buttons: list[str]


# ---- Creatives ------------------------------------------------------------


class CreativeRequest(BaseModel):
    subject: str = Field(..., min_length=2, max_length=500)
    headline: str | None = Field(None, max_length=200)
    background: str | None = Field(None, max_length=200)
    style: str = "corporate"
    aspect_ratio: str = "1:1"
    quality: str = "standard"
    count: int = Field(1, ge=1, le=4)


class CreativeResponse(BaseModel):
    images: list[str]
    # Which source produced each image, positionally aligned with `images`.
    # "pollinations-…" is AI generation; "loremflickr"/"picsum" mean the AI host
    # failed and a stock photo was substituted. The client shows this so a
    # fallback is never mistaken for a generated creative.
    sources: list[str] = []


# ---- Video plans ----------------------------------------------------------


class VideoPlanRequest(BaseModel):
    concept: str = Field(..., min_length=2, max_length=900)
    duration: int = Field(15, ge=3, le=60)
    platform: str = "instagram"
    style: str = "Modern & Clean"
    motion: str | None = None
    provider: str | None = None


class VideoScene(BaseModel):
    start: int
    seconds: int
    shot: str
    on_screen: str = ""
    voiceover: str = ""


class VideoPlanResponse(BaseModel):
    hook: str
    scenes: list[VideoScene]
    cta: str
    total_seconds: int
    # False until a video provider is configured. The client must not present a
    # plan as a rendered video.
    renderable: bool
    note: str


# ---- Campaigns ------------------------------------------------------------
# Field names are snake_case on the wire, matching the rest of the API. The
# client maps them once in lib/ads/store.js rather than every component
# knowing both spellings.


class CampaignBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    objective: str = Field("Brand Awareness", max_length=60)
    platforms: list[str] = Field(default_factory=list)
    status: str = Field("draft", max_length=20)
    brief: str | None = None


class CampaignCreate(CampaignBase):
    pass


class CampaignUpdate(BaseModel):
    """Every field optional — a PATCH sets only what it names."""

    name: str | None = Field(None, min_length=1, max_length=200)
    objective: str | None = Field(None, max_length=60)
    platforms: list[str] | None = None
    status: str | None = Field(None, max_length=20)
    brief: str | None = None
    creatives: int | None = Field(None, ge=0)


class Campaign(CampaignBase):
    id: int
    creatives: int = 0
    # None until the campaign has actually run — see the model's note on why
    # this is not 0.0.
    ctr: float | None = None
    impressions: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
