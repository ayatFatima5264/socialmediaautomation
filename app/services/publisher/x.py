"""Real X (Twitter) publisher — posts via the official X API v2.

Constructed with the user's connected SocialAccount (OAuth 2.0 access token +
refresh token) and the DB session, so it can refresh and persist a rotated token
without the user present.

Publishes tweets through ``POST /2/tweets`` (see ``services.social.x_api``):
  * text-only posts,
  * single image, and multiple images (up to X's limit of 4).

Media reuses the project's existing pipeline unchanged — visuals are stored as
public URLs on ``Post.media`` and passed in as ``media_urls``. X (unlike Meta)
won't fetch a URL, so the X-specific step is: download the bytes from that URL
and upload them to X's official media endpoint, then attach the returned media
ids to the tweet. No new media storage/validation/compression is introduced.

Video and polls remain seams: ``x_api.upload_media`` already takes a media
category (video needs X's chunked upload) and ``create_tweet`` already accepts
``poll`` / ``reply_to`` (threads) — no refactor of this class or its callers.

Token handling (delegated to social_accounts.service, not duplicated here):
  * proactive  — refresh before posting when the stored token is near expiry.
  * reactive   — on a 401 mid-flight (token revoked/rotated), refresh once and
                 retry the publish exactly one more time.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.social_account import SocialAccount
from app.schemas.post import Platform
from app.services.publisher.base import BasePublisher, PublishResult
from app.services.social import x_api
from app.services.social_accounts import service as accounts_service
from app.services.social_accounts.base import OAuthError

logger = logging.getLogger(__name__)

# X's character limit for a standard (non-verified) tweet.
TWEET_MAX_CHARS = x_api.TWEET_MAX_CHARS


class XPublisher(BasePublisher):
    platform = Platform.twitter

    def __init__(self, account: SocialAccount, db: Session | None = None) -> None:
        self.account = account
        # Needed to persist a refreshed/rotated token. Optional so the class can
        # still publish (without persisting a refresh) if ever built without one.
        self.db = db

    async def publish(
        self,
        *,
        content: str,
        hashtags: list[str],
        image_url: str | None = None,
        media_urls: list[str] | None = None,
    ) -> PublishResult:
        # Accept both the legacy single `image_url` and the general `media_urls`
        # list the scheduler now supplies from Post.media.
        urls = list(media_urls or ([image_url] if image_url else []))

        text = _compose_tweet(content, hashtags)
        if not text.strip() and not urls:
            return PublishResult(
                success=False, error="Nothing to publish — no text or media."
            )
        if len(text) > TWEET_MAX_CHARS:
            return PublishResult(
                success=False,
                error=(
                    f"Tweet is {len(text)} characters; X allows {TWEET_MAX_CHARS}. "
                    "Shorten the content or use fewer hashtags. "
                    "(Automatic thread splitting arrives in a later phase.)"
                ),
            )

        try:
            data = await self._publish(text, urls)
        except OAuthError as exc:  # refresh itself failed (no/expired refresh token)
            logger.warning("X publish: token refresh failed: %s", exc)
            return PublishResult(
                success=False,
                error=(
                    "X authentication failed — the connection may have been "
                    f"revoked. Reconnect your X account and try again. ({exc})"
                ),
            )
        except x_api.XAPIError as exc:
            logger.warning("X publish failed (status %s): %s", exc.status_code, exc.message)
            return PublishResult(success=False, error=_user_message(exc))

        tweet_id = (data.get("data") or {}).get("id")
        if not tweet_id:
            return PublishResult(
                success=False, error="X API did not return a tweet id."
            )
        logger.info("Published to X as tweet %s", tweet_id)
        return PublishResult(success=True, external_id=tweet_id)

    # ---- internals -------------------------------------------------------
    async def _publish(self, text: str, media_urls: list[str]) -> dict:
        """Upload any media then create the tweet, refreshing the token
        proactively and (on a 401 anywhere in the sequence) once reactively.

        The refresh+retry wraps the whole media→tweet sequence because media
        upload and tweet creation use the same access token.
        """
        await self._ensure_fresh_token()
        try:
            return await self._upload_and_tweet(text, media_urls)
        except x_api.XAPIError as exc:
            # Only a 401 is worth a refresh+retry; 403/429/5xx are not auth issues.
            if not exc.is_auth_error or self.db is None:
                raise
            logger.info(
                "X publish: access token rejected (401) — refreshing and retrying once"
            )
            await accounts_service.refresh_tokens(self.db, self.account)
            return await self._upload_and_tweet(text, media_urls)

    async def _upload_and_tweet(self, text: str, media_urls: list[str]) -> dict:
        media_ids = await self._upload_media(media_urls) if media_urls else None
        return await x_api.create_tweet(
            access_token=self.account.access_token, text=text, media_ids=media_ids
        )

    async def _upload_media(self, media_urls: list[str]) -> list[str]:
        """Download each visual from the pipeline URL and upload it to X.

        Returns the ordered media ids. X caps a tweet at 4 images, so extras are
        dropped with a log line (never silently). Non-image media is rejected
        with a clear error until the pipeline provides video.
        """
        limit = x_api.MAX_IMAGES_PER_TWEET
        urls = media_urls[:limit]
        if len(media_urls) > limit:
            logger.info(
                "X publish: %d images provided but X allows %d — uploading the first %d",
                len(media_urls), limit, limit,
            )

        media_ids: list[str] = []
        for url in urls:
            data, mime = await x_api.download_media(url)
            if not x_api.is_supported_image(mime):
                raise x_api.XAPIError(
                    f"Unsupported media type {mime!r} for X — images only "
                    "(jpeg, png, gif, webp) are supported at this time."
                )
            media_ids.append(
                await x_api.upload_media(
                    access_token=self.account.access_token,
                    data=data,
                    mime_type=mime,
                    category="tweet_image",
                )
            )
        return media_ids

    async def _ensure_fresh_token(self) -> None:
        """Refresh proactively when the stored token is expired/near expiry."""
        if self.db is None:
            return  # no session to persist through — use the token as-is
        if accounts_service.token_needs_refresh(self.account):
            logger.info("X publish: access token near expiry — refreshing before post")
            await accounts_service.refresh_tokens(self.db, self.account)


def _compose_tweet(content: str, hashtags: list[str]) -> str:
    """Join post content and hashtags into a single tweet body."""
    tags = " ".join(f"#{t.lstrip('#')}" for t in (hashtags or []) if t and t.strip())
    content = (content or "").strip()
    return f"{content}\n\n{tags}".strip() if tags else content


def _user_message(exc: x_api.XAPIError) -> str:
    """Turn an XAPIError into a clear, actionable message for the post record."""
    if exc.is_rate_limited:
        wait = f" Try again in ~{exc.retry_after}s." if exc.retry_after else ""
        return f"X rate limit reached — the post was not published.{wait}"
    if exc.is_auth_error:
        return (
            "X rejected the access token (expired or permissions revoked). "
            "Reconnect your X account and try again."
        )
    if _is_plan_credit_error(exc):
        return (
            "Your X API plan has no posting credits left, so the post wasn't "
            "published. Upgrade your X API tier or wait for the monthly quota to "
            "reset, then try again. (Manage it in the X Developer Portal.)"
        )
    return f"X API error: {exc.message}"


def _is_plan_credit_error(exc: x_api.XAPIError) -> bool:
    """Detect X's plan/quota rejection (e.g. "does not have any credits to
    fulfill this request"), which X returns as a 403 rather than a rate limit."""
    message = (exc.message or "").lower()
    return "credit" in message or "does not have access" in message
