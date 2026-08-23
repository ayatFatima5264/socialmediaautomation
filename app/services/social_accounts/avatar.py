"""Profile pictures that outlive the CDN link they arrived on.

Meta, LinkedIn and Threads hand out **signed, expiring** avatar URLs — look for
`?ext=1785938535` on a Facebook picture or `&oe=...` on an fbcdn one. We stored
that URL at connect time and never touched it again, so a few weeks later every
card on /accounts rendered a broken image. Re-fetching the same URL server-side
does not help: what expired is the signature, not the transport.

So we copy the bytes while the link is still valid and serve them from
`/api/media/{token}`, which never expires. Re-syncing an account stores a fresh
copy and drops the old one, so an account keeps exactly one cached avatar.

Every failure here is soft. An avatar is decoration: if the fetch fails we hand
back the original URL and let the card fall back to the platform icon, rather
than failing a connect or a sync over a picture.
"""
from __future__ import annotations

import logging

import httpx
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.media_asset import MediaAsset
from app.routes.media import ALLOWED_TYPES, store_media_bytes

logger = logging.getLogger(__name__)

# An avatar is a thumbnail; anything larger is not one, and we store these in
# the database next to the user's uploads.
MAX_AVATAR_BYTES = 2 * 1024 * 1024
FETCH_TIMEOUT = 10.0

# The path our own media URLs are built on — see routes/media.public_url.
_MEDIA_PATH = "/api/media/"


def cached_token(url: str | None) -> str | None:
    """The media token if `url` is already one of ours, else None.

    Matched on the path rather than the full origin so a URL stored before the
    backend moved host (dev vs Render) is still recognised as ours.
    """
    if not url or _MEDIA_PATH not in url:
        return None
    token = url.rsplit(_MEDIA_PATH, 1)[1].split("?")[0].split("/")[0]
    return token or None


def _drop(db: Session, url: str | None) -> None:
    """Delete the media row behind a previously cached avatar."""
    token = cached_token(url)
    if not token:
        return
    db.execute(delete(MediaAsset).where(MediaAsset.token == token))
    db.commit()


async def cache_avatar(
    db: Session,
    *,
    user_id: int,
    url: str | None,
    previous: str | None = None,
) -> str | None:
    """Return the avatar URL to persist: our own copy when we can make one.

    `previous` is the URL currently on the account, so the row it points at can
    be cleaned up once a newer copy is in place.
    """
    if not url:
        return None
    if cached_token(url):
        return url  # already ours — nothing upstream left to fetch

    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.content
            content_type = (
                (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
            )
    except Exception as exc:  # network, timeout, 403 on an expired signature…
        logger.warning("Avatar fetch failed for user %s: %s", user_id, exc)
        return url

    if content_type not in ALLOWED_TYPES:
        logger.warning(
            "Avatar for user %s is %s, not an image — keeping the remote URL",
            user_id, content_type or "untyped",
        )
        return url
    if not data or len(data) > MAX_AVATAR_BYTES:
        logger.warning(
            "Avatar for user %s is %d bytes — outside what we cache", user_id, len(data)
        )
        return url

    try:
        stored = store_media_bytes(
            db=db,
            user_id=user_id,
            data=data,
            content_type=content_type,
            filename=f"avatar.{ALLOWED_TYPES[content_type]}",
        )
    except Exception as exc:
        logger.warning("Could not store avatar for user %s: %s", user_id, exc)
        return url

    _drop(db, previous)
    return stored.url
