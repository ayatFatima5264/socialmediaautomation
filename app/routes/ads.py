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
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_current_user_optional
from app.database import get_db
from app.models.ad_campaign import AdCampaign
from app.models.campaign_asset import ASSET_KINDS, CampaignAsset as CampaignAssetRow
from app.models.user import User
from app.schemas.ads import (
    AdCopyRequest,
    Campaign,
    CampaignAsset,
    CampaignAssetBatch,
    CampaignAssetUpdate,
    CampaignAssetWithCampaign,
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


# How the campaign list can be ordered. A whitelist rather than accepting a
# column name from the query string, which would be an injection surface and
# would let a client sort by a column the UI has no way to display.
_CAMPAIGN_SORTS = {
    "updated": AdCampaign.updated_at.desc(),
    "created": AdCampaign.created_at.desc(),
    "name": AdCampaign.name.asc(),
}


@router.get("/campaigns", response_model=list[Campaign])
def list_campaigns(
    status: str | None = None,
    q: str | None = None,
    sort: str = "updated",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AdCampaign]:
    """The user's campaigns, most recently touched first.

    Filtering happens in SQL rather than in the client so the list page stays
    correct as an account grows past the point where shipping every row to the
    browser is reasonable.

    ---- Archived ----------------------------------------------------------
    Archiving exists to get finished work out of the way, so an unfiltered list
    EXCLUDES archived campaigns. Asking for them explicitly (`status=archived`)
    is the only way to see them — otherwise archiving would be a label that
    changes nothing, and the Studio home would fill up with work the user has
    already put away.
    """
    query = db.query(AdCampaign).filter(AdCampaign.user_id == user.id)

    if status:
        query = query.filter(AdCampaign.status == status)
    else:
        query = query.filter(AdCampaign.status != "archived")

    if q and q.strip():
        # Name and brief: the two fields a user actually remembers a campaign
        # by. ilike keeps it case-insensitive on Postgres and SQLite alike.
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(AdCampaign.name.ilike(term), AdCampaign.brief.ilike(term))
        )

    return query.order_by(_CAMPAIGN_SORTS.get(sort, _CAMPAIGN_SORTS["updated"])).all()


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


@router.post("/campaigns/{campaign_id}/duplicate", response_model=Campaign, status_code=201)
def duplicate_campaign(
    campaign_id: int,
    with_assets: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AdCampaign:
    """Copy a campaign, by default with everything it has produced.

    A campaign is a project, and duplicating a project that arrived empty would
    surprise anyone who meant "start the summer version of this". `with_assets`
    is there for the other case — reusing a brief for a genuinely new run.

    The copy is always a DRAFT whatever the original's status: duplicating an
    active campaign must not produce a second campaign that claims to be live.
    """
    source = _owned(db, user, campaign_id)

    copy = AdCampaign(
        user_id=user.id,
        name=f"{source.name} (copy)"[:200],
        campaign_type=source.campaign_type,
        objective=source.objective,
        platforms=list(source.platforms or []),
        status="draft",
        brief=source.brief,
        tone=source.tone,
        audience=source.audience,
        creatives=0,
    )
    db.add(copy)
    db.flush()

    if with_assets:
        for asset in (
            db.query(CampaignAssetRow)
            .filter(CampaignAssetRow.campaign_id == source.id)
            .all()
        ):
            db.add(
                CampaignAssetRow(
                    user_id=user.id,
                    campaign_id=copy.id,
                    kind=asset.kind,
                    title=asset.title,
                    url=asset.url,
                    body=asset.body,
                    tool=asset.tool,
                    meta=dict(asset.meta or {}),
                )
            )
        db.flush()
        _recount(db, copy)

    db.commit()
    db.refresh(copy)
    return copy


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
    row = _owned(db, user, campaign_id)
    # Assets are deleted explicitly rather than relying on the FK's ON DELETE
    # CASCADE: SQLite does not enforce foreign keys unless the pragma is on, so
    # on a dev database the cascade would silently leave orphans behind.
    db.query(CampaignAssetRow).filter(
        CampaignAssetRow.campaign_id == row.id
    ).delete(synchronize_session=False)
    db.delete(row)
    db.commit()


# ---------------------------------------------------------------------------
# Campaign assets
# ---------------------------------------------------------------------------
# The creative library. Every generator saves what it produced here against the
# campaign it was opened from, so the work survives navigating away — which is
# what makes a campaign a project rather than a form.


def _recount(db: Session, campaign: AdCampaign) -> None:
    """Set the campaign's creative count from its assets.

    Recounted rather than incremented: a counter that is nudged up on create
    and down on delete drifts the first time either path is missed, and the
    number is on the campaign card where a user will notice it being wrong.
    """
    campaign.creatives = (
        db.query(CampaignAssetRow)
        .filter(CampaignAssetRow.campaign_id == campaign.id)
        .count()
    )


def _owned_asset(db: Session, user: User, campaign_id: int, asset_id: int) -> CampaignAssetRow:
    row = (
        db.query(CampaignAssetRow)
        .filter(
            CampaignAssetRow.id == asset_id,
            CampaignAssetRow.campaign_id == campaign_id,
            CampaignAssetRow.user_id == user.id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Asset not found.")
    return row


@router.get("/assets", response_model=list[CampaignAssetWithCampaign])
def recent_assets(
    limit: int = 12,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CampaignAssetWithCampaign]:
    """The user's most recent assets across every campaign.

    Powers the Studio home's Recent Assets strip, which is deliberately NOT a
    per-campaign view — it is the answer to "what was I last working on".
    """
    rows = (
        db.query(CampaignAssetRow, AdCampaign.name)
        .join(AdCampaign, AdCampaign.id == CampaignAssetRow.campaign_id)
        .filter(CampaignAssetRow.user_id == user.id)
        .order_by(CampaignAssetRow.created_at.desc(), CampaignAssetRow.id.desc())
        .limit(max(1, min(limit, 50)))
        .all()
    )
    return [
        CampaignAssetWithCampaign(
            **CampaignAsset.model_validate(asset).model_dump(),
            campaign_name=name,
        )
        for asset, name in rows
    ]


@router.get("/campaigns/{campaign_id}/assets", response_model=list[CampaignAsset])
def list_assets(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CampaignAssetRow]:
    _owned(db, user, campaign_id)
    return (
        db.query(CampaignAssetRow)
        .filter(CampaignAssetRow.campaign_id == campaign_id)
        .order_by(CampaignAssetRow.created_at.desc(), CampaignAssetRow.id.desc())
        .all()
    )


@router.post(
    "/campaigns/{campaign_id}/assets",
    response_model=list[CampaignAsset],
    status_code=201,
)
def create_assets(
    campaign_id: int,
    body: CampaignAssetBatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CampaignAssetRow]:
    campaign = _owned(db, user, campaign_id)

    unknown = {a.kind for a in body.assets} - set(ASSET_KINDS)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown asset kind(s): {', '.join(sorted(unknown))}",
        )

    rows = [
        CampaignAssetRow(
            user_id=user.id,
            campaign_id=campaign.id,
            **asset.model_dump(),
        )
        for asset in body.assets
    ]
    db.add_all(rows)
    db.flush()
    _recount(db, campaign)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


@router.patch(
    "/campaigns/{campaign_id}/assets/{asset_id}", response_model=CampaignAsset
)
def update_asset(
    campaign_id: int,
    asset_id: int,
    body: CampaignAssetUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CampaignAssetRow:
    row = _owned_asset(db, user, campaign_id, asset_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


@router.post(
    "/campaigns/{campaign_id}/assets/{asset_id}/duplicate",
    response_model=CampaignAsset,
    status_code=201,
)
def duplicate_asset(
    campaign_id: int,
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CampaignAssetRow:
    campaign = _owned(db, user, campaign_id)
    source = _owned_asset(db, user, campaign_id, asset_id)

    copy = CampaignAssetRow(
        user_id=user.id,
        campaign_id=campaign.id,
        kind=source.kind,
        # Truncated so repeatedly duplicating cannot grow past the column.
        title=f"{source.title} (copy)"[:200],
        url=source.url,
        body=source.body,
        tool=source.tool,
        meta=dict(source.meta or {}),
    )
    db.add(copy)
    db.flush()
    _recount(db, campaign)
    db.commit()
    db.refresh(copy)
    return copy


@router.delete("/campaigns/{campaign_id}/assets/{asset_id}", status_code=204)
def delete_asset(
    campaign_id: int,
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    campaign = _owned(db, user, campaign_id)
    db.delete(_owned_asset(db, user, campaign_id, asset_id))
    db.flush()
    _recount(db, campaign)
    db.commit()
