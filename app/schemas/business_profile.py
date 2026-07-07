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

    @field_validator("brand_voice", "business_goals", mode="before")
    @classmethod
    def _clean_list(cls, v: object) -> list[str]:
        if not v:
            return []
        if isinstance(v, str):
            v = [v]
        return [str(x).strip() for x in v if str(x).strip()]

    @field_validator("business_name", "industry", "target_audience", "website", "business_description")
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
    updated_at: datetime | None = None
