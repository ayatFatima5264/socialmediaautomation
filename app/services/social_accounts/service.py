"""Social Accounts orchestration — the business logic behind the routes.

Ties together the repository (persistence), the OAuth providers (platform I/O)
and the connect/refresh/disconnect rules. Routes stay thin; the rules live here.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.timeutils import utcnow
from app.models.pending_connection import PendingConnection
from app.models.social_account import SocialAccount
from app.models.user import User
from app.repositories import SocialAccountRepository
from app.schemas.post import Platform
from app.schemas.social_account import (
    AccountCandidate,
    AccountsOverview,
    AccountStatus,
    PendingConnectionRead,
    PlatformSummary,
    SocialAccountRead,
)
from app.services.social_accounts import oauth_state, pending
from app.services.social_accounts.base import (
    OAuthError,
    OAuthProvider,
    OAuthTokens,
    ProfileInfo,
    generate_pkce_pair,
)
from app.services.social_accounts.registry import (
    PROVIDERS,
    get_provider,
    provider_for_slug,
)

logger = logging.getLogger(__name__)


class ConnectError(Exception):
    """A connect/refresh could not proceed; carries an HTTP status + message."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class CallbackResult:
    """Outcome of an OAuth callback.

    status "connected" — a single account was stored.
    status "select"    — several candidates; `pending_id` identifies the choice.
    """

    status: str
    platform: Platform
    pending_id: str | None = None


# --------------------------------------------------------------------------
# Serialization / status
# --------------------------------------------------------------------------
def effective_status(account: SocialAccount) -> AccountStatus:
    """The status to show the UI, accounting for expiry since it was stored."""
    if (
        account.status == AccountStatus.connected.value
        and account.token_expires_at is not None
        and account.token_expires_at <= utcnow()
    ):
        return AccountStatus.token_expired
    try:
        return AccountStatus(account.status)
    except ValueError:
        return AccountStatus.error


def serialize(account: SocialAccount) -> SocialAccountRead:
    read = SocialAccountRead.model_validate(account)
    read.status = effective_status(account)
    read.reauth_required = reauth_required(account)
    return read


def build_overview(db: Session, user: User) -> AccountsOverview:
    repo = SocialAccountRepository(db)
    accounts = repo.list_for_user(user.id)
    by_platform = {a.platform: a for a in accounts}

    summary: list[PlatformSummary] = []
    for platform in Platform:
        account = by_platform.get(platform.value)
        summary.append(
            PlatformSummary(
                platform=platform,
                connected=account is not None,
                status=effective_status(account)
                if account
                else AccountStatus.not_connected,
            )
        )

    reads = [serialize(a) for a in accounts]
    return AccountsOverview(
        accounts=reads,
        summary=summary,
        connected_count=len(accounts),
        total_platforms=len(Platform),
    )


def get_account(db: Session, user: User, platform: Platform) -> SocialAccount | None:
    return SocialAccountRepository(db).get(user.id, platform)


# --------------------------------------------------------------------------
# Connect
# --------------------------------------------------------------------------
def start_connect(db: Session, user: User, platform: Platform) -> dict:
    """Begin connecting a platform via real OAuth.

    Always returns {"authorize_url": "..."} for the client to redirect to — there
    is no simulated/mock path. If the platform has no credentials configured, a
    503 is raised. Enforces one-account-per-platform: a live connection can't be
    duplicated (an expired one may be reconnected).
    """
    repo = SocialAccountRepository(db)
    existing = repo.get(user.id, platform)
    # A live connection can't be duplicated — except when it needs
    # re-authorization (a newly-required scope is missing), in which case
    # reconnecting is exactly how the user grants it.
    if (
        existing is not None
        and effective_status(existing) == AccountStatus.connected
        and not reauth_required(existing)
    ):
        raise ConnectError(
            f"{platform.value.capitalize()} account already connected.", status_code=409
        )

    provider = get_provider(platform)
    if not provider.is_configured:
        raise ConnectError(
            f"{platform.value.capitalize()} is not configured. Add its OAuth "
            "credentials to .env (see docs/OAUTH_CALLBACKS.md).",
            status_code=503,
        )
    return {"authorize_url": _build_authorize_url(user, provider)}


def _build_authorize_url(user: User, provider: OAuthProvider) -> str:
    code_verifier = None
    code_challenge = None
    if provider.use_pkce:
        code_verifier, code_challenge = generate_pkce_pair()
    state = oauth_state.encode_state(
        user_id=user.id, slug=provider.slug, code_verifier=code_verifier
    )
    return provider.authorize_url(state=state, code_challenge=code_challenge)


async def complete_callback(db: Session, slug: str, code: str, state: str) -> CallbackResult:
    """Handle an OAuth redirect: verify state, exchange code, connect or choose.

    Returns a CallbackResult: `status="connected"` when a single account was
    stored, or `status="select"` (with `pending_id`) when the user must pick from
    several. Raises OAuthError / ConnectError with a user-safe message on failure.
    """
    provider = provider_for_slug(slug)
    if provider is None:
        raise ConnectError(f"Unknown platform '{slug}'.", status_code=404)

    try:
        decoded = oauth_state.decode_state(state)
    except Exception as exc:  # noqa: BLE001 — invalid/expired/tampered state
        raise ConnectError("Invalid or expired authorization state.", 400) from exc

    if decoded["slug"] != slug:
        raise ConnectError("Authorization state does not match platform.", 400)

    user = db.get(User, decoded["user_id"])
    if user is None:
        raise ConnectError("Unknown user for this authorization.", 400)

    logger.info("OAuth callback: exchanging code for %s (user %s)", slug, user.id)
    tokens = await provider.exchange_code(code, code_verifier=decoded["code_verifier"])
    accounts = await provider.list_accounts(tokens)

    if not accounts:
        logger.info("No connectable %s account for user %s", slug, user.id)
        raise ConnectError(provider.no_accounts_error, 400)

    if len(accounts) == 1:
        repo = SocialAccountRepository(db)
        _upsert(repo, user, provider.platform, tokens=tokens, profile=accounts[0])
        logger.info(
            "Connected %s account @%s (user %s)",
            provider.platform.value, accounts[0].username, user.id,
        )
        return CallbackResult(status="connected", platform=provider.platform)

    # Several candidates — let the user choose which one to connect.
    row = pending.create(
        db, user_id=user.id, platform=provider.platform, tokens=tokens, candidates=accounts
    )
    logger.info(
        "%s: %d candidate accounts for user %s — awaiting selection",
        slug, len(accounts), user.id,
    )
    return CallbackResult(status="select", platform=provider.platform, pending_id=row.id)


# --------------------------------------------------------------------------
# Multi-account selection
# --------------------------------------------------------------------------
def get_pending(db: Session, user: User, pending_id: str) -> PendingConnectionRead:
    """Return the candidate accounts for a pending selection (no tokens)."""
    row = pending.get(db, pending_id, user.id)
    if row is None:
        raise ConnectError("This account selection has expired. Please reconnect.", 404)
    candidates = [
        AccountCandidate(
            account_id=c.account_id,
            username=c.username,
            display_name=c.display_name,
            profile_picture=c.profile_picture,
            page_name=c.page_name,
        )
        for c in pending.candidates_of(row)
    ]
    return PendingConnectionRead(
        id=row.id, platform=Platform(row.platform), candidates=candidates
    )


def select_account(
    db: Session, user: User, pending_id: str, account_id: str
) -> SocialAccount:
    """Finish a multi-account connect: store the chosen candidate only."""
    row = pending.get(db, pending_id, user.id)
    if row is None:
        raise ConnectError("This account selection has expired. Please reconnect.", 404)

    chosen = next(
        (c for c in pending.candidates_of(row) if c.account_id == account_id), None
    )
    if chosen is None:
        raise ConnectError("That account is not part of this selection.", 400)

    platform = Platform(row.platform)
    repo = SocialAccountRepository(db)
    account = _upsert(repo, user, platform, tokens=pending.tokens_of(row), profile=chosen)
    pending.delete(db, row)
    logger.info(
        "Connected %s account @%s (user %s) via selection",
        platform.value, chosen.username, user.id,
    )
    return account


# --------------------------------------------------------------------------
# Scope / re-authorization
# --------------------------------------------------------------------------
def missing_required_scopes(account: SocialAccount) -> list[str]:
    """Required scopes the account's stored token was NOT granted.

    Compares the platform provider's `required_scopes` against the scopes we
    recorded at connect time. An account connected before a scope became required
    has it missing (its stored scopes are NULL or lack the entry), which is
    exactly the reconnect case. Providers with no required_scopes never match.
    """
    provider = get_provider(Platform(account.platform))
    required = getattr(provider, "required_scopes", None) or []
    if not required:
        return []
    granted = set((account.scopes or "").split())
    return [scope for scope in required if scope not in granted]


def reauth_required(account: SocialAccount) -> bool:
    """True if the account must be reconnected to grant a newly-required scope.

    This never disconnects the account — it only signals that re-authorization is
    needed (e.g. X's media.write for image/video posting). Text-only publishing
    keeps working, so the account stays connected.
    """
    return bool(missing_required_scopes(account))


# --------------------------------------------------------------------------
# Token lifecycle (used by publishers before calling a platform API)
# --------------------------------------------------------------------------
def token_needs_refresh(account: SocialAccount, *, leeway_seconds: int = 120) -> bool:
    """True if the account's access token is expired or about to expire.

    Only refreshable accounts qualify: one with no stored refresh token, or no
    known expiry (a long-lived token), is left untouched. `leeway_seconds` gives
    callers a margin so they refresh just before a token would lapse mid-request.
    """
    if not account.refresh_token or account.token_expires_at is None:
        return False
    return account.token_expires_at <= utcnow() + timedelta(seconds=leeway_seconds)


async def refresh_tokens(db: Session, account: SocialAccount) -> SocialAccount:
    """Force-refresh an account's OAuth tokens and persist them, in place.

    Reuses the platform provider's `refresh()` and the shared token-application
    logic so publishers never duplicate token handling. Persists immediately so a
    later failure in the same request can't lose a freshly rotated refresh token.
    Raises OAuthError if there is no refresh token or the provider refresh fails.
    """
    if not account.refresh_token:
        raise OAuthError("No refresh token stored — reconnect the account.")
    provider = get_provider(Platform(account.platform))
    tokens = await provider.refresh(account.refresh_token)
    _apply_tokens(account, tokens)
    account.last_synced_at = utcnow()
    db.commit()
    db.refresh(account)
    return account


# --------------------------------------------------------------------------
# Refresh
# --------------------------------------------------------------------------
async def refresh_account(db: Session, user: User, platform: Platform) -> SocialAccount:
    repo = SocialAccountRepository(db)
    account = repo.get(user.id, platform)
    if account is None:
        raise ConnectError(f"{platform.value.capitalize()} is not connected.", 404)

    provider = get_provider(platform)
    if not provider.is_configured:
        raise ConnectError(
            f"{platform.value.capitalize()} is not configured — cannot refresh.", 503
        )

    if not account.refresh_token and platform not in (
        Platform.instagram,
        Platform.threads,
    ):
        raise ConnectError(
            f"{platform.value.capitalize()} has no refresh token — reconnect it.", 400
        )

    try:
        # Instagram/Threads refresh the long-lived access token itself.
        token_arg = account.refresh_token or account.access_token
        tokens = await provider.refresh(token_arg)
    except (OAuthError, NotImplementedError) as exc:
        account.status = AccountStatus.error.value
        repo.save(account)
        raise ConnectError(f"Refresh failed: {exc}", 400) from exc

    _apply_tokens(account, tokens)
    account.status = AccountStatus.connected.value
    account.last_synced_at = utcnow()
    return repo.save(account)


# --------------------------------------------------------------------------
# Disconnect
# --------------------------------------------------------------------------
def disconnect(db: Session, user: User, platform: Platform) -> None:
    repo = SocialAccountRepository(db)
    account = repo.get(user.id, platform)
    if account is None:
        raise ConnectError(f"{platform.value.capitalize()} is not connected.", 404)
    repo.delete(account)


# --------------------------------------------------------------------------
# Internals
# --------------------------------------------------------------------------
def _upsert(
    repo: SocialAccountRepository,
    user: User,
    platform: Platform,
    *,
    tokens: OAuthTokens,
    profile: ProfileInfo,
) -> SocialAccount:
    account = repo.get(user.id, platform)
    is_new = account is None
    if account is None:
        account = SocialAccount(user_id=user.id, platform=platform.value)

    _apply_tokens(account, tokens)
    # Record the scopes granted for this token so we can later detect when a
    # newly-required scope is missing. X returns `scope` in the token response;
    # if a provider omits it, fall back to the scopes we requested (OAuth 2.0
    # auth-code grants all requested scopes on consent — none are partial).
    provider = get_provider(platform)
    account.scopes = tokens.raw.get("scope") or " ".join(provider.scopes) or None
    account.account_id = profile.account_id or account.account_id or f"{platform.value}:{user.id}"
    account.page_id = profile.page_id
    account.username = profile.username
    account.display_name = profile.display_name
    account.profile_picture = profile.profile_picture
    account.status = AccountStatus.connected.value
    account.last_synced_at = utcnow()
    if is_new or account.connected_at is None:
        account.connected_at = utcnow()

    try:
        return repo.add(account) if is_new else repo.save(account)
    except IntegrityError as exc:  # unique (user, platform) — concurrent connect
        repo.db.rollback()
        raise ConnectError(
            f"{platform.value.capitalize()} account already connected.", 409
        ) from exc


def _apply_tokens(account: SocialAccount, tokens: OAuthTokens) -> None:
    account.access_token = tokens.access_token
    if tokens.refresh_token:
        account.refresh_token = tokens.refresh_token
    account.token_expires_at = (
        utcnow() + timedelta(seconds=tokens.expires_in) if tokens.expires_in else None
    )
