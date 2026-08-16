"""Public OAuth redirect endpoints.

Every provider redirects the browser back to a stable, documented URL:

    GET /api/auth/{platform}/callback

where {platform} is the public slug: facebook, instagram, linkedin, x,
pinterest, threads. Register these exact URLs in each developer portal — they
never change (see docs/OAUTH_CALLBACKS.md).

Meta additionally requires two callbacks of its own before an app's settings
will save, and calls them itself rather than through a browser:

    GET|POST /api/auth/threads/uninstall  — the user removed the app
    GET|POST /api/auth/threads/delete     — the user asked for their data back
    GET|POST /api/auth/meta/deauthorize   — same handler, Facebook/Instagram name
    GET|POST /api/auth/meta/delete        — same handler, Facebook/Instagram name

They cover Facebook, Instagram and Threads alike: Meta identifies the person by
one app-scoped user id, and the handler verifies the signature against every
configured app secret, so either app's callback can point at either URL. All are
public, verify Meta's `signed_request`, answer JSON (never a redirect) and always
return 200.

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
from sqlalchemy import and_, or_, select
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
# The platforms a Meta signed_request can be about. Facebook and Instagram are
# authorized through one Meta app and Threads through the Threads API, but Meta
# gives an app a single deletion callback and identifies the person by one
# app-scoped user id — so a request has to be matched against all three.
_META_PLATFORMS = (Platform.threads, Platform.facebook, Platform.instagram)


def _meta_app_secrets() -> list[str | None]:
    """Every app secret a Meta callback could legitimately be signed with."""
    return [
        get_provider(Platform.threads).client_secret,
        settings.meta_app_secret,
    ]


def _forget_meta_accounts(db: Session, signed_request: str | None) -> int:
    """Delete every Meta connection the request names. Returns how many went.

    This is the whole of the user's data for those platforms: each row holds the
    access token and the account handle, and posts already published belong to
    the user's own profile, not to us.

    Rows are matched on `platform_user_id` — the id Meta itself names — which for
    Instagram is the Facebook user id rather than the Instagram Business account
    id in `account_id`.

    `account_id` is checked too, but *only* for rows that have no
    `platform_user_id`, i.e. connections made before that column existed. The
    narrowing matters: app-scoped user ids are issued per app, so the same
    numeric id can belong to two different people across the Threads app and the
    Facebook/Instagram app. Matching `account_id` unconditionally would let a
    deletion request for one of them delete the other's connection.
    """
    payload = meta_callbacks.parse_signed_request_any(
        signed_request, _meta_app_secrets()
    )
    meta_user_id = meta_callbacks.user_id_of(payload)
    if not meta_user_id:
        return 0

    accounts = list(
        db.scalars(
            select(SocialAccount).where(
                SocialAccount.platform.in_([p.value for p in _META_PLATFORMS]),
                or_(
                    SocialAccount.platform_user_id == meta_user_id,
                    and_(
                        SocialAccount.platform_user_id.is_(None),
                        SocialAccount.account_id == meta_user_id,
                    ),
                ),
            )
        ).all()
    )
    if not accounts:
        return 0

    platforms = sorted({account.platform for account in accounts})
    for account in accounts:
        db.delete(account)
    db.commit()
    # Meta's own identifier for the request and which platforms were cleared —
    # never the access token, the signed_request, or the account handle.
    logger.info(
        "Meta callback: removed %d connection(s) (%s) for meta user %s",
        len(accounts), ", ".join(platforms), meta_user_id,
    )
    return len(accounts)


# Both paths run the same handler. `/threads/...` is the URL already registered
# in the Threads app's dashboard and must keep working; `/meta/...` is the same
# endpoint under a name that reads correctly in the Facebook/Instagram app's
# settings. Registering one function at two paths keeps that a naming choice
# rather than a second implementation to keep in step.
_UNINSTALL_PATHS = ("/threads/uninstall", "/meta/deauthorize")
_DELETE_PATHS = ("/threads/delete", "/meta/delete")
_STATUS_PATH = "/threads/delete/status"


async def meta_uninstall(
    request: Request, db: Session = Depends(get_db)
) -> JSONResponse:
    """Meta calls this when a user removes the app from their account.

    The connection is deleted, so the app stops holding a token the user has
    revoked, and the Accounts page shows the platform as disconnected.
    """
    signed_request = await _signed_request_of(request)
    try:
        _forget_meta_accounts(db, signed_request)
    except Exception:  # noqa: BLE001 — Meta must still get its 200
        logger.exception("Meta deauthorize callback failed")
    return JSONResponse({"success": True})


async def meta_delete(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    """Meta's data-deletion request callback.

    Must answer with a status URL and a confirmation code, per Meta's spec. The
    deletion is synchronous and complete — there are only the connection rows to
    remove — so the status page can report it done rather than promising a later
    job.

    Note this deletes the *social connections*, which is all Meta's request is
    about. Deleting the whole AutoSocial account is a separate, user-initiated
    action (DELETE /auth/me), because a Meta user id does not authorize erasing
    data belonging to other platforms.
    """
    signed_request = await _signed_request_of(request)
    try:
        _forget_meta_accounts(db, signed_request)
    except Exception:  # noqa: BLE001 — Meta must still get its 200
        logger.exception("Meta delete callback failed")

    confirmation_code = secrets.token_hex(8)
    return JSONResponse(
        {
            "url": f"{settings.backend_url}/api/auth{_STATUS_PATH}"
            f"?code={confirmation_code}",
            "confirmation_code": confirmation_code,
        }
    )


@router.get(_STATUS_PATH)
def meta_delete_status(code: str = Query(default="")) -> JSONResponse:
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
                "Any Facebook, Instagram or Threads connection for this account "
                "has been deleted from AutoSocial AI, including its stored "
                "access token."
            ),
        }
    )


# GET and POST are registered separately, each with its own operation_id.
# A single api_route carrying both methods emits one id for two OpenAPI
# operations, which makes the schema ambiguous and warns on every startup.
def _register_alias(path: str, handler) -> None:
    slug = path.strip("/").replace("/", "_")
    for method in ("GET", "POST"):
        router.api_route(
            path,
            methods=[method],
            operation_id=f"{handler.__name__}_{slug}_{method.lower()}",
        )(handler)


for _path in _UNINSTALL_PATHS:
    _register_alias(_path, meta_uninstall)
for _path in _DELETE_PATHS:
    _register_alias(_path, meta_delete)


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
