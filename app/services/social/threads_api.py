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
        is_auth_error: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.is_auth_error = is_auth_error


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

        error = _classify_error(resp)
        if resp.status_code >= 500 and attempt < _MAX_ATTEMPTS:
            last_error = error
            await asyncio.sleep(_BACKOFF_BASE * (2 ** (attempt - 1)))
            continue
        raise error

    raise last_error or ThreadsAPIError("Threads API request failed after retries.")


def _classify_error(resp: httpx.Response) -> ThreadsAPIError:
    try:
        data = resp.json()
    except ValueError:
        data = {}
    message = ""
    if isinstance(data, dict):
        message = (data.get("error") or {}).get("message", "") if isinstance(
            data.get("error"), dict
        ) else str(data.get("error") or "")
    status = resp.status_code
    error = ThreadsAPIError(
        message or f"Threads API error {status}",
        status_code=status,
        is_auth_error=status in (401, 403),
    )
    logger.warning("Threads API error %d: %s", status, error.message)
    return error
