"""Public OAuth redirect endpoints.

Every provider redirects the browser back to a stable, documented URL:

    GET /api/auth/{platform}/callback

where {platform} is the public slug: facebook, instagram, linkedin, x,
pinterest, threads. Register these exact URLs in each developer portal — they
never change (see docs/OAUTH_CALLBACKS.md).

Meta additionally requires two callbacks of its own before the Threads API
settings will save, and calls them itself rather than through a browser:

    GET|POST /api/auth/threads/uninstall  — the user removed the app
    GET|POST /api/auth/threads/delete     — the user asked for their data back

Both are public, verify Meta's `signed_request`, answer JSON (never a redirect)
and always return 200.

The callback has no auth header (it's a top-level browser redirect); the user
is identified by the signed `state` minted when the connect flow started. On
success or failure the browser is bounced back to the frontend Accounts page
with a status flag, so the SPA can show a toast.
"""
from __future__ import annotations

import logging
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.social_account import SocialAccount
from app.schemas.post import Platform
from app.services.social_accounts import meta_callbacks, service
from app.services.social_accounts.base import OAuthError
from app.services.social_accounts.registry import get_provider
from app.services.social_accounts.service import ConnectError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["oauth"])


def _redirect(**params: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.frontend_url}/accounts?{urlencode(params)}")


# ---------------------------------------------------------------------------
# Meta deauthorize / data-deletion callbacks (Threads)
#
# Meta requires both URLs before its Threads API settings can be saved, and
# calls them itself — with no session, only a `signed_request` proving the call
# came from Meta. So they are public, answer JSON directly (never a redirect,
# which Meta's validator will not follow), and always return 200:
#
#   * a bare GET is Meta checking the URL is alive while you save the settings;
#   * an unverifiable POST is answered exactly like a verified one, so the
#     endpoint can't be used to probe which accounts exist.
#
# Declared before /{platform}/callback purely for readability — the literal
# paths differ in their last segment, so they cannot collide.
# ---------------------------------------------------------------------------
def _forget_threads_account(db: Session, signed_request: str | None) -> bool:
    """Delete the Threads connection the request names. True if one went.

    This is the whole of the user's data for Threads: the row holds the token
    and the account handle, and posts already published are theirs, not ours.
    """
    payload = meta_callbacks.parse_signed_request(
        signed_request, get_provider(Platform.threads).client_secret
    )
    threads_user_id = meta_callbacks.user_id_of(payload)
    if not threads_user_id:
        return False

    accounts = list(
        db.scalars(
            select(SocialAccount).where(
                SocialAccount.platform == Platform.threads.value,
                SocialAccount.account_id == threads_user_id,
            )
        ).all()
    )
    for account in accounts:
        db.delete(account)
    if accounts:
        db.commit()
        # The Threads user id is Meta's own identifier for the request, not a
        # credential — the token is never logged.
        logger.info(
            "Threads callback: removed %d connection(s) for threads user %s",
            len(accounts), threads_user_id,
        )
    return bool(accounts)


@router.api_route("/threads/uninstall", methods=["GET", "POST"])
async def threads_uninstall(
    request: Request, db: Session = Depends(get_db)
) -> JSONResponse:
    """Meta calls this when a user removes the app from their Threads account.

    The connection is deleted, so the app stops holding a token the user has
    revoked, and the Accounts page shows Threads as disconnected.
    """
    signed_request = await _signed_request_of(request)
    try:
        _forget_threads_account(db, signed_request)
    except Exception:  # noqa: BLE001 — Meta must still get its 200
        logger.exception("Threads uninstall callback failed")
    return JSONResponse({"success": True})


@router.api_route("/threads/delete", methods=["GET", "POST"])
async def threads_delete(
    request: Request, db: Session = Depends(get_db)
) -> JSONResponse:
    """Meta's data-deletion request callback.

    Must answer with a status URL and a confirmation code, per Meta's spec. The
    deletion is synchronous and complete — there is one row to remove — so the
    status page can report it done rather than promising a later job.
    """
    signed_request = await _signed_request_of(request)
    try:
        _forget_threads_account(db, signed_request)
    except Exception:  # noqa: BLE001 — Meta must still get its 200
        logger.exception("Threads delete callback failed")

    confirmation_code = secrets.token_hex(8)
    return JSONResponse(
        {
            "url": f"{settings.backend_url}/api/auth/threads/delete/status"
            f"?code={confirmation_code}",
            "confirmation_code": confirmation_code,
        }
    )


@router.get("/threads/delete/status")
def threads_delete_status(code: str = Query(default="")) -> JSONResponse:
    """Human-checkable status for a data-deletion request.

    Deletion happens inline in the callback above, so any request that reached
    us is already finished. The code is echoed back for the user's records; it
    is deliberately not a lookup key, because storing one would mean keeping a
    record of the very person who asked to be forgotten.
    """
    return JSONResponse(
        {
            "confirmation_code": code,
            "status": "completed",
            "detail": (
                "Any Threads connection for this account has been deleted from "
                "AutoSocial AI, including its stored access token."
            ),
        }
    )


async def _signed_request_of(request: Request) -> str | None:
    """Meta posts `signed_request` as a form field; accept it on the query
    string too, since its dashboard validator pings the URL with a bare GET."""
    if request.method == "POST":
        try:
            form = await request.form()
        except Exception:  # noqa: BLE001 — a bodyless/odd POST is still a 200
            return None
        value = form.get("signed_request")
        if isinstance(value, str):
            return value
    return request.query_params.get("signed_request")


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
