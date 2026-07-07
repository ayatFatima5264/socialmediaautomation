"""Scheduling Service — decides *when* each planned post goes out.

v1 uses a static best-times heuristic (see constants.BEST_HOURS) combined with
the user's timezone. It is intentionally isolated so a later data-driven engine
(per-account, performance-based) can replace it without touching callers.

All returned datetimes are naive UTC, matching the rest of the app
(see app.core.timeutils).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.timeutils import utcnow
from app.schemas.post import Platform
from app.services.planner.constants import (
    BEST_HOURS,
    DEFAULT_HOURS,
    FREQUENCY_PER_WEEK,
)


def resolve_per_week(frequency: str, posts_per_week: int) -> int:
    """Posts per week for a frequency (custom uses the user's number)."""
    per = FREQUENCY_PER_WEEK.get(frequency, 7)
    if frequency == "custom" or per == 0:
        return max(1, min(posts_per_week, 7))
    return per


def _tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def plan_dates(
    *,
    duration_days: int,
    frequency: str,
    posts_per_week: int,
    tzname: str = "UTC",
) -> list[date]:
    """The local calendar dates to post on, starting tomorrow.

    Daily fills every day; other frequencies spread evenly across the window so
    posts aren't bunched together.
    """
    tz = _tz(tzname)
    today_local = datetime.now(tz).date()
    start = today_local + timedelta(days=1)

    per_week = resolve_per_week(frequency, posts_per_week)
    if per_week >= 7:
        return [start + timedelta(days=i) for i in range(duration_days)]

    count = max(1, round(duration_days / 7 * per_week))
    if count >= duration_days:
        return [start + timedelta(days=i) for i in range(duration_days)]

    step = duration_days / count
    seen: set[int] = set()
    dates: list[date] = []
    for i in range(count):
        offset = min(duration_days - 1, round(i * step))
        while offset in seen and offset < duration_days - 1:
            offset += 1
        seen.add(offset)
        dates.append(start + timedelta(days=offset))
    return dates


def schedule_time(
    *,
    platform: Platform,
    local_date: date,
    tzname: str,
    slot: int = 0,
) -> datetime:
    """Return a naive-UTC datetime for posting `platform` on `local_date`.

    `slot` staggers multiple platforms on the same day to different good hours,
    so they don't all fire at the exact same minute.
    """
    tz = _tz(tzname)
    hours = BEST_HOURS.get(platform, DEFAULT_HOURS)
    hour = hours[slot % len(hours)]
    # Stagger minutes a little per slot for a natural cadence.
    minute = (slot * 7) % 60

    local_dt = datetime(
        local_date.year, local_date.month, local_date.day, hour, minute, tzinfo=tz
    )
    naive_utc = local_dt.astimezone(timezone.utc).replace(tzinfo=None)

    # Never schedule in the past (e.g. a plan created late in the day).
    now = utcnow()
    if naive_utc <= now:
        naive_utc = now + timedelta(hours=1)
    return naive_utc
