"""Pydantic models for the post-generation API.

These define the JSON contract between the FastAPI backend and the React
frontend, so the shapes here are what the UI should expect.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Platform(str, Enum):
    instagram = "instagram"
    facebook = "facebook"
    twitter = "twitter"  # Twitter / X
    linkedin = "linkedin"
    threads = "threads"


class Tone(str, Enum):
    professional = "professional"
    casual = "casual"
    funny = "funny"
    inspirational = "inspirational"
    bold = "bold"
    friendly = "friendly"
    informative = "informative"
    promotional = "promotional"


class GeneratePostRequest(BaseModel):
    topic: str = Field(..., min_length=2, max_length=500,
                       description="What the post is about.")
    tone: Tone = Tone.professional
    # A specific platform, or omit / pass null to generate for ALL platforms.
    platform: Platform | None = Field(
        default=None,
        description="Target platform. If null, generates for every platform.",
    )
    audience: str | None = Field(
        default=None, max_length=200,
        description="Optional target audience, e.g. 'startup founders'.",
    )
    include_hashtags: bool = True
    # When true, also returns a short and a long variant of the post.
    variants: bool = False
    # Optional per-request override of the configured provider ("groq"/"mock").
    provider: str | None = None


class GeneratedPost(BaseModel):
    platform: Platform
    text: str
    short_version: str | None = None
    long_version: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    character_count: int = 0
    char_limit: int | None = None
    within_limit: bool = True


class GeneratePostResponse(BaseModel):
    provider: str
    model: str
    results: list[GeneratedPost]


# ---------------------------------------------------------------------------
# Persistence / scheduling
# ---------------------------------------------------------------------------
class PostStatus(str, Enum):
    draft = "draft"            # saved, not scheduled
    scheduled = "scheduled"    # has a future publish time, awaiting the scheduler
    publishing = "publishing"  # being published right now (transient)
    published = "published"    # successfully published
    failed = "failed"          # publish attempt failed


class PostCreate(BaseModel):
    platform: Platform
    content: str = Field(..., min_length=1, max_length=63206)
    hashtags: list[str] = Field(default_factory=list)
    # If set and in the future, the post is scheduled; otherwise it's a draft.
    scheduled_time: datetime | None = None


class PostUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=63206)
    hashtags: list[str] | None = None
    # Setting this (to a future time) (re)schedules the post.
    scheduled_time: datetime | None = None


class PostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    platform: Platform
    content: str
    hashtags: list[str]
    status: PostStatus
    scheduled_time: datetime | None
    published_time: datetime | None
    external_id: str | None
    error: str | None
    created_at: datetime
