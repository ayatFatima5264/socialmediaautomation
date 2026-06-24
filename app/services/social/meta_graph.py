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


async def resolve_instagram_account(
    access_token: str, page_id: str | None = None
) -> dict:
    """Find the Instagram Business account reachable with this token.

    Returns {"account_id", "page_id", "username", "page_name"}.
    When page_id is given, uses that Page; otherwise scans the user's Pages and
    picks the first one with a linked Instagram account.
    """
    async with httpx.AsyncClient(timeout=settings.ai_request_timeout) as client:
        candidates: list[dict] = []
        if page_id:
            page = await _get(
                client,
                page_id,
                {"fields": "name,instagram_business_account", "access_token": access_token},
            )
            candidates = [page]
        else:
            data = await _get(
                client,
                "me/accounts",
                {"fields": "name,instagram_business_account", "access_token": access_token},
            )
            candidates = data.get("data", [])

        for page in candidates:
            iga = page.get("instagram_business_account")
            if iga and iga.get("id"):
                ig_id = iga["id"]
                profile = await _get(
                    client,
                    ig_id,
                    {"fields": "username", "access_token": access_token},
                )
                return {
                    "account_id": ig_id,
                    "page_id": page.get("id"),
                    "username": profile.get("username"),
                    "page_name": page.get("name"),
                }

    raise GraphAPIError(
        "No Instagram Business account found for this token. Make sure your "
        "Instagram account is a Business/Creator account linked to a Facebook "
        "Page, and that the token has instagram_basic + instagram_content_publish "
        "+ pages_show_list permissions."
    )


# --------------------------------------------------------------------------
# Publishing (Content Publishing API)
# --------------------------------------------------------------------------
async def publish_image(
    *, ig_account_id: str, access_token: str, image_url: str, caption: str
) -> str:
    """Publish a single image post. Returns the published media id.

    Two-step per Meta's API: create a media container, then publish it. The
    image must be at a publicly reachable URL — Instagram fetches it server-side.
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

        published = await _post(
            client,
            f"{ig_account_id}/media_publish",
            {"creation_id": creation_id, "access_token": access_token},
        )
        media_id = published.get("id")
        if not media_id:
            raise GraphAPIError("Graph API did not return a published media id.")
        return media_id


def oauth_login_url(state: str) -> str:
    """Build the Facebook Login dialog URL for the OAuth redirect flow."""
    from urllib.parse import urlencode

    scopes = [
        "instagram_basic",
        "instagram_content_publish",
        "pages_show_list",
        "pages_read_engagement",
    ]
    params = {
        "client_id": settings.meta_app_id or "",
        "redirect_uri": settings.meta_oauth_redirect_uri,
        "scope": ",".join(scopes),
        "response_type": "code",
        "state": state,
    }
    return f"https://www.facebook.com/{settings.meta_graph_version}/dialog/oauth?{urlencode(params)}"


async def exchange_code_for_token(code: str) -> str:
    """Exchange an OAuth `code` (from the redirect) for a user access token."""
    if not (settings.meta_app_id and settings.meta_app_secret):
        raise GraphAPIError("META_APP_ID / META_APP_SECRET must be set for OAuth login.")
    async with httpx.AsyncClient(timeout=settings.ai_request_timeout) as client:
        data = await _get(
            client,
            "oauth/access_token",
            {
                "client_id": settings.meta_app_id,
                "client_secret": settings.meta_app_secret,
                "redirect_uri": settings.meta_oauth_redirect_uri,
                "code": code,
            },
        )
    return data["access_token"]
