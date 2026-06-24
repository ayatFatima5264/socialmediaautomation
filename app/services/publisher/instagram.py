"""Real Instagram publisher — posts via the Meta Graph Content Publishing API.

Constructed with the user's connected SocialAccount (token + IG account id).
Instagram cannot publish text-only posts: every post needs an image or video at
a public URL, with the text as the caption. If no `image_url` is supplied we
fail with a clear, actionable message rather than silently doing nothing.
"""
from __future__ import annotations

import logging

from app.models.social_account import SocialAccount
from app.schemas.post import Platform
from app.services.publisher.base import BasePublisher, PublishResult
from app.services.social import meta_graph

logger = logging.getLogger(__name__)


class InstagramPublisher(BasePublisher):
    platform = Platform.instagram

    def __init__(self, account: SocialAccount) -> None:
        self.account = account

    async def publish(
        self, *, content: str, hashtags: list[str], image_url: str | None = None
    ) -> PublishResult:
        if not image_url:
            return PublishResult(
                success=False,
                error=(
                    "Instagram requires an image or video — text-only posts can't "
                    "be published. Attach an image URL to this post and try again."
                ),
            )

        caption = _build_caption(content, hashtags)
        try:
            media_id = await meta_graph.publish_image(
                ig_account_id=self.account.account_id,
                access_token=self.account.access_token,
                image_url=image_url,
                caption=caption,
            )
        except meta_graph.GraphAPIError as exc:
            logger.warning("Instagram publish failed: %s", exc)
            return PublishResult(success=False, error=str(exc))

        logger.info("Published to Instagram as media %s", media_id)
        return PublishResult(success=True, external_id=media_id)


def _build_caption(content: str, hashtags: list[str]) -> str:
    tags = " ".join(f"#{t.lstrip('#')}" for t in hashtags if t)
    return f"{content}\n\n{tags}".strip() if tags else content
