"""Thin async client for the Pinterest API v5 (api.pinterest.com/v5).

Covers what publishing a Pin needs: list the user's boards (a Pin must target a
board) and create an image Pin. Pins REQUIRE an image — there is no text-only
Pin. Auth is the stored OAuth access token as a Bearer credential.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

PINTEREST_API_BASE = "https://api.pinterest.com/v5"

_MAX_ATTEMPTS = 3
_BACKOFF_BASE = 0.5

# Pinterest field limits.
TITLE_MAX = 100
DESCRIPTION_MAX = 800


class PinterestAPIError(Exception):
    """A Pinterest API call failed. Flags let callers branch without parsing text."""

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


async def list_boards(access_token: str) -> list[dict]:
    """Return the user's boards: [{id, name}, ...] (first page, up to 100)."""
    data = await _request(
        "GET", "boards", access_token, params={"page_size": 100}
    )
    items = data.get("items") or []
    return [{"id": b.get("id"), "name": b.get("name")} for b in items if b.get("id")]


async def create_pin(
    *,
    access_token: str,
    board_id: str,
    image_url: str,
    title: str,
    description: str,
) -> str:
    """Create an image Pin on a board. Returns the pin id."""
    body: dict[str, Any] = {
        "board_id": board_id,
        "title": title[:TITLE_MAX],
        "description": description[:DESCRIPTION_MAX],
        "media_source": {"source_type": "image_url", "url": image_url},
    }
    data = await _request("POST", "pins", access_token, json=body)
    pin_id = data.get("id")
    if not pin_id:
        raise PinterestAPIError("Pinterest did not return a pin id.")
    return pin_id


async def _request(
    method: str,
    path: str,
    access_token: str,
    *,
    json: dict | None = None,
    params: dict | None = None,
) -> dict:
    url = f"{PINTEREST_API_BASE}/{path}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    last_error: PinterestAPIError | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=settings.ai_request_timeout) as client:
                resp = await client.request(
                    method, url, headers=headers, json=json, params=params
                )
        except httpx.HTTPError as exc:
            last_error = PinterestAPIError(f"Pinterest API request failed: {exc}")
            if attempt < _MAX_ATTEMPTS:
                await asyncio.sleep(_BACKOFF_BASE * (2 ** (attempt - 1)))
                continue
            raise last_error

        if resp.status_code < 400:
            try:
                data = resp.json()
            except ValueError:
                raise PinterestAPIError(
                    f"Pinterest returned non-JSON ({resp.status_code})."
                )
            return data if isinstance(data, dict) else {"data": data}

        error = _classify_error(resp)
        if resp.status_code >= 500 and attempt < _MAX_ATTEMPTS:
            last_error = error
            await asyncio.sleep(_BACKOFF_BASE * (2 ** (attempt - 1)))
            continue
        raise error

    raise last_error or PinterestAPIError("Pinterest API request failed after retries.")


def _classify_error(resp: httpx.Response) -> PinterestAPIError:
    try:
        data = resp.json()
    except ValueError:
        data = {}
    message = ""
    if isinstance(data, dict):
        message = str(data.get("message") or data.get("error_description") or "")
    status = resp.status_code
    error = PinterestAPIError(
        message or f"Pinterest API error {status}",
        status_code=status,
        is_auth_error=status in (401, 403),
        is_rate_limited=status == 429,
    )
    logger.warning("Pinterest API error %d: %s", status, error.message)
    return error
