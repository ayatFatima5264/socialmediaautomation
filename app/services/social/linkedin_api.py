"""Thin async client for the official LinkedIn REST API (member posts).

Isolates every LinkedIn HTTP concern — endpoint, bearer auth, the required
version + protocol headers, transient retries, and error classification — behind
one function so the publisher stays declarative.

We publish a member text share via ``POST /rest/posts`` (the current, versioned
Posts API — ``/v2/ugcPosts`` is legacy). The created post's URN is returned in
the ``x-restli-id`` response header, not the body.

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


async def create_text_post(
    *,
    access_token: str,
    author_urn: str,
    text: str,
    visibility: str = "PUBLIC",
) -> str:
    """Publish a member text share via ``POST /rest/posts``.

    Returns the created post's URN (e.g. ``urn:li:share:12345``). Raises
    LinkedInAPIError on failure.
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
    preview = text.replace("\n", " ")[:60]
    logger.info("LinkedIn create_text_post: %d chars | %r", len(text), preview)
    post_id = await _request("posts", access_token=access_token, json=payload)
    logger.info("LinkedIn create_text_post ok: id=%s", post_id)
    return post_id


# --------------------------------------------------------------------------
# HTTP core: headers, transient retries, error classification
# --------------------------------------------------------------------------
async def _request(path: str, *, access_token: str, json: dict) -> str:
    """POST to a LinkedIn REST path; return the created resource's URN from the
    ``x-restli-id`` header (falling back to the body's ``id``)."""
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
                resp = await client.post(url, headers=headers, json=json)
        except httpx.HTTPError as exc:  # network/DNS/timeout — transient
            last_error = LinkedInAPIError(f"LinkedIn API request failed: {exc}")
            logger.warning(
                "LinkedIn API POST %s network error (attempt %d/%d): %s",
                path, attempt, _MAX_ATTEMPTS, exc,
            )
            if attempt < _MAX_ATTEMPTS:
                await asyncio.sleep(_BACKOFF_BASE * (2 ** (attempt - 1)))
                continue
            raise last_error

        if resp.status_code < 400:
            return resp.headers.get("x-restli-id") or _body_id(resp)

        error = _classify_error(resp)
        if resp.status_code >= 500 and attempt < _MAX_ATTEMPTS:
            logger.warning(
                "LinkedIn API POST %s -> %d (attempt %d/%d), retrying: %s",
                path, resp.status_code, attempt, _MAX_ATTEMPTS, error.message,
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
