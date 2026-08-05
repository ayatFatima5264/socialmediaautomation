"""AI Ads Studio endpoints.

Thin wrappers over app/services/ads_service.py. Error mapping matches the rest
of the API: a missing/unconfigured provider is a 503 (the operator must fix it),
a provider that failed at request time is a 502 (try again).

Auth is optional here, matching /api/generate-post: the Studio is behind the
app's own route guard, and a signed-in user is only needed once these results
start being saved against an account.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_current_user_optional
from app.database import get_db
from app.models.ad_campaign import AdCampaign
from app.models.user import User
from app.schemas.ads import (
    AdCopyRequest,
    Campaign,
    CampaignCreate,
    CampaignUpdate,
    AdCopyResponse,
    CreativeRequest,
    CreativeResponse,
    CtaRequest,
    CtaResponse,
    HeadlineRequest,
    HeadlineResponse,
    VideoPlanRequest,
    VideoPlanResponse,
)
from app.services import ads_service
from app.services.ads_service import HEADLINE_LIMIT, NATIVE_BUTTONS
from app.services.image_service import ImageError
from app.services.providers import ProviderConfigError, ProviderError

router = APIRouter(prefix="/api/ads", tags=["ads"])

# Caption ceilings per platform, mirroring PLATFORM_SPECS. The copy endpoint
# truncates to these so a variant can never come back unusable.
CHAR_LIMITS = {
    "instagram": 2200,
    "facebook": 63206,
    "twitter": 280,
    "linkedin": 3000,
    "pinterest": 500,
}


def _guard(exc: Exception) -> HTTPException:
    if isinstance(exc, ProviderConfigError):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=502, detail=str(exc))


@router.post("/copy", response_model=AdCopyResponse)
async def ad_copy(
    req: AdCopyRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> AdCopyResponse:
    try:
        variants = await ads_service.generate_ad_copy(
            product=req.product,
            audience=req.audience,
            offer=req.offer,
            platform=req.platform,
            tone=req.tone,
            cta=req.cta,
            char_limit=CHAR_LIMITS.get(req.platform, 2200),
            variants=req.variants,
            provider_name=req.provider,
        )
    except (ProviderConfigError, ProviderError) as exc:
        raise _guard(exc) from exc

    if not variants:
        raise HTTPException(status_code=502, detail="The model returned no usable copy.")
    return AdCopyResponse(variants=variants)


@router.post("/headlines", response_model=HeadlineResponse)
async def headlines(
    req: HeadlineRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> HeadlineResponse:
    try:
        items = await ads_service.generate_headlines(
            product=req.product,
            offer=req.offer,
            angles=req.angles,
            platform=req.platform,
            count=req.count,
            provider_name=req.provider,
        )
    except (ProviderConfigError, ProviderError) as exc:
        raise _guard(exc) from exc

    if not items:
        raise HTTPException(status_code=502, detail="The model returned no headlines.")
    return HeadlineResponse(headlines=items, limit=HEADLINE_LIMIT)


@router.post("/ctas", response_model=CtaResponse)
async def ctas(
    req: CtaRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> CtaResponse:
    try:
        items = await ads_service.generate_ctas(
            offer=req.offer,
            stage=req.stage,
            platform=req.platform,
            tone=req.tone,
            count=req.count,
            provider_name=req.provider,
        )
    except (ProviderConfigError, ProviderError) as exc:
        raise _guard(exc) from exc

    if not items:
        raise HTTPException(status_code=502, detail="The model returned no CTAs.")
    return CtaResponse(
        ctas=items,
        buttons=NATIVE_BUTTONS.get(req.platform, NATIVE_BUTTONS["facebook"]),
    )


@router.post("/creative", response_model=CreativeResponse)
async def creative(
    req: CreativeRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> CreativeResponse:
    try:
        images, sources = await ads_service.generate_creative(
            subject=req.subject,
            headline=req.headline,
            background=req.background,
            style=req.style,
            aspect_ratio=req.aspect_ratio,
            quality=req.quality,
            count=req.count,
        )
    except ImageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not images:
        raise HTTPException(status_code=502, detail="No image could be generated.")
    return CreativeResponse(images=images, sources=sources)


@router.post("/video-plan", response_model=VideoPlanResponse)
async def video_plan(
    req: VideoPlanRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> VideoPlanResponse:
    """A shot plan for a video ad — NOT a rendered video.

    See ads_service.generate_video_plan: no video model is configured, so this
    returns the part a language model can genuinely produce. The response
    carries `renderable: False`.
    """
    try:
        plan = await ads_service.generate_video_plan(
            concept=req.concept,
            duration=req.duration,
            platform=req.platform,
            style=req.style,
            motion=req.motion,
            provider_name=req.provider,
        )
    except (ProviderConfigError, ProviderError) as exc:
        raise _guard(exc) from exc

    if not plan.get("scenes"):
        raise HTTPException(status_code=502, detail="The model returned no scenes.")
    return VideoPlanResponse(**plan)


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------
# Unlike the generation endpoints above, these REQUIRE a signed-in user: a
# campaign is that user's data and every query is scoped to their id. Anything
# else would let one account read another's campaigns by guessing an integer.


def _owned(db: Session, user: User, campaign_id: int) -> AdCampaign:
    row = (
        db.query(AdCampaign)
        .filter(AdCampaign.id == campaign_id, AdCampaign.user_id == user.id)
        .first()
    )
    if row is None:
        # 404 rather than 403 for a campaign owned by someone else: telling a
        # stranger that an id exists is itself a leak.
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return row


@router.get("/campaigns", response_model=list[Campaign])
def list_campaigns(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AdCampaign]:
    """The user's campaigns, most recently touched first."""
    return (
        db.query(AdCampaign)
        .filter(AdCampaign.user_id == user.id)
        .order_by(AdCampaign.updated_at.desc())
        .all()
    )


@router.post("/campaigns", response_model=Campaign, status_code=201)
def create_campaign(
    body: CampaignCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AdCampaign:
    row = AdCampaign(user_id=user.id, **body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/campaigns/{campaign_id}", response_model=Campaign)
def get_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AdCampaign:
    return _owned(db, user, campaign_id)


@router.patch("/campaigns/{campaign_id}", response_model=Campaign)
def update_campaign(
    campaign_id: int,
    body: CampaignUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AdCampaign:
    row = _owned(db, user, campaign_id)
    # exclude_unset so a PATCH that names only `status` cannot blank the brief.
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/campaigns/{campaign_id}", status_code=204)
def delete_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    db.delete(_owned(db, user, campaign_id))
    db.commit()
