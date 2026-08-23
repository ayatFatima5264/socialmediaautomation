"""Usage metering for Video Studio.

Video Studio is the first part of AutoSocial where an action has a real marginal
cost. This module records those actions and answers "how much has this user used
this month" — nothing more.

What it deliberately does NOT do:

  * **No pricing.** No currency, no plan names, no tiers. Those are commercial
    decisions and hardcoding them here is exactly what makes a pricing change a
    code change. `frontend/src/config/pricing.js` already states that there is
    no billing integration; this file keeps that true.
  * **No blocking, by default.** `LIMITS` ships generous and enforcement is
    opt-in per metric. A limit that fires before anyone has agreed what the
    plans are would be inventing product policy in a service module.

What it does do is make metering possible later without a backfill: every
metered call appends a row as it completes, so the day a plan exists, the
history is already there.

The seam for a future billing system is `check_allowance()`. Today it reads
`LIMITS`; tomorrow it reads the user's plan. Callers already handle the refusal.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.usage_event import METRICS, UsageEvent

logger = logging.getLogger(__name__)


class UsageLimitExceeded(RuntimeError):
    """The user has spent their allowance of a metric for the period."""

    def __init__(self, metric: str, used: float, limit: float) -> None:
        self.metric = metric
        self.used = used
        self.limit = limit
        super().__init__(
            f"You have used your {metric.replace('_', ' ')} allowance for this "
            f"month ({used:.0f} of {limit:.0f})."
        )


@dataclass(frozen=True)
class Limit:
    """One metric's monthly allowance.

    `enforced=False` means the number is recorded and reported but never
    refuses a request — which is every metric today. Turning one on is a
    one-word change here, and the callers already raise correctly.
    """

    metric: str
    monthly: float
    unit: str
    enforced: bool = False


# Per-user, per-calendar-month. Sized to be well clear of ordinary use while
# still bounding the damage a runaway script could do on a Render Free plan.
LIMITS: dict[str, Limit] = {
    "voice_seconds": Limit("voice_seconds", 3600, "seconds"),
    "transcription_seconds": Limit("transcription_seconds", 7200, "seconds"),
    "render_seconds": Limit("render_seconds", 3600, "seconds"),
    "ai_images": Limit("ai_images", 500, "images"),
    "storage_bytes": Limit("storage_bytes", 5 * 1024**3, "bytes"),
    "exports": Limit("exports", 500, "exports"),
    "repurpose_clips": Limit("repurpose_clips", 200, "clips"),
}


def _period_start(now: datetime | None = None) -> datetime:
    """Midnight UTC on the first of the current month.

    Calendar months rather than rolling 30 days: a user reading "used 12 of 60
    minutes" expects it to reset on a date they can name.
    """
    now = now or datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def record(
    db: Session,
    *,
    user_id: int,
    metric: str,
    quantity: float,
    source: str | None = None,
    project_id: int | None = None,
    meta: dict | None = None,
    commit: bool = True,
) -> UsageEvent | None:
    """Append one usage event.

    Returns None for an unknown metric or a non-positive quantity rather than
    raising: metering is bookkeeping around an operation that has already
    succeeded, and it must never be the thing that fails the request the user
    actually made. The mistake is logged instead.
    """
    if metric not in METRICS:
        logger.warning("Ignoring usage for unknown metric %r", metric)
        return None
    if quantity is None or quantity <= 0:
        return None

    event = UsageEvent(
        user_id=user_id,
        project_id=project_id,
        metric=metric,
        quantity=float(quantity),
        source=source,
        meta=meta or {},
    )
    db.add(event)
    if commit:
        db.commit()
    return event


def used(db: Session, *, user_id: int, metric: str) -> float:
    """How much of a metric this user has spent in the current month."""
    total = db.scalar(
        select(func.coalesce(func.sum(UsageEvent.quantity), 0.0)).where(
            UsageEvent.user_id == user_id,
            UsageEvent.metric == metric,
            UsageEvent.created_at >= _period_start(),
        )
    )
    return float(total or 0.0)


def summary(db: Session, *, user_id: int) -> dict:
    """Everything the usage panel needs, in one query per metric.

    Shaped for display: each metric reports what was used, what the allowance
    is, whether it is actually enforced, and when the period rolls over. The UI
    must be able to say "recorded, not charged" honestly.
    """
    period_start = _period_start()
    # First of next month, computed by stepping into it rather than by adding
    # 30 days — which would land in the wrong month twice a year.
    period_end = (period_start + timedelta(days=32)).replace(day=1)

    rows = db.execute(
        select(UsageEvent.metric, func.sum(UsageEvent.quantity))
        .where(
            UsageEvent.user_id == user_id,
            UsageEvent.created_at >= period_start,
        )
        .group_by(UsageEvent.metric)
    ).all()
    spent = {metric: float(total or 0.0) for metric, total in rows}

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        # No plan exists yet, and saying so is more useful than inventing one.
        "plan": None,
        "metrics": [
            {
                "metric": limit.metric,
                "unit": limit.unit,
                "used": spent.get(limit.metric, 0.0),
                "limit": limit.monthly,
                "enforced": limit.enforced,
            }
            for limit in LIMITS.values()
        ],
    }


def check_allowance(
    db: Session,
    *,
    user_id: int,
    metric: str,
    requested: float = 0.0,
) -> None:
    """Raise UsageLimitExceeded if this request would exceed an enforced limit.

    Called *before* the expensive operation, with the amount it is about to
    consume. A metric whose limit is not enforced returns silently — which is
    all of them today, on purpose (see the module docstring).

    This function is the seam a billing system replaces: swap `LIMITS[metric]`
    for the signed-in user's plan entitlement and every call site already does
    the right thing.
    """
    limit = LIMITS.get(metric)
    if limit is None or not limit.enforced:
        return

    already = used(db, user_id=user_id, metric=metric)
    if already + max(0.0, requested) > limit.monthly:
        raise UsageLimitExceeded(metric, already, limit.monthly)
