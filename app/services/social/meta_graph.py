"""Thin async client for the Meta (Facebook/Instagram) Graph API.

Covers exactly what connecting + publishing an Instagram account needs:
  * exchange a short-lived token for a long-lived one
  * discover the user's Pages and their linked Instagram Business accounts
  * read an Instagram account's username
  * create + publish a media container (image/video + caption)

Every call raises GraphAPIError with the platform's own message on failure, so
callers can surface a clear reason to the user.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.config import settings


class GraphAPIError(Exception):
    """A Graph API call returned an error (or the HTTP request failed)."""


def _base() -> str:
    return f"https://graph.facebook.com/{settings.meta_graph_version}"


async def _get(client: httpx.AsyncClient, path: str, params: dict[str, Any]) -> dict:
    try:
        resp = await client.get(f"{_base()}/{path}", params=params)
    except httpx.HTTPError as exc:  # network/DNS/timeout
        raise GraphAPIError(f"Graph API request failed: {exc}") from exc
    return _parse(resp)


async def _post(client: httpx.AsyncClient, path: str, params: dict[str, Any]) -> dict:
    try:
        resp = await client.post(f"{_base()}/{path}", params=params)
    except httpx.HTTPError as exc:
        raise GraphAPIError(f"Graph API request failed: {exc}") from exc
    return _parse(resp)


def _parse(resp: httpx.Response) -> dict:
    try:
        data = resp.json()
    except ValueError:
        raise GraphAPIError(f"Graph API returned non-JSON ({resp.status_code}).")
    if resp.status_code != 200 or (isinstance(data, dict) and "error" in data):
        msg = ""
        if isinstance(data, dict):
            msg = (data.get("error") or {}).get("message", "") or str(data)
        raise GraphAPIError(msg or f"Graph API error {resp.status_code}")
    return data


# --------------------------------------------------------------------------
# Connection / account resolution
# --------------------------------------------------------------------------
async def exchange_for_long_lived_token(short_token: str) -> tuple[str, int | None]:
    """Exchange a short-lived token for a long-lived one (~60 days).

    Requires META_APP_ID/SECRET. Returns (token, expires_in_seconds). If the app
    credentials aren't configured, returns the token unchanged so the manual
    connect flow still works with an already-long-lived token.
    """
    if not (settings.meta_app_id and settings.meta_app_secret):
        return short_token, None
    async with httpx.AsyncClient(timeout=settings.ai_request_timeout) as client:
        data = await _get(
            client,
            "oauth/access_token",
            {
                "grant_type": "fb_exchange_token",
                "client_id": settings.meta_app_id,
                "client_secret": settings.meta_app_secret,
                "fb_exchange_token": short_token,
            },
        )
    return data["access_token"], data.get("expires_in")


async def list_instagram_accounts(access_token: str) -> list[dict]:
    """Return EVERY Instagram Business account linked to the user's Pages.

    Each item: {account_id, page_id, page_name, username, name,
    profile_picture_url}. Empty list if none are linked. This is what powers the
    "choose which Instagram account to connect" step (Buffer/Hootsuite style).
    """
    accounts: list[dict] = []
    async with httpx.AsyncClient(timeout=settings.ai_request_timeout) as client:
        # Page through the user's Pages (100 at a time).
        url = "me/accounts"
        params: dict = {
            # Check both linkage fields: the classic `instagram_business_account`
            # and the newer `connected_instagram_account` some setups use.
            "fields": "name,instagram_business_account,connected_instagram_account",
            "access_token": access_token,
            "limit": 100,
        }
        pages: list[dict] = []
        while True:
            data = await _get(client, url, params)
            pages.extend(data.get("data", []))
            nxt = (data.get("paging") or {}).get("next")
            if not nxt or len(pages) >= 500:  # sane cap
                break
            # `next` is a full URL; strip the base so _get can reuse it.
            url = nxt.replace(f"{_base()}/", "")
            params = {}

        for page in pages:
            iga = page.get("instagram_business_account") or page.get(
                "connected_instagram_account"
            )
            if not (iga and iga.get("id")):
                continue
            ig_id = iga["id"]
            profile = await _get(
                client,
                ig_id,
                {
                    "fields": "username,name,profile_picture_url",
                    "access_token": access_token,
                },
            )
            accounts.append(
                {
                    "account_id": ig_id,
                    "page_id": page.get("id"),
                    "page_name": page.get("name"),
                    "username": profile.get("username"),
                    "name": profile.get("name"),
                    "profile_picture_url": profile.get("profile_picture_url"),
                }
            )
    return accounts


# --------------------------------------------------------------------------
# Publishing (Content Publishing API)
# --------------------------------------------------------------------------
_MEDIA_POLL_ATTEMPTS = 20
_MEDIA_POLL_INTERVAL = 2.0  # seconds


async def publish_image(
    *, ig_account_id: str, access_token: str, image_url: str, caption: str
) -> str:
    """Publish a single image post. Returns the published media id.

    Three steps per Meta's API: create a media container, wait for Instagram to
    finish ingesting the image, then publish it. The image must be at a publicly
    reachable URL — Instagram fetches it server-side.
    """
    async with httpx.AsyncClient(timeout=settings.ai_request_timeout) as client:
        container = await _post(
            client,
            f"{ig_account_id}/media",
            {"image_url": image_url, "caption": caption, "access_token": access_token},
        )
        creation_id = container.get("id")
        if not creation_id:
            raise GraphAPIError("Graph API did not return a media container id.")

        # Publishing before the container is FINISHED fails ("Media ID is not
        # available"), so poll until Instagram has ingested the image.
        await _await_container_ready(client, creation_id, access_token)

        published = await _post(
            client,
            f"{ig_account_id}/media_publish",
            {"creation_id": creation_id, "access_token": access_token},
        )
        media_id = published.get("id")
        if not media_id:
            raise GraphAPIError("Graph API did not return a published media id.")
        return media_id


# --------------------------------------------------------------------------
# Facebook Page publishing
# --------------------------------------------------------------------------
async def list_pages(access_token: str) -> list[dict]:
    """Return the Facebook Pages the user manages: {id, name, access_token}.

    Posting to a Page is authorized by that Page's OWN access token (returned
    here), not the user token — so publishers resolve the Page token at publish
    time from the stored user token. Empty list if the user manages no Pages.
    """
    pages: list[dict] = []
    async with httpx.AsyncClient(timeout=settings.ai_request_timeout) as client:
        url = "me/accounts"
        params: dict = {
            "fields": "name,access_token",
            "access_token": access_token,
            "limit": 100,
        }
        while True:
            data = await _get(client, url, params)
            pages.extend(data.get("data", []))
            nxt = (data.get("paging") or {}).get("next")
            if not nxt or len(pages) >= 500:  # sane cap
                break
            url = nxt.replace(f"{_base()}/", "")
            params = {}
    return pages


async def create_page_post(
    *,
    page_id: str,
    page_access_token: str,
    message: str,
    image_url: str | None = None,
) -> str:
    """Publish a text or single-image post to a Facebook Page. Returns the post id.

    With `image_url` (a publicly reachable URL) it creates a photo post via
    `/{page}/photos`; otherwise a text post via `/{page}/feed`. Facebook fetches
    the image server-side, so no upload/polling step is needed (unlike Instagram).
    """
    async with httpx.AsyncClient(timeout=settings.ai_request_timeout) as client:
        if image_url:
            data = await _post(
                client,
                f"{page_id}/photos",
                {
                    "url": image_url,
                    "caption": message,
                    "access_token": page_access_token,
                },
            )
            # /photos returns {"id": <photo id>, "post_id": <feed post id>}.
            post_id = data.get("post_id") or data.get("id")
        else:
            data = await _post(
                client,
                f"{page_id}/feed",
                {"message": message, "access_token": page_access_token},
            )
            post_id = data.get("id")
        if not post_id:
            raise GraphAPIError("Graph API did not return a post id.")
        return post_id


async def _await_container_ready(
    client: httpx.AsyncClient, creation_id: str, access_token: str
) -> None:
    """Poll a media container until Instagram reports it FINISHED."""
    import asyncio

    for _ in range(_MEDIA_POLL_ATTEMPTS):
        status = await _get(
            client,
            creation_id,
            {"fields": "status_code", "access_token": access_token},
        )
        code = status.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise GraphAPIError(
                f"Instagram could not process the image (status: {code}). "
                "Check the image URL is public and a supported format/size."
            )
        await asyncio.sleep(_MEDIA_POLL_INTERVAL)
    raise GraphAPIError(
        "Timed out waiting for Instagram to process the image. Try again."
    )
