"""Shared FastAPI dependencies for authentication."""
from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.database import get_db
from app.models.user import User

# tokenUrl is the login endpoint; powers Swagger UI's "Authorize" button.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
# Same, but returns None instead of 401 when no token is present — for endpoints
# that work anonymously but personalize when a user is signed in.
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

_credentials_exc = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = decode_token(token)
        subject = payload.get("sub")
        if subject is None:
            raise _credentials_exc
        user_id = int(subject)
    except (jwt.PyJWTError, ValueError, TypeError):
        raise _credentials_exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _credentials_exc
    return user


def get_current_user_optional(
    token: str | None = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db),
) -> User | None:
    """Return the signed-in user, or None if there's no/invalid token.

    Never raises — used by endpoints that are usable anonymously but personalize
    (e.g. inject the business profile) when a user is authenticated.
    """
    if not token:
        return None
    try:
        payload = decode_token(token)
        subject = payload.get("sub")
        user_id = int(subject) if subject is not None else None
    except (jwt.PyJWTError, ValueError, TypeError):
        return None
    if user_id is None:
        return None
    user = db.get(User, user_id)
    return user if user and user.is_active else None
