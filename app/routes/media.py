"""Uploaded media — give a composer image a public URL so it can be published.

    POST /api/media          — upload an image (authenticated), returns its URL
    GET  /api/media/{token}  — serve those bytes (PUBLIC, no auth)

The read route has no auth by design: Pinterest, Instagram and Facebook publish
an image by fetching the URL from their own servers, with no credentials of
ours. An unguessable token is therefore the boundary — see models/media_asset.

Only images are accepted, and only up to MAX_UPLOAD_BYTES, so this can't become
a general-purpose file host.
"""
from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user
from app.database import get_db
from app.models.media_asset import MediaAsset
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/media", tags=["media"])

# Comfortably above a phone photo, well under what would strain the database.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# What the publishing platforms actually accept.
ALLOWED_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


class UploadedMedia(BaseModel):
    """The public handle for an uploaded image."""

    url: str
    token: str
    content_type: str
    size_bytes: int


def public_url(token: str) -> str:
    """Absolute URL a platform's servers can fetch. Absolute, not relative:
    Pinterest fetches this from its own infrastructure, not from the browser."""
    return f"{settings.backend_url}/api/media/{token}"


@router.post("", response_model=UploadedMedia, status_code=201)
async def upload_media(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UploadedMedia:
    """Store an image and return the URL a platform can fetch it from."""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="The file is empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Image is too large ({len(raw) // (1024 * 1024)} MB). "
                f"The limit is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
            ),
        )

    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                "Only images can be published (JPEG, PNG, WebP or GIF). "
                f"This file is {content_type or 'of an unknown type'}."
            ),
        )

    asset = MediaAsset(
        user_id=user.id,
        token=secrets.token_urlsafe(32),
        content_type=content_type,
        filename=(file.filename or None),
        size_bytes=len(raw),
        data=raw,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    logger.info(
        "Stored upload %s (%s, %d bytes) for user %s",
        asset.token[:8], content_type, asset.size_bytes, user.id,
    )
    return UploadedMedia(
        url=public_url(asset.token),
        token=asset.token,
        content_type=asset.content_type,
        size_bytes=asset.size_bytes,
    )


@router.get("/{token}")
def get_media(token: str, db: Session = Depends(get_db)) -> Response:
    """Serve an uploaded image. Public — a platform fetches this URL itself."""
    asset = db.scalars(
        select(MediaAsset).where(MediaAsset.token == token)
    ).first()
    if asset is None:
        raise HTTPException(status_code=404, detail="Image not found.")
    return Response(
        content=asset.data,
        media_type=asset.content_type,
        headers={
            # The token addresses immutable bytes, so it can be cached hard —
            # which also keeps a platform's repeated fetches cheap.
            "Cache-Control": "public, max-age=31536000, immutable",
            "Content-Length": str(asset.size_bytes),
        },
    )
