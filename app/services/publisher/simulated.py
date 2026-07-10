"""Simulated publisher — logs the publish and returns a fake platform id.

Real platform integrations require OAuth apps + platform review, so this lets
the entire schedule→publish flow work end-to-end today. Replace per platform
later (e.g. InstagramPublisher) and register it in registry.py.
"""
from __future__ import annotations

import asyncio
import logging

from app.schemas.post import Platform
from app.services.publisher.base import BasePublisher, PublishResult

logger = logging.getLogger(__name__)


class SimulatedPublisher(BasePublisher):
    def __init__(self, platform: Platform) -> None:
        self.platform = platform

    async def publish(
        self,
        *,
        content: str,
        hashtags: list[str],
        image_url: str | None = None,
        media_urls: list[str] | None = None,
    ) -> PublishResult:
        # Simulate network latency to a platform API.
        await asyncio.sleep(0.1)

        digest = abs(hash((self.platform.value, content))) % 10**8
        external_id = f"sim_{self.platform.value}_{digest:08d}"

        preview = content.replace("\n", " ")[:60]
        logger.info(
            "[SIMULATED PUBLISH] %s -> %s | %d chars, %d hashtags | %r",
            self.platform.value,
            external_id,
            len(content),
            len(hashtags),
            preview,
        )
        return PublishResult(success=True, external_id=external_id)
