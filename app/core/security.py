"""Password hashing (bcrypt) and JWT access tokens."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings

# bcrypt only considers the first 72 bytes of the password; we truncate
# consistently in both hash and verify so longer inputs behave predictably.
_BCRYPT_MAX_BYTES = 72


def _prepare(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(password), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str | int, expires_minutes: int | None = None) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )
    payload = {"sub": str(subject), "iat": now, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Decode/validate a JWT. Raises jwt.PyJWTError on any problem."""
    return jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )


# ---- Password-reset tokens -------------------------------------------------
# Short-lived, single-purpose JWTs. The `type: "reset"` claim keeps them
# distinct from access tokens: a reset token can't be used as a bearer token
# (see core.deps) and an access token can't be used to reset a password.
_RESET_TOKEN_TYPE = "reset"


def create_reset_token(user_id: str | int, expires_minutes: int | None = None) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(
        minutes=expires_minutes or settings.password_reset_expire_minutes
    )
    payload = {
        "sub": str(user_id),
        "type": _RESET_TOKEN_TYPE,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_reset_token(token: str) -> dict:
    """Decode a reset token. Raises jwt.PyJWTError if invalid/expired or not a
    reset token."""
    payload = decode_token(token)
    if payload.get("type") != _RESET_TOKEN_TYPE:
        raise jwt.InvalidTokenError("Not a password-reset token")
    return payload
