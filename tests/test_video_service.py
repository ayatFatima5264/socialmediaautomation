"""Tests for image → Reel rendering.

Two things here are worth more than the rendering itself. The source URL is
supplied by the caller and fetched by *our* server, so the guard against
private address space is a security boundary, not a nicety. And the endpoint
must hand back a public /api/media URL — a server filesystem path is useless to
the client and to the platform that has to fetch it.

Nothing here reaches the network: the download is mocked, and the one real
render runs at a deliberately tiny size.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.services import video_service
from app.services.video_service import (
    MAX_SOURCE_BYTES,
    VideoGenerationError,
    _assert_public_http_url,
    generate_image_video,
)

# An 8x14 JPEG — a real one Pillow can decode, small enough to inline.
JPEG_BYTES = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb0043001b12141714111b1716"
    "171e1c1b2028422b28252528513a3d3042605565645f555d5b6a7899816a7190735b"
    "5d85b586909ea3abadab6780bcc9baa6c799a8aba4ffdb0043011c1e1e2823284e2b"
    "2b4ea46e5d6ea4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4"
    "a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4ffc0001108000e0008030122"
    "00021101031101ffc4001f0000010501010101010100000000000000000102030405"
    "060708090a0bffc400b5100002010303020403050504040000017d01020300041105"
    "122131410613516107227114328191a1082342b1c11552d1f02433627282090a1617"
    "18191a25262728292a3435363738393a434445464748494a535455565758595a6364"
    "65666768696a737475767778797a838485868788898a92939495969798999aa2a3a4"
    "a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1"
    "e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9faffc4001f0100030101010101010101"
    "010000000000000102030405060708090a0bffc400b5110002010204040304070504"
    "0400010277000102031104052131061241510761711322328108144291a1b1c10923"
    "3352f0156272d10a162434e125f11718191a262728292a35363738393a4344454647"
    "48494a535455565758595a636465666768696a737475767778797a82838485868788"
    "898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6"
    "c7c8c9cad2d3d4d5d6d7d8d9dae2e3e4e5e6e7e8e9eaf2f3f4f5f6f7f8f9faffda00"
    "0c03010002110311003f008a8a28aee28fffd9"
)


# ---------------------------------------------------------------------------
# The SSRF boundary: what the server is willing to fetch on a caller's behalf.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/img.jpg",
        "http://localhost/img.jpg",
        # The cloud metadata service — the classic SSRF payload.
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/img.jpg",
        "http://192.168.1.1/img.jpg",
        "http://172.16.0.1/img.jpg",
        "http://[::1]/img.jpg",
    ],
)
def test_private_and_loopback_hosts_are_refused(url):
    with pytest.raises(VideoGenerationError, match="public host"):
        _assert_public_http_url(url)


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "ftp://example.com/x.jpg", "gopher://x/1"]
)
def test_non_http_schemes_are_refused(url):
    with pytest.raises(VideoGenerationError, match="http"):
        _assert_public_http_url(url)


def test_a_public_address_is_allowed():
    # An IP literal, so this doesn't depend on DNS being reachable.
    _assert_public_http_url("https://8.8.8.8/img.jpg")


@pytest.fixture()
def anyio_backend():
    return "asyncio"


def _mock_httpx(monkeypatch, handler):
    """Route every AsyncClient in the process through `handler`."""
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **kw: real_client(
            *a, **{**kw, "transport": httpx.MockTransport(handler)}
        ),
    )


@pytest.mark.anyio
async def test_a_redirect_to_an_internal_host_is_refused(monkeypatch):
    """A public URL is free to redirect at an internal one — the final host is
    what actually gets fetched, so every hop is re-checked."""
    _mock_httpx(
        monkeypatch,
        lambda request: httpx.Response(
            302, headers={"location": "http://169.254.169.254/latest/meta-data/"}
        ),
    )
    with pytest.raises(VideoGenerationError, match="public host"):
        await video_service._fetch_image_bytes("https://8.8.8.8/img.jpg")


@pytest.mark.anyio
async def test_an_oversized_body_is_refused_without_being_buffered(monkeypatch):
    _mock_httpx(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            headers={"content-type": "image/jpeg"},
            content=b"x" * (MAX_SOURCE_BYTES + 1024),
        ),
    )
    with pytest.raises(VideoGenerationError, match="larger than"):
        await video_service._fetch_image_bytes("https://8.8.8.8/big.jpg")


@pytest.mark.anyio
async def test_a_non_image_response_is_refused(monkeypatch):
    _mock_httpx(
        monkeypatch,
        lambda request: httpx.Response(
            200, headers={"content-type": "text/html"}, content=b"<html>"
        ),
    )
    with pytest.raises(VideoGenerationError, match="did not return an image"):
        await video_service._fetch_image_bytes("https://8.8.8.8/page.html")


@pytest.mark.anyio
async def test_endless_redirects_terminate(monkeypatch):
    _mock_httpx(
        monkeypatch,
        lambda request: httpx.Response(
            302, headers={"location": "https://8.8.8.8/again"}
        ),
    )
    with pytest.raises(VideoGenerationError, match="too many times"):
        await video_service._fetch_image_bytes("https://8.8.8.8/img.jpg")


# ---------------------------------------------------------------------------
# Rendering: parameter validation and file ownership.
# ---------------------------------------------------------------------------
@pytest.mark.anyio
@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"duration": 0}, "duration"),
        ({"duration": -1}, "duration"),
        ({"width": 0}, "width and height"),
        ({"height": -10}, "width and height"),
        ({"zoom": 0.9}, "Zoom must be >= 1.0"),
        ({"zoom": 2.0}, "not be greater than 1.5"),
    ],
)
async def test_invalid_parameters_are_rejected(kwargs, message):
    with pytest.raises(VideoGenerationError, match=message):
        await generate_image_video("https://8.8.8.8/img.jpg", **kwargs)


@pytest.mark.anyio
async def test_a_failed_render_leaves_no_output_file(monkeypatch, tmp_path):
    """Including the file the caller named — a partial MP4 is not a result."""
    out = tmp_path / "reel.mp4"

    async def boom(url):
        raise VideoGenerationError("nope")

    monkeypatch.setattr(video_service, "_fetch_image_bytes", boom)

    with pytest.raises(VideoGenerationError):
        await generate_image_video("https://8.8.8.8/img.jpg", output_path=str(out))

    assert not out.exists()


@pytest.mark.anyio
async def test_render_produces_a_playable_file_and_cleans_up(monkeypatch, tmp_path):
    """The real thing, at a size that renders in well under a second."""

    async def fake_fetch(url):
        return JPEG_BYTES

    monkeypatch.setattr(video_service, "_fetch_image_bytes", fake_fetch)

    before = set(Path(tempfile.gettempdir()).glob("autosocial_video_*"))
    out = tmp_path / "reel.mp4"

    result = await generate_image_video(
        "https://8.8.8.8/img.jpg",
        duration=0.2,
        width=64,
        height=112,
        # 1.0 must be legal and must mean "no zoom" — it is the documented
        # floor of the range the API accepts.
        zoom=1.0,
        output_path=str(out),
    )

    assert result == str(out)
    assert out.exists() and out.stat().st_size > 0
    # The scratch directory holding the downloaded/prepared frames is gone.
    assert set(Path(tempfile.gettempdir()).glob("autosocial_video_*")) == before


# ---------------------------------------------------------------------------
# The endpoint: authenticated, and it returns a URL rather than a server path.
# ---------------------------------------------------------------------------
@pytest.fixture()
def client():
    tmp = Path(tempfile.mkdtemp()) / "video.db"
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


def _register(client, email="video@example.com"):
    client.post(
        "/auth/register",
        json={"email": email, "password": "correct-horse", "full_name": "Video"},
    )
    token = client.post(
        "/auth/login", data={"username": email, "password": "correct-horse"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


REQUEST = {"image_url": "https://8.8.8.8/img.jpg", "duration": 2.0}


def test_generating_a_video_requires_authentication(client):
    """It burns real CPU and fetches a caller-supplied URL server-side."""
    assert client.post("/api/generate-video", json=REQUEST).status_code == 401


def test_the_response_is_a_fetchable_url_not_a_server_path(client, monkeypatch):
    rendered: dict = {}

    async def fake_render(image_url, **kwargs):
        path = Path(kwargs["output_path"])
        path.write_bytes(b"\x00\x00\x00 ftypisom fake mp4")
        rendered["path"] = path
        return str(path)

    monkeypatch.setattr("app.routes.posts.generate_image_video", fake_render)

    headers = _register(client)
    r = client.post("/api/generate-video", json=REQUEST, headers=headers)
    assert r.status_code == 200

    body = r.json()
    assert body["video_url"].startswith("http")
    assert "/api/media/" in body["video_url"]
    # Not a filesystem path — no drive letter, no temp directory.
    assert "Temp" not in body["video_url"] and ":\\" not in body["video_url"]

    # And the URL actually serves the video, with no auth, as a platform would.
    token = body["video_url"].rsplit("/", 1)[-1]
    got = client.get(f"/api/media/{token}")
    assert got.status_code == 200
    assert got.headers["content-type"] == "video/mp4"

    # The rendered file was deleted once its bytes were in the database.
    assert not rendered["path"].exists()


def test_a_render_failure_is_reported_and_cleans_up(client, monkeypatch):
    rendered: dict = {}

    async def fake_render(image_url, **kwargs):
        rendered["path"] = Path(kwargs["output_path"])
        raise video_service.VideoGenerationError(
            "Image URL must point at a public host."
        )

    monkeypatch.setattr("app.routes.posts.generate_image_video", fake_render)

    headers = _register(client, "fail@example.com")
    r = client.post("/api/generate-video", json=REQUEST, headers=headers)

    assert r.status_code == 502
    assert "public host" in r.json()["detail"]
    assert not rendered["path"].exists()
