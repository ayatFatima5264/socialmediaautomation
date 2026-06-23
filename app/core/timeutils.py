"""Datetime helpers.

We store all timestamps as naive UTC so scheduling comparisons behave
identically on SQLite (no tz support) and PostgreSQL.
"""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current time as a naive UTC datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_naive_utc(dt: datetime) -> datetime:
    """Normalize any datetime to naive UTC.

    Aware datetimes are converted to UTC; naive datetimes are assumed to
    already be UTC.
    """
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt
