"""Tests for cached profile pictures.

Meta and LinkedIn hand out signed avatar URLs that expire, so a connected
account's picture used to turn into a broken image a few weeks after connecting.
These cover the copy-it-while-it-is-fresh path in
`app.services.social_accounts.avatar`, and the soft failures that must never
take a connect or a sync down with them.
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.media_asset import MediaAsset
from app.models.user import User
from app.services.social_accounts import avatar

# The smallest valid PNG (1x1, transparent).
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6360000002000100ffff03000006"
    "000557bfabd40000000049454e44ae426082"
)

REMOTE = "https://scontent.example.com/avatar.png?oe=6A51E933"


@pytest.fixture()
def db():
    tmp = Path(tempfile.mkdtemp()) / "avatar.db"
    engine = create_engine(f"sqlite:///{tmp}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    session.add(User(email="a@example.com", full_name="A", hashed_password="x"))
    session.commit()
    yield session
    session.close()
    engine.dispose()


class _Response:
    def __init__(self, status: int, content: bytes, content_type: str):
        self.status_code = status
        self.content = content
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code}", request=None, response=None
            )


def _serve(monkeypatch, response, log: list | None = None):
    """Point the avatar fetcher at a canned response instead of the network."""

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            if log is not None:
                log.append(url)
            return response

    monkeypatch.setattr(avatar.httpx, "AsyncClient", _Client)


def _cache(db, url, previous=None):
    return asyncio.run(
        avatar.cache_avatar(db, user_id=1, url=url, previous=previous)
    )


def test_live_avatar_is_copied_into_our_own_media(db, monkeypatch):
    _serve(monkeypatch, _Response(200, PNG_BYTES, "image/png"))

    url = _cache(db, REMOTE)

    token = avatar.cached_token(url)
    assert token, f"expected a media URL, got {url}"
    asset = db.query(MediaAsset).filter_by(token=token).one()
    assert asset.data == PNG_BYTES
    assert asset.content_type == "image/png"


def test_our_own_url_is_not_refetched(db, monkeypatch):
    fetched: list[str] = []
    _serve(monkeypatch, _Response(200, PNG_BYTES, "image/png"), log=fetched)

    ours = _cache(db, REMOTE)
    fetched.clear()

    assert _cache(db, ours) == ours
    assert fetched == []


def test_expired_signature_keeps_the_original_url(db, monkeypatch):
    # What an aged Meta avatar link actually answers.
    _serve(monkeypatch, _Response(403, b"", "text/plain"))

    assert _cache(db, REMOTE) == REMOTE
    assert db.query(MediaAsset).count() == 0


def test_a_non_image_is_not_stored(db, monkeypatch):
    _serve(monkeypatch, _Response(200, b"{}", "application/json"))

    assert _cache(db, REMOTE) == REMOTE
    assert db.query(MediaAsset).count() == 0


def test_an_oversized_avatar_is_not_stored(db, monkeypatch):
    too_big = b"\x00" * (avatar.MAX_AVATAR_BYTES + 1)
    _serve(monkeypatch, _Response(200, too_big, "image/png"))

    assert _cache(db, REMOTE) == REMOTE
    assert db.query(MediaAsset).count() == 0


def test_resyncing_replaces_the_previous_copy(db, monkeypatch):
    _serve(monkeypatch, _Response(200, PNG_BYTES, "image/png"))

    first = _cache(db, REMOTE)
    second = _cache(db, "https://scontent.example.com/avatar.png?oe=NEWER", previous=first)

    assert second != first
    assert avatar.cached_token(first) not in {a.token for a in db.query(MediaAsset)}
    assert db.query(MediaAsset).count() == 1


def test_no_picture_stays_none(db, monkeypatch):
    _serve(monkeypatch, _Response(200, PNG_BYTES, "image/png"))
    assert _cache(db, None) is None
