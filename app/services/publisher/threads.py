"""Real Threads publisher — posts via the Threads API (graph.threads.net).

The connected account stores the Threads user id (`account_id`) and a long-lived
token with `threads_content_publish`. Publishing is the two-step container flow
in `threads_api`: create a container (TEXT, or IMAGE with the text as caption),
then publish it.

Media reuses the project's existing pipeline unchanged — visuals are already
public URLs on `Post.media`, and Threads fetches them server-side from that URL,
so there is no upload step and no second image store.

Video is deliberately not published here. Nothing in the post pipeline produces
a hosted video (uploads accept images only), so accepting one would mean
inventing infrastructure to satisfy a path no user can reach. A video attachment
is refused with a clear message instead of being sent as an image.

Token handling (delegated to social_accounts.service, not duplicated here):
  * proactive — refresh before posting when the stored token is near expiry.
    Threads tokens last 60 days and die permanently if left unrefreshed, so
    this is the difference between a working connection and a lost one.
  * reactive  — on an auth failure mid-flight, refresh once and retry.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.social_account import SocialAccount
from app.schemas.post import Platform
from app.services.publisher.base import BasePublisher, PublishResult
from app.services.social import threads_api
from app.services.social_accounts import service as accounts_service
from app.services.social_accounts.base import OAuthError

logger = logging.getLogger(__name__)

# Threads' per-post character limit.
POST_MAX_CHARS = 500

# Extensions Threads would treat as video. Detected from the URL because the
# publisher contract carries media URLs, not their types.
_VIDEO_SUFFIXES = (".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv")


class ThreadsPublisher(BasePublisher):
    platform = Platform.threads

    def __init__(self, account: SocialAccount, db: Session | None = None) -> None:
        self.account = account
        # Needed to persist a refreshed token. Optional so the class can still
        # publish (without persisting a refresh) if ever built without one.
        self.db = db

    async def publish(
        self,
        *,
        content: str,
        hashtags: list[str],
        image_url: str | None = None,
        media_urls: list[str] | None = None,
        options: dict | None = None,
    ) -> PublishResult:
        text = _compose(content, hashtags)
        image = image_url or (media_urls[0] if media_urls else None)

        if image and _is_video(image):
            return PublishResult(
                success=False,
                error=(
                    "Threads video posts aren't supported yet — this post has a "
                    "video attached. Publish it with an image or as text only."
                ),
            )
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
            media_id = await self._publish(text, image)
        except OAuthError as exc:  # the refresh itself failed
            logger.warning("Threads publish: token refresh failed: %s", exc)
            return PublishResult(
                success=False,
                error=(
                    "Threads authentication failed — the connection may have "
                    "expired or been revoked. Reconnect your Threads account "
                    "and try again."
                ),
            )
        except threads_api.ThreadsAPIError as exc:
            logger.warning(
                "Threads publish failed (status %s, code %s): %s",
                exc.status_code, exc.code, exc.message,
            )
            return PublishResult(success=False, error=_user_message(exc))

        logger.info("Published to Threads as %s", media_id)
        return PublishResult(success=True, external_id=media_id)

    # ---- internals -------------------------------------------------------
    async def _publish(self, text: str, image: str | None) -> str:
        """Post, refreshing the token proactively and once reactively.

        The retry wraps the whole container→publish sequence because both steps
        use the same access token.
        """
        await self._ensure_fresh_token()
        try:
            return await self._post(text, image)
        except threads_api.ThreadsAPIError as exc:
            # Only a rejected token is worth a refresh+retry. A missing
            # permission or a bad image is not something refreshing can fix.
            if not exc.is_auth_error or self.db is None:
                raise
            logger.info(
                "Threads publish: access token rejected — refreshing and "
                "retrying once"
            )
            await accounts_service.refresh_tokens(self.db, self.account)
            return await self._post(text, image)

    async def _post(self, text: str, image: str | None) -> str:
        return await threads_api.publish_post(
            user_id=self.account.account_id,
            access_token=self.account.access_token,
            text=text,
            image_url=image,
        )

    async def _ensure_fresh_token(self) -> None:
        """Refresh proactively when the stored token is expired/near expiry."""
        if self.db is None:
            return  # no session to persist through — use the token as-is
        if accounts_service.token_needs_refresh(self.account):
            logger.info(
                "Threads publish: access token near expiry — refreshing before post"
            )
            await accounts_service.refresh_tokens(self.db, self.account)


def _is_video(url: str) -> bool:
    return urlparse(url).path.lower().endswith(_VIDEO_SUFFIXES)


def _compose(content: str, hashtags: list[str]) -> str:
    tags = " ".join(f"#{t.lstrip('#')}" for t in (hashtags or []) if t and t.strip())
    content = (content or "").strip()
    return f"{content}\n\n{tags}".strip() if tags else content


def _detail(exc: threads_api.ThreadsAPIError) -> str:
    """Meta's own explanation, when it sent one worth repeating.

    Only the `message` field is used — never the whole payload — so nothing
    about the request, including the token that made it, is echoed back.
    """
    message = (exc.message or "").strip()
    if not message or message.lower().startswith("threads api error"):
        return ""
    return f' Threads said: "{message.rstrip(".")}".'


def _user_message(exc: threads_api.ThreadsAPIError) -> str:
    """Turn a ThreadsAPIError into a clear, actionable message for the post
    record. Never includes a token, an app secret or a raw API payload."""
    if exc.is_rate_limited:
        return (
            "Threads rate limit reached — the post was not published. Threads "
            "allows a limited number of posts per day; try again later."
        )
    if exc.is_auth_error:
        return (
            "Threads rejected the access token (expired or revoked). Reconnect "
            "your Threads account and try again."
        )
    if exc.is_permission_error:
        return (
            "Threads refused the request — the connection is missing the "
            "publishing permission. Reconnect your Threads account to grant "
            "content publishing, then try again."
        )
    if exc.is_server_error:
        return (
            "Threads is having trouble right now (server error) — the post was "
            "not published. Try again shortly."
        )
    if exc.is_media_error:
        return (
            "Threads could not use the attached image. It must be a JPEG or PNG "
            f"at a public URL that Threads can download.{_detail(exc)}"
        )
    return f"Threads rejected the post.{_detail(exc)}"
