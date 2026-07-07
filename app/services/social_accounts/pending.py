"""Pending multi-account connections — persistence + (de)serialization.

Backs the "choose which account to connect" step. A pending row holds the fresh
OAuth token and the candidate list; it expires so tokens don't linger.
"""
from __future__ import annotations

import json
import secrets
from dataclasses import asdict
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutils import utcnow
from app.models.pending_connection import PendingConnection
from app.schemas.post import Platform
from app.services.social_accounts.base import OAuthTokens, ProfileInfo

# How long a pending selection stays valid.
PENDING_TTL = timedelta(minutes=15)


def create(
    db: Session,
    *,
    user_id: int,
    platform: Platform,
    tokens: OAuthTokens,
    candidates: list[ProfileInfo],
) -> PendingConnection:
    _purge_expired(db)
    expires_at = (
        utcnow() + timedelta(seconds=tokens.expires_in) if tokens.expires_in else None
    )
    row = PendingConnection(
        id=secrets.token_urlsafe(24),
        user_id=user_id,
        platform=platform.value,
        access_token=tokens.access_token,
        token_expires_at=expires_at,
        candidates=json.dumps([asdict(c) for c in candidates]),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get(db: Session, pending_id: str, user_id: int) -> PendingConnection | None:
    row = db.get(PendingConnection, pending_id)
    if row is None or row.user_id != user_id:
        return None
    if _is_expired(row):
        db.delete(row)
        db.commit()
        return None
    return row


def candidates_of(row: PendingConnection) -> list[ProfileInfo]:
    return [ProfileInfo(**c) for c in json.loads(row.candidates)]


def tokens_of(row: PendingConnection) -> OAuthTokens:
    expires_in = None
    if row.token_expires_at is not None:
        expires_in = max(0, int((row.token_expires_at - utcnow()).total_seconds()))
    return OAuthTokens(access_token=row.access_token, expires_in=expires_in)


def delete(db: Session, row: PendingConnection) -> None:
    db.delete(row)
    db.commit()


def _is_expired(row: PendingConnection) -> bool:
    created = row.created_at
    if created.tzinfo is not None:
        created = created.replace(tzinfo=None)
    return utcnow() - created > PENDING_TTL


def _purge_expired(db: Session) -> None:
    cutoff = utcnow() - PENDING_TTL
    rows = db.scalars(
        select(PendingConnection).where(PendingConnection.created_at < cutoff)
    ).all()
    for row in rows:
        db.delete(row)
    if rows:
        db.commit()
