"""Business profile persistence + AI-context assembly.

Kept in one small module: the routes get/upsert the profile through here, and
the AI layer asks here for a ready-to-inject context string. Empty/skipped
fields are simply omitted from the context, so the AI works with a partial (or
even empty) profile.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.business_profile import BusinessProfile
from app.schemas.business_profile import BusinessProfileUpdate


def get_profile(db: Session, user_id: int) -> BusinessProfile | None:
    return db.scalars(
        select(BusinessProfile).where(BusinessProfile.user_id == user_id)
    ).first()


def upsert_profile(
    db: Session, user_id: int, data: BusinessProfileUpdate
) -> BusinessProfile:
    """Create or fully update the user's profile from the given desired state."""
    profile = get_profile(db, user_id)
    if profile is None:
        profile = BusinessProfile(user_id=user_id)
        db.add(profile)

    profile.business_name = data.business_name
    profile.industry = data.industry
    profile.business_description = data.business_description
    profile.target_audience = data.target_audience
    profile.brand_voice = data.brand_voice
    profile.business_goals = data.business_goals
    profile.website = data.website

    db.commit()
    db.refresh(profile)
    return profile


def build_context(profile: BusinessProfile | None) -> str | None:
    """Render a compact context block for prompts, or None if nothing is set.

    Only non-empty fields are included, so a partially-filled profile still
    produces useful guidance and an empty one produces no context at all.
    """
    if profile is None:
        return None

    lines: list[str] = []
    if profile.business_name:
        lines.append(f"Business name: {profile.business_name}")
    if profile.industry:
        lines.append(f"Industry: {profile.industry}")
    if profile.business_description:
        lines.append(f"About the business: {profile.business_description}")
    if profile.target_audience:
        lines.append(f"Target audience: {profile.target_audience}")
    if profile.brand_voice:
        lines.append(f"Brand voice: {', '.join(profile.brand_voice)}")
    if profile.business_goals:
        lines.append(f"Business goals: {', '.join(profile.business_goals)}")
    if profile.website:
        lines.append(f"Website: {profile.website}")

    if not lines:
        return None
    return "\n".join(lines)


def context_for_user(db: Session, user_id: int) -> str | None:
    """Convenience: the AI-ready context string for a user (or None)."""
    return build_context(get_profile(db, user_id))
