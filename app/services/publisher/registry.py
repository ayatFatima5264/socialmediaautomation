"""Maps a platform to its publisher implementation.

If the user has a connected SocialAccount for the platform and a real adapter
exists, use it; otherwise fall back to the SimulatedPublisher so the
schedule→publish flow still works end-to-end in dev.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.social_account import SocialAccount
from app.schemas.post import Platform
from app.services.publisher.base import BasePublisher
from app.services.publisher.instagram import InstagramPublisher
from app.services.publisher.linkedin import LinkedInPublisher
from app.services.publisher.simulated import SimulatedPublisher
from app.services.publisher.x import XPublisher

#: Platforms with a real adapter, keyed by platform.
_REAL_PLATFORMS = {Platform.instagram, Platform.twitter, Platform.linkedin}


def get_publisher(
    platform: Platform,
    account: SocialAccount | None = None,
    db: Session | None = None,
) -> BasePublisher:
    """Return the publisher for a platform.

    `account` is the user's connected account for that platform (if any). A real
    publisher is used only when both a connected account and a real adapter
    exist; everything else is simulated. `db` is passed to adapters that must
    persist state during publishing (e.g. X refreshing a rotated OAuth token).
    """
    if account is not None and platform in _REAL_PLATFORMS:
        if platform is Platform.instagram:
            return InstagramPublisher(account)
        if platform is Platform.twitter:
            return XPublisher(account, db)
        if platform is Platform.linkedin:
            return LinkedInPublisher(account)
    return SimulatedPublisher(platform)
