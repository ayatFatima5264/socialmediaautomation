"""Tests for uploaded media — the public URL that makes publishing possible.

Platforms publish an image by fetching a URL from their own servers, so a
composer upload is only publishable once it has a durable public URL. These
cover the upload rules, the public read, ownership, and the end-to-end path a
Pinterest post takes from an uploaded file to a created Pin.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.routes.media import MAX_UPLOAD_BYTES

# The smallest valid PNG (1x1, transparent).
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6360000002000100ffff03000006"
    "000557bfabd40000000049454e44ae426082"
)


@pytest.fixture()
def client():
    tmp = Path(tempfile.mkdtemp()) / "media.db"
    engine = create_engine(f"sqlite:///{tmp}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


def _register(client, email="media@example.com"):
    client.post(
        "/auth/register",
        json={"email": email, "password": "correct-horse", "full_name": "Media"},
    )
    token = client.post(
        "/auth/login", data={"username": email, "password": "correct-horse"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _upload(client, headers, data=PNG_BYTES, name="pic.png", ctype="image/png"):
    return client.post(
        "/api/media", files={"file": (name, data, ctype)}, headers=headers
    )


def test_upload_returns_a_fetchable_public_url(client):
    headers = _register(client)
    r = _upload(client, headers)
    assert r.status_code == 201

    body = r.json()
    assert body["url"].endswith(f"/api/media/{body['token']}")
    # Absolute, not relative — Pinterest fetches it from its own servers.
    assert body["url"].startswith("http")
    assert body["size_bytes"] == len(PNG_BYTES)

    # The URL serves the exact bytes, with no authentication.
    got = client.get(f"/api/media/{body['token']}")
    assert got.status_code == 200
    assert got.content == PNG_BYTES
    assert got.headers["content-type"] == "image/png"


def test_public_read_needs_no_login(client):
    """The platforms fetch this URL with no credentials of ours."""
    headers = _register(client, "anon@example.com")
    token = _upload(client, headers).json()["token"]

    fresh = TestClient(app)  # no Authorization header at all
    assert fresh.get(f"/api/media/{token}").status_code == 200


def test_upload_requires_authentication(client):
    assert _upload(client, {}).status_code == 401


def test_unknown_token_is_404(client):
    assert client.get("/api/media/nope-not-a-real-token").status_code == 404


def test_tokens_are_unguessable_and_unique(client):
    headers = _register(client, "tokens@example.com")
    tokens = {_upload(client, headers).json()["token"] for _ in range(3)}
    assert len(tokens) == 3
    for token in tokens:
        assert len(token) >= 32  # not a sequential id


def test_non_images_are_rejected(client):
    headers = _register(client, "pdf@example.com")
    r = _upload(client, headers, b"%PDF-1.4 fake", "doc.pdf", "application/pdf")
    assert r.status_code == 415
    assert "Only images" in r.json()["detail"]


def test_empty_file_is_rejected(client):
    headers = _register(client, "empty@example.com")
    assert _upload(client, headers, b"").status_code == 422


def test_oversized_upload_is_rejected(client):
    headers = _register(client, "big@example.com")
    r = _upload(client, headers, b"x" * (MAX_UPLOAD_BYTES + 1))
    assert r.status_code == 413
    assert "too large" in r.json()["detail"]


@pytest.mark.parametrize(
    "ctype", ["image/jpeg", "image/png", "image/webp", "image/gif"]
)
def test_every_platform_supported_image_type_is_accepted(client, ctype):
    headers = _register(client, f"type-{ctype.split('/')[1]}@example.com")
    assert _upload(client, headers, PNG_BYTES, "x", ctype).status_code == 201


def test_content_type_with_charset_suffix_is_accepted(client):
    """Some browsers send `image/png; charset=binary`."""
    headers = _register(client, "charset@example.com")
    assert _upload(
        client, headers, PNG_BYTES, "x.png", "image/png; charset=binary"
    ).status_code == 201


def test_upload_is_attributed_to_the_uploading_user(client):
    """Two users' uploads stay distinct; neither token collides or overwrites."""
    a = _register(client, "user-a@example.com")
    b = _register(client, "user-b@example.com")
    token_a = _upload(client, a, PNG_BYTES, "a.png").json()["token"]
    token_b = _upload(client, b, PNG_BYTES + b"\x00", "b.png").json()["token"]

    assert token_a != token_b
    assert client.get(f"/api/media/{token_a}").content == PNG_BYTES
    assert client.get(f"/api/media/{token_b}").content == PNG_BYTES + b"\x00"


def test_uploaded_image_can_be_published_as_a_pin(client, monkeypatch):
    """The whole point: upload → post → Pin, with Pinterest fetching the URL."""
    import httpx

    from app.core.timeutils import utcnow
    from app.models.social_account import SocialAccount
    from app.schemas.post import Platform

    headers = _register(client, "e2e@example.com")
    uploaded = _upload(client, headers).json()

    # Connect Pinterest for this user.
    db = next(app.dependency_overrides[get_db]())
    user_id = client.get("/auth/me", headers=headers).json()["id"]
    db.add(
        SocialAccount(
            user_id=user_id,
            platform=Platform.pinterest.value,
            access_token="pina-token",
            account_id="tester",
            username="tester",
            status="connected",
            connected_at=utcnow(),
            page_id="board-1",
        )
    )
    db.commit()
    db.close()

    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = str(request.url).rsplit("/v5/", 1)[-1].split("?")[0]
        if path.startswith("boards/"):
            return httpx.Response(200, json={"id": "board-1", "name": "Board"})
        if path == "pins":
            import json as _json

            seen["body"] = _json.loads(request.content)
            return httpx.Response(201, json={"id": "pin-999"})
        return httpx.Response(404, json={"code": 0, "message": "nope"})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **kw: real_client(*a, **{**kw, "transport": httpx.MockTransport(handler)}),
    )

    post = client.post(
        "/api/posts",
        json={
            "platform": "pinterest",
            "content": "From an uploaded photo",
            "media": [{"type": "image", "url": uploaded["url"]}],
        },
        headers=headers,
    ).json()
    published = client.post(f"/api/posts/{post['id']}/publish", headers=headers).json()

    assert published["status"] == "published"
    assert published["external_id"] == "pin-999"
    # Pinterest was handed the uploaded image's public URL.
    assert seen["body"]["media_source"] == {
        "source_type": "image_url",
        "url": uploaded["url"],
    }
