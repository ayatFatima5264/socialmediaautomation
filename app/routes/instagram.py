
"""Instagram publish endpoints — target the user's connected Business account.

Publishing goes through the Meta Graph API using the Instagram Business account
connected via Social Accounts (Instagram Business Login). There is no longer a
hard-coded personal-account token: connect an Instagram account first, then
publish to it.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.timeutils import utcnow
from app.database import get_db
from app.models.post import Post
from app.models.social_account import SocialAccount
from app.models.user import User
from app.repositories import SocialAccountRepository
from app.schemas.post import Platform, PostStatus
from app.services.image_service import ImageError
from app.services.image_service import generate as generate_image
from app.services.social import meta_graph

router = APIRouter(prefix="/instagram", tags=["Instagram"])


def _connected_account(db: Session, user: User) -> SocialAccount:
    """The user's connected Instagram Business account, or a 400 if none."""
    account = SocialAccountRepository(db).get(user.id, Platform.instagram)
    if account is None:
        raise HTTPException(
            status_code=400,
            detail="No Instagram account connected. Connect one in Social Accounts first.",
        )
    return account


@router.get("/profile")
async def profile(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Return the connected Business account's basic profile."""
    account = _connected_account(db, user)
    return {
        "account_id": account.account_id,
        "username": account.username,
        "page_id": account.page_id,
        "display_name": account.display_name,
    }


class PublishRequest(BaseModel):
    caption: str = Field(default="", description="Post caption (text + hashtags).")
    # Provide a ready image URL, OR an image_prompt to AI-generate one.
    image_url: str | None = Field(default=None, description="Publicly reachable image URL.")
    image_prompt: str | None = Field(
        default=None, description="If set (and no image_url), AI-generate the image from this."
    )
    # Optional, for a clean History record. Falls back to caption / [].
    content: str | None = Field(default=None, description="Post body for History.")
    hashtags: list[str] = Field(default_factory=list)


@router.post("/publish")
async def publish(
    req: PublishRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Publish an image post to the connected Instagram Business account.

    Supply image_url, or image_prompt to AI-generate one.
    """
    account = _connected_account(db, user)

    image_url = req.image_url
    if not image_url:
        if not req.image_prompt:
            raise HTTPException(
                status_code=422,
                detail="Provide either image_url or image_prompt.",
            )
        try:
            # verify=True renders the image now so Instagram's fetch is fast
            # (and a bad image fails here, not mid-publish).
            image_url = await generate_image(req.image_prompt, verify=True)
        except ImageError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Persist first as 'publishing' so even a failed publish shows in History.
    post = Post(
        user_id=user.id,
        platform=Platform.instagram.value,
        content=req.content or req.caption,
        hashtags=req.hashtags,
        status=PostStatus.publishing.value,
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    try:
        media_id = await meta_graph.publish_image(
            ig_account_id=account.account_id,
            access_token=account.access_token,
            image_url=image_url,
            caption=req.caption,
        )
    except meta_graph.GraphAPIError as exc:
        post.status = PostStatus.failed.value
        post.error = str(exc)
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    post.status = PostStatus.published.value
    post.external_id = media_id
    post.published_time = utcnow()
    post.error = None
    db.commit()

    return {
        "success": True,
        "media_id": media_id,
        "image_url": image_url,
        "post_id": post.id,
    }
