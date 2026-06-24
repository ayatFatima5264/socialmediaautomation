"""Publisher abstraction.

Each platform implements the same contract: take post content + hashtags and
publish it, returning a PublishResult. Today these are simulated; swapping in
real platform APIs (Meta Graph API, X API, LinkedIn API, ...) means adding a
real BasePublisher subclass and registering it — nothing else changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.schemas.post import Platform


@dataclass
class PublishResult:
    success: bool
    external_id: str | None = None  # the post id returned by the platform
    error: str | None = None


class BasePublisher(ABC):
    platform: Platform

    @abstractmethod
    async def publish(
        self, *, content: str, hashtags: list[str], image_url: str | None = None
    ) -> PublishResult:
        """Publish a post to the platform.

        `image_url` is a publicly reachable media URL. Some platforms (Instagram)
        require it; text-only platforms ignore it.
        """
        raise NotImplementedError
