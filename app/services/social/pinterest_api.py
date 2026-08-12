"""Thin async client for the Pinterest API v5 (api.pinterest.com/v5).

Covers what publishing a Pin needs: list the user's boards (a Pin must target a
board), look one board up (to prove it still exists before publishing), and
create an image Pin. Pins REQUIRE an image — there is no text-only Pin. Auth is
the stored OAuth access token as a Bearer credential.

Errors come back as a single PinterestAPIError carrying flags (auth, rate
limit, not found, server) so callers branch on those instead of parsing text,
and never surface a raw Pinterest payload — or a token — to the user.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

PINTEREST_API_BASE = "https://api.pinterest.com/v5"
# Same v5 API, separate environment. A Trial-tier app may only create Pins here
# — production answers 403 — so this is where publishing happens until the app
# is granted Standard access. See settings.pinterest_sandbox.
PINTEREST_SANDBOX_BASE = "https://api-sandbox.pinterest.com/v5"


def api_base() -> str:
    """The v5 host to call, per the app's access tier."""
    return PINTEREST_SANDBOX_BASE if settings.pinterest_sandbox else PINTEREST_API_BASE

_MAX_ATTEMPTS = 3
_BACKOFF_BASE = 0.5

# Pinterest field limits (PinCreate schema, API v5).
TITLE_MAX = 100
DESCRIPTION_MAX = 800
LINK_MAX = 2048
ALT_TEXT_MAX = 500
BOARD_NAME_MAX = 180
BOARD_DESCRIPTION_MAX = 500

# Boards are paged; 250 is the API maximum page size.
_BOARD_PAGE_SIZE = 250
# Stop after this many pages so a pathological account can't spin forever.
_MAX_BOARD_PAGES = 10


class PinterestAPIError(Exception):
    """A Pinterest API call failed. Flags let callers branch without parsing text."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: int | None = None,
        is_auth_error: bool = False,
        is_rate_limited: bool = False,
        is_not_found: bool = False,
        is_server_error: bool = False,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        # Pinterest's own numeric error code from the response body.
        self.code = code
        self.is_auth_error = is_auth_error
        self.is_rate_limited = is_rate_limited
        self.is_not_found = is_not_found
        self.is_server_error = is_server_error
        self.retry_after = retry_after


async def list_boards(access_token: str) -> list[dict]:
    """Every board the user owns or collaborates on: [{id, name, privacy}, ...].

    Follows Pinterest's bookmark pagination so an account with more boards than
    one page still sees all of them in the picker.
    """
    boards: list[dict] = []
    bookmark: str | None = None
    for _ in range(_MAX_BOARD_PAGES):
        params: dict[str, Any] = {"page_size": _BOARD_PAGE_SIZE}
        if bookmark:
            params["bookmark"] = bookmark
        data = await _request("GET", "boards", access_token, params=params)
        for board in data.get("items") or []:
            if board.get("id"):
                boards.append(
                    {
                        "id": str(board["id"]),
                        "name": board.get("name") or "Untitled board",
                        "privacy": board.get("privacy"),
                    }
                )
        bookmark = data.get("bookmark")
        if not bookmark:
            break
    return boards


async def get_board(access_token: str, board_id: str) -> dict:
    """Fetch one board. Raises PinterestAPIError with `is_not_found` if it's gone."""
    data = await _request("GET", f"boards/{board_id}", access_token)
    return {
        "id": str(data.get("id") or board_id),
        "name": data.get("name") or "Untitled board",
        "privacy": data.get("privacy"),
    }


async def create_board(
    *,
    access_token: str,
    name: str,
    description: str | None = None,
    privacy: str = "PUBLIC",
) -> dict:
    """Create a board and return it as {id, name, privacy}.

    Needed because a Pin can't exist without a board and boards don't cross
    environments: an account with boards in production starts with none in
    Sandbox, and Pinterest's own website only manages the production ones.
    """
    body: dict[str, Any] = {"name": name[:BOARD_NAME_MAX], "privacy": privacy}
    if description:
        body["description"] = description[:BOARD_DESCRIPTION_MAX]

    data = await _request("POST", "boards", access_token, json=body)
    if not data.get("id"):
        raise PinterestAPIError("Pinterest did not return a board id.")
    return {
        "id": str(data["id"]),
        "name": data.get("name") or name,
        "privacy": data.get("privacy") or privacy,
    }


async def create_pin(
    *,
    access_token: str,
    board_id: str,
    image_url: str,
    title: str,
    description: str,
    link: str | None = None,
    alt_text: str | None = None,
) -> str:
    """Create an image Pin on a board. Returns the pin id.

    `image_url` must be a publicly reachable URL — Pinterest fetches the image
    server-side (media_source.source_type = "image_url"), so no upload step and
    no second media store is involved.
    """
    body: dict[str, Any] = {
        "board_id": board_id,
        "title": title[:TITLE_MAX],
        "description": description[:DESCRIPTION_MAX],
        "media_source": {"source_type": "image_url", "url": image_url},
    }
    if link:
        body["link"] = link[:LINK_MAX]
    if alt_text:
        body["alt_text"] = alt_text[:ALT_TEXT_MAX]

    data = await _request("POST", "pins", access_token, json=body)
    pin_id = data.get("id")
    if not pin_id:
        raise PinterestAPIError("Pinterest did not return a pin id.")
    return str(pin_id)


async def _request(
    method: str,
    path: str,
    access_token: str,
    *,
    json: dict | None = None,
    params: dict | None = None,
) -> dict:
    url = f"{api_base()}/{path}"
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

        error = _classify_error(resp, f"{method} {path}")
        # 5xx is transient; so is a 429 that tells us how long to wait for.
        retryable = error.is_server_error or error.is_rate_limited
        if retryable and attempt < _MAX_ATTEMPTS:
            last_error = error
            delay = _BACKOFF_BASE * (2 ** (attempt - 1))
            if error.is_rate_limited:
                # Honour Retry-After, but never stall a request for minutes.
                delay = min(error.retry_after or delay, 10)
            await asyncio.sleep(delay)
            continue
        raise error

    raise last_error or PinterestAPIError("Pinterest API request failed after retries.")


def _classify_error(resp: httpx.Response, operation: str = "") -> PinterestAPIError:
    try:
        data = resp.json()
    except ValueError:
        data = {}
    message = ""
    code = None
    if isinstance(data, dict):
        message = str(data.get("message") or data.get("error_description") or "")
        raw_code = data.get("code")
        code = raw_code if isinstance(raw_code, int) else None

    status = resp.status_code
    error = PinterestAPIError(
        message or f"Pinterest API error {status}",
        status_code=status,
        code=code,
        is_auth_error=status in (401, 403),
        is_rate_limited=status == 429,
        is_not_found=status == 404,
        is_server_error=status >= 500,
        retry_after=_retry_after(resp),
    )
    # Log the failing call, the status and Pinterest's message — never the token
    # or headers. The operation matters: a 403 listing boards and a 403 creating
    # a Pin have completely different causes.
    logger.warning(
        "Pinterest API error %d on %s (code=%s): %s",
        status, operation or "?", code, error.message,
    )
    return error


def _retry_after(resp: httpx.Response) -> int | None:
    raw = resp.headers.get("Retry-After")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None
