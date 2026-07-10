"""Thin async client for the official LinkedIn REST API (member posts).

Isolates every LinkedIn HTTP concern — endpoint, bearer auth, the required
version + protocol headers, transient retries, and error classification — behind
one function so the publisher stays declarative.

We publish a member share via ``POST /rest/posts`` (the current, versioned
Posts API — ``/v2/ugcPosts`` is legacy). The created post's URN is returned in
the ``x-restli-id`` response header, not the body. An image is attached by first
uploading it (``/rest/images?action=initializeUpload`` → PUT the bytes) and
referencing the returned image URN in the post's ``content.media``.

Auth: the connected account's OAuth access token, which must carry the
``w_member_social`` scope (granted by LinkedIn's "Share on LinkedIn" product).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

LINKEDIN_API_BASE = "https://api.linkedin.com/rest"

# Transient-failure retry policy (network hiccups + 5xx). Auth (401) and
# rate limits (429) are NOT retried — the caller surfaces a clear message.
_MAX_ATTEMPTS = 3
_BACKOFF_BASE = 0.5  # seconds → 0.5, 1.0 between attempts


class LinkedInAPIError(Exception):
    """A LinkedIn API call failed. Flags let callers branch without parsing text."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        is_auth_error: bool = False,
        is_rate_limited: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.is_auth_error = is_auth_error
        self.is_rate_limited = is_rate_limited


async def create_post(
    *,
    access_token: str,
    author_urn: str,
    text: str,
    image_urn: str | None = None,
    image_title: str | None = None,
    visibility: str = "PUBLIC",
) -> str:
    """Publish a member share via ``POST /rest/posts``.

    With ``image_urn`` (from :func:`upload_image`) the share carries that image;
    otherwise it is text-only. Returns the created post's URN (e.g.
    ``urn:li:share:12345``). Raises LinkedInAPIError on failure.
    """
    payload: dict[str, Any] = {
        "author": author_urn,
        "commentary": text,
        "visibility": visibility,
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    if image_urn:
        media: dict[str, Any] = {"id": image_urn}
        if image_title:
            media["title"] = image_title[:400]
        payload["content"] = {"media": media}
    preview = text.replace("\n", " ")[:60]
    logger.info(
        "LinkedIn create_post: %d chars, image=%s | %r",
        len(text), bool(image_urn), preview,
    )
    resp = await _send("POST", "posts", access_token=access_token, json=payload)
    post_id = resp.headers.get("x-restli-id") or _body_id(resp)
    logger.info("LinkedIn create_post ok: id=%s", post_id)
    return post_id


# Backwards-compatible alias for the text-only entry point.
async def create_text_post(*, access_token: str, author_urn: str, text: str) -> str:
    return await create_post(
        access_token=access_token, author_urn=author_urn, text=text
    )


async def upload_image(
    *, access_token: str, owner_urn: str, image_url: str
) -> str:
    """Upload an image to LinkedIn; return its image URN (``urn:li:image:...``).

    Three steps: initializeUpload (returns a one-time uploadUrl + image URN),
    download the image bytes from ``image_url``, then PUT the bytes to the
    uploadUrl. The returned URN is referenced in the post's ``content.media``.
    """
    init = await _send(
        "POST",
        "images?action=initializeUpload",
        access_token=access_token,
        json={"initializeUploadRequest": {"owner": owner_urn}},
    )
    value = (init.json() or {}).get("value") or {}
    upload_url = value.get("uploadUrl")
    image_urn = value.get("image")
    if not upload_url or not image_urn:
        raise LinkedInAPIError("LinkedIn did not return an image upload URL.")

    image_bytes = await _fetch_bytes(image_url)
    await _put_bytes(upload_url, access_token, image_bytes)
    logger.info("LinkedIn upload_image ok: %s (%d bytes)", image_urn, len(image_bytes))
    return image_urn


async def _fetch_bytes(url: str) -> bytes:
    try:
        async with httpx.AsyncClient(
            timeout=settings.ai_request_timeout, follow_redirects=True
        ) as client:
            resp = await client.get(url)
    except httpx.HTTPError as exc:
        raise LinkedInAPIError(f"Could not download the image: {exc}") from exc
    if resp.status_code >= 400:
        raise LinkedInAPIError(
            f"Could not download the image (HTTP {resp.status_code})."
        )
    return resp.content


async def _put_bytes(upload_url: str, access_token: str, data: bytes) -> None:
    try:
        async with httpx.AsyncClient(timeout=settings.ai_request_timeout) as client:
            resp = await client.put(
                upload_url,
                content=data,
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.HTTPError as exc:
        raise LinkedInAPIError(f"Image upload failed: {exc}") from exc
    if resp.status_code >= 400:
        raise LinkedInAPIError(
            f"LinkedIn image upload failed (HTTP {resp.status_code})."
        )


# --------------------------------------------------------------------------
# HTTP core: headers, transient retries, error classification
# --------------------------------------------------------------------------
async def _send(
    method: str, path: str, *, access_token: str, json: dict
) -> httpx.Response:
    """Send a request to a LinkedIn REST path with the required headers and
    transient-retry policy. Returns the successful response (caller reads the
    ``x-restli-id`` header or the JSON body); raises LinkedInAPIError otherwise."""
    url = f"{LINKEDIN_API_BASE}/{path}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": settings.linkedin_api_version,
    }
    last_error: LinkedInAPIError | None = None

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=settings.ai_request_timeout) as client:
                resp = await client.request(method, url, headers=headers, json=json)
        except httpx.HTTPError as exc:  # network/DNS/timeout — transient
            last_error = LinkedInAPIError(f"LinkedIn API request failed: {exc}")
            logger.warning(
                "LinkedIn API %s %s network error (attempt %d/%d): %s",
                method, path, attempt, _MAX_ATTEMPTS, exc,
            )
            if attempt < _MAX_ATTEMPTS:
                await asyncio.sleep(_BACKOFF_BASE * (2 ** (attempt - 1)))
                continue
            raise last_error

        if resp.status_code < 400:
            return resp

        error = _classify_error(resp)
        if resp.status_code >= 500 and attempt < _MAX_ATTEMPTS:
            logger.warning(
                "LinkedIn API %s %s -> %d (attempt %d/%d), retrying: %s",
                method, path, resp.status_code, attempt, _MAX_ATTEMPTS, error.message,
            )
            last_error = error
            await asyncio.sleep(_BACKOFF_BASE * (2 ** (attempt - 1)))
            continue
        raise error

    raise last_error or LinkedInAPIError("LinkedIn API request failed after retries.")


def _body_id(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except ValueError:
        return ""
    return str(data.get("id", "")) if isinstance(data, dict) else ""


def _classify_error(resp: httpx.Response) -> LinkedInAPIError:
    try:
        data = resp.json()
    except ValueError:
        data = {}
    status = resp.status_code
    message = ""
    if isinstance(data, dict):
        message = str(data.get("message") or data.get("error_description") or "")
    if not message:
        message = f"LinkedIn API error {status}"
    error = LinkedInAPIError(
        message,
        status_code=status,
        is_auth_error=status in (401, 403),
        is_rate_limited=status == 429,
    )
    logger.warning("LinkedIn API error %d: %s", status, message)
    return error
