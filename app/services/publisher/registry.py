"""Maps a platform to its publisher implementation.

This is the single place to wire in real adapters later, e.g.:

    _REAL = {Platform.twitter: TwitterPublisher()}
    def get_publisher(platform):
        return _REAL.get(platform) or SimulatedPublisher(platform)
"""
from __future__ import annotations

from app.schemas.post import Platform
from app.services.publisher.base import BasePublisher
from app.services.publisher.simulated import SimulatedPublisher


def get_publisher(platform: Platform) -> BasePublisher:
    return SimulatedPublisher(platform)
