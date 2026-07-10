"""Real Facebook publisher — posts to a connected Facebook Page via the Graph API.

Facebook publishes to a **Page** the user manages, not a personal profile. The
connected account stores the user's long-lived token (with `pages_manage_posts`);
this publisher resolves the target Page and its Page access token at publish time
via `me/accounts`, then posts to the Page's feed (or `/photos` when an image is
attached).

Page selection: the account's stored `page_id` if present, otherwise the first
Page the user manages. If the user manages no Page, we fail with a clear message.
"""
from __future__ import annotations

import logging

from app.models.social_account import SocialAccount
from app.schemas.post import Platform
from app.services.publisher.base import BasePublisher, PublishResult
from app.services.social import meta_graph

logger = logging.getLogger(__name__)

# Facebook's practical per-post character limit.
POST_MAX_CHARS = 63206


class FacebookPublisher(BasePublisher):
    platform = Platform.facebook

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
        message = _compose(content, hashtags)
        image = image_url or (media_urls[0] if media_urls else None)
        if not message.strip() and not image:
            return PublishResult(
                success=False, error="Nothing to publish — the post is empty."
            )
        if len(message) > POST_MAX_CHARS:
            return PublishResult(
                success=False,
                error=(
                    f"Post is {len(message)} characters; Facebook allows "
                    f"{POST_MAX_CHARS}. Shorten the content."
                ),
            )

        try:
            page = await self._resolve_page()
        except meta_graph.GraphAPIError as exc:
            logger.warning("Facebook publish: could not list Pages: %s", exc)
            return PublishResult(success=False, error=_user_message(exc))

        if page is None:
            return PublishResult(
                success=False,
                error=(
                    "No Facebook Page found for this account. Facebook posts "
                    "publish to a Page you manage — create or get access to a "
                    "Page, then reconnect Facebook."
                ),
            )

        try:
            post_id = await meta_graph.create_page_post(
                page_id=page["id"],
                page_access_token=page["access_token"],
                message=message,
                image_url=image,
            )
        except meta_graph.GraphAPIError as exc:
            logger.warning("Facebook publish failed: %s", exc)
            return PublishResult(success=False, error=_user_message(exc))

        logger.info("Published to Facebook Page %s as %s", page["id"], post_id)
        return PublishResult(success=True, external_id=post_id)

    async def _resolve_page(self) -> dict | None:
        """The Page to post to: the stored page_id if it matches one the user
        manages, else the first managed Page. None if the user manages none."""
        pages = await meta_graph.list_pages(self.account.access_token)
        if not pages:
            return None
        if self.account.page_id:
            for page in pages:
                if page.get("id") == self.account.page_id:
                    return page
        return pages[0]


def _compose(content: str, hashtags: list[str]) -> str:
    """Join post content and hashtags into a single Facebook post body."""
    tags = " ".join(f"#{t.lstrip('#')}" for t in (hashtags or []) if t and t.strip())
    content = (content or "").strip()
    return f"{content}\n\n{tags}".strip() if tags else content


def _user_message(exc: meta_graph.GraphAPIError) -> str:
    """Turn a GraphAPIError into a clear, actionable message for the post record."""
    text = str(exc)
    low = text.lower()
    if "permission" in low or "oauth" in low or "token" in low or "expired" in low:
        return (
            "Facebook rejected the request (token expired or a permission is "
            "missing). Reconnect your Facebook account and try again."
        )
    return f"Facebook API error: {text}"
