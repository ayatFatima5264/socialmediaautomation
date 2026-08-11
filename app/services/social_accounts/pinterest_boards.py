"""Pinterest board orchestration for the Accounts / composer UI.

Every Pin must be saved to a board, so the UI needs the user's board list before
it can offer a choice. This module owns that flow: resolve the caller's own
connected Pinterest account, keep its 30-day access token fresh, call the API v5
boards endpoints, and translate failures into the same ConnectError the rest of
the Social Accounts module raises.

Ownership is enforced by construction — the account is always looked up as
(this user, pinterest), so one user's connection can never be read or used by
another. Tokens never leave this layer.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.timeutils import utcnow
from app.models.social_account import SocialAccount
from app.models.user import User
from app.repositories import SocialAccountRepository
from app.schemas.post import Platform
from app.schemas.social_account import AccountStatus
from app.services.social import pinterest_api
from app.services.social_accounts.base import OAuthError
from app.services.social_accounts.service import (
    ConnectError,
    refresh_tokens,
    token_needs_refresh,
)

logger = logging.getLogger(__name__)


async def list_boards(db: Session, user: User) -> list[dict]:
    """The user's Pinterest boards: [{id, name, privacy}, ...].

    Always fetched live from Pinterest, so the "refresh boards" action in the UI
    is simply calling this again — a board created moments ago shows up.
    """
    account = _require_account(db, user)
    await _ensure_fresh_token(db, account)
    try:
        return await pinterest_api.list_boards(account.access_token)
    except pinterest_api.PinterestAPIError as exc:
        _flag_if_auth_error(db, account, exc)
        raise ConnectError(_user_message(exc), _status_for(exc)) from exc


async def set_default_board(db: Session, user: User, board_id: str) -> SocialAccount:
    """Remember which board Pins go to when a post doesn't name one.

    The board is verified against Pinterest first, so a stale or foreign id can
    never be stored. Stored on `page_id` — the model's per-platform identifier
    slot, which for Pinterest means "default board".
    """
    account = _require_account(db, user)
    board_id = (board_id or "").strip()
    if not board_id:
        raise ConnectError("Choose a board.", 400)

    await _ensure_fresh_token(db, account)
    try:
        board = await pinterest_api.get_board(account.access_token, board_id)
    except pinterest_api.PinterestAPIError as exc:
        if exc.is_not_found:
            raise ConnectError(
                "That Pinterest board no longer exists. Refresh the board list "
                "and pick another.",
                404,
            ) from exc
        _flag_if_auth_error(db, account, exc)
        raise ConnectError(_user_message(exc), _status_for(exc)) from exc

    account.page_id = board["id"]
    account.last_synced_at = utcnow()
    return SocialAccountRepository(db).save(account)


def clear_default_board(db: Session, user: User) -> SocialAccount:
    """Forget the default board (posts must then name one)."""
    account = _require_account(db, user)
    account.page_id = None
    return SocialAccountRepository(db).save(account)


# --------------------------------------------------------------------------
# Internals
# --------------------------------------------------------------------------
def _require_account(db: Session, user: User) -> SocialAccount:
    account = SocialAccountRepository(db).get(user.id, Platform.pinterest)
    if account is None:
        raise ConnectError("Pinterest is not connected.", 404)
    return account


async def _ensure_fresh_token(db: Session, account: SocialAccount) -> None:
    """Refresh the access token when it is expired or about to expire."""
    if not token_needs_refresh(account):
        return
    try:
        await refresh_tokens(db, account)
    except OAuthError as exc:
        account.status = AccountStatus.error.value
        SocialAccountRepository(db).save(account)
        logger.warning("Pinterest token refresh failed for user %s", account.user_id)
        # 409, not 401 — see _status_for: a 401 would log the user out of the app.
        raise ConnectError(
            "Your Pinterest authorization has expired. Reconnect Pinterest to "
            "continue.",
            409,
        ) from exc


def _flag_if_auth_error(
    db: Session, account: SocialAccount, exc: pinterest_api.PinterestAPIError
) -> None:
    """Mark the account as needing attention when Pinterest rejects the token,
    so the Accounts page shows "Reconnect" instead of silently failing."""
    if exc.status_code == 401:
        account.status = AccountStatus.error.value
        SocialAccountRepository(db).save(account)


def _status_for(exc: pinterest_api.PinterestAPIError) -> int:
    """Map a Pinterest failure to the status THIS API returns.

    Never 401: that status means "your AutoSocial session is invalid", and the
    frontend clears the login token when it sees one. Pinterest rejecting its
    own token is an upstream problem with one connected account — it must not
    sign the user out of the app. Those cases become 409 ("reconnect Pinterest"),
    which the UI shows as an inline message.
    """
    if exc.status_code in (401, 403):
        return 409
    if exc.status_code == 429:
        return 429
    if exc.is_not_found:
        return 404
    return 502


def _user_message(exc: pinterest_api.PinterestAPIError) -> str:
    """A safe, actionable message — never a raw payload or a token."""
    if exc.is_rate_limited:
        wait = f" Try again in ~{exc.retry_after}s." if exc.retry_after else ""
        return f"Pinterest rate limit reached.{wait}"
    if exc.status_code == 401:
        return (
            "Pinterest rejected the access token (expired or revoked). "
            "Reconnect your Pinterest account."
        )
    if exc.status_code == 403:
        return (
            "Pinterest refused the request — the connection is missing board "
            "access. Reconnect your Pinterest account to grant it."
        )
    if exc.is_server_error:
        return "Pinterest is having trouble right now. Try again shortly."
    return f"Could not load Pinterest boards: {exc.message}"
