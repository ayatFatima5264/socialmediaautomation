"""Shared fixtures for the Video Studio asset-system tests.

The three suites this supports — the Media Library, Templates and the Music
Library — all need the same thing: a real FastAPI app, a real database with the
full schema, and object storage pointed somewhere that is not the developer's
machine. That setup was already being written out longhand in
`test_video_api.py`; it is here so the three new files do not make four copies
of it.

Every fixture is named distinctly (`studio_client`, not `client`) so nothing
here shadows the local fixtures the existing suites define for themselves. A
conftest fixture silently replacing one a test file already had is exactly the
kind of change that makes an unrelated suite fail for reasons nobody can find.

**Nothing in these tests reaches the network.** Storage is the database
backend, no TTS provider is called, and the Openverse client is replaced by the
`fake_openverse` fixture wherever a music search is exercised.
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers every model on Base.metadata)
from app.database import Base, get_db
from app.main import app
from app.services.storage import reset_storage_cache

PASSWORD = "correct-horse-battery"

# A 44-byte silent WAV — real enough for ffmpeg to probe, small enough to
# inline. Same bytes `test_video_foundation.py` uses.
WAV_BYTES = (
    b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
    b"\x44\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
)

# A 32x32 solid-colour PNG, 99 bytes.
#
# Deliberately not the 1x1 PNG used elsewhere in the suite: ingest probes an
# image with ffmpeg and the dimension pattern it matches on requires at least
# two digits, so a 1x1 file is reported as having no video stream and is
# rejected. That is a sensible guard against matching stray numbers in an
# ffmpeg log, but it means a one-pixel image is not a valid fixture here.
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000020000000200802000000fc18eda3"
    "0000002a49444154789c6310d8d94853c4306ac1a805a3168c5a306ac1a805a316"
    "8c5a306ac1a805a3160c150b009cfe284cfedcae2b0000000049454e44ae426082"
)

SRT_BYTES = b"1\n00:00:00,000 --> 00:00:02,000\nHello\n"


def png_bytes(width: int = 32, height: int = 32, rgb: tuple = (16, 185, 129)) -> bytes:
    """A real, valid PNG of the given size and colour.

    Needed because ingest genuinely decodes what it is given: appending a byte
    to an existing PNG to make "a different file" produces something ffmpeg
    rejects as corrupt, so every test that needs two distinct images has to
    build two real ones. Varying the size or the colour changes the bytes, and
    therefore the checksum, which is what the de-duplication tests turn on.
    """
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return (
            struct.pack(">I", len(data))
            + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


@pytest.fixture()
def studio_session_factory(tmp_path, monkeypatch):
    """A database with the full schema, with storage pointed at it.

    `DatabaseStorage` opens its own sessions by design — it has to work from a
    background renderer that has no request-scoped session — so `SessionLocal`
    is monkeypatched or it writes to the developer's real database.
    """
    url = f"sqlite:///{(tmp_path / 'studio.db').as_posix()}"
    engine = create_engine(url, connect_args={"check_same_thread": False})

    # SQLite ignores foreign keys unless asked, per connection. Without this,
    # the `ON DELETE SET NULL` that every asset reference is declared with does
    # nothing here — so a test asserting that deleting a file empties the scene
    # using it would pass on Postgres and quietly prove nothing on SQLite.
    @event.listens_for(engine, "connect")
    def _enforce_foreign_keys(dbapi_connection, _record):  # pragma: no cover
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    monkeypatch.setattr("app.services.storage.database.SessionLocal", factory)
    monkeypatch.setattr("app.config.settings.storage_backend", "database")
    reset_storage_cache()

    yield factory

    reset_storage_cache()
    engine.dispose()


@pytest.fixture()
def studio_client(studio_session_factory):
    """The real app, on the test database, with the system templates seeded."""
    factory = studio_session_factory

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    # What `init_db()` does on boot, minus the parts these routes do not need.
    # Without it there are no system templates and every template assertion is
    # made against an empty library.
    from app.services.video import templates as template_service

    seed = factory()
    try:
        template_service.sync_system_templates(seed)
    finally:
        seed.close()

    app.dependency_overrides[get_db] = override_get_db
    # Not `with TestClient(...)`: that runs lifespan, which starts the
    # scheduler and touches the real database. None of these routes need it.
    yield TestClient(app)

    app.dependency_overrides.clear()


@pytest.fixture()
def studio_db(studio_session_factory):
    """A plain session, for the assertions that are easier against the ORM."""
    session = studio_session_factory()
    try:
        yield session
    finally:
        session.close()


def register(client, email="assets@example.com") -> dict:
    """Create an account and return its Authorization header."""
    client.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Asset Tester"},
    )
    token = client.post(
        "/auth/login", data={"username": email, "password": PASSWORD}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def headers(studio_client) -> dict:
    return register(studio_client)


@pytest.fixture()
def other_headers(studio_client) -> dict:
    """A second account. Every ownership test needs somebody else to be."""
    return register(studio_client, email="someone-else@example.com")


@pytest.fixture()
def project(studio_client, headers) -> dict:
    response = studio_client.post("/api/video/projects", headers=headers, json={})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture(scope="session")
def small_video(tmp_path_factory) -> bytes:
    """A real one-second MP4, encoded once per session.

    Ingest probes an upload with ffmpeg rather than trusting the declared
    content type, so a test that needs a *video* needs real video bytes — a
    buffer labelled `video/mp4` is rejected, correctly, and no amount of
    labelling gets around it. Session-scoped because the encode is the slowest
    thing in the suite and every copy is identical.
    """
    import subprocess
    import tempfile

    from app.services.video.ffmpeg import ffmpeg_path

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "clip.mp4"
        subprocess.run(
            [
                ffmpeg_path(), "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=1",
                "-f", "lavfi", "-i", "sine=frequency=300:duration=1",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                "-shortest", "-y", str(path),
            ],
            check=True, capture_output=True, timeout=120,
        )
        return path.read_bytes()
