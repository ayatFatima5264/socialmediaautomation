"""Maps a platform to its publisher implementation.

If the user has a connected SocialAccount for the platform and a real adapter
exists, use it; otherwise fall back to the SimulatedPublisher so the
schedule→publish flow still works end-to-end in dev.
"""
from __future__ import annotations

from app.models.social_account import SocialAccount
from app.schemas.post import Platform
from app.services.publisher.base import BasePublisher
from app.services.publisher.instagram import InstagramPublisher
from app.services.publisher.simulated import SimulatedPublisher

#: Platforms with a real adapter, keyed by platform.
_REAL_PLATFORMS = {Platform.instagram}


def get_publisher(
    platform: Platform, account: SocialAccount | None = None
) -> BasePublisher:
    """Return the publisher for a platform.

    `account` is the user's connected account for that platform (if any). A real
    publisher is used only when both a connected account and a real adapter
    exist; everything else is simulated.
    """
    if account is not None and platform in _REAL_PLATFORMS:
        if platform is Platform.instagram:
            return InstagramPublisher(account)
    return SimulatedPublisher(platform)
