"""Post persistence, scheduling and publishing endpoints (all user-scoped)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.timeutils import to_naive_utc, utcnow
from app.database import get_db
from app.models.post import Post
from app.models.user import User
from app.schemas.post import PostCreate, PostRead, PostStatus, PostUpdate
from app.services.scheduler import publish_post

router = APIRouter(prefix="/api/posts", tags=["posts"])

_EDITABLE = {PostStatus.draft.value, PostStatus.scheduled.value, PostStatus.failed.value}


def _get_owned(db: Session, post_id: int, user: User) -> Post:
    post = db.get(Post, post_id)
    if post is None or post.user_id != user.id:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@router.post("", response_model=PostRead, status_code=status.HTTP_201_CREATED)
def create_post(
    data: PostCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Post:
    """Create a post. With a future scheduled_time it's scheduled; else a draft."""
    post_status = PostStatus.draft.value
    scheduled = None
    if data.scheduled_time is not None:
        scheduled = to_naive_utc(data.scheduled_time)
        if scheduled <= utcnow():
            raise HTTPException(
                status_code=422, detail="scheduled_time must be in the future"
            )
        post_status = PostStatus.scheduled.value

    post = Post(
        user_id=user.id,
        platform=data.platform.value,
        content=data.content,
        hashtags=data.hashtags,
        status=post_status,
        scheduled_time=scheduled,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


@router.get("", response_model=list[PostRead])
def list_posts(
    status: PostStatus | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Post]:
    query = select(Post).where(Post.user_id == user.id)
    if status is not None:
        query = query.where(Post.status == status.value)
    query = query.order_by(Post.created_at.desc())
    return list(db.scalars(query).all())


@router.get("/{post_id}", response_model=PostRead)
def get_post(
    post_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Post:
    return _get_owned(db, post_id, user)


@router.patch("/{post_id}", response_model=PostRead)
def update_post(
    post_id: int,
    data: PostUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Post:
    post = _get_owned(db, post_id, user)
    if post.status not in _EDITABLE:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot edit a post with status '{post.status}'",
        )

    if data.content is not None:
        post.content = data.content
    if data.hashtags is not None:
        post.hashtags = data.hashtags
    if data.scheduled_time is not None:
        scheduled = to_naive_utc(data.scheduled_time)
        if scheduled <= utcnow():
            raise HTTPException(
                status_code=422, detail="scheduled_time must be in the future"
            )
        post.scheduled_time = scheduled
        post.status = PostStatus.scheduled.value

    db.commit()
    db.refresh(post)
    return post


@router.post("/{post_id}/publish", response_model=PostRead)
async def publish_now(
    post_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Post:
    """Publish immediately, bypassing the schedule."""
    post = _get_owned(db, post_id, user)
    if post.status == PostStatus.published.value:
        raise HTTPException(status_code=409, detail="Post already published")
    return await publish_post(db, post)


@router.post("/{post_id}/cancel", response_model=PostRead)
def cancel_schedule(
    post_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Post:
    """Cancel a scheduled post, returning it to draft."""
    post = _get_owned(db, post_id, user)
    if post.status != PostStatus.scheduled.value:
        raise HTTPException(status_code=409, detail="Post is not scheduled")
    post.status = PostStatus.draft.value
    post.scheduled_time = None
    db.commit()
    db.refresh(post)
    return post


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(
    post_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    post = _get_owned(db, post_id, user)
    db.delete(post)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
