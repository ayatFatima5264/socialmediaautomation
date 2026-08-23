"""Thumbnail Studio endpoints.

    GET    /api/video/thumbnails/options       formats, templates, palettes
    POST   /api/video/thumbnails/design        template + words -> a design
    POST   /api/video/thumbnails/variations    one design -> several
    POST   /api/video/thumbnails/preview       a design -> PNG bytes, stored nowhere
    POST   /api/video/thumbnails               a design -> a saved file
    GET    /api/video/thumbnails               this user's saved thumbnails
    GET    /api/video/thumbnails/{id}/download?format=png|jpg
    POST   /api/video/thumbnails/{id}/attach?project_id=
    DELETE /api/video/thumbnails/{id}

**Preview and download are the same renderer.** `/preview` returns image bytes
from `thumbnails.render` at a reduced scale; saving calls the same function at
full size. There is no browser-side drawing to disagree with the file, which is
the same rule the video preview follows for the same reason.

**Preview stores nothing.** A design the user is still nudging must not leave a
file in their library or bytes in a bucket they pay for — the same decision
Voice Studio's preview makes.

Thumbnails are ordinary `VideoAsset`s of kind `thumbnail`, so they appear in
the Media Library, count toward storage, and are deleted by the same code as
everything else. The design that produced one is kept on its `meta` so it can
be reopened and edited rather than only re-downloaded.
"""
from __future__ import annotations

import base64
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user
from app.database import get_db
from app.models.business_profile import BusinessProfile
from app.models.user import User
from app.models.video_asset import VideoAsset
from app.schemas.video_thumbnails import (
    BackgroundRequest,
    DesignDocument,
    DesignRequest,
    RenderRequest,
    SaveThumbnail,
    ThumbnailOptions,
    ThumbnailRead,
    VariationsRequest,
    VariationsResult,
)
from app.services.video import assets as asset_service
from app.services.video import projects as project_service
from app.services.video import thumbnails as studio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video/thumbnails", tags=["thumbnail-studio"])

# A thumbnail is one still. Anything past this is a design with a background
# nobody needed at that size, and Pillow work grows with the pixel count.
MAX_SOURCE_BYTES = 20 * 1024 * 1024


def _brand(db: Session, user: User) -> dict:
    """The user's Brand Kit, or an empty dict."""
    row = db.scalars(
        select(BusinessProfile).where(BusinessProfile.user_id == user.id)
    ).first()
    if row is None:
        return {}
    return {
        "business_name": row.business_name,
        "brand_colors": list(row.brand_colors or []),
        "logo_url": row.logo_url,
    }


def _asset_bytes(db: Session, *, user: User, asset_id: int | None) -> bytes | None:
    """The bytes of one of this user's assets, or None.

    Scoped to the owner, so a design naming somebody else's asset id renders
    without it rather than reading their file.
    """
    if not asset_id:
        return None
    try:
        asset = asset_service.get_asset(db, user_id=user.id, asset_id=asset_id)
        data, _ = asset_service.read_asset(asset)
    except asset_service.AssetError:
        logger.info("Thumbnail referenced asset %s, which is gone", asset_id)
        return None
    return data if len(data) <= MAX_SOURCE_BYTES else None


def _logo_bytes(db: Session, *, user: User, design: dict) -> bytes | None:
    """The logo to draw: an explicit asset, else the Brand Kit's.

    The Brand Kit stores `logo_url` as either a remote URL or a `data:` URL —
    a data URL is decoded here, and a remote one is *not fetched*. Rendering
    must not depend on somebody else's host being up, and a thumbnail is a
    synchronous request; the fix for a remote logo is to upload it once, which
    the Media Library already does.
    """
    for layer in design.get("layers") or []:
        if layer.get("type") != "logo":
            continue
        data = _asset_bytes(db, user=user, asset_id=layer.get("asset_id"))
        if data:
            return data

        url = (_brand(db, user).get("logo_url") or "").strip()
        if url.startswith("data:") and "," in url:
            try:
                return base64.b64decode(url.split(",", 1)[1])
            except (ValueError, TypeError):
                logger.info("Brand Kit logo is not decodable base64")
        return None
    return None


def _render(db: Session, *, user: User, design: dict, fmt: str, scale: float) -> bytes:
    """Resolve a design's images and draw it. The one path to pixels."""
    document = studio.normalize(design)
    background = None
    if document["background"]["kind"] == "image":
        background = _asset_bytes(
            db, user=user, asset_id=document["background"]["asset_id"]
        )

    try:
        return studio.render(
            document,
            background_image=background,
            logo_image=_logo_bytes(db, user=user, design=document),
            fmt=fmt,
            scale=scale,
        )
    except studio.ThumbnailError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _read(asset: VideoAsset) -> ThumbnailRead:
    meta = asset.meta or {}
    return ThumbnailRead(
        id=asset.id,
        title=asset.title,
        url=f"{settings.backend_url}/api/storage/o/{asset.token}",
        content_type=asset.content_type,
        size_bytes=asset.size_bytes,
        width=asset.width,
        height=asset.height,
        created_at=asset.created_at,
        design=meta.get("design") or {},
        project_id=asset.project_id,
    )


# ---------------------------------------------------------------------------
# Designing
# ---------------------------------------------------------------------------


@router.get("/options", response_model=ThumbnailOptions)
def options(user: User = Depends(get_current_user)) -> ThumbnailOptions:
    from app.services.video.compositor import font_available

    return ThumbnailOptions(
        **studio.options(), text_rendering_available=font_available()
    )


@router.post("/design", response_model=DesignDocument)
def make_design(
    body: DesignRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DesignDocument:
    """A design from a template and some words.

    Returned rather than stored: this is the starting point the user then
    edits, and persisting every abandoned first draft would fill their library
    with thumbnails they never chose.
    """
    design = studio.build_design(
        template=body.template,
        headline=body.headline,
        kicker=body.kicker,
        format_key=body.format,
        palette=body.palette,
        background_asset_id=body.background_asset_id,
        logo_asset_id=body.logo_asset_id,
        brand=_brand(db, user) if body.use_brand else None,
    )
    return DesignDocument(**design)


@router.post("/background", response_model=dict)
async def generate_background(
    body: BackgroundRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Generate a background image from a prompt.

    The picture is fetched and **stored as an ordinary asset** before the
    design points at it — the same rule the scene visuals follow. A thumbnail
    whose background is a remote URL is one that renders differently next week
    and stops rendering when that host goes down.

    Returns the asset, not a design: the studio sets it as the background and
    re-renders, which keeps every other control the user has already set.
    """
    from app.models.video_project import VideoProject
    from app.services.video import visuals

    spec = studio.FORMATS_BY_KEY.get(body.format) or studio.FORMATS_BY_KEY[
        studio.DEFAULT_FORMAT
    ]

    # `attach_ai_image` wants somewhere to put the result. A thumbnail has no
    # project or scene, so it is handed lightweight stand-ins carrying just the
    # canvas and the prompt — the alternative is a second copy of the
    # generate-fetch-store sequence, which is exactly the duplication the
    # visuals module exists to prevent.
    canvas = VideoProject(
        user_id=user.id,
        width=spec["width"],
        height=spec["height"],
        aspect_ratio=_ratio_for(spec),
    )
    scene = _ThumbnailScene(prompt=body.prompt)

    try:
        asset = await visuals.attach_ai_image(
            db, project=canvas, scene=scene, prompt=body.prompt
        )
    except visuals.VisualError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "asset_id": asset.id,
        "url": f"{settings.backend_url}/api/storage/o/{asset.token}",
        "title": asset.title,
        "width": asset.width,
        "height": asset.height,
    }


def _ratio_for(spec: dict) -> str:
    """The closest aspect-ratio label for a thumbnail format.

    The image provider takes a ratio, not a pixel size, and a thumbnail format
    is not one of the video presets — so this maps the shape rather than
    inventing a preset for a still.
    """
    ratio = spec["width"] / spec["height"]
    for label, value in (("16:9", 16 / 9), ("1:1", 1.0), ("4:5", 0.8), ("9:16", 9 / 16)):
        if abs(ratio - value) < 0.08:
            return label
    return "16:9" if ratio >= 1 else "9:16"


class _ThumbnailScene:
    """The two fields `visuals.attach_ai_image` reads, and nothing else.

    Deliberately not a `VideoScene`: a thumbnail has no scene, and creating a
    real row to throw away would leave orphans in `video_scenes` every time
    somebody generated a background they did not keep.
    """

    def __init__(self, prompt: str):
        self.title = "Thumbnail"
        self.position = 0
        self.visual_prompt = prompt
        self.settings = {"visual_mode": "natural"}
        self.asset_id = None
        self.source = "pending"


@router.post("/variations", response_model=VariationsResult)
def make_variations(
    body: VariationsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VariationsResult:
    """Several designs from one, for the user to choose between."""
    return VariationsResult(designs=studio.variations(body.design, count=body.count))


@router.post("/preview")
def preview(
    body: RenderRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Draw a design and return the image. **Nothing is stored.**

    The same function the download uses, at a smaller scale — so what is on
    screen is the file, not an approximation of it.
    """
    data = _render(
        db, user=user, design=body.design, fmt=body.format, scale=body.scale
    )
    return Response(
        content=data,
        media_type="image/png" if body.format == "png" else "image/jpeg",
        headers={
            "Content-Length": str(len(data)),
            # A preview changes with every keystroke and is per-user; nothing
            # in front of the API may hold on to it.
            "Cache-Control": "private, max-age=0, no-store",
        },
    )


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------


@router.post("", response_model=ThumbnailRead, status_code=201)
def save(
    body: SaveThumbnail,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ThumbnailRead:
    """Render a design at full size and keep it in the library.

    The design travels onto the asset's `meta`, so the file can be reopened in
    the studio and changed — a thumbnail you can only re-download is a dead
    end, and "make the headline smaller" should not mean starting again.
    """
    document = studio.normalize(body.design)

    project = None
    if body.project_id is not None:
        try:
            project = project_service.get_project(
                db, user_id=user.id, project_id=body.project_id
            )
        except project_service.ProjectError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    data = _render(db, user=user, design=document, fmt=body.format, scale=1.0)

    headline = next(
        (
            layer.get("text")
            for layer in document["layers"]
            if layer.get("type") == "text" and (layer.get("text") or "").strip()
        ),
        "",
    )
    title = (body.title or headline or "Thumbnail").strip()[:200]

    try:
        asset = asset_service.store_asset(
            db,
            user_id=user.id,
            kind="thumbnail",
            data=data,
            content_type="image/png" if body.format == "png" else "image/jpeg",
            title=title,
            filename=f"thumbnail.{body.format}",
            project_id=project.id if project else None,
            # Measured already — do not decode the image again to learn what we
            # just drew.
            probe=False,
            width=document["width"],
            height=document["height"],
            meta={"source": "thumbnail_studio", "design": document},
        )
    except asset_service.AssetError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if project is not None:
        project.thumbnail_asset_id = asset.id
        db.commit()

    return _read(asset)


@router.get("", response_model=list[ThumbnailRead])
def listing(
    project_id: int | None = None,
    limit: int = Query(default=60, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ThumbnailRead]:
    """This user's saved thumbnails, newest first."""
    rows = asset_service.user_assets(
        db, user_id=user.id, kind="thumbnail", project_id=project_id, limit=limit
    )
    return [_read(row) for row in rows]


@router.post("/{asset_id}/attach", response_model=ThumbnailRead)
def attach(
    asset_id: int,
    project_id: int = Query(..., description="The project to use this thumbnail for."),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ThumbnailRead:
    """Make a saved thumbnail a project's cover — the "Add to Project" action."""
    try:
        asset = asset_service.get_asset(db, user_id=user.id, asset_id=asset_id)
        project = project_service.get_project(
            db, user_id=user.id, project_id=project_id
        )
    except (asset_service.AssetError, project_service.ProjectError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    project_service.attach_asset(db, project=project, asset=asset)
    project.thumbnail_asset_id = asset.id
    db.commit()
    db.refresh(asset)
    return _read(asset)


@router.get("/{asset_id}/download")
def download(
    asset_id: int,
    format: str = Query(default="png", pattern="^(png|jpg)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Download a saved thumbnail as PNG or JPG.

    A request for the format it was *not* saved in is re-rendered from the
    design rather than transcoded, so a JPG of a PNG thumbnail is drawn at full
    quality instead of being a recompression of an already-compressed image.
    Falling back to the stored bytes when there is no design keeps thumbnails
    saved before this worked downloadable.
    """
    try:
        asset = asset_service.get_asset(db, user_id=user.id, asset_id=asset_id)
    except asset_service.AssetError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    wanted = "image/png" if format == "png" else "image/jpeg"
    design = (asset.meta or {}).get("design")

    if asset.content_type == wanted or not design:
        try:
            data, content_type = asset_service.read_asset(asset)
        except asset_service.AssetError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    else:
        data = _render(db, user=user, design=design, fmt=format, scale=1.0)
        content_type = wanted

    stem = "".join(
        character if character.isalnum() or character in " -_" else ""
        for character in (asset.title or "thumbnail")
    ).strip() or "thumbnail"

    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{stem[:60]}.{format}"',
            "Content-Length": str(len(data)),
            "Cache-Control": "private, max-age=0, no-store",
        },
    )


@router.delete("/{asset_id}", status_code=204)
def delete(
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    try:
        asset = asset_service.get_asset(db, user_id=user.id, asset_id=asset_id)
    except asset_service.AssetError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    asset_service.delete_asset(db, asset)
    return Response(status_code=204)
