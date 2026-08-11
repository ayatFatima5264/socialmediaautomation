"""Tests for the Pinterest integration (OAuth v5, boards, publishing).

Runs against a throwaway SQLite database and a stubbed Pinterest API — no
network, no credentials, no state left behind. What's covered:

  * OAuth: scopes/endpoints match API v5, state validation, refresh, errors.
  * Boards: per-user isolation, the default board, deleted boards.
  * Publishing: board resolution, token refresh (proactive + reactive 401),
    and every Pinterest HTTP failure mapping to a safe user-facing message.
"""
from __future__ import annotations

import tempfile
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.timeutils import utcnow
from app.database import Base, get_db
from app.main import app
from app.models.social_account import SocialAccount
from app.schemas.post import Platform
from app.schemas.social_account import AccountStatus
from app.services.publisher.pinterest import PinterestPublisher
from app.services.social import pinterest_api
from app.services.social_accounts import oauth_state
from app.services.social_accounts.registry import get_provider


@pytest.fixture()
def session_factory():
    tmp = Path(tempfile.mkdtemp()) / "pinterest.db"
    engine = create_engine(f"sqlite:///{tmp}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, autocommit=False)
    engine.dispose()


@pytest.fixture()
def client(session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _register(client, email="pinterest@example.com"):
    client.post(
        "/auth/register",
        json={"email": email, "password": "correct-horse", "full_name": "Pin Tester"},
    )
    token = client.post(
        "/auth/login", data={"username": email, "password": "correct-horse"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _connect_pinterest(session_factory, user_id: int, **overrides) -> SocialAccount:
    """Insert a connected Pinterest account directly (skips the OAuth round-trip)."""
    db = session_factory()
    try:
        account = SocialAccount(
            user_id=user_id,
            platform=Platform.pinterest.value,
            access_token=overrides.pop("access_token", "pina-test-token"),
            refresh_token=overrides.pop("refresh_token", "pinr-test-refresh"),
            token_expires_at=overrides.pop("token_expires_at", utcnow() + timedelta(days=30)),
            scopes=overrides.pop(
                "scopes", "user_accounts:read boards:read boards:write pins:read pins:write"
            ),
            account_id="pintester",
            username="pintester",
            display_name="Pin Tester",
            status=AccountStatus.connected.value,
            connected_at=utcnow(),
            **overrides,
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        db.expunge(account)
        return account
    finally:
        db.close()


def _user_id(client, headers) -> int:
    return client.get("/auth/me", headers=headers).json()["id"]


# ---------------------------------------------------------------------------
# A stubbed Pinterest API. Routes requests by (method, path) so a test can say
# "boards/123 is a 404" without patching internals.
# ---------------------------------------------------------------------------
class FakePinterest:
    def __init__(self, routes: dict, *, api_base: str = pinterest_api.PINTEREST_API_BASE):
        self.routes = routes
        self.api_base = api_base
        self.calls: list[tuple[str, str, dict | None]] = []
        self.tokens_seen: list[str | None] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = str(request.url).removeprefix(f"{self.api_base}/").split("?")[0]
        key = (request.method, path)
        body = None
        if request.content:
            import json as _json

            body = _json.loads(request.content)
        self.calls.append((request.method, path, body))
        self.tokens_seen.append(request.headers.get("Authorization"))

        entry = self.routes.get(key)
        if entry is None:
            return httpx.Response(404, json={"code": 0, "message": "Not found"})
        if callable(entry):
            entry = entry(len([c for c in self.calls if c[:2] == key]))
        status, payload = entry
        return httpx.Response(status, json=payload)


@pytest.fixture()
def fake_pinterest(monkeypatch):
    """Install a stub transport for both the API client and OAuth token calls."""

    def install(routes: dict, *, token_response: tuple[int, dict] | None = None):
        fake = FakePinterest(routes)

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/oauth/token"):
                if token_response is None:
                    return httpx.Response(400, json={"message": "no token route"})
                status, payload = token_response
                return httpx.Response(status, json=payload)
            return fake.handler(request)

        real_client = httpx.AsyncClient

        def patched(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            return real_client(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", patched)
        return fake

    return install


# ---------------------------------------------------------------------------
# OAuth provider configuration
# ---------------------------------------------------------------------------
def test_provider_matches_api_v5_contract():
    p = get_provider(Platform.pinterest)
    assert p.authorize_endpoint == "https://www.pinterest.com/oauth/"
    assert p.token_endpoint == "https://api.pinterest.com/v5/oauth/token"
    # POST /v5/pins requires exactly these four; user_accounts:read powers the
    # profile card.
    for scope in ("boards:read", "boards:write", "pins:read", "pins:write"):
        assert scope in p.scopes
        assert scope in p.required_scopes
    assert "user_accounts:read" in p.scopes
    # Pinterest expects Basic client auth and comma-separated scopes.
    assert p.token_auth == "basic"
    assert p.scope_separator == ","
    # Continuous refresh: needed by apps created before 2025-09-25, ignored by newer ones.
    assert p.token_params == {"continuous_refresh": "true"}


def test_authorize_url_carries_state_and_scopes():
    p = get_provider(Platform.pinterest)
    url = p.authorize_url(state="signed-state")
    assert url.startswith("https://www.pinterest.com/oauth/?")
    assert "response_type=code" in url
    assert "state=signed-state" in url
    assert "boards%3Awrite" in url  # comma-joined, URL-encoded
    assert "%2Fapi%2Fauth%2Fpinterest%2Fcallback" in url


def test_client_secret_is_never_in_the_authorize_url(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "pinterest_client_secret", "super-secret")
    url = get_provider(Platform.pinterest).authorize_url(state="s")
    assert "super-secret" not in url


def test_redirect_uri_override_wins(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "pinterest_redirect_uri", "https://api.example.com/cb")
    assert get_provider(Platform.pinterest).redirect_uri == "https://api.example.com/cb"


# ---------------------------------------------------------------------------
# OAuth callback: cancellation, CSRF state, errors
# ---------------------------------------------------------------------------
def test_callback_handles_user_cancellation(client):
    r = client.get(
        "/api/auth/pinterest/callback",
        params={"error": "access_denied", "error_description": "user denied"},
        follow_redirects=False,
    )
    assert r.status_code == 307
    assert "error=access_denied" in r.headers["location"]
    assert "platform=pinterest" in r.headers["location"]


def test_callback_rejects_a_tampered_state(client):
    r = client.get(
        "/api/auth/pinterest/callback",
        params={"code": "abc", "state": "not-a-signed-state"},
        follow_redirects=False,
    )
    assert r.status_code == 307
    assert "Invalid+or+expired+authorization+state" in r.headers["location"]


def test_callback_rejects_state_minted_for_another_platform(client):
    state = oauth_state.encode_state(user_id=1, slug="linkedin", code_verifier=None)
    r = client.get(
        "/api/auth/pinterest/callback",
        params={"code": "abc", "state": state},
        follow_redirects=False,
    )
    assert "does+not+match+platform" in r.headers["location"]


def test_callback_without_a_code_is_rejected(client):
    r = client.get(
        "/api/auth/pinterest/callback", params={"state": "x"}, follow_redirects=False
    )
    assert "error=missing_code" in r.headers["location"]


def test_connect_requires_credentials(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "pinterest_client_id", None)
    monkeypatch.setattr(settings, "pinterest_client_secret", None)
    headers = _register(client, "noconfig@example.com")
    r = client.post("/api/social/pinterest/connect", headers=headers)
    assert r.status_code == 503
    assert "not configured" in r.json()["detail"]


def test_connect_returns_an_authorize_url(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "pinterest_client_id", "test-id")
    monkeypatch.setattr(settings, "pinterest_client_secret", "test-secret")
    headers = _register(client, "connect@example.com")
    r = client.post("/api/social/pinterest/connect", headers=headers)
    assert r.status_code == 200
    url = r.json()["authorize_url"]
    assert url.startswith("https://www.pinterest.com/oauth/?")
    assert "test-secret" not in url


# ---------------------------------------------------------------------------
# Account state: reconnect signalling, token-free serialization
# ---------------------------------------------------------------------------
def test_account_missing_a_publishing_scope_is_flagged_for_reconnect(
    client, session_factory
):
    headers = _register(client, "oldscopes@example.com")
    # Connected before boards:write was requested.
    _connect_pinterest(
        session_factory,
        _user_id(client, headers),
        scopes="user_accounts:read boards:read pins:read pins:write",
    )
    account = client.get("/api/social/pinterest", headers=headers).json()
    assert account["reauth_required"] is True
    assert account["status"] == "connected"  # still usable, just needs re-auth


def test_account_response_never_exposes_tokens(client, session_factory):
    headers = _register(client, "notokens@example.com")
    _connect_pinterest(session_factory, _user_id(client, headers))
    body = client.get("/api/social/pinterest", headers=headers).text
    assert "pina-test-token" not in body
    assert "pinr-test-refresh" not in body
    assert "access_token" not in body


def test_expired_token_surfaces_as_token_expired(client, session_factory):
    headers = _register(client, "expired@example.com")
    _connect_pinterest(
        session_factory,
        _user_id(client, headers),
        token_expires_at=utcnow() - timedelta(hours=1),
    )
    assert client.get("/api/social/pinterest", headers=headers).json()["status"] == (
        "token_expired"
    )


def test_disconnect_then_reconnect(client, session_factory, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "pinterest_client_id", "test-id")
    monkeypatch.setattr(settings, "pinterest_client_secret", "test-secret")
    headers = _register(client, "reconnect@example.com")
    _connect_pinterest(session_factory, _user_id(client, headers))

    # A live connection can't be duplicated...
    assert client.post("/api/social/pinterest/connect", headers=headers).status_code == 409
    # ...until it's disconnected, after which connecting starts a fresh OAuth run.
    assert client.delete("/api/social/pinterest", headers=headers).status_code == 200
    assert client.get("/api/social/pinterest", headers=headers).status_code == 404
    r = client.post("/api/social/pinterest/connect", headers=headers)
    assert r.status_code == 200 and r.json()["authorize_url"]


# ---------------------------------------------------------------------------
# Boards endpoint
# ---------------------------------------------------------------------------
BOARDS_PAGE = (
    200,
    {
        "items": [
            {"id": "111", "name": "Recipes", "privacy": "PUBLIC"},
            {"id": "222", "name": "Ideas", "privacy": "SECRET"},
        ],
        "bookmark": None,
    },
)


def test_boards_require_a_connected_account(client):
    headers = _register(client, "noboards@example.com")
    r = client.get("/api/social/pinterest/boards", headers=headers)
    assert r.status_code == 404
    assert r.json()["detail"] == "Pinterest is not connected."


def test_boards_require_authentication(client):
    assert client.get("/api/social/pinterest/boards").status_code == 401


def test_boards_are_listed_with_the_default(client, session_factory, fake_pinterest):
    fake_pinterest({("GET", "boards"): BOARDS_PAGE, ("GET", "boards/111"): (200, {"id": "111", "name": "Recipes"})})
    headers = _register(client, "boards@example.com")
    _connect_pinterest(session_factory, _user_id(client, headers))

    r = client.get("/api/social/pinterest/boards", headers=headers)
    assert r.status_code == 200
    assert [b["name"] for b in r.json()["boards"]] == ["Recipes", "Ideas"]
    assert r.json()["default_board_id"] is None

    # Setting a default verifies the board exists first, then stores its id.
    assert (
        client.put(
            "/api/social/pinterest/default-board",
            json={"board_id": "111"},
            headers=headers,
        ).status_code
        == 200
    )
    assert client.get("/api/social/pinterest/boards", headers=headers).json()[
        "default_board_id"
    ] == "111"


def test_setting_a_deleted_board_as_default_is_rejected(
    client, session_factory, fake_pinterest
):
    fake_pinterest({("GET", "boards/999"): (404, {"code": 4, "message": "Board not found"})})
    headers = _register(client, "gone@example.com")
    _connect_pinterest(session_factory, _user_id(client, headers))

    r = client.put(
        "/api/social/pinterest/default-board", json={"board_id": "999"}, headers=headers
    )
    assert r.status_code == 404
    assert "no longer exists" in r.json()["detail"]


def test_board_pagination_follows_bookmarks(client, session_factory, fake_pinterest):
    def paged(call_number: int):
        if call_number == 1:
            return (200, {"items": [{"id": "1", "name": "First"}], "bookmark": "b2"})
        return (200, {"items": [{"id": "2", "name": "Second"}], "bookmark": None})

    fake_pinterest({("GET", "boards"): paged})
    headers = _register(client, "paged@example.com")
    _connect_pinterest(session_factory, _user_id(client, headers))

    names = [b["name"] for b in client.get(
        "/api/social/pinterest/boards", headers=headers
    ).json()["boards"]]
    assert names == ["First", "Second"]


def test_boards_401_asks_the_user_to_reconnect(client, session_factory, fake_pinterest):
    """A rejected Pinterest token must NOT be reported as 401.

    The frontend clears the login token on any 401 (see lib/api.js), so
    returning one here would sign the user out of AutoSocial AI because one
    connected account went stale. It becomes a 409 instead.
    """
    fake_pinterest({("GET", "boards"): (401, {"code": 2, "message": "Authentication failed"})})
    headers = _register(client, "unauth@example.com")
    _connect_pinterest(session_factory, _user_id(client, headers))

    r = client.get("/api/social/pinterest/boards", headers=headers)
    assert r.status_code == 409
    assert "Reconnect" in r.json()["detail"]
    # The account is flagged so the card offers a Reconnect button.
    assert client.get("/api/social/pinterest", headers=headers).json()["status"] == "error"
    # ...and the user is still signed in.
    assert client.get("/auth/me", headers=headers).status_code == 200


def test_no_pinterest_endpoint_ever_answers_401_for_a_signed_in_user(
    client, session_factory, fake_pinterest
):
    """Guards the whole surface, not just the one path above."""
    failures = {
        ("GET", "boards"): (403, {"code": 7, "message": "Forbidden"}),
        ("GET", "boards/1"): (403, {"code": 7, "message": "Forbidden"}),
    }
    fake_pinterest(failures)
    headers = _register(client, "no401@example.com")
    _connect_pinterest(
        session_factory,
        _user_id(client, headers),
        # Expired token with an unusable refresh token: forces the refresh path too.
        token_expires_at=utcnow() - timedelta(days=1),
    )

    for call in (
        lambda: client.get("/api/social/pinterest/boards", headers=headers),
        lambda: client.put(
            "/api/social/pinterest/default-board",
            json={"board_id": "1"},
            headers=headers,
        ),
    ):
        assert call().status_code != 401
    assert client.get("/auth/me", headers=headers).status_code == 200


def test_boards_429_is_reported_as_a_rate_limit(client, session_factory, fake_pinterest):
    fake_pinterest({("GET", "boards"): (429, {"code": 8, "message": "Too many requests"})})
    headers = _register(client, "rate@example.com")
    _connect_pinterest(session_factory, _user_id(client, headers))

    r = client.get("/api/social/pinterest/boards", headers=headers)
    assert r.status_code == 429
    assert "rate limit" in r.json()["detail"].lower()


def test_one_user_cannot_see_another_users_boards(
    client, session_factory, fake_pinterest
):
    """The board list is looked up as (caller, pinterest) — never by account id."""
    fake_pinterest({("GET", "boards"): BOARDS_PAGE})
    owner = _register(client, "owner@example.com")
    _connect_pinterest(session_factory, _user_id(client, owner))

    intruder = _register(client, "intruder@example.com")
    r = client.get("/api/social/pinterest/boards", headers=intruder)
    assert r.status_code == 404  # the intruder has no Pinterest connection
    assert client.get("/api/social/pinterest", headers=intruder).status_code == 404


# ---------------------------------------------------------------------------
# Publishing
# ---------------------------------------------------------------------------
PIN_OK = (201, {"id": "pin-123"})


@pytest.mark.anyio
async def test_publish_creates_a_pin_on_the_selected_board(
    session_factory, fake_pinterest
):
    fake = fake_pinterest(
        {("GET", "boards/111"): (200, {"id": "111", "name": "Recipes"}), ("POST", "pins"): PIN_OK}
    )
    account = _connect_pinterest(session_factory, 1)
    db = session_factory()
    result = await PinterestPublisher(db.merge(account), db).publish(
        content="Autumn soup\nWarming and easy",
        hashtags=["soup", "autumn"],
        media_urls=["https://cdn.example.com/soup.png"],
        options={"board_id": "111", "link": "https://example.com/recipe"},
    )
    db.close()

    assert result.success is True
    assert result.external_id == "pin-123"
    body = next(b for m, p, b in fake.calls if (m, p) == ("POST", "pins"))
    assert body["board_id"] == "111"
    assert body["title"] == "Autumn soup"  # first line
    assert "#soup" in body["description"]
    assert body["link"] == "https://example.com/recipe"
    assert body["media_source"] == {
        "source_type": "image_url",
        "url": "https://cdn.example.com/soup.png",
    }


@pytest.mark.anyio
async def test_publish_without_an_image_fails_clearly(session_factory, fake_pinterest):
    fake_pinterest({})
    account = _connect_pinterest(session_factory, 1)
    db = session_factory()
    result = await PinterestPublisher(db.merge(account), db).publish(
        content="Text only", hashtags=[], options={"board_id": "111"}
    )
    db.close()
    assert result.success is False
    assert "can't be text-only" in result.error


@pytest.mark.anyio
async def test_publish_falls_back_to_the_default_board(session_factory, fake_pinterest):
    fake = fake_pinterest(
        {("GET", "boards/777"): (200, {"id": "777", "name": "Default"}), ("POST", "pins"): PIN_OK}
    )
    account = _connect_pinterest(session_factory, 1, page_id="777")
    db = session_factory()
    result = await PinterestPublisher(db.merge(account), db).publish(
        content="Pin me", hashtags=[], media_urls=["https://cdn.example.com/a.png"]
    )
    db.close()
    assert result.success is True
    body = next(b for m, p, b in fake.calls if (m, p) == ("POST", "pins"))
    assert body["board_id"] == "777"


@pytest.mark.anyio
async def test_publish_reports_a_deleted_board(session_factory, fake_pinterest):
    fake_pinterest({("GET", "boards/111"): (404, {"code": 4, "message": "Board not found"})})
    account = _connect_pinterest(session_factory, 1)
    db = session_factory()
    result = await PinterestPublisher(db.merge(account), db).publish(
        content="Pin me",
        hashtags=[],
        media_urls=["https://cdn.example.com/a.png"],
        options={"board_id": "111"},
    )
    db.close()
    assert result.success is False
    assert "no longer exists" in result.error


@pytest.mark.anyio
async def test_publish_with_no_board_and_several_boards_asks_the_user_to_choose(
    session_factory, fake_pinterest
):
    fake_pinterest({("GET", "boards"): BOARDS_PAGE})
    account = _connect_pinterest(session_factory, 1)
    db = session_factory()
    result = await PinterestPublisher(db.merge(account), db).publish(
        content="Pin me", hashtags=[], media_urls=["https://cdn.example.com/a.png"]
    )
    db.close()
    assert result.success is False
    assert "Choose which Pinterest board" in result.error


@pytest.mark.anyio
async def test_publish_with_no_boards_at_all(session_factory, fake_pinterest):
    fake_pinterest({("GET", "boards"): (200, {"items": [], "bookmark": None})})
    account = _connect_pinterest(session_factory, 1)
    db = session_factory()
    result = await PinterestPublisher(db.merge(account), db).publish(
        content="Pin me", hashtags=[], media_urls=["https://cdn.example.com/a.png"]
    )
    db.close()
    assert result.success is False
    assert "No Pinterest board found" in result.error


@pytest.mark.anyio
async def test_publish_refreshes_an_expiring_token_first(session_factory, fake_pinterest):
    fake = fake_pinterest(
        {("GET", "boards/111"): (200, {"id": "111"}), ("POST", "pins"): PIN_OK},
        token_response=(
            200,
            {
                "access_token": "pina-fresh",
                "refresh_token": "pinr-rotated",
                "expires_in": 2592000,
                "scope": "boards:read boards:write pins:read pins:write",
            },
        ),
    )
    account = _connect_pinterest(
        session_factory, 1, token_expires_at=utcnow() + timedelta(seconds=30)
    )
    db = session_factory()
    live = db.merge(account)
    result = await PinterestPublisher(live, db).publish(
        content="Pin me",
        hashtags=[],
        media_urls=["https://cdn.example.com/a.png"],
        options={"board_id": "111"},
    )

    assert result.success is True
    # The rotated tokens were persisted, and the Pin used the fresh one.
    db.refresh(live)
    assert live.access_token == "pina-fresh"
    assert live.refresh_token == "pinr-rotated"
    assert "Bearer pina-fresh" in fake.tokens_seen
    db.close()


@pytest.mark.anyio
async def test_publish_retries_once_after_a_401(session_factory, fake_pinterest):
    def pins(call_number: int):
        if call_number == 1:
            return (401, {"code": 2, "message": "Authentication failed"})
        return PIN_OK

    fake = fake_pinterest(
        {("GET", "boards/111"): (200, {"id": "111"}), ("POST", "pins"): pins},
        token_response=(
            200, {"access_token": "pina-after-401", "refresh_token": "r2", "expires_in": 2592000}
        ),
    )
    account = _connect_pinterest(session_factory, 1)
    db = session_factory()
    result = await PinterestPublisher(db.merge(account), db).publish(
        content="Pin me",
        hashtags=[],
        media_urls=["https://cdn.example.com/a.png"],
        options={"board_id": "111"},
    )
    db.close()

    assert result.success is True
    assert result.external_id == "pin-123"
    assert len([c for c in fake.calls if c[:2] == ("POST", "pins")]) == 2


@pytest.mark.anyio
async def test_publish_reports_a_failed_refresh_as_reconnect(
    session_factory, fake_pinterest
):
    fake_pinterest(
        {("GET", "boards/111"): (200, {"id": "111"})},
        token_response=(400, {"message": "invalid_grant"}),
    )
    account = _connect_pinterest(
        session_factory, 1, token_expires_at=utcnow() - timedelta(days=1)
    )
    db = session_factory()
    result = await PinterestPublisher(db.merge(account), db).publish(
        content="Pin me",
        hashtags=[],
        media_urls=["https://cdn.example.com/a.png"],
        options={"board_id": "111"},
    )
    db.close()
    assert result.success is False
    assert "Reconnect your Pinterest account" in result.error


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "payload", "expected"),
    [
        (400, {"code": 3, "message": "Invalid image."}, "Pinterest rejected the Pin"),
        (403, {"code": 7, "message": "Forbidden"}, "missing a required permission"),
        (429, {"code": 8, "message": "Too many requests"}, "rate limit reached"),
        (500, {"code": 1, "message": "Server error"}, "having trouble right now"),
    ],
)
async def test_pin_api_errors_become_safe_user_messages(
    session_factory, fake_pinterest, status, payload, expected
):
    fake_pinterest(
        {("GET", "boards/111"): (200, {"id": "111"}), ("POST", "pins"): (status, payload)}
    )
    account = _connect_pinterest(session_factory, 1)
    db = session_factory()
    result = await PinterestPublisher(db.merge(account), db).publish(
        content="Pin me",
        hashtags=[],
        media_urls=["https://cdn.example.com/a.png"],
        options={"board_id": "111"},
    )
    db.close()

    assert result.success is False
    assert expected in result.error
    # A failure message must never leak the credential that produced it.
    assert "pina-test-token" not in result.error
    assert "pinr-test-refresh" not in result.error


@pytest.mark.anyio
async def test_pin_title_and_description_respect_pinterest_limits(
    session_factory, fake_pinterest
):
    fake = fake_pinterest(
        {("GET", "boards/111"): (200, {"id": "111"}), ("POST", "pins"): PIN_OK}
    )
    account = _connect_pinterest(session_factory, 1)
    db = session_factory()
    await PinterestPublisher(db.merge(account), db).publish(
        content="T" * 300 + "\n" + "D" * 1200,
        hashtags=["x"],
        media_urls=["https://cdn.example.com/a.png"],
        options={"board_id": "111"},
    )
    db.close()

    body = next(b for m, p, b in fake.calls if (m, p) == ("POST", "pins"))
    assert len(body["title"]) == pinterest_api.TITLE_MAX
    assert len(body["description"]) == pinterest_api.DESCRIPTION_MAX


# ---------------------------------------------------------------------------
# Scheduling — Pinterest rides the existing scheduler
# ---------------------------------------------------------------------------
def test_scheduled_pin_stores_its_board_and_publishes_through_the_scheduler(
    client, session_factory, fake_pinterest
):
    fake = fake_pinterest(
        {("GET", "boards/111"): (200, {"id": "111"}), ("POST", "pins"): PIN_OK}
    )
    headers = _register(client, "scheduled@example.com")
    _connect_pinterest(session_factory, _user_id(client, headers))

    created = client.post(
        "/api/posts",
        json={
            "platform": "pinterest",
            "content": "Scheduled pin",
            "hashtags": ["autumn"],
            "media": [{"type": "image", "url": "https://cdn.example.com/a.png"}],
            "platform_options": {"board_id": "111", "link": "https://example.com"},
        },
        headers=headers,
    ).json()
    assert created["platform_options"] == {
        "board_id": "111",
        "link": "https://example.com",
    }

    # The scheduler's publish path is the same one "publish now" uses.
    published = client.post(f"/api/posts/{created['id']}/publish", headers=headers).json()
    assert published["status"] == "published"
    assert published["external_id"] == "pin-123"
    body = next(b for m, p, b in fake.calls if (m, p) == ("POST", "pins"))
    assert body["board_id"] == "111"


def test_scheduled_pin_records_the_failure_reason(
    client, session_factory, fake_pinterest
):
    fake_pinterest({("GET", "boards/111"): (404, {"code": 4, "message": "Board not found"})})
    headers = _register(client, "schedfail@example.com")
    _connect_pinterest(session_factory, _user_id(client, headers))

    created = client.post(
        "/api/posts",
        json={
            "platform": "pinterest",
            "content": "Doomed pin",
            "media": [{"type": "image", "url": "https://cdn.example.com/a.png"}],
            "platform_options": {"board_id": "111"},
        },
        headers=headers,
    ).json()
    published = client.post(f"/api/posts/{created['id']}/publish", headers=headers).json()

    assert published["status"] == "failed"
    assert "no longer exists" in published["error"]


def test_a_user_cannot_publish_another_users_post(client, session_factory):
    owner = _register(client, "owner2@example.com")
    created = client.post(
        "/api/posts",
        json={"platform": "pinterest", "content": "Mine"},
        headers=owner,
    ).json()

    intruder = _register(client, "intruder2@example.com")
    assert client.post(
        f"/api/posts/{created['id']}/publish", headers=intruder
    ).status_code == 404


@pytest.fixture()
def anyio_backend():
    return "asyncio"
