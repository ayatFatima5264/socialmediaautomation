"""Tests for the user data deletion flow.

Covers the three ways data leaves this app, plus the encryption protecting it
while it is here:

  * DELETE /auth/me            — the user erases their whole account
  * DELETE /api/social/{p}     — the user disconnects one platform
  * the Meta callbacks         — Meta asks us to forget a person

The multi-tenancy assertions are the point of most of these: every deletion
path is checked to remove exactly one user's rows and leave every other user's
alone. Runs against a throwaway SQLite database — no network, no credentials.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import tempfile
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core import crypto
from app.core.timeutils import utcnow
from app.database import Base, get_db
from app.main import app
from app.models.ad_campaign import AdCampaign
from app.models.business_profile import BusinessProfile
from app.models.content_plan import ContentPlan
from app.models.media_asset import MediaAsset
from app.models.post import Post
from app.models.social_account import SocialAccount
from app.models.user import User
from app.schemas.post import Platform
from app.services import account_deletion

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND = REPO_ROOT / "frontend"


@pytest.fixture()
def session_factory():
    tmp = Path(tempfile.mkdtemp()) / "deletion.db"
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


def _register(client, email):
    client.post(
        "/auth/register",
        json={"email": email, "password": "correct-horse", "full_name": "Test User"},
    )
    token = client.post(
        "/auth/login", data={"username": email, "password": "correct-horse"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _user_id(client, headers) -> int:
    return client.get("/auth/me", headers=headers).json()["id"]


def _connect(session_factory, user_id, platform, **overrides) -> int:
    """Give a user a connected account on `platform`. Returns its row id."""
    db = session_factory()
    try:
        account = SocialAccount(
            user_id=user_id,
            platform=platform.value,
            access_token=overrides.pop("access_token", f"{platform.value}-token"),
            refresh_token=overrides.pop("refresh_token", f"{platform.value}-refresh"),
            account_id=overrides.pop("account_id", f"{platform.value}-acct-{user_id}"),
            token_expires_at=utcnow() + timedelta(days=30),
            **overrides,
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        return account.id
    finally:
        db.close()


def _seed_content(session_factory, user_id) -> None:
    """A row in each of the other user-owned tables, so deletion has work to do."""
    db = session_factory()
    try:
        db.add(Post(user_id=user_id, content="hello world", platform=Platform.threads.value))
        db.add(ContentPlan(user_id=user_id, name="August plan"))
        db.add(AdCampaign(user_id=user_id, name="Launch"))
        db.add(BusinessProfile(user_id=user_id, business_name="Acme"))
        db.add(
            MediaAsset(
                user_id=user_id,
                token=f"tok-{user_id}",
                content_type="image/png",
                size_bytes=3,
                data=b"png",
            )
        )
        db.commit()
    finally:
        db.close()


def _counts(session_factory, user_id) -> dict[str, int]:
    db = session_factory()
    try:
        return {
            model.__tablename__: db.query(model)
            .filter(model.user_id == user_id)
            .count()
            for model in (Post, ContentPlan, AdCampaign, BusinessProfile, MediaAsset, SocialAccount)
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 1. A user can delete their own account
# ---------------------------------------------------------------------------
def test_user_can_delete_their_own_account(client, session_factory):
    headers = _register(client, "owner@example.com")
    user_id = _user_id(client, headers)
    _seed_content(session_factory, user_id)
    _connect(session_factory, user_id, Platform.threads)

    r = client.request("DELETE", "/auth/me", headers=headers, json={"confirmation": "DELETE"})
    assert r.status_code == 200
    assert "deleted" in r.json()["message"].lower()

    db = session_factory()
    try:
        assert db.get(User, user_id) is None
    finally:
        db.close()
    assert set(_counts(session_factory, user_id).values()) == {0}


def test_deleted_account_can_no_longer_authenticate(client, session_factory):
    headers = _register(client, "gone@example.com")
    client.request("DELETE", "/auth/me", headers=headers, json={"confirmation": "DELETE"})
    # The JWT is still cryptographically valid; the user it names is not there.
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_deletion_requires_the_typed_confirmation(client, session_factory):
    headers = _register(client, "careful@example.com")
    user_id = _user_id(client, headers)

    for body in ({"confirmation": "delete"}, {"confirmation": "yes"}, {"confirmation": ""}):
        r = client.request("DELETE", "/auth/me", headers=headers, json=body)
        assert r.status_code == 400, body

    r = client.request("DELETE", "/auth/me", headers=headers, json={})
    assert r.status_code == 422  # confirmation is required

    db = session_factory()
    try:
        assert db.get(User, user_id) is not None
    finally:
        db.close()


def test_deletion_requires_authentication(client):
    r = client.request("DELETE", "/auth/me", json={"confirmation": "DELETE"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# 2 & 7. One user can never reach another user's data
# ---------------------------------------------------------------------------
def test_deletion_endpoint_accepts_no_user_id(client, session_factory):
    """The account deleted is whoever the bearer token names. A body naming
    someone else changes nothing — the field is not read, and `extra` fields are
    ignored, so the caller's own account is the only one that can go."""
    victim = _register(client, "victim@example.com")
    victim_id = _user_id(client, victim)
    _seed_content(session_factory, victim_id)
    _connect(session_factory, victim_id, Platform.instagram)

    attacker = _register(client, "attacker@example.com")
    attacker_id = _user_id(client, attacker)

    r = client.request(
        "DELETE",
        "/auth/me",
        headers=attacker,
        json={"confirmation": "DELETE", "user_id": victim_id, "id": victim_id, "email": "victim@example.com"},
    )
    assert r.status_code == 200

    db = session_factory()
    try:
        assert db.get(User, victim_id) is not None, "the other user was deleted"
        assert db.get(User, attacker_id) is None, "the caller's own account survived"
    finally:
        db.close()
    # Every one of the victim's rows is still there.
    assert all(count > 0 for count in _counts(session_factory, victim_id).values())


def test_deleting_one_account_leaves_other_users_untouched(client, session_factory):
    leaver = _register(client, "leaver@example.com")
    leaver_id = _user_id(client, leaver)
    _seed_content(session_factory, leaver_id)
    _connect(session_factory, leaver_id, Platform.threads)

    stayer = _register(client, "stayer@example.com")
    stayer_id = _user_id(client, stayer)
    _seed_content(session_factory, stayer_id)
    _connect(session_factory, stayer_id, Platform.threads)
    _connect(session_factory, stayer_id, Platform.facebook)

    before = _counts(session_factory, stayer_id)
    client.request("DELETE", "/auth/me", headers=leaver, json={"confirmation": "DELETE"})

    assert _counts(session_factory, stayer_id) == before
    assert set(_counts(session_factory, leaver_id).values()) == {0}


# ---------------------------------------------------------------------------
# 3. Deleting an account removes that user's social accounts
# ---------------------------------------------------------------------------
def test_account_deletion_removes_every_connected_platform(client, session_factory):
    headers = _register(client, "connected@example.com")
    user_id = _user_id(client, headers)
    for platform in Platform:
        _connect(session_factory, user_id, platform)

    db = session_factory()
    try:
        assert db.query(SocialAccount).filter_by(user_id=user_id).count() == len(Platform)
    finally:
        db.close()

    client.request("DELETE", "/auth/me", headers=headers, json={"confirmation": "DELETE"})

    db = session_factory()
    try:
        assert db.query(SocialAccount).filter_by(user_id=user_id).count() == 0
    finally:
        db.close()


def test_deletion_covers_every_user_owned_table(session_factory):
    """Guards against a new user-owned table being added without being deleted.

    The reference set is read from the live schema (every table with a foreign
    key to `users`), so this fails the moment a model is added and forgotten —
    which is exactly the way a deletion feature quietly rots.
    """
    db = session_factory()
    try:
        referencing = account_deletion.tables_referencing_users(db)
    finally:
        db.close()

    missed = referencing - account_deletion.user_owned_tables()
    assert not missed, f"tables reference users but are never deleted: {sorted(missed)}"


# ---------------------------------------------------------------------------
# 4, 5, 6, 14. Disconnecting one platform erases its credentials only
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "platform",
    [Platform.threads, Platform.instagram, Platform.facebook,
     Platform.pinterest, Platform.linkedin, Platform.twitter],
)
def test_disconnect_deletes_that_platforms_tokens_only(client, session_factory, platform):
    headers = _register(client, f"dc-{platform.value}@example.com")
    user_id = _user_id(client, headers)
    for p in Platform:
        _connect(session_factory, user_id, p)

    r = client.delete(f"/api/social/{platform.value}", headers=headers)
    assert r.status_code == 200

    db = session_factory()
    try:
        # The row is gone entirely, so the access and refresh tokens are too.
        assert db.query(SocialAccount).filter_by(
            user_id=user_id, platform=platform.value
        ).first() is None
        # Every other connection survives, tokens intact.
        others = db.query(SocialAccount).filter_by(user_id=user_id).all()
        assert len(others) == len(Platform) - 1
        assert all(a.access_token for a in others)
    finally:
        db.close()


def test_disconnect_leaves_the_users_other_data_alone(client, session_factory):
    headers = _register(client, "keeps-content@example.com")
    user_id = _user_id(client, headers)
    _seed_content(session_factory, user_id)
    _connect(session_factory, user_id, Platform.threads)

    client.delete(f"/api/social/{Platform.threads.value}", headers=headers)

    counts = _counts(session_factory, user_id)
    assert counts["social_accounts"] == 0
    assert all(count > 0 for table, count in counts.items() if table != "social_accounts")

    db = session_factory()
    try:
        assert db.get(User, user_id) is not None
    finally:
        db.close()


def test_disconnect_cannot_reach_another_users_connection(client, session_factory):
    owner = _register(client, "owns-threads@example.com")
    owner_id = _user_id(client, owner)
    _connect(session_factory, owner_id, Platform.threads)

    other = _register(client, "no-threads@example.com")
    # The other user has no Threads account of their own, so this is a 404 —
    # never a hit on someone else's row, which the repository scopes by user id.
    assert client.delete("/api/social/threads", headers=other).status_code == 404

    db = session_factory()
    try:
        assert db.query(SocialAccount).filter_by(user_id=owner_id).count() == 1
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 8 & 9. Meta's data-deletion callback
# ---------------------------------------------------------------------------
def _signed_request(payload: dict, secret: str) -> str:
    """Build a signed_request exactly the way Meta does."""

    def b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    encoded = b64(json.dumps(payload).encode())
    sig = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
    return f"{b64(sig)}.{encoded}"


@pytest.fixture()
def meta_secrets(monkeypatch):
    """Threads and Facebook/Instagram in two separate Meta apps, as they may be."""
    from app.config import settings

    monkeypatch.setattr(settings, "threads_client_id", "threads-app-id")
    monkeypatch.setattr(settings, "threads_client_secret", "threads-secret")
    monkeypatch.setattr(settings, "meta_app_id", "meta-app-id")
    monkeypatch.setattr(settings, "meta_app_secret", "meta-secret")
    return {"threads": "threads-secret", "meta": "meta-secret"}


def _valid(payload_user_id: str, secret: str) -> str:
    return _signed_request(
        {"algorithm": "HMAC-SHA256", "user_id": payload_user_id, "issued_at": 1}, secret
    )


@pytest.mark.parametrize("path", ["/api/auth/threads/delete", "/api/auth/meta/delete"])
def test_valid_meta_deletion_removes_the_named_connections(
    client, session_factory, meta_secrets, path
):
    """One Meta user id can name a Facebook, an Instagram and a Threads row.

    Instagram is the case that matters: its `account_id` is the Instagram
    Business account id, so it can only be found through `platform_user_id`.
    """
    headers = _register(client, "meta-user@example.com")
    user_id = _user_id(client, headers)
    _connect(session_factory, user_id, Platform.threads,
             account_id="meta-123", platform_user_id="meta-123")
    _connect(session_factory, user_id, Platform.facebook,
             account_id="meta-123", platform_user_id="meta-123")
    _connect(session_factory, user_id, Platform.instagram,
             account_id="ig-business-999", platform_user_id="meta-123")
    # Not a Meta platform — must survive a Meta deletion request.
    _connect(session_factory, user_id, Platform.pinterest)

    signed = _valid("meta-123", meta_secrets["threads"])
    r = client.post(path, data={"signed_request": signed})
    assert r.status_code == 200

    body = r.json()
    assert body["confirmation_code"]
    assert body["url"].endswith(f"?code={body['confirmation_code']}")

    db = session_factory()
    try:
        remaining = {a.platform for a in db.query(SocialAccount).filter_by(user_id=user_id)}
        assert remaining == {Platform.pinterest.value}
        # The account itself is untouched: Meta asked us to forget a connection,
        # not to delete a person's whole AutoSocial account.
        assert db.get(User, user_id) is not None
    finally:
        db.close()


def test_legacy_rows_without_platform_user_id_are_still_matched(
    client, session_factory, meta_secrets
):
    """Accounts connected before `platform_user_id` existed must not be stranded
    — for them `account_id` is the only id we hold."""
    headers = _register(client, "legacy@example.com")
    user_id = _user_id(client, headers)
    _connect(session_factory, user_id, Platform.threads,
             account_id="legacy-42", platform_user_id=None)

    signed = _valid("legacy-42", meta_secrets["threads"])
    assert client.post("/api/auth/meta/delete", data={"signed_request": signed}).status_code == 200

    db = session_factory()
    try:
        assert db.query(SocialAccount).filter_by(user_id=user_id).count() == 0
    finally:
        db.close()


def test_account_id_fallback_cannot_reach_a_different_person(
    client, session_factory, meta_secrets
):
    """App-scoped ids are issued per Meta app, so the same number can belong to
    two different people across the Threads app and the Facebook/Instagram app.
    A row that carries its own `platform_user_id` must be matched on that alone,
    never on a coincidentally equal `account_id`."""
    victim = _register(client, "coincidence@example.com")
    victim_id = _user_id(client, victim)
    # Facebook connection whose Instagram-Business-style account_id happens to
    # equal the *Threads* user id of somebody else entirely.
    _connect(session_factory, victim_id, Platform.instagram,
             account_id="1234567890", platform_user_id="fb-owner-of-this-row")

    signed = _valid("1234567890", meta_secrets["threads"])
    assert client.post("/api/auth/meta/delete", data={"signed_request": signed}).status_code == 200

    db = session_factory()
    try:
        assert db.query(SocialAccount).filter_by(user_id=victim_id).count() == 1, (
            "an unrelated person's connection was deleted on an id collision"
        )
    finally:
        db.close()


def test_callback_accepts_either_configured_app_secret(client, session_factory, meta_secrets):
    """Facebook/Instagram and Threads can be separate Meta apps with separate
    secrets, while Meta allows one callback URL — so both must verify."""
    headers = _register(client, "two-apps@example.com")
    user_id = _user_id(client, headers)
    _connect(session_factory, user_id, Platform.facebook,
             account_id="fb-77", platform_user_id="fb-77")

    signed = _valid("fb-77", meta_secrets["meta"])  # signed by the *other* app
    assert client.post("/api/auth/meta/delete", data={"signed_request": signed}).status_code == 200

    db = session_factory()
    try:
        assert db.query(SocialAccount).filter_by(user_id=user_id).count() == 0
    finally:
        db.close()


@pytest.mark.parametrize("path", ["/api/auth/threads/delete", "/api/auth/meta/delete"])
def test_forged_signature_deletes_nothing(client, session_factory, meta_secrets, path):
    headers = _register(client, "safe@example.com")
    user_id = _user_id(client, headers)
    _connect(session_factory, user_id, Platform.threads,
             account_id="meta-abc", platform_user_id="meta-abc")

    forged = _valid("meta-abc", "not-the-app-secret")
    r = client.post(path, data={"signed_request": forged})
    # Answered identically to a valid call, so the endpoint is not an oracle.
    assert r.status_code == 200

    db = session_factory()
    try:
        assert db.query(SocialAccount).filter_by(user_id=user_id).count() == 1
    finally:
        db.close()


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "garbage",
        "only-one-part",
        "!!!.!!!",
        # A valid signature over a payload claiming a non-HMAC algorithm.
        None,
    ],
)
def test_malformed_deletion_requests_delete_nothing(
    client, session_factory, meta_secrets, bad
):
    headers = _register(client, "malformed@example.com")
    user_id = _user_id(client, headers)
    _connect(session_factory, user_id, Platform.threads,
             account_id="meta-xyz", platform_user_id="meta-xyz")

    if bad is None:
        bad = _signed_request(
            {"algorithm": "none", "user_id": "meta-xyz"}, meta_secrets["threads"]
        )

    r = client.post("/api/auth/meta/delete", data={"signed_request": bad})
    assert r.status_code == 200

    db = session_factory()
    try:
        assert db.query(SocialAccount).filter_by(user_id=user_id).count() == 1
    finally:
        db.close()


def test_deletion_status_endpoint_reports_completed(client, meta_secrets):
    r = client.post(
        "/api/auth/meta/delete", data={"signed_request": _valid("nobody", meta_secrets["threads"])}
    )
    code = r.json()["confirmation_code"]
    status = client.get("/api/auth/threads/delete/status", params={"code": code})
    assert status.status_code == 200
    body = status.json()
    assert body["confirmation_code"] == code
    assert body["status"] == "completed"
    assert "deleted" in body["detail"].lower()


@pytest.mark.parametrize(
    "path",
    ["/api/auth/threads/delete", "/api/auth/threads/uninstall",
     "/api/auth/meta/delete", "/api/auth/meta/deauthorize"],
)
def test_meta_callbacks_answer_a_bare_get_with_json(client, path):
    """Meta's dashboard pings the URL while you press Save — a redirect or an
    error here is exactly what stops the settings saving."""
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 200
    assert "location" not in {k.lower() for k in r.headers}
    assert r.headers["content-type"].startswith("application/json")


def test_deletion_callback_never_logs_a_token(client, session_factory, meta_secrets, caplog):
    headers = _register(client, "quiet@example.com")
    user_id = _user_id(client, headers)
    _connect(session_factory, user_id, Platform.threads, account_id="meta-log",
             platform_user_id="meta-log", access_token="super-secret-token")

    signed = _valid("meta-log", meta_secrets["threads"])
    with caplog.at_level("DEBUG"):
        client.post("/api/auth/meta/delete", data={"signed_request": signed})

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "super-secret-token" not in logged
    assert signed not in logged
    assert meta_secrets["threads"] not in logged


# ---------------------------------------------------------------------------
# 10, 11, 12. The public /data-deletion page
# ---------------------------------------------------------------------------
def _read(*parts) -> str:
    return (FRONTEND.joinpath(*parts)).read_text(encoding="utf-8")


def test_data_deletion_route_is_public():
    """It must sit inside PublicLayout, not behind ProtectedRoute — Meta's
    reviewers open this URL with no account."""
    app_jsx = _read("src", "App.jsx")
    assert '<Route path="/data-deletion"' in app_jsx

    public_block = app_jsx.split("<Route element={<PublicLayout />}>")[1].split("</Route>")[0]
    assert "/data-deletion" in public_block, "route is not in the public layout"


def test_data_deletion_is_linked_from_the_footer_and_sitemap():
    site = _read("src", "config", "site.js")
    # A labelled footer entry, in the same Legal group as Privacy and Terms.
    assert re.search(
        r"\{\s*to:\s*'/data-deletion',\s*label:\s*'Data Deletion'\s*\}", site
    ), "no Data Deletion link in the footer config"
    # Present in the indexable route list, so it reaches robots/sitemap.
    assert re.search(r"MARKETING_ROUTES\s*=\s*\[[^\]]*'/data-deletion'", site, re.S)
    assert "/data-deletion" in _read("src", "seo", "pages.data.js")


def test_data_deletion_page_only_describes_features_that_exist():
    """The page tells users to click Delete Account and Disconnect. Both have to
    be real, or the page is a promise the app does not keep."""
    page = _read("src", "pages", "marketing", "DataDeletion.jsx")
    assert "Delete Account" in page and "Disconnect" in page

    settings_page = _read("src", "pages", "Settings.jsx")
    assert "Delete Account" in settings_page
    assert "DeleteAccountModal" in settings_page
    assert "api.deleteAccount" in settings_page

    assert "deleteAccount:" in _read("src", "lib", "api.js")
    assert "DELETE" in _read("src", "components", "DeleteAccountModal.jsx")


@pytest.mark.skipif(
    not (FRONTEND / "dist" / "index.html").exists(),
    reason="frontend has not been built (run: npm --prefix frontend run build)",
)
def test_production_build_serves_data_deletion_not_a_404():
    built = FRONTEND / "dist" / "data-deletion" / "index.html"
    assert built.exists(), "no prerendered /data-deletion in the production build"

    html = built.read_text(encoding="utf-8")
    assert "<title>Data Deletion" in html
    assert "Page Not Found" not in html
    # Must be indexable, unlike the 404 shell every unmatched path falls back to.
    assert 'name="robots" content="index, follow"' in html

    sitemap = (FRONTEND / "dist" / "sitemap.xml").read_text(encoding="utf-8")
    assert "/data-deletion" in sitemap


# ---------------------------------------------------------------------------
# 13. Tokens survive encryption — publishing still works
# ---------------------------------------------------------------------------
@pytest.fixture()
def encryption_key(monkeypatch):
    from cryptography.fernet import Fernet
    from app.config import settings

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "token_encryption_key", key)
    crypto.reset_cache()
    yield key
    monkeypatch.undo()
    crypto.reset_cache()


def test_tokens_round_trip_through_the_orm(session_factory, encryption_key):
    """What the app reads back must be exactly what it wrote — otherwise every
    publish would fail with an invalid token."""
    db = session_factory()
    try:
        db.add(User(id=1, email="e@example.com", hashed_password="x"))
        account = SocialAccount(
            user_id=1,
            platform=Platform.threads.value,
            access_token="th-access-token",
            refresh_token="th-refresh-token",
            account_id="th-1",
        )
        db.add(account)
        db.commit()
        db.expunge_all()

        loaded = db.query(SocialAccount).one()
        assert loaded.access_token == "th-access-token"
        assert loaded.refresh_token == "th-refresh-token"
    finally:
        db.close()


def test_tokens_are_ciphertext_in_the_database(session_factory, encryption_key):
    db = session_factory()
    try:
        db.add(User(id=1, email="e@example.com", hashed_password="x"))
        db.add(
            SocialAccount(
                user_id=1,
                platform=Platform.threads.value,
                access_token="th-access-token",
                refresh_token="th-refresh-token",
                account_id="th-1",
            )
        )
        db.commit()

        stored = db.execute(
            text("SELECT access_token, refresh_token FROM social_accounts")
        ).one()
    finally:
        db.close()

    for value in stored:
        assert value.startswith(crypto.PREFIX)
        assert "th-access-token" not in value
        assert "th-refresh-token" not in value


def test_existing_plaintext_tokens_keep_working(session_factory, encryption_key):
    """An account connected before encryption was switched on must not break."""
    db = session_factory()
    try:
        db.add(User(id=1, email="e@example.com", hashed_password="x"))
        db.commit()
        # Written the way the old code did: straight through, no marker.
        db.execute(
            text(
                "INSERT INTO social_accounts (user_id, platform, access_token, "
                "account_id, status, created_at, updated_at) VALUES "
                "(1, 'threads', 'legacy-plaintext', 'th-1', 'connected', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        db.commit()

        assert db.query(SocialAccount).one().access_token == "legacy-plaintext"
    finally:
        db.close()


def test_encrypt_existing_tokens_backfills_plaintext_rows(session_factory, encryption_key):
    import app.database as database

    db = session_factory()
    try:
        db.add(User(id=1, email="e@example.com", hashed_password="x"))
        db.commit()
        db.execute(
            text(
                "INSERT INTO social_accounts (user_id, platform, access_token, "
                "refresh_token, account_id, status, created_at, updated_at) VALUES "
                "(1, 'threads', 'legacy-plaintext', 'legacy-refresh', 'th-1', "
                "'connected', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        db.commit()
        engine = db.get_bind()
    finally:
        db.close()

    # Point the migration at this test database rather than the app's own.
    original = database.engine
    database.engine = engine
    try:
        database.encrypt_existing_tokens()
        database.encrypt_existing_tokens()  # idempotent — a second run is a no-op
    finally:
        database.engine = original

    db = session_factory()
    try:
        raw = db.execute(text("SELECT access_token, refresh_token FROM social_accounts")).one()
        assert all(value.startswith(crypto.PREFIX) for value in raw)
        # And still readable as the original values through the ORM.
        account = db.query(SocialAccount).one()
        assert account.access_token == "legacy-plaintext"
        assert account.refresh_token == "legacy-refresh"
    finally:
        db.close()


def test_undecryptable_token_marks_the_account_for_reconnect(session_factory, encryption_key):
    """A row encrypted with a key we no longer hold must not look healthy."""
    from app.schemas.social_account import AccountStatus
    from app.services.social_accounts import service

    db = session_factory()
    try:
        db.add(User(id=1, email="e@example.com", hashed_password="x"))
        db.commit()
        db.execute(
            text(
                "INSERT INTO social_accounts (user_id, platform, access_token, "
                "account_id, status, created_at, updated_at) VALUES "
                "(1, 'threads', :token, 'th-1', 'connected', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"token": crypto.PREFIX + "gAAAAABmnot-a-real-token"},
        )
        db.commit()

        account = db.query(SocialAccount).one()
        assert account.access_token is None
        assert service.effective_status(account) == AccountStatus.error
    finally:
        db.close()


def test_no_key_configured_stores_plaintext_and_still_works(session_factory, monkeypatch):
    """A deploy that has not set the key yet must keep working, not lose every
    connection."""
    from app.config import settings

    monkeypatch.setattr(settings, "token_encryption_key", None)
    crypto.reset_cache()
    try:
        db = session_factory()
        try:
            db.add(User(id=1, email="e@example.com", hashed_password="x"))
            db.add(
                SocialAccount(
                    user_id=1,
                    platform=Platform.threads.value,
                    access_token="plain-token",
                    account_id="th-1",
                )
            )
            db.commit()

            assert db.query(SocialAccount).one().access_token == "plain-token"
            stored = db.execute(text("SELECT access_token FROM social_accounts")).scalar_one()
            assert stored == "plain-token"
        finally:
            db.close()
    finally:
        crypto.reset_cache()
