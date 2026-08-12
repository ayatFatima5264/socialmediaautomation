"""Thin async client for the Threads API (graph.threads.net).

Publishing on Threads is a two-step flow, like Instagram:
  1. create a media container (`POST /{user_id}/threads`) — text, or image+text
  2. publish it (`POST /{user_id}/threads_publish`)

Text-only posts publish immediately. For an image, Threads ingests it
server-side, so we poll the container status until it is FINISHED before
publishing. Every failure raises ThreadsAPIError with the platform's message.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

THREADS_API_BASE = "https://graph.threads.net/v1.0"

_MAX_ATTEMPTS = 3
_BACKOFF_BASE = 0.5
# Image containers need a moment to ingest before they can be published.
_MEDIA_POLL_ATTEMPTS = 15
_MEDIA_POLL_INTERVAL = 2.0  # seconds


class ThreadsAPIError(Exception):
    """A Threads API call failed. Flags let callers branch without parsing text."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: int | None = None,
        subcode: int | None = None,
        is_auth_error: bool = False,
        is_rate_limited: bool = False,
        is_permission_error: bool = False,
        is_server_error: bool = False,
        is_media_error: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        # Meta's own error code / subcode from the response body.
        self.code = code
        self.subcode = subcode
        self.is_auth_error = is_auth_error
        self.is_rate_limited = is_rate_limited
        self.is_permission_error = is_permission_error
        self.is_server_error = is_server_error
        # The container was rejected because of the media itself (bad URL,
        # unsupported format, download failure) rather than the request.
        self.is_media_error = is_media_error


# Meta error codes that mean "slow down" regardless of HTTP status — the Graph
# API often returns them as 400.
_RATE_LIMIT_CODES = {4, 17, 32, 613}
# "Permissions error" / "requires permission" family.
_PERMISSION_CODES = {10, 200, 803}
# Token problems Meta reports as code 190 (with subcodes for expiry/revocation).
_AUTH_CODES = {102, 190}


async def publish_post(
    *,
    user_id: str,
    access_token: str,
    text: str,
    image_url: str | None = None,
) -> str:
    """Create and publish a Threads post. Returns the published media id."""
    creation_id = await _create_container(
        user_id=user_id, access_token=access_token, text=text, image_url=image_url
    )
    if image_url:
        await _await_container_ready(creation_id, access_token)
    media_id = await _publish_container(
        user_id=user_id, access_token=access_token, creation_id=creation_id
    )
    return media_id


async def _create_container(
    *, user_id: str, access_token: str, text: str, image_url: str | None
) -> str:
    params: dict[str, Any] = {"access_token": access_token, "text": text}
    if image_url:
        params["media_type"] = "IMAGE"
        params["image_url"] = image_url
    else:
        params["media_type"] = "TEXT"
    data = await _request(f"{user_id}/threads", params)
    creation_id = data.get("id")
    if not creation_id:
        raise ThreadsAPIError("Threads did not return a media container id.")
    return creation_id


async def _publish_container(
    *, user_id: str, access_token: str, creation_id: str
) -> str:
    data = await _request(
        f"{user_id}/threads_publish",
        {"access_token": access_token, "creation_id": creation_id},
    )
    media_id = data.get("id")
    if not media_id:
        raise ThreadsAPIError("Threads did not return a published media id.")
    return media_id


async def _await_container_ready(creation_id: str, access_token: str) -> None:
    """Poll an image container until Threads reports it FINISHED."""
    for _ in range(_MEDIA_POLL_ATTEMPTS):
        data = await _request(
            creation_id,
            {"access_token": access_token, "fields": "status"},
            method="GET",
        )
        status = data.get("status")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise ThreadsAPIError(
                f"Threads could not process the image (status: {status}). "
                "Check the image URL is public and a supported format."
            )
        await asyncio.sleep(_MEDIA_POLL_INTERVAL)
    raise ThreadsAPIError("Timed out waiting for Threads to process the image.")


async def _request(path: str, params: dict, *, method: str = "POST") -> dict:
    url = f"{THREADS_API_BASE}/{path}"
    last_error: ThreadsAPIError | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=settings.ai_request_timeout) as client:
                resp = await client.request(method, url, params=params)
        except httpx.HTTPError as exc:
            last_error = ThreadsAPIError(f"Threads API request failed: {exc}")
            if attempt < _MAX_ATTEMPTS:
                await asyncio.sleep(_BACKOFF_BASE * (2 ** (attempt - 1)))
                continue
            raise last_error

        if resp.status_code < 400:
            try:
                data = resp.json()
            except ValueError:
                raise ThreadsAPIError(
                    f"Threads returned non-JSON ({resp.status_code})."
                )
            return data if isinstance(data, dict) else {"data": data}

        error = _classify_error(resp, f"{method} {path}")
        # 5xx is transient. A rate limit is too, but only briefly worth waiting
        # out — a longer block is the caller's to report, not to sit through.
        if (error.is_server_error or error.is_rate_limited) and attempt < _MAX_ATTEMPTS:
            last_error = error
            await asyncio.sleep(_BACKOFF_BASE * (2 ** (attempt - 1)))
            continue
        raise error

    raise last_error or ThreadsAPIError("Threads API request failed after retries.")


def _classify_error(resp: httpx.Response, operation: str = "") -> ThreadsAPIError:
    """Turn a Graph error body into flags callers can branch on.

    Meta reports most failures as HTTP 400 and distinguishes them by `code` /
    `error_subcode`, so the status alone says very little — a rate limit, an
    expired token and a bad image URL all arrive the same way.
    """
    try:
        data = resp.json()
    except ValueError:
        data = {}
    err = data.get("error") if isinstance(data, dict) else None
    if not isinstance(err, dict):
        err = {}
    message = err.get("message") or err.get("error_user_msg") or ""
    code = err.get("code") if isinstance(err.get("code"), int) else None
    subcode = (
        err.get("error_subcode") if isinstance(err.get("error_subcode"), int) else None
    )

    status = resp.status_code
    lowered = message.lower()
    error = ThreadsAPIError(
        message or f"Threads API error {status}",
        status_code=status,
        code=code,
        subcode=subcode,
        is_auth_error=status == 401 or code in _AUTH_CODES,
        is_rate_limited=status == 429 or code in _RATE_LIMIT_CODES,
        is_permission_error=status == 403 or code in _PERMISSION_CODES,
        is_server_error=status >= 500,
        is_media_error=any(
            hint in lowered
            for hint in ("media", "image", "video", "url", "download", "format")
        ),
    )
    # The failing call, the status and Meta's message only — never the params,
    # which carry the access token.
    logger.warning(
        "Threads API error %d on %s (code=%s subcode=%s): %s",
        status, operation or "?", code, subcode, error.message,
    )
    return error
