"""Real Threads publisher — posts via the Threads API (graph.threads.net).

The connected account stores the Threads user id (`account_id`) and a long-lived
token with `threads_content_publish`. Publishing is the two-step container flow
in `threads_api`. Text-only posts work; an attached image is posted with the
text as its caption.
"""
from __future__ import annotations

import logging

from app.models.social_account import SocialAccount
from app.schemas.post import Platform
from app.services.publisher.base import BasePublisher, PublishResult
from app.services.social import threads_api

logger = logging.getLogger(__name__)

# Threads' per-post character limit.
POST_MAX_CHARS = 500


class ThreadsPublisher(BasePublisher):
    platform = Platform.threads

    def __init__(self, account: SocialAccount) -> None:
        self.account = account

    async def publish(
        self,
        *,
        content: str,
        hashtags: list[str],
        image_url: str | None = None,
        media_urls: list[str] | None = None,
    ) -> PublishResult:
        text = _compose(content, hashtags)
        image = image_url or (media_urls[0] if media_urls else None)
        if not text.strip() and not image:
            return PublishResult(
                success=False, error="Nothing to publish — the post is empty."
            )
        if len(text) > POST_MAX_CHARS:
            return PublishResult(
                success=False,
                error=(
                    f"Post is {len(text)} characters; Threads allows "
                    f"{POST_MAX_CHARS}. Shorten the content or use fewer hashtags."
                ),
            )

        try:
            media_id = await threads_api.publish_post(
                user_id=self.account.account_id,
                access_token=self.account.access_token,
                text=text,
                image_url=image,
            )
        except threads_api.ThreadsAPIError as exc:
            logger.warning("Threads publish failed: %s", exc)
            return PublishResult(success=False, error=_user_message(exc))

        logger.info("Published to Threads as %s", media_id)
        return PublishResult(success=True, external_id=media_id)


def _compose(content: str, hashtags: list[str]) -> str:
    tags = " ".join(f"#{t.lstrip('#')}" for t in (hashtags or []) if t and t.strip())
    content = (content or "").strip()
    return f"{content}\n\n{tags}".strip() if tags else content


def _user_message(exc: threads_api.ThreadsAPIError) -> str:
    if exc.is_auth_error:
        return (
            "Threads rejected the access token (expired or permission revoked). "
            "Reconnect your Threads account and try again."
        )
    return f"Threads API error: {exc.message}"
