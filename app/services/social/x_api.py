"""Thin async client for the official X (Twitter) API v2.

Isolates every X HTTP concern — endpoint, bearer auth, transient retries, rate
limit and error parsing — behind small functions, so publishers stay
declarative and the Phase-2 additions (media upload, polls, threads) are new
functions here rather than changes to callers.

Every failure raises XAPIError carrying enough context (auth vs rate-limit vs
transient server error) for callers to react appropriately: refresh a token,
surface a wait, or let the post be retried later.

Endpoint reference (current official host, api.x.com; api.twitter.com still
resolves to the same v2 API):
  * POST /2/tweets        — create a tweet (text, media, poll, reply)
  * POST /2/media/upload  — upload media bytes, returns a media id to attach
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Current official v2 host.
X_API_BASE = "https://api.x.com/2"

# Transient-failure retry policy (network hiccups + 5xx). Auth (401) and rate
# limits (429) are deliberately NOT retried here — the caller decides whether to
# refresh a token or surface a wait.
_MAX_ATTEMPTS = 3
_BACKOFF_BASE = 0.5  # seconds → 0.5, 1.0 between attempts

# X's character limit for a standard (non-verified) tweet.
TWEET_MAX_CHARS = 280

# X allows at most 4 images on a single tweet (or 1 GIF, or 1 video).
MAX_IMAGES_PER_TWEET = 4


class XAPIError(Exception):
    """An X API call failed. Flags let callers branch without parsing strings."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        is_auth_error: bool = False,
        is_rate_limited: bool = False,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.is_auth_error = is_auth_error
        self.is_rate_limited = is_rate_limited
        self.retry_after = retry_after  # seconds, when known (rate limits)


# --------------------------------------------------------------------------
# Publishing: tweets
# --------------------------------------------------------------------------
async def create_tweet(
    *,
    access_token: str,
    text: str,
    media_ids: list[str] | None = None,
    poll: dict[str, Any] | None = None,
    reply_to: str | None = None,
    quote_tweet_id: str | None = None,
) -> dict:
    """Create a tweet via ``POST /2/tweets``. Returns the parsed response
    (``{"data": {"id", "text"}}``).

    Phase 1 uses ``text`` only. The remaining parameters are the Phase-2 seams —
    pass ``media_ids`` for images/video, ``poll`` for polls, ``reply_to`` for the
    next tweet in a thread, ``quote_tweet_id`` for a quote — and require no change
    to this function's callers.
    """
    payload = _tweet_payload(
        text=text,
        media_ids=media_ids,
        poll=poll,
        reply_to=reply_to,
        quote_tweet_id=quote_tweet_id,
    )
    preview = text.replace("\n", " ")[:60]
    logger.info(
        "X API create_tweet: %d chars, media=%s, poll=%s, reply_to=%s | %r",
        len(text), bool(media_ids), bool(poll), reply_to, preview,
    )
    data = await _request("POST", "tweets", access_token=access_token, json=payload)
    tweet_id = (data.get("data") or {}).get("id")
    logger.info("X API create_tweet ok: tweet_id=%s", tweet_id)
    return data


def _tweet_payload(
    *,
    text: str,
    media_ids: list[str] | None,
    poll: dict[str, Any] | None,
    reply_to: str | None,
    quote_tweet_id: str | None,
) -> dict:
    """Build the /2/tweets request body. Optional keys are omitted when unset so
    the same builder serves Phase 1 (text) and Phase 2 (media/poll/thread)."""
    body: dict[str, Any] = {"text": text}
    if media_ids:
        body["media"] = {"media_ids": list(media_ids)}
    if poll:
        body["poll"] = poll  # {"options": [...], "duration_minutes": N}
    if reply_to:
        body["reply"] = {"in_reply_to_tweet_id": str(reply_to)}
    if quote_tweet_id:
        body["quote_tweet_id"] = str(quote_tweet_id)
    return body


# --------------------------------------------------------------------------
# Publishing: media
# --------------------------------------------------------------------------
# MIME types X accepts for image uploads (GIF is treated as an image too).
_SUPPORTED_IMAGE_MIME = {"image/jpeg", "image/png", "image/gif", "image/webp"}


async def download_media(url: str) -> tuple[bytes, str]:
    """Fetch the bytes + MIME type of a media URL from the existing pipeline.

    The project's media pipeline stores every visual as a publicly reachable URL
    (Pollinations / stock providers). X — unlike Meta — will not fetch a URL, so
    the X integration downloads the bytes here and uploads them in `upload_media`.
    Raises XAPIError on a network failure or non-200 response.
    """
    try:
        async with httpx.AsyncClient(
            timeout=settings.ai_request_timeout, follow_redirects=True
        ) as client:
            resp = await client.get(url)
    except httpx.HTTPError as exc:
        raise XAPIError(f"Could not fetch media for X: {exc}") from exc
    if resp.status_code != 200:
        raise XAPIError(
            f"Media source returned {resp.status_code} — image unavailable for X."
        )
    mime = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    return resp.content, mime or "application/octet-stream"


async def upload_media(
    *,
    access_token: str,
    data: bytes,
    mime_type: str,
    category: str = "tweet_image",
) -> str:
    """Upload media bytes to X via ``POST /2/media/upload``; return the media id.

    `category` is X's media_category — "tweet_image" for images (Phase 2 here).
    Video uses "tweet_video" and X's chunked INIT/APPEND/FINALIZE flow, which
    slots in as a separate branch when the media pipeline gains video.

    Requires the token to carry the ``media.write`` scope, in addition to
    ``tweet.write``. Raises XAPIError (auth/rate-limit/other) on failure.
    """
    logger.info(
        "X API media upload: %d bytes, mime=%s, category=%s",
        len(data), mime_type, category,
    )
    # Simple (single-request) upload — valid for images. multipart/form-data.
    result = await _request(
        "POST",
        "media/upload",
        access_token=access_token,
        files={"media": ("upload", data, mime_type)},
        data={"media_category": category},
    )
    # v2 returns {"data": {"id": ...}}; v1.1-style responses use media_id_string.
    media_id = (
        (result.get("data") or {}).get("id")
        or result.get("media_id_string")
        or (str(result["media_id"]) if result.get("media_id") else None)
    )
    if not media_id:
        raise XAPIError("X media upload did not return a media id.")
    logger.info("X API media upload ok: media_id=%s", media_id)
    return str(media_id)


def is_supported_image(mime_type: str) -> bool:
    return (mime_type or "").lower() in _SUPPORTED_IMAGE_MIME


# --------------------------------------------------------------------------
# HTTP core: auth header, transient retries, error classification, logging
# --------------------------------------------------------------------------
async def _request(
    method: str,
    path: str,
    *,
    access_token: str,
    json: dict | None = None,
    data: dict | None = None,
    files: dict | None = None,
    params: dict | None = None,
) -> dict:
    url = f"{X_API_BASE}/{path}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    last_error: XAPIError | None = None

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=settings.ai_request_timeout) as client:
                resp = await client.request(
                    method, url, headers=headers,
                    json=json, data=data, files=files, params=params,
                )
        except httpx.HTTPError as exc:  # network/DNS/timeout — transient
            last_error = XAPIError(f"X API request failed: {exc}")
            logger.warning(
                "X API %s %s network error (attempt %d/%d): %s",
                method, path, attempt, _MAX_ATTEMPTS, exc,
            )
            if attempt < _MAX_ATTEMPTS:
                await _sleep_backoff(attempt)
                continue
            raise last_error

        if resp.status_code < 400:
            return _parse_ok(resp)

        error = _classify_error(resp)
        # Retry only transient server errors; auth/rate-limit/other client
        # errors are terminal for this request and bubble up to the caller.
        if resp.status_code >= 500 and attempt < _MAX_ATTEMPTS:
            logger.warning(
                "X API %s %s -> %d (attempt %d/%d), retrying: %s",
                method, path, resp.status_code, attempt, _MAX_ATTEMPTS, error.message,
            )
            last_error = error
            await _sleep_backoff(attempt)
            continue
        raise error

    raise last_error or XAPIError("X API request failed after retries.")


async def _sleep_backoff(attempt: int) -> None:
    await asyncio.sleep(_BACKOFF_BASE * (2 ** (attempt - 1)))


def _parse_ok(resp: httpx.Response) -> dict:
    try:
        data = resp.json()
    except ValueError:
        raise XAPIError(
            f"X API returned non-JSON ({resp.status_code}).",
            status_code=resp.status_code,
        )
    return data if isinstance(data, dict) else {"data": data}


def _classify_error(resp: httpx.Response) -> XAPIError:
    try:
        data = resp.json()
    except ValueError:
        data = {}
    status = resp.status_code
    message = _error_message(data, status)
    is_rate = status == 429
    error = XAPIError(
        message,
        status_code=status,
        # 401 → token expired/invalid → a refresh + retry can recover it.
        # 403 (duplicate/forbidden) is NOT auth: it must not trigger a refresh.
        is_auth_error=status == 401,
        is_rate_limited=is_rate,
        retry_after=_retry_after(resp) if is_rate else None,
    )
    logger.warning("X API error %d: %s", status, message)
    return error


def _error_message(data: Any, status_code: int) -> str:
    """Best-effort human message from X's problem+json / errors[] shapes."""
    if isinstance(data, dict):
        detail = data.get("detail") or data.get("title")
        errs = data.get("errors")
        if isinstance(errs, list) and errs:
            parts = [
                str(e.get("message") or e.get("detail") or e.get("title") or e)
                for e in errs
                if e
            ]
            joined = "; ".join(p for p in parts if p)
            detail = f"{detail}: {joined}" if detail and joined else (detail or joined)
        if detail:
            return str(detail)
    return f"X API error {status_code}"


def _retry_after(resp: httpx.Response) -> int | None:
    """Seconds to wait: prefer the standard Retry-After, fall back to X's
    x-rate-limit-reset epoch."""
    retry_after = resp.headers.get("retry-after")
    if retry_after and retry_after.isdigit():
        return int(retry_after)
    reset = resp.headers.get("x-rate-limit-reset")
    if reset and reset.isdigit():
        return max(0, int(reset) - int(time.time()))
    return None
