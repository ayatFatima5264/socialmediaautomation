"""Real Pinterest publisher — creates an image Pin via the Pinterest API v5.

A Pin ALWAYS needs an image and a target board, so this publisher:
  * requires an image (text-only posts fail with a clear message);
  * resolves the target board in a documented order — the board chosen for this
    post, else the account's default board, else the user's only board — and
    verifies it still exists before pinning, so a board deleted on Pinterest
    produces "pick another board" rather than a Pin landing somewhere the user
    didn't choose.

Media reuses the project's existing pipeline unchanged: visuals are already
public URLs on `Post.media`, and Pinterest fetches them server-side via
`media_source: {source_type: "image_url"}`. No second image store, no upload.

Token handling (delegated to social_accounts.service, not duplicated here):
  * proactive — refresh before publishing when the stored 30-day access token
    is at/near expiry.
  * reactive  — on a 401 mid-flight (token revoked/rotated), refresh once and
    retry the publish exactly one more time.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.social_account import SocialAccount
from app.schemas.post import Platform
from app.services.publisher.base import BasePublisher, PublishResult
from app.services.social import pinterest_api
from app.services.social_accounts import service as accounts_service
from app.services.social_accounts.base import OAuthError

logger = logging.getLogger(__name__)


class BoardError(Exception):
    """No usable target board; the message is written for the user."""


class PinterestPublisher(BasePublisher):
    platform = Platform.pinterest

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
        image = image_url or (media_urls[0] if media_urls else None)
        if not image:
            return PublishResult(
                success=False,
                error=(
                    "Pinterest requires an image — Pins can't be text-only. "
                    "Attach an image to this post and try again."
                ),
            )

        opts = options or {}
        link = _clean(opts.get("link"))
        alt_text = _clean(opts.get("alt_text"))
        chosen_board = _clean(opts.get("board_id"))

        try:
            pin_id = await self._publish(
                image=image,
                title_source=content,
                hashtags=hashtags,
                chosen_board=chosen_board,
                link=link,
                alt_text=alt_text,
            )
        except BoardError as exc:
            logger.info("Pinterest publish: no usable board — %s", exc)
            return PublishResult(success=False, error=str(exc))
        except OAuthError as exc:  # the refresh itself failed
            logger.warning("Pinterest publish: token refresh failed: %s", exc)
            return PublishResult(
                success=False,
                error=(
                    "Pinterest authentication failed — the connection may have "
                    "been revoked. Reconnect your Pinterest account and try again."
                ),
            )
        except pinterest_api.PinterestAPIError as exc:
            logger.warning(
                "Pinterest publish failed (status %s): %s", exc.status_code, exc.message
            )
            return PublishResult(success=False, error=_user_message(exc))

        logger.info("Published to Pinterest as pin %s", pin_id)
        return PublishResult(success=True, external_id=pin_id)

    # ---- internals -------------------------------------------------------
    async def _publish(
        self,
        *,
        image: str,
        title_source: str,
        hashtags: list[str],
        chosen_board: str | None,
        link: str | None,
        alt_text: str | None,
    ) -> str:
        """Resolve the board and create the Pin, refreshing the token proactively
        and (on a 401 anywhere in the sequence) once reactively."""
        await self._ensure_fresh_token()
        try:
            return await self._resolve_and_pin(
                image, title_source, hashtags, chosen_board, link, alt_text
            )
        except pinterest_api.PinterestAPIError as exc:
            # Only a 401 is worth a refresh+retry. A 403 means the scope/permission
            # is missing, which refreshing cannot fix.
            if exc.status_code != 401 or self.db is None:
                raise
            logger.info(
                "Pinterest publish: access token rejected (401) — refreshing and "
                "retrying once"
            )
            await accounts_service.refresh_tokens(self.db, self.account)
            return await self._resolve_and_pin(
                image, title_source, hashtags, chosen_board, link, alt_text
            )

    async def _resolve_and_pin(
        self,
        image: str,
        title_source: str,
        hashtags: list[str],
        chosen_board: str | None,
        link: str | None,
        alt_text: str | None,
    ) -> str:
        board_id = await self._resolve_board(chosen_board)
        title, description = _compose(title_source, hashtags)
        return await pinterest_api.create_pin(
            access_token=self.account.access_token,
            board_id=board_id,
            image_url=image,
            title=title,
            description=description,
            link=link,
            alt_text=alt_text,
        )

    async def _resolve_board(self, chosen_board: str | None) -> str:
        """The board to pin to, verified to still exist.

        Order: the board selected for this post, then the account's default
        board, then — only if the user has exactly one — that board. Anything
        else asks the user to choose, rather than guessing a destination.
        """
        token = self.account.access_token

        for board_id, source in (
            (chosen_board, "selected"),
            (_clean(self.account.page_id), "default"),
        ):
            if not board_id:
                continue
            try:
                await pinterest_api.get_board(token, board_id)
            except pinterest_api.PinterestAPIError as exc:
                if exc.is_not_found:
                    raise BoardError(
                        f"The {source} Pinterest board no longer exists (it was "
                        "deleted or is no longer shared with you). Pick another "
                        "board for this post and try again."
                    ) from exc
                raise
            return board_id

        boards = await pinterest_api.list_boards(token)
        if not boards:
            # Not "make one on Pinterest": in Sandbox — where a Trial-tier app
            # must publish — the website manages a different set of boards and
            # can't create one here. The picker's "+ New board" can.
            raise BoardError(
                "No Pinterest board found — every Pin must be saved to one. "
                'Use "+ New board" next to the board picker to create your '
                "first, then try again."
            )
        if len(boards) > 1:
            raise BoardError(
                "Choose which Pinterest board to pin to — your account has "
                f"{len(boards)} boards, so there is no obvious default. Pick one "
                "on the post, or set a default board on the Accounts page."
            )
        logger.info(
            "Pinterest publish: no board chosen — using the account's only board %s",
            boards[0]["id"],
        )
        return boards[0]["id"]

    async def _ensure_fresh_token(self) -> None:
        """Refresh proactively when the stored token is expired/near expiry."""
        if self.db is None:
            return  # no session to persist through — use the token as-is
        if accounts_service.token_needs_refresh(self.account):
            logger.info(
                "Pinterest publish: access token near expiry — refreshing before pin"
            )
            await accounts_service.refresh_tokens(self.db, self.account)


def _clean(value: object) -> str | None:
    """A trimmed non-empty string, or None."""
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


def _compose(content: str, hashtags: list[str]) -> tuple[str, str]:
    """Return (title, description). Title is the first line of content; the
    description is the full content plus hashtags."""
    content = (content or "").strip()
    tags = " ".join(f"#{t.lstrip('#')}" for t in (hashtags or []) if t and t.strip())
    title = content.split("\n", 1)[0] if content else "New Pin"
    description = f"{content}\n\n{tags}".strip() if tags else content
    return title, description


def _detail(exc: pinterest_api.PinterestAPIError) -> str:
    """Pinterest's own explanation, if it sent one worth repeating.

    Only the `message` field is used — never the whole payload — so nothing
    about the request, including the token that made it, can be echoed back.
    """
    message = (exc.message or "").strip()
    if not message or message.lower().startswith("pinterest api error"):
        return ":"
    code = f", code {exc.code}" if exc.code else ""
    return f': "{message.rstrip(".")}"{code}.'


def _user_message(exc: pinterest_api.PinterestAPIError) -> str:
    """Turn a PinterestAPIError into a clear, actionable message for the post
    record. Never includes a token, a client secret or a raw API payload."""
    if exc.is_rate_limited:
        wait = f" Try again in ~{exc.retry_after}s." if exc.retry_after else ""
        return (
            "Pinterest rate limit reached — the Pin was not created."
            f"{wait} Trial API access has a daily call limit; it resets each day."
        )
    if exc.status_code == 401:
        return (
            "Pinterest rejected the access token (expired or revoked). "
            "Reconnect your Pinterest account and try again."
        )
    if exc.status_code == 403:
        # Pinterest returns 403 for several unrelated reasons — a missing scope,
        # an account that isn't a business account, a feature the app's access
        # tier doesn't cover. Its own sentence is the only thing that
        # distinguishes them, so pass it through: it names the cause and
        # contains no credential.
        return (
            "Pinterest refused the request"
            f"{_detail(exc)} This usually means the connection is missing a "
            "permission, or your Pinterest account isn't a business account "
            "(Pin creation needs one). Try reconnecting Pinterest first."
        )
    if exc.is_not_found:
        return (
            "Pinterest could not find that board. Pick another board for this "
            "post and try again."
        )
    if exc.is_server_error:
        return (
            "Pinterest is having trouble right now (server error) — the Pin was "
            "not created. Try again shortly."
        )
    if exc.status_code == 400:
        return (
            f"Pinterest rejected the Pin: {exc.message} Check the image URL is "
            "publicly reachable and that the title and description are valid."
        )
    return f"Pinterest API error: {exc.message}"
