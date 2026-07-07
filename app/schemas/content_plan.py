"""Pydantic contracts for the AI Content Planner API."""
from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.post import Platform, PostStatus


# ---------------------------------------------------------------------------
# Setup (Step 1)
# ---------------------------------------------------------------------------
class PlannerSetup(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    duration_days: int = Field(default=7, ge=1, le=31)
    frequency: str = Field(default="daily")  # daily | 3_week | 5_week | custom
    posts_per_week: int = Field(default=7, ge=1, le=7)
    platforms: list[Platform] = Field(default_factory=list, min_length=1)
    goals: list[str] = Field(default_factory=list)
    content_mix: list[str] = Field(default_factory=list)
    user_prompt: str | None = Field(default=None, max_length=2000)
    auto_mode: bool = False


# ---------------------------------------------------------------------------
# Strategy topics (Step 2)
# ---------------------------------------------------------------------------
class TopicItem(BaseModel):
    id: str
    date: date_cls
    weekday: str
    content_type: str
    topic: str


class TopicsUpdate(BaseModel):
    """Replace the plan's topic list (edit / add / delete / reorder)."""
    topics: list[TopicItem]


class RegenerateTopicRequest(BaseModel):
    topic_id: str


# ---------------------------------------------------------------------------
# Generated posts (Step 3+)
# ---------------------------------------------------------------------------
class PlannerPostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: Platform
    content: str
    hashtags: list[str]
    status: PostStatus
    approval_status: str | None
    scheduled_time: datetime | None
    content_type: str | None
    topic: str | None
    media: list | None = None
    character_count: int = 0


class PlannerPostUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=63206)
    hashtags: list[str] | None = None
    scheduled_time: datetime | None = None


class GenerateRequest(BaseModel):
    # Reserved for the AI Visuals step; text-only for now.
    with_images: bool = False


class ApproveRequest(BaseModel):
    all: bool = False
    post_ids: list[int] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Plan read models
# ---------------------------------------------------------------------------
class PlanSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source: str
    status: str
    duration_days: int
    frequency: str
    platforms: list[str]
    total_posts: int
    generated_posts: int
    created_at: datetime


class PlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source: str
    duration_days: int
    frequency: str
    posts_per_week: int
    platforms: list[str]
    goals: list[str]
    content_mix: list[str]
    user_prompt: str | None
    timezone: str
    auto_mode: bool
    theme: str | None = None
    summary: str | None = None
    topics: list[TopicItem]
    status: str
    total_posts: int
    generated_posts: int
    error: str | None
    created_at: datetime
    posts: list[PlannerPostRead] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Planner settings
# ---------------------------------------------------------------------------
class PlannerSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    default_duration_days: int
    default_frequency: str
    default_posts_per_week: int
    default_platforms: list[str]
    default_goals: list[str]
    default_content_mix: list[str]
    auto_mode: bool
    timezone: str


class PlannerSettingsUpdate(BaseModel):
    default_duration_days: int = Field(default=7, ge=1, le=31)
    default_frequency: str = "daily"
    default_posts_per_week: int = Field(default=7, ge=1, le=7)
    default_platforms: list[Platform] = Field(default_factory=list)
    default_goals: list[str] = Field(default_factory=list)
    default_content_mix: list[str] = Field(default_factory=list)
    auto_mode: bool = False
    timezone: str = "UTC"
