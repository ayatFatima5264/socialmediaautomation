"""Public OAuth redirect endpoints.

Every provider redirects the browser back to a stable, documented URL:

    GET /api/auth/{platform}/callback

where {platform} is the public slug: facebook, instagram, linkedin, x,
pinterest, threads. Register these exact URLs in each developer portal — they
never change (see docs/OAUTH_CALLBACKS.md).

The callback has no auth header (it's a top-level browser redirect); the user
is identified by the signed `state` minted when the connect flow started. On
success or failure the browser is bounced back to the frontend Accounts page
with a status flag, so the SPA can show a toast.
"""
from __future__ import annotations

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.services.social_accounts import service
from app.services.social_accounts.base import OAuthError
from app.services.social_accounts.service import ConnectError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["oauth"])


def _redirect(**params: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.frontend_url}/accounts?{urlencode(params)}")


@router.get("/{platform}/callback")
async def oauth_callback(
    platform: str,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    # The user denied consent, or the provider returned an error.
    if error:
        logger.info("OAuth %s error: %s", platform, error_description or error)
        return _redirect(error=error, platform=platform)

    if not code or not state:
        return _redirect(error="missing_code", platform=platform)

    try:
        result = await service.complete_callback(db, platform, code, state)
    except (OAuthError, ConnectError) as exc:
        logger.warning("OAuth %s callback failed: %s", platform, exc)
        message = getattr(exc, "message", str(exc))
        return _redirect(error=message, platform=platform)
    except Exception:  # noqa: BLE001 — never leak internals to the browser
        logger.exception("Unexpected error in OAuth %s callback", platform)
        return _redirect(error="unexpected_error", platform=platform)

    # Several accounts to choose from — send the user to the picker.
    if result.status == "select":
        return _redirect(select=result.platform.value, pending=result.pending_id)
    return _redirect(connected=result.platform.value)
