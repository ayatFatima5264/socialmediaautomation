"""Real LinkedIn publisher — posts a member text share via the LinkedIn REST API.

Constructed with the user's connected SocialAccount. The account's `account_id`
is the member id (OpenID `sub`); LinkedIn's author URN is `urn:li:person:{id}`.
The stored access token must carry the `w_member_social` scope.

Publishes text shares and single-image shares: an attached image is uploaded to
LinkedIn (`linkedin_api.upload_image`) and referenced in the post's media.
"""
from __future__ import annotations

import logging

from app.models.social_account import SocialAccount
from app.schemas.post import Platform
from app.services.publisher.base import BasePublisher, PublishResult
from app.services.social import linkedin_api

logger = logging.getLogger(__name__)

# LinkedIn's per-share commentary limit.
POST_MAX_CHARS = 3000


class LinkedInPublisher(BasePublisher):
    platform = Platform.linkedin

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
        text = _compose_post(content, hashtags)
        image = image_url or (media_urls[0] if media_urls else None)
        if not text.strip() and not image:
            return PublishResult(
                success=False, error="Nothing to publish — the post is empty."
            )
        if len(text) > POST_MAX_CHARS:
            return PublishResult(
                success=False,
                error=(
                    f"Post is {len(text)} characters; LinkedIn allows "
                    f"{POST_MAX_CHARS}. Shorten the content or use fewer hashtags."
                ),
            )

        author_urn = f"urn:li:person:{self.account.account_id}"
        try:
            image_urn = None
            if image:
                image_urn = await linkedin_api.upload_image(
                    access_token=self.account.access_token,
                    owner_urn=author_urn,
                    image_url=image,
                )
            post_id = await linkedin_api.create_post(
                access_token=self.account.access_token,
                author_urn=author_urn,
                text=text,
                image_urn=image_urn,
            )
        except linkedin_api.LinkedInAPIError as exc:
            logger.warning("LinkedIn publish failed: %s", exc)
            return PublishResult(success=False, error=_user_message(exc))

        logger.info("Published to LinkedIn as %s", post_id)
        return PublishResult(success=True, external_id=post_id)


def _compose_post(content: str, hashtags: list[str]) -> str:
    """Join post content and hashtags into a single LinkedIn share body."""
    tags = " ".join(f"#{t.lstrip('#')}" for t in (hashtags or []) if t and t.strip())
    content = (content or "").strip()
    return f"{content}\n\n{tags}".strip() if tags else content


def _user_message(exc: linkedin_api.LinkedInAPIError) -> str:
    """Turn a LinkedInAPIError into a clear, actionable message for the record."""
    if exc.is_rate_limited:
        return "LinkedIn rate limit reached — the post was not published. Try again later."
    if exc.is_auth_error:
        return (
            "LinkedIn rejected the access token (expired or permission not "
            "granted). Reconnect your LinkedIn account and try again."
        )
    return f"LinkedIn API error: {exc.message}"
