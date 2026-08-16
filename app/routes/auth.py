"""Authentication endpoints: register, login (JWT), current user, and the
email-based password reset flow."""
from __future__ import annotations

import logging

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user
from app.core.security import (
    create_access_token,
    create_reset_token,
    decode_reset_token,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.models.user import User
from app.schemas.user import (
    DELETE_CONFIRMATION,
    DeleteAccountRequest,
    ForgotPasswordRequest,
    MessageResponse,
    ResetPasswordRequest,
    Token,
    UserCreate,
    UserRead,
    UserUpdate,
)
from app.services import account_deletion, email_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: Session = Depends(get_db)) -> User:
    exists = db.scalar(select(User).where(User.email == data.email))
    if exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    user = User(
        email=data.email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    """OAuth2 password flow. `username` field is the user's email."""
    user = db.scalar(select(User).where(User.email == form.username))
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Inactive account"
        )
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserRead)
def read_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch("/me", response_model=UserRead)
def update_me(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Update the signed-in user's own profile.

    Only fields present in the request body are touched, so a client sending
    just `full_name` can't accidentally null out anything else.
    """
    fields = data.model_dump(exclude_unset=True)

    if "full_name" in fields:
        name = (fields["full_name"] or "").strip()
        # Treat an all-whitespace name as "cleared" rather than storing blanks.
        current_user.full_name = name or None

    db.commit()
    db.refresh(current_user)
    return current_user


@router.delete("/me", response_model=MessageResponse)
def delete_me(
    data: DeleteAccountRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Permanently delete the signed-in user's account and all of their data.

    Multi-tenancy: the account deleted is the one `get_current_user` resolved
    from the bearer token. The request body carries no user id and none is
    accepted, so there is no input a client could vary to reach another account.

    The typed confirmation is checked server-side as well as in the UI — a modal
    is a convenience, not a control, and this endpoint is reachable without one.
    """
    if data.confirmation.strip() != DELETE_CONFIRMATION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Type "{DELETE_CONFIRMATION}" to confirm deleting your account.',
        )

    account_deletion.delete_user_account(db, current_user)
    return MessageResponse(
        message=(
            "Your account and all of its data have been permanently deleted. "
            "Any connected social accounts have been disconnected and their "
            "access tokens erased."
        )
    )


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    data: ForgotPasswordRequest, db: Session = Depends(get_db)
) -> MessageResponse:
    """Email a password-reset link if the account exists.

    Always returns the same generic message so the endpoint can't be used to
    discover which emails are registered (no user enumeration).
    """
    user = db.scalar(select(User).where(User.email == data.email))
    if user and user.is_active:
        token = create_reset_token(user.id)
        reset_link = f"{settings.frontend_url.rstrip('/')}/reset-password?token={token}"
        email_service.send_password_reset(user.email, reset_link)
    else:
        logger.info("Password reset requested for unknown/inactive email: %s", data.email)
    return MessageResponse(
        message="If an account exists for that email, we've sent password reset instructions."
    )


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(
    data: ResetPasswordRequest, db: Session = Depends(get_db)
) -> MessageResponse:
    """Set a new password using a valid reset token."""
    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="This reset link is invalid or has expired. Please request a new one.",
    )
    try:
        payload = decode_reset_token(data.token)
    except jwt.PyJWTError as exc:
        raise invalid from exc

    subject = payload.get("sub")
    user = db.get(User, int(subject)) if subject is not None else None
    if user is None or not user.is_active:
        raise invalid

    user.hashed_password = hash_password(data.password)
    db.commit()
    logger.info("Password reset completed for user %s", user.id)
    return MessageResponse(
        message="Your password has been reset. You can now sign in with your new password."
    )
