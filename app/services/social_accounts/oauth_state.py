"""Signed, stateless OAuth `state` tokens.

The `state` round-tripped through the provider must (a) identify the user who
started the flow — the public callback has no auth header — and (b) carry the
PKCE code_verifier so the token exchange is stateless (no server-side session).

We reuse the app's JWT secret to sign a short-lived token, so a tampered or
expired `state` is rejected. CSRF protection comes for free: an attacker can't
forge a valid state for another user without the secret.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings

# OAuth round-trips are quick; keep the window tight to limit replay.
_STATE_TTL_MINUTES = 15


def encode_state(*, user_id: int, slug: str, code_verifier: str | None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "slug": slug,
        "cv": code_verifier,
        "iat": now,
        "exp": now + timedelta(minutes=_STATE_TTL_MINUTES),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_state(state: str) -> dict:
    """Return {user_id, slug, code_verifier}. Raises jwt.PyJWTError if invalid."""
    data = jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    return {
        "user_id": int(data["sub"]),
        "slug": data.get("slug"),
        "code_verifier": data.get("cv"),
    }
