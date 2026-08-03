"""Business profile schemas — the onboarding answers used as AI context.

Every field is optional: the wizard can be skipped question-by-question, and a
Settings edit may clear a field. The API accepts the full desired state on each
PUT (a full upsert), so omitted fields fall back to their empty defaults.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Allowed option sets (kept in sync with the frontend). "Other" lets users type
# a custom value, so these are guidance, not hard constraints on free text.
INDUSTRIES = [
    "Technology", "Marketing", "Recruitment", "Healthcare", "Education",
    "Finance", "Real Estate", "E-commerce", "Agency", "Other",
]
BRAND_VOICES = [
    "Professional", "Friendly", "Educational", "Conversational", "Bold", "Luxury",
]
BUSINESS_GOALS = [
    "Generate Leads", "Increase Sales", "Brand Awareness", "Grow Followers",
    "Drive Website Traffic", "Promote Products or Services",
]


class BusinessProfileUpdate(BaseModel):
    """Full desired state of the profile (all fields optional)."""

    business_name: str | None = Field(default=None, max_length=255)
    industry: str | None = Field(default=None, max_length=100)
    business_description: str | None = Field(default=None, max_length=4000)
    target_audience: str | None = Field(default=None, max_length=255)
    brand_voice: list[str] = Field(default_factory=list)
    business_goals: list[str] = Field(default_factory=list)
    website: str | None = Field(default=None, max_length=500)

    # ---- Brand Kit -------------------------------------------------------
    # Generous max_length: logo_url may be a data: URL for an uploaded file,
    # which avoids needing file storage for a single small image per user.
    logo_url: str | None = Field(default=None, max_length=1_500_000)
    brand_colors: list[str] = Field(default_factory=list)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=500)

    @field_validator("brand_voice", "business_goals", mode="before")
    @classmethod
    def _clean_list(cls, v: object) -> list[str]:
        if not v:
            return []
        if isinstance(v, str):
            v = [v]
        return [str(x).strip() for x in v if str(x).strip()]

    @field_validator("brand_colors", mode="before")
    @classmethod
    def _clean_colors(cls, v: object) -> list[str]:
        """Keep only well-formed hex colours, normalised to #rrggbb.

        The overlay renderer writes these straight into SVG fill attributes, so
        anything that isn't a valid colour is dropped rather than passed
        through — a malformed value would silently break the rendered layer.
        """
        if not v:
            return []
        if isinstance(v, str):
            v = [v]
        out: list[str] = []
        for raw in v:
            c = str(raw).strip().lower()
            if not c.startswith("#"):
                c = f"#{c}"
            # Expand shorthand #abc -> #aabbcc.
            if len(c) == 4 and all(ch in "0123456789abcdef" for ch in c[1:]):
                c = "#" + "".join(ch * 2 for ch in c[1:])
            if len(c) == 7 and all(ch in "0123456789abcdef" for ch in c[1:]):
                out.append(c)
        return out[:6]

    @field_validator(
        "business_name", "industry", "target_audience", "website",
        "business_description", "logo_url", "phone", "email", "address",
    )
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class BusinessProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    business_name: str | None
    industry: str | None
    business_description: str | None
    target_audience: str | None
    brand_voice: list[str]
    business_goals: list[str]
    website: str | None
    logo_url: str | None = None
    brand_colors: list[str] = []
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    updated_at: datetime | None = None
