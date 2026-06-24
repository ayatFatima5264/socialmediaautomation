"""Instagram Login API (graph.instagram.com) helpers.

The connected Business/Creator account uses the newer Instagram API with
Instagram Login — tokens start with "IGAA…" and call graph.instagram.com
directly (no Facebook Page hop). This module covers reading the profile and
publishing an image post (create container -> publish).

Uses httpx (already a project dependency) instead of `requests`, and reads the
token from settings so it isn't hard-coded.
"""
from __future__ import annotations

import asyncio

import httpx

from app.config import settings

# How long to wait for Instagram to finish ingesting the image before publishing.
_MEDIA_POLL_ATTEMPTS = 20
_MEDIA_POLL_INTERVAL = 2.0  # seconds


class InstagramError(Exception):
    """An Instagram API call failed; carries the platform's own message."""


def _base() -> str:
    return settings.instagram_graph_base.rstrip("/")


def _token(override: str | None = None) -> str:
    token = override or settings.instagram_access_token
    if not token:
        raise InstagramError(
            "INSTAGRAM_ACCESS_TOKEN is not set. Add it to your .env."
        )
    return token


async def get_instagram_profile(access_token: str | None = None) -> dict:
    """Return the connected account's profile (id, username, account_type)."""
    params = {
        "fields": "user_id,username,account_type",
        "access_token": _token(access_token),
    }
    async with httpx.AsyncClient(timeout=settings.ai_request_timeout) as client:
        resp = await client.get(f"{_base()}/me", params=params)
    return _parse(resp)


async def publish_image(
    *, caption: str, image_url: str, access_token: str | None = None
) -> str:
    """Publish a single image post; returns the published media id.

    Two steps per the API: create a media container, then publish it. The image
    must be at a publicly reachable URL — Instagram fetches it server-side.
    """
    token = _token(access_token)
    async with httpx.AsyncClient(timeout=settings.ai_request_timeout) as client:
        # Send as form body (data=), not query params: captions carry emojis and
        # punctuation, and non-ASCII in the query string makes the Graph API
        # reject the request ("error parsing the body").
        container = _parse(
            await client.post(
                f"{_base()}/me/media",
                data={"image_url": image_url, "caption": caption, "access_token": token},
            )
        )
        creation_id = container.get("id")
        if not creation_id:
            raise InstagramError("No media container id returned.")

        # Instagram fetches/processes the image asynchronously. Publishing before
        # it's FINISHED fails ("Media ID is not available"), so poll first.
        await _await_container_ready(client, creation_id, token)

        published = _parse(
            await client.post(
                f"{_base()}/me/media_publish",
                data={"creation_id": creation_id, "access_token": token},
            )
        )
        media_id = published.get("id")
        if not media_id:
            raise InstagramError("No published media id returned.")
        return media_id


async def _await_container_ready(
    client: httpx.AsyncClient, creation_id: str, token: str
) -> None:
    """Poll a media container until Instagram reports it FINISHED."""
    for _ in range(_MEDIA_POLL_ATTEMPTS):
        status = _parse(
            await client.get(
                f"{_base()}/{creation_id}",
                params={"fields": "status_code", "access_token": token},
            )
        )
        code = status.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise InstagramError(
                f"Instagram could not process the image (status: {code}). "
                "Check the image URL is public and a supported format/size."
            )
        await asyncio.sleep(_MEDIA_POLL_INTERVAL)
    raise InstagramError(
        "Timed out waiting for Instagram to process the image. Try again."
    )


def _parse(resp: httpx.Response) -> dict:
    try:
        data = resp.json()
    except ValueError:
        raise InstagramError(f"Instagram returned non-JSON ({resp.status_code}).")
    if resp.status_code != 200 or (isinstance(data, dict) and "error" in data):
        msg = ""
        if isinstance(data, dict):
            msg = (data.get("error") or {}).get("message", "") or str(data)
        raise InstagramError(msg or f"Instagram API error {resp.status_code}")
    return data
