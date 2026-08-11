"""Social Accounts management API (user-scoped).

    GET    /api/social/accounts          — overview: accounts + summary
    GET    /api/social/{platform}         — one connected account (404 if none)
    POST   /api/social/{platform}/connect — begin connect (OAuth redirect / dev)
    DELETE /api/social/{platform}         — disconnect and remove credentials
    POST   /api/social/{platform}/refresh — refresh tokens / re-sync

    GET    /api/social/pinterest/boards        — the user's Pinterest boards
    PUT    /api/social/pinterest/default-board — board Pins default to
    DELETE /api/social/pinterest/default-board — clear that default

Access/refresh tokens are write-only over the API — SocialAccountRead never
exposes them. Mutating endpoints answer with a uniform {success, message}
envelope. The OAuth redirect leg lives in routes/oauth.py.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.post import Platform
from app.schemas.social_account import (
    AccountsOverview,
    ApiResponse,
    PendingConnectionRead,
    PinterestBoard,
    PinterestBoardsResponse,
    SelectAccountRequest,
    SetDefaultBoardRequest,
    SocialAccountRead,
)
from app.services.social_accounts import pinterest_boards, service
from app.services.social_accounts.service import ConnectError

router = APIRouter(prefix="/api/social", tags=["social-accounts"])


def _handle(exc: ConnectError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/accounts", response_model=AccountsOverview)
def overview(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AccountsOverview:
    return service.build_overview(db, user)


# Multi-account selection (e.g. choosing one of several Instagram Business
# accounts). Declared before /{platform} so the literal path wins.
@router.get("/connections/pending/{pending_id}", response_model=PendingConnectionRead)
def pending_candidates(
    pending_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PendingConnectionRead:
    try:
        return service.get_pending(db, user, pending_id)
    except ConnectError as exc:
        raise _handle(exc) from exc


@router.post("/connections/select", response_model=ApiResponse)
def select_pending(
    data: SelectAccountRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApiResponse:
    try:
        account = service.select_account(db, user, data.pending_id, data.account_id)
    except ConnectError as exc:
        raise _handle(exc) from exc
    return ApiResponse(
        success=True,
        message=f"{account.platform.capitalize()} connected.",
        account=service.serialize(account),
    )


# Pinterest boards. Declared before /{platform} for clarity — a Pin must name a
# board, so the composer and the account card both read this list.
@router.get("/pinterest/boards", response_model=PinterestBoardsResponse)
async def pinterest_board_list(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PinterestBoardsResponse:
    """The signed-in user's Pinterest boards, fetched live from Pinterest.

    Called again whenever the UI's "refresh boards" action runs, so a board
    created seconds ago appears without reconnecting.
    """
    try:
        boards = await pinterest_boards.list_boards(db, user)
    except ConnectError as exc:
        raise _handle(exc) from exc
    account = service.get_account(db, user, Platform.pinterest)
    return PinterestBoardsResponse(
        boards=[PinterestBoard(**b) for b in boards],
        default_board_id=account.page_id if account else None,
    )


@router.put("/pinterest/default-board", response_model=ApiResponse)
async def pinterest_set_default_board(
    data: SetDefaultBoardRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApiResponse:
    """Set the board Pins go to when a post doesn't name one."""
    try:
        account = await pinterest_boards.set_default_board(db, user, data.board_id)
    except ConnectError as exc:
        raise _handle(exc) from exc
    return ApiResponse(
        success=True,
        message="Default Pinterest board saved.",
        account=service.serialize(account),
    )


@router.delete("/pinterest/default-board", response_model=ApiResponse)
def pinterest_clear_default_board(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApiResponse:
    try:
        account = pinterest_boards.clear_default_board(db, user)
    except ConnectError as exc:
        raise _handle(exc) from exc
    return ApiResponse(
        success=True,
        message="Default Pinterest board cleared.",
        account=service.serialize(account),
    )


@router.get("/{platform}", response_model=SocialAccountRead)
def get_one(
    platform: Platform,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SocialAccountRead:
    account = service.get_account(db, user, platform)
    if account is None:
        raise HTTPException(
            status_code=404,
            detail=f"{platform.value.capitalize()} is not connected.",
        )
    return service.serialize(account)


@router.post("/{platform}/connect", response_model=ApiResponse)
def connect(
    platform: Platform,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApiResponse:
    """Begin connecting a platform.

    Returns an `authorize_url` for the client to redirect to (real OAuth), or a
    completed `account` when a dev simulated connect ran inline.
    """
    try:
        result = service.start_connect(db, user, platform)
    except ConnectError as exc:
        raise _handle(exc) from exc

    if "authorize_url" in result:
        return ApiResponse(
            success=True,
            message=f"Redirecting to {platform.value.capitalize()} to authorize…",
            authorize_url=result["authorize_url"],
        )
    return ApiResponse(
        success=True,
        message=f"{platform.value.capitalize()} connected.",
        account=result["account"],
    )


@router.delete("/{platform}", response_model=ApiResponse)
def disconnect(
    platform: Platform,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApiResponse:
    try:
        service.disconnect(db, user, platform)
    except ConnectError as exc:
        raise _handle(exc) from exc
    return ApiResponse(
        success=True, message=f"{platform.value.capitalize()} disconnected."
    )


@router.post("/{platform}/refresh", response_model=ApiResponse)
async def refresh(
    platform: Platform,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApiResponse:
    try:
        account = await service.refresh_account(db, user, platform)
    except ConnectError as exc:
        raise _handle(exc) from exc
    return ApiResponse(
        success=True,
        message=f"{platform.value.capitalize()} refreshed.",
        account=service.serialize(account),
    )
