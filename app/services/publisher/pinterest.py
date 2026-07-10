"""Real Pinterest publisher — creates an image Pin via the Pinterest API v5.

A Pin ALWAYS needs an image and a target board, so this publisher:
  * requires an image (text-only posts fail with a clear message);
  * resolves the target board (stored `page_id` if it matches, else the first
    board the user has) — Pinterest has no default board.

The connected account stores the OAuth token (with `pins:write`) and the
username as `account_id`. The post content becomes the Pin's title/description.
"""
from __future__ import annotations

import logging

from app.models.social_account import SocialAccount
from app.schemas.post import Platform
from app.services.publisher.base import BasePublisher, PublishResult
from app.services.social import pinterest_api

logger = logging.getLogger(__name__)


class PinterestPublisher(BasePublisher):
    platform = Platform.pinterest

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
        image = image_url or (media_urls[0] if media_urls else None)
        if not image:
            return PublishResult(
                success=False,
                error=(
                    "Pinterest requires an image — Pins can't be text-only. "
                    "Attach an image to this post and try again."
                ),
            )

        try:
            board = await self._resolve_board()
        except pinterest_api.PinterestAPIError as exc:
            logger.warning("Pinterest publish: could not list boards: %s", exc)
            return PublishResult(success=False, error=_user_message(exc))

        if board is None:
            return PublishResult(
                success=False,
                error=(
                    "No Pinterest board found. Create a board on Pinterest, then "
                    "try again — every Pin must be saved to a board."
                ),
            )

        title, description = _compose(content, hashtags)
        try:
            pin_id = await pinterest_api.create_pin(
                access_token=self.account.access_token,
                board_id=board["id"],
                image_url=image,
                title=title,
                description=description,
            )
        except pinterest_api.PinterestAPIError as exc:
            logger.warning("Pinterest publish failed: %s", exc)
            return PublishResult(success=False, error=_user_message(exc))

        logger.info("Published to Pinterest board %s as pin %s", board["id"], pin_id)
        return PublishResult(success=True, external_id=pin_id)

    async def _resolve_board(self) -> dict | None:
        """The board to pin to: the stored page_id if it matches one of the
        user's boards, else the first board. None if the user has no boards."""
        boards = await pinterest_api.list_boards(self.account.access_token)
        if not boards:
            return None
        if self.account.page_id:
            for board in boards:
                if board.get("id") == self.account.page_id:
                    return board
        return boards[0]


def _compose(content: str, hashtags: list[str]) -> tuple[str, str]:
    """Return (title, description). Title is the first line of content; the
    description is the full content plus hashtags."""
    content = (content or "").strip()
    tags = " ".join(f"#{t.lstrip('#')}" for t in (hashtags or []) if t and t.strip())
    title = content.split("\n", 1)[0] if content else "New Pin"
    description = f"{content}\n\n{tags}".strip() if tags else content
    return title, description


def _user_message(exc: pinterest_api.PinterestAPIError) -> str:
    if exc.is_rate_limited:
        return "Pinterest rate limit reached — the Pin was not created. Try again later."
    if exc.is_auth_error:
        return (
            "Pinterest rejected the access token (expired or permission revoked). "
            "Reconnect your Pinterest account and try again."
        )
    return f"Pinterest API error: {exc.message}"
