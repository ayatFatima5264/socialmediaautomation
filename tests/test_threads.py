"""Tests for the Threads integration (OAuth, token lifecycle, publishing).

Runs against a throwaway SQLite database and a stubbed Threads API — no
network, no credentials, no state left behind. What's covered:

  * OAuth: scopes/endpoints match the Threads API, state validation, the
    long-lived exchange, and refresh (which uses the access token).
  * Publishing: the two-step container flow for text and image posts, token
    refresh (proactive + reactive), and every failure mapping to a safe message.
  * Scheduling and per-user isolation through the existing endpoints.
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
from app.services.publisher.threads import POST_MAX_CHARS, ThreadsPublisher
from app.services.social import threads_api
from app.services.social_accounts import oauth_state
from app.services.social_accounts.registry import get_provider


@pytest.fixture()
def session_factory():
    tmp = Path(tempfile.mkdtemp()) / "threads.db"
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


def _register(client, email="threads@example.com"):
    client.post(
        "/auth/register",
        json={"email": email, "password": "correct-horse", "full_name": "Threads User"},
    )
    token = client.post(
        "/auth/login", data={"username": email, "password": "correct-horse"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _connect_threads(session_factory, user_id: int, **overrides) -> SocialAccount:
    db = session_factory()
    try:
        account = SocialAccount(
            user_id=user_id,
            platform=Platform.threads.value,
            access_token=overrides.pop("access_token", "th-long-lived-token"),
            token_expires_at=overrides.pop(
                "token_expires_at", utcnow() + timedelta(days=60)
            ),
            scopes=overrides.pop("scopes", "threads_basic threads_content_publish"),
            account_id=overrides.pop("account_id", "17841400000000000"),
            username="threadsuser",
            display_name="Threads User",
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
# A stubbed Threads API, routed by (method, path).
# ---------------------------------------------------------------------------
class FakeThreads:
    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[tuple[str, str, dict]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.split("/v1.0/", 1)[-1].lstrip("/")
        params = dict(request.url.params)
        key = (request.method, path)
        self.calls.append((request.method, path, params))

        entry = self.routes.get(key)
        if entry is None:
            return httpx.Response(
                400, json={"error": {"message": "Unknown Graph path", "code": 100}}
            )
        if callable(entry):
            entry = entry(len([c for c in self.calls if c[:2] == key]))
        status, payload = entry
        return httpx.Response(status, json=payload)

    def params_for(self, method: str, path: str) -> dict:
        return next(p for m, pa, p in self.calls if (m, pa) == (method, path))


@pytest.fixture()
def fake_threads(monkeypatch):
    """Stub the Graph transport, including the token endpoints."""

    def install(routes: dict, *, token_response: tuple[int, dict] | None = None):
        fake = FakeThreads(routes)

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith(("/access_token", "/refresh_access_token")):
                if token_response is None:
                    return httpx.Response(
                        400, json={"error": {"message": "no token route"}}
                    )
                status, payload = token_response
                return httpx.Response(status, json=payload)
            return fake.handler(request)

        real_client = httpx.AsyncClient
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda *a, **kw: real_client(
                *a, **{**kw, "transport": httpx.MockTransport(handler)}
            ),
        )
        return fake

    return install


# ---------------------------------------------------------------------------
# OAuth provider configuration
# ---------------------------------------------------------------------------
def test_provider_matches_the_threads_api_contract():
    p = get_provider(Platform.threads)
    assert p.authorize_endpoint == "https://threads.net/oauth/authorize"
    assert p.token_endpoint == "https://graph.threads.net/oauth/access_token"
    assert p.scopes == ["threads_basic", "threads_content_publish"]
    # Both are needed to publish, so a connection missing one asks to reconnect.
    assert p.required_scopes == ["threads_basic", "threads_content_publish"]
    assert p.scope_separator == ","
    # Threads issues no refresh token — the access token renews itself.
    assert p.refresh_uses_access_token is True


def test_authorize_url_carries_state_and_scopes():
    p = get_provider(Platform.threads)
    url = p.authorize_url(state="signed-state")
    assert url.startswith("https://threads.net/oauth/authorize?")
    assert "response_type=code" in url
    assert "state=signed-state" in url
    assert "threads_basic%2Cthreads_content_publish" in url
    assert "%2Fapi%2Fauth%2Fthreads%2Fcallback" in url


def test_app_secret_never_appears_in_the_authorize_url(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "threads_client_secret", "top-secret")
    url = get_provider(Platform.threads).authorize_url(state="s")
    assert "top-secret" not in url


def test_app_id_aliases_are_accepted(monkeypatch):
    """Meta's dashboard says App ID/secret; the project says client id/secret."""
    from app.config import settings

    p = get_provider(Platform.threads)
    monkeypatch.setattr(settings, "threads_client_id", None)
    monkeypatch.setattr(settings, "threads_client_secret", None)
    monkeypatch.setattr(settings, "threads_app_id", "app-123")
    monkeypatch.setattr(settings, "threads_app_secret", "app-secret")
    assert p.client_id == "app-123"
    assert p.is_configured is True


def test_redirect_uri_override_wins(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(
        settings, "threads_redirect_uri", "https://api.example.com/api/auth/threads/callback"
    )
    assert get_provider(Platform.threads).redirect_uri == (
        "https://api.example.com/api/auth/threads/callback"
    )


# ---------------------------------------------------------------------------
# OAuth callback: cancellation, CSRF, errors
# ---------------------------------------------------------------------------
def test_callback_handles_user_cancellation(client):
    r = client.get(
        "/api/auth/threads/callback",
        params={"error": "access_denied", "error_description": "user denied"},
        follow_redirects=False,
    )
    assert r.status_code == 307
    assert "error=access_denied" in r.headers["location"]
    assert "platform=threads" in r.headers["location"]


def test_callback_rejects_a_tampered_state(client):
    r = client.get(
        "/api/auth/threads/callback",
        params={"code": "abc", "state": "forged"},
        follow_redirects=False,
    )
    assert "Invalid+or+expired+authorization+state" in r.headers["location"]


def test_callback_rejects_state_minted_for_another_platform(client):
    state = oauth_state.encode_state(user_id=1, slug="pinterest", code_verifier=None)
    r = client.get(
        "/api/auth/threads/callback",
        params={"code": "abc", "state": state},
        follow_redirects=False,
    )
    assert "does+not+match+platform" in r.headers["location"]


def test_connect_requires_credentials(client, monkeypatch):
    from app.config import settings

    for field in (
        "threads_client_id",
        "threads_client_secret",
        "threads_app_id",
        "threads_app_secret",
    ):
        monkeypatch.setattr(settings, field, None)
    headers = _register(client, "noconfig-threads@example.com")
    r = client.post("/api/social/threads/connect", headers=headers)
    assert r.status_code == 503


def test_connect_returns_an_authorize_url(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "threads_client_id", "id")
    monkeypatch.setattr(settings, "threads_client_secret", "secret")
    headers = _register(client, "connect-threads@example.com")
    r = client.post("/api/social/threads/connect", headers=headers)
    assert r.status_code == 200
    assert r.json()["authorize_url"].startswith("https://threads.net/oauth/authorize?")
    assert "secret" not in r.json()["authorize_url"]


# ---------------------------------------------------------------------------
# Token lifecycle
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_refresh_uses_the_access_token_against_the_refresh_endpoint(fake_threads):
    """Threads has no refresh token: the long-lived one renews itself."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
            200, json={"access_token": "th-renewed", "expires_in": 5184000}
        )

    import httpx as _httpx

    real = _httpx.AsyncClient
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            _httpx,
            "AsyncClient",
            lambda *a, **kw: real(*a, **{**kw, "transport": _httpx.MockTransport(handler)}),
        )
        tokens = await get_provider(Platform.threads).refresh("th-current")

    assert tokens.access_token == "th-renewed"
    assert tokens.expires_in == 5184000  # 60 days
    assert "refresh_access_token" in seen["url"]
    assert "grant_type=th_refresh_token" in seen["url"]


def test_an_account_with_no_refresh_token_is_still_refreshable(session_factory):
    """The shared helper must not treat 'no refresh token' as 'cannot refresh'
    for Threads, or its 60-day token would silently die."""
    from app.services.social_accounts.service import token_needs_refresh

    account = _connect_threads(
        session_factory, 1, token_expires_at=utcnow() + timedelta(minutes=1)
    )
    assert account.refresh_token is None
    assert token_needs_refresh(account) is True


def test_account_missing_a_scope_is_flagged_for_reconnect(client, session_factory):
    headers = _register(client, "oldscope-threads@example.com")
    _connect_threads(session_factory, _user_id(client, headers), scopes="threads_basic")
    account = client.get("/api/social/threads", headers=headers).json()
    assert account["reauth_required"] is True


def test_account_response_never_exposes_the_token(client, session_factory):
    headers = _register(client, "notoken-threads@example.com")
    _connect_threads(session_factory, _user_id(client, headers))
    body = client.get("/api/social/threads", headers=headers).text
    assert "th-long-lived-token" not in body
    assert "access_token" not in body


def test_disconnect_then_reconnect(client, session_factory, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "threads_client_id", "id")
    monkeypatch.setattr(settings, "threads_client_secret", "secret")
    headers = _register(client, "reconnect-threads@example.com")
    _connect_threads(session_factory, _user_id(client, headers))

    assert client.post("/api/social/threads/connect", headers=headers).status_code == 409
    assert client.delete("/api/social/threads", headers=headers).status_code == 200
    assert client.get("/api/social/threads", headers=headers).status_code == 404
    assert client.post("/api/social/threads/connect", headers=headers).status_code == 200


# ---------------------------------------------------------------------------
# Publishing
# ---------------------------------------------------------------------------
USER = "17841400000000000"


@pytest.mark.anyio
async def test_text_post_uses_the_two_step_container_flow(session_factory, fake_threads):
    fake = fake_threads(
        {
            ("POST", f"{USER}/threads"): (200, {"id": "container-1"}),
            ("POST", f"{USER}/threads_publish"): (200, {"id": "thread-99"}),
        }
    )
    account = _connect_threads(session_factory, 1)
    db = session_factory()
    result = await ThreadsPublisher(db.merge(account), db).publish(
        content="Hello Threads", hashtags=["launch"]
    )
    db.close()

    assert result.success is True
    assert result.external_id == "thread-99"

    created = fake.params_for("POST", f"{USER}/threads")
    assert created["media_type"] == "TEXT"
    assert "Hello Threads" in created["text"]
    assert "#launch" in created["text"]
    assert "image_url" not in created

    published = fake.params_for("POST", f"{USER}/threads_publish")
    assert published["creation_id"] == "container-1"


@pytest.mark.anyio
async def test_image_post_waits_for_the_container_then_publishes(
    session_factory, fake_threads, monkeypatch
):
    monkeypatch.setattr(threads_api, "_MEDIA_POLL_INTERVAL", 0)
    fake = fake_threads(
        {
            ("POST", f"{USER}/threads"): (200, {"id": "container-2"}),
            ("GET", "container-2"): lambda n: (
                (200, {"status": "IN_PROGRESS"}) if n == 1 else (200, {"status": "FINISHED"})
            ),
            ("POST", f"{USER}/threads_publish"): (200, {"id": "thread-100"}),
        }
    )
    account = _connect_threads(session_factory, 1)
    db = session_factory()
    result = await ThreadsPublisher(db.merge(account), db).publish(
        content="With a picture",
        hashtags=[],
        media_urls=["https://cdn.example.com/a.png"],
    )
    db.close()

    assert result.success is True
    assert result.external_id == "thread-100"
    created = fake.params_for("POST", f"{USER}/threads")
    assert created["media_type"] == "IMAGE"
    assert created["image_url"] == "https://cdn.example.com/a.png"
    # It polled until the container was ready before publishing.
    assert len([c for c in fake.calls if c[1] == "container-2"]) == 2


@pytest.mark.anyio
async def test_a_container_that_errors_is_reported(
    session_factory, fake_threads, monkeypatch
):
    monkeypatch.setattr(threads_api, "_MEDIA_POLL_INTERVAL", 0)
    fake_threads(
        {
            ("POST", f"{USER}/threads"): (200, {"id": "container-3"}),
            ("GET", "container-3"): (200, {"status": "ERROR"}),
        }
    )
    account = _connect_threads(session_factory, 1)
    db = session_factory()
    result = await ThreadsPublisher(db.merge(account), db).publish(
        content="Bad image", hashtags=[], media_urls=["https://cdn.example.com/x.png"]
    )
    db.close()
    assert result.success is False
    assert "image" in result.error.lower()


@pytest.mark.anyio
async def test_video_attachments_are_refused_clearly(session_factory, fake_threads):
    """Nothing in the pipeline hosts video, so this must not be sent as an image."""
    fake = fake_threads({})
    account = _connect_threads(session_factory, 1)
    db = session_factory()
    result = await ThreadsPublisher(db.merge(account), db).publish(
        content="Watch this", hashtags=[], media_urls=["https://cdn.example.com/clip.mp4"]
    )
    db.close()
    assert result.success is False
    assert "video" in result.error.lower()
    assert fake.calls == []  # never reached the API


@pytest.mark.anyio
async def test_over_length_posts_are_rejected_before_the_api(session_factory, fake_threads):
    fake = fake_threads({})
    account = _connect_threads(session_factory, 1)
    db = session_factory()
    result = await ThreadsPublisher(db.merge(account), db).publish(
        content="x" * (POST_MAX_CHARS + 1), hashtags=[]
    )
    db.close()
    assert result.success is False
    assert str(POST_MAX_CHARS) in result.error
    assert fake.calls == []


@pytest.mark.anyio
async def test_publish_refreshes_an_expiring_token_first(session_factory, fake_threads):
    fake = fake_threads(
        {
            ("POST", f"{USER}/threads"): (200, {"id": "c"}),
            ("POST", f"{USER}/threads_publish"): (200, {"id": "thread-1"}),
        },
        token_response=(200, {"access_token": "th-renewed", "expires_in": 5184000}),
    )
    account = _connect_threads(
        session_factory, 1, token_expires_at=utcnow() + timedelta(seconds=30)
    )
    db = session_factory()
    live = db.merge(account)
    result = await ThreadsPublisher(live, db).publish(content="Hi", hashtags=[])

    assert result.success is True
    db.refresh(live)
    assert live.access_token == "th-renewed"
    # The renewed token is what published.
    assert fake.params_for("POST", f"{USER}/threads")["access_token"] == "th-renewed"
    db.close()


@pytest.mark.anyio
async def test_publish_retries_once_after_the_token_is_rejected(
    session_factory, fake_threads
):
    def container(n: int):
        if n == 1:
            return (401, {"error": {"message": "Invalid OAuth access token", "code": 190}})
        return (200, {"id": "c"})

    fake = fake_threads(
        {
            ("POST", f"{USER}/threads"): container,
            ("POST", f"{USER}/threads_publish"): (200, {"id": "thread-2"}),
        },
        token_response=(200, {"access_token": "th-after-401", "expires_in": 5184000}),
    )
    account = _connect_threads(session_factory, 1)
    db = session_factory()
    result = await ThreadsPublisher(db.merge(account), db).publish(
        content="Hi", hashtags=[]
    )
    db.close()

    assert result.success is True
    assert result.external_id == "thread-2"
    assert len([c for c in fake.calls if c[1] == f"{USER}/threads"]) == 2


@pytest.mark.anyio
async def test_a_failed_refresh_asks_the_user_to_reconnect(session_factory, fake_threads):
    fake_threads(
        {("POST", f"{USER}/threads"): (200, {"id": "c"})},
        token_response=(400, {"error": {"message": "Session has expired"}}),
    )
    account = _connect_threads(
        session_factory, 1, token_expires_at=utcnow() - timedelta(days=1)
    )
    db = session_factory()
    result = await ThreadsPublisher(db.merge(account), db).publish(
        content="Hi", hashtags=[]
    )
    db.close()
    assert result.success is False
    assert "Reconnect your Threads account" in result.error


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "payload", "expected"),
    [
        (400, {"error": {"message": "Too many requests", "code": 4}}, "rate limit"),
        (
            403,
            {"error": {"message": "Permissions error", "code": 200}},
            "missing the publishing permission",
        ),
        (500, {"error": {"message": "Internal error"}}, "having trouble right now"),
        (
            400,
            {"error": {"message": "The image url is not accessible", "code": 100}},
            "could not use the attached image",
        ),
        (400, {"error": {"message": "Unsupported request", "code": 100}}, "rejected the post"),
    ],
)
async def test_api_errors_become_safe_user_messages(
    session_factory, fake_threads, status, payload, expected
):
    fake_threads({("POST", f"{USER}/threads"): (status, payload)})
    account = _connect_threads(session_factory, 1)
    db = session_factory()
    result = await ThreadsPublisher(db.merge(account), db).publish(
        content="Hi", hashtags=[]
    )
    db.close()

    assert result.success is False
    assert expected in result.error.lower() or expected in result.error
    # A failure message must never carry the credential that produced it.
    assert "th-long-lived-token" not in result.error


# ---------------------------------------------------------------------------
# Scheduling and ownership, through the real endpoints
# ---------------------------------------------------------------------------
def test_a_scheduled_threads_post_publishes_through_the_shared_scheduler(
    client, session_factory, fake_threads
):
    fake = fake_threads(
        {
            ("POST", f"{USER}/threads"): (200, {"id": "c"}),
            ("POST", f"{USER}/threads_publish"): (200, {"id": "thread-sched"}),
        }
    )
    headers = _register(client, "sched-threads@example.com")
    _connect_threads(session_factory, _user_id(client, headers))

    created = client.post(
        "/api/posts",
        json={"platform": "threads", "content": "Scheduled hello", "hashtags": ["ai"]},
        headers=headers,
    ).json()
    published = client.post(f"/api/posts/{created['id']}/publish", headers=headers).json()

    assert published["status"] == "published"
    assert published["external_id"] == "thread-sched"
    assert fake.params_for("POST", f"{USER}/threads")["media_type"] == "TEXT"


def test_a_failed_threads_publish_records_the_reason(
    client, session_factory, fake_threads
):
    fake_threads(
        {
            ("POST", f"{USER}/threads"): (
                403,
                {"error": {"message": "Permissions error", "code": 200}},
            )
        }
    )
    headers = _register(client, "schedfail-threads@example.com")
    _connect_threads(session_factory, _user_id(client, headers))

    created = client.post(
        "/api/posts",
        json={"platform": "threads", "content": "Doomed"},
        headers=headers,
    ).json()
    published = client.post(f"/api/posts/{created['id']}/publish", headers=headers).json()

    assert published["status"] == "failed"
    assert "permission" in published["error"].lower()


def test_one_user_cannot_use_another_users_threads_connection(client, session_factory):
    owner = _register(client, "owner-threads@example.com")
    _connect_threads(session_factory, _user_id(client, owner))

    intruder = _register(client, "intruder-threads@example.com")
    assert client.get("/api/social/threads", headers=intruder).status_code == 404


@pytest.fixture()
def anyio_backend():
    return "asyncio"


# ---------------------------------------------------------------------------
# Meta's deauthorize / data-deletion callbacks
#
# Meta requires both URLs before the Threads API settings will save, calls them
# itself with no session, and proves the call with a signed_request.
# ---------------------------------------------------------------------------
def _signed_request(payload: dict, secret: str) -> str:
    """Build a signed_request exactly the way Meta does."""
    import base64, hashlib, hmac, json

    def b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    encoded = b64(json.dumps(payload).encode())
    sig = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
    return f"{b64(sig)}.{encoded}"


@pytest.fixture()
def threads_secret(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "threads_client_id", "app-id")
    monkeypatch.setattr(settings, "threads_client_secret", "app-secret")
    return "app-secret"


def _threads_account_count(session_factory) -> int:
    db = session_factory()
    try:
        return (
            db.query(SocialAccount)
            .filter(SocialAccount.platform == Platform.threads.value)
            .count()
        )
    finally:
        db.close()


@pytest.mark.parametrize("path", ["/api/auth/threads/uninstall", "/api/auth/threads/delete"])
def test_bare_get_answers_200_without_redirecting(client, path):
    """This is Meta's dashboard checking the URL while you press Save. A
    redirect or an error here is exactly what stops the settings saving."""
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 200
    assert "location" not in {k.lower() for k in r.headers}
    assert r.headers["content-type"].startswith("application/json")


@pytest.mark.parametrize("path", ["/api/auth/threads/uninstall", "/api/auth/threads/delete"])
def test_callbacks_need_no_authentication(client, path):
    """Meta calls these with no session of ours."""
    assert client.post(path, data={}).status_code == 200


def test_uninstall_removes_only_that_threads_connection(
    client, session_factory, threads_secret
):
    headers = _register(client, "uninstall@example.com")
    _connect_threads(session_factory, _user_id(client, headers), account_id="th-user-1")

    # A second user's Threads account, and a Pinterest one, must both survive.
    other = _register(client, "bystander@example.com")
    _connect_threads(session_factory, _user_id(client, other), account_id="th-user-2")
    db = session_factory()
    db.add(
        SocialAccount(
            user_id=_user_id(client, headers),
            platform=Platform.pinterest.value,
            access_token="pina-token",
            account_id="pintester",
            status=AccountStatus.connected.value,
        )
    )
    db.commit()
    db.close()

    signed = _signed_request(
        {"algorithm": "HMAC-SHA256", "user_id": "th-user-1", "issued_at": 1},
        threads_secret,
    )
    r = client.post("/api/auth/threads/uninstall", data={"signed_request": signed})
    assert r.status_code == 200

    assert client.get("/api/social/threads", headers=headers).status_code == 404
    assert client.get("/api/social/threads", headers=other).status_code == 200
    assert client.get("/api/social/pinterest", headers=headers).status_code == 200


def test_delete_answers_with_a_status_url_and_confirmation_code(
    client, session_factory, threads_secret
):
    headers = _register(client, "delete@example.com")
    _connect_threads(session_factory, _user_id(client, headers), account_id="th-del")

    signed = _signed_request(
        {"algorithm": "HMAC-SHA256", "user_id": "th-del", "issued_at": 1}, threads_secret
    )
    r = client.post("/api/auth/threads/delete", data={"signed_request": signed})
    assert r.status_code == 200

    body = r.json()
    assert body["confirmation_code"]
    assert body["url"].endswith(f"code={body['confirmation_code']}")
    # The data really is gone, not merely promised.
    assert client.get("/api/social/threads", headers=headers).status_code == 404

    # And the status URL is reachable and says so.
    status = client.get(
        "/api/auth/threads/delete/status", params={"code": body["confirmation_code"]}
    )
    assert status.status_code == 200
    assert status.json()["status"] == "completed"


def test_a_forged_signature_deletes_nothing(client, session_factory, threads_secret):
    """The signature is the only thing separating Meta from an anonymous POST."""
    headers = _register(client, "forged@example.com")
    _connect_threads(session_factory, _user_id(client, headers), account_id="th-safe")

    forged = _signed_request(
        {"algorithm": "HMAC-SHA256", "user_id": "th-safe", "issued_at": 1},
        "not-the-app-secret",
    )
    r = client.post("/api/auth/threads/uninstall", data={"signed_request": forged})

    # Answered identically to a valid call, so it reveals nothing...
    assert r.status_code == 200
    # ...but the connection is untouched.
    assert client.get("/api/social/threads", headers=headers).status_code == 200


def test_malformed_signed_requests_are_survived(client, session_factory, threads_secret):
    before = _threads_account_count(session_factory)
    for bad in ["", "garbage", "only-one-part", "a.b", "!!!.???"]:
        r = client.post("/api/auth/threads/uninstall", data={"signed_request": bad})
        assert r.status_code == 200
    assert _threads_account_count(session_factory) == before


def test_callbacks_never_leak_tokens_or_account_details(
    client, session_factory, threads_secret
):
    headers = _register(client, "noleak@example.com")
    _connect_threads(session_factory, _user_id(client, headers), account_id="th-leak")

    signed = _signed_request(
        {"algorithm": "HMAC-SHA256", "user_id": "th-leak", "issued_at": 1}, threads_secret
    )
    for path in ("/api/auth/threads/uninstall", "/api/auth/threads/delete"):
        body = client.post(path, data={"signed_request": signed}).text
        assert "th-long-lived-token" not in body
        assert "app-secret" not in body
        assert "threadsuser" not in body
        assert "noleak@example.com" not in body
