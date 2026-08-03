"""Tests for PATCH /auth/me — the endpoint behind Settings → Edit Profile.

Runs against a throwaway SQLite database so it needs no external services and
leaves no state behind. The app's `get_db` dependency is overridden rather than
mocked so the route exercises real SQLAlchemy session behaviour.
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


@pytest.fixture()
def client():
    tmp = Path(tempfile.mkdtemp()) / "test.db"
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


def _register(client, email="settings@example.com", name="Original Name"):
    client.post(
        "/auth/register",
        json={"email": email, "password": "correct-horse", "full_name": name},
    )
    token = client.post(
        "/auth/login", data={"username": email, "password": "correct-horse"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_updates_full_name(client):
    headers = _register(client)

    r = client.patch("/auth/me", json={"full_name": "Fatima Aslam"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["full_name"] == "Fatima Aslam"

    # The change persists to the next read, not just the response body.
    assert client.get("/auth/me", headers=headers).json()["full_name"] == "Fatima Aslam"


def test_omitted_fields_are_left_alone(client):
    """An empty patch must not blank out existing values.

    This is the reason the route uses exclude_unset: without it, an unset
    `full_name` would arrive as None and silently wipe the stored name.
    """
    headers = _register(client, email="untouched@example.com", name="Keep Me")

    r = client.patch("/auth/me", json={}, headers=headers)
    assert r.status_code == 200
    assert r.json()["full_name"] == "Keep Me"


def test_whitespace_only_name_is_stored_as_null(client):
    headers = _register(client, email="blank@example.com")

    r = client.patch("/auth/me", json={"full_name": "   "}, headers=headers)
    assert r.status_code == 200
    assert r.json()["full_name"] is None


def test_requires_authentication(client):
    assert client.patch("/auth/me", json={"full_name": "Nobody"}).status_code == 401


def test_cannot_change_email_or_privileged_fields(client):
    """Unknown keys must be ignored, not applied.

    Email identifies the account and is not user-editable here; is_active would
    let a user resurrect a disabled account.
    """
    headers = _register(client, email="fixed@example.com")

    r = client.patch(
        "/auth/me",
        json={"full_name": "New Name", "email": "attacker@example.com", "is_active": False},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "fixed@example.com"
    assert body["is_active"] is True
    assert body["full_name"] == "New Name"
