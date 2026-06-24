"""Connected social account endpoints (user-scoped).

Two ways to connect Instagram:
  * POST /api/accounts/instagram/connect  — paste a token (+ optional Page id).
    Best for local dev; works with a long-lived token even without app secrets.
  * GET  /api/accounts/instagram/oauth-url -> redirect to Facebook login, which
    returns to /callback. Needs META_APP_ID/SECRET + a registered redirect URI.

Access tokens are write-only over the API — SocialAccountRead never exposes them.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user
from app.core.security import create_access_token, decode_token
from app.core.timeutils import utcnow
from app.database import get_db
from app.models.social_account import SocialAccount
from app.models.user import User
from app.schemas.post import Platform
from app.schemas.social_account import InstagramConnectRequest, SocialAccountRead
from app.services.social import meta_graph

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _expiry_from_seconds(seconds: int | None):
    if not seconds:
        return None
    from datetime import timedelta

    return utcnow() + timedelta(seconds=seconds)


def _upsert_instagram(
    db: Session, user: User, *, token: str, expires_at, resolved: dict
) -> SocialAccount:
    account = db.scalars(
        select(SocialAccount).where(
            SocialAccount.user_id == user.id,
            SocialAccount.platform == Platform.instagram.value,
        )
    ).first()

    if account is None:
        account = SocialAccount(user_id=user.id, platform=Platform.instagram.value)
        db.add(account)

    account.access_token = token
    account.token_expires_at = expires_at
    account.account_id = resolved["account_id"]
    account.page_id = resolved.get("page_id")
    account.username = resolved.get("username")
    db.commit()
    db.refresh(account)
    return account


@router.get("", response_model=list[SocialAccountRead])
def list_accounts(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SocialAccount]:
    return list(
        db.scalars(
            select(SocialAccount).where(SocialAccount.user_id == user.id)
        ).all()
    )


@router.post("/instagram/connect", response_model=SocialAccountRead)
async def connect_instagram(
    data: InstagramConnectRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SocialAccount:
    """Connect an Instagram account from a pasted access token."""
    try:
        long_token, expires_in = await meta_graph.exchange_for_long_lived_token(
            data.access_token
        )
        resolved = await meta_graph.resolve_instagram_account(long_token, data.page_id)
    except meta_graph.GraphAPIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _upsert_instagram(
        db, user,
        token=long_token,
        expires_at=_expiry_from_seconds(expires_in),
        resolved=resolved,
    )


@router.get("/instagram/oauth-url")
def instagram_oauth_url(user: User = Depends(get_current_user)) -> dict:
    """Return the Facebook login URL to start the OAuth connect flow.

    `state` carries a short-lived token identifying the user, so the public
    /callback (which has no auth header) can tie the result back to them.
    """
    if not settings.meta_app_id:
        raise HTTPException(
            status_code=503,
            detail="OAuth login needs META_APP_ID/SECRET. Use the token connect flow instead.",
        )
    state = create_access_token(str(user.id))
    return {"url": meta_graph.oauth_login_url(state)}


@router.get("/instagram/callback")
async def instagram_callback(
    state: str = Query(...),
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """OAuth redirect target. Exchanges the code, stores the account, bounces
    the browser back to the frontend Accounts page with a status flag."""
    redirect_ok = f"{settings.frontend_url}/accounts?connected=instagram"
    redirect_err = f"{settings.frontend_url}/accounts?error="

    if error or not code:
        return RedirectResponse(redirect_err + (error or "missing_code"))

    try:
        user_id = int(decode_token(state).get("sub"))
    except Exception:
        return RedirectResponse(redirect_err + "bad_state")

    user = db.get(User, user_id)
    if user is None:
        return RedirectResponse(redirect_err + "unknown_user")

    try:
        token = await meta_graph.exchange_code_for_token(code)
        long_token, expires_in = await meta_graph.exchange_for_long_lived_token(token)
        resolved = await meta_graph.resolve_instagram_account(long_token)
    except meta_graph.GraphAPIError as exc:
        logger.warning("Instagram OAuth connect failed: %s", exc)
        return RedirectResponse(redirect_err + "graph_error")

    _upsert_instagram(
        db, user,
        token=long_token,
        expires_at=_expiry_from_seconds(expires_in),
        resolved=resolved,
    )
    return RedirectResponse(redirect_ok)


@router.delete("/{platform}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect(
    platform: Platform,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    account = db.scalars(
        select(SocialAccount).where(
            SocialAccount.user_id == user.id,
            SocialAccount.platform == platform.value,
        )
    ).first()
    if account is None:
        raise HTTPException(status_code=404, detail="Account not connected")
    db.delete(account)
    db.commit()
    from fastapi import Response

    return Response(status_code=status.HTTP_204_NO_CONTENT)
