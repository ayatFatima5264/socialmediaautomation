"""Business profile + onboarding endpoints (user-scoped).

    GET  /api/business-profile        — the user's profile (empty if none yet)
    PUT  /api/business-profile        — create/update (full upsert)
    POST /api/onboarding/complete     — mark the onboarding wizard as finished
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.business_profile import BusinessProfileRead, BusinessProfileUpdate
from app.services import business_profile_service as svc

router = APIRouter(prefix="/api", tags=["business-profile"])

# An empty profile shape for users who haven't filled anything in yet.
_EMPTY = BusinessProfileRead(
    business_name=None,
    industry=None,
    business_description=None,
    target_audience=None,
    brand_voice=[],
    business_goals=[],
    website=None,
)


@router.get("/business-profile", response_model=BusinessProfileRead)
def read_profile(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BusinessProfileRead:
    profile = svc.get_profile(db, user.id)
    return BusinessProfileRead.model_validate(profile) if profile else _EMPTY


@router.put("/business-profile", response_model=BusinessProfileRead)
def update_profile(
    data: BusinessProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BusinessProfileRead:
    profile = svc.upsert_profile(db, user.id, data)
    return BusinessProfileRead.model_validate(profile)


@router.post("/onboarding/complete", response_model=dict)
def complete_onboarding(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Mark the onboarding wizard as finished so it never shows again."""
    if not user.onboarding_completed:
        user.onboarding_completed = True
        db.commit()
    return {"success": True, "onboarding_completed": True}
