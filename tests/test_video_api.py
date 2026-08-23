"""Video Studio HTTP layer: the routes the frontend actually calls.

The service layer is covered in `test_video_foundation.py`. What is tested here
is everything that only exists at the HTTP boundary and could therefore be got
wrong without a single service test failing:

  * an endpoint that forgot its `Depends(get_current_user)`,
  * an ownership check that exists in the service but is bypassed by the route,
  * the wrong status code for a conflict or a missing project,
  * a partial PATCH that blanks the fields it did not mention,
  * and the one route that is public on purpose.

Every test drives the real router through `TestClient`. Nothing reaches the
network: storage is the database backend, and no AI provider is called.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.database import Base, get_db
from app.main import app
from app.services.storage import reset_storage_cache

PASSWORD = "correct-horse-battery"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'api.db').as_posix()}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    # DatabaseStorage opens its own sessions by design, so it has to be pointed
    # at the test database explicitly or it writes to the developer's.
    monkeypatch.setattr("app.services.storage.database.SessionLocal", factory)
    monkeypatch.setattr("app.config.settings.storage_backend", "database")
    reset_storage_cache()

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    # What `init_db()` does on boot, minus the parts these routes do not need.
    # Without it there are no system templates and every template test is
    # asserting against an empty library.
    from app.services.video import templates as template_service

    seed = factory()
    try:
        template_service.sync_system_templates(seed)
    finally:
        seed.close()

    app.dependency_overrides[get_db] = override_get_db
    # `with TestClient(...)` runs lifespan, which would start the scheduler and
    # touch the real database; the routes under test need neither.
    yield TestClient(app)

    app.dependency_overrides.clear()
    reset_storage_cache()
    engine.dispose()


def auth(client, email="studio@example.com") -> dict:
    client.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Studio"},
    )
    token = client.post(
        "/auth/login", data={"username": email, "password": PASSWORD}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def make_project(client, headers, **body) -> dict:
    response = client.post("/api/video/projects", headers=headers, json=body or {})
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/video/capabilities"),
        ("get", "/api/video/templates"),
        ("get", "/api/video/projects"),
        ("post", "/api/video/projects"),
        ("get", "/api/video/projects/1"),
        ("patch", "/api/video/projects/1"),
        ("post", "/api/video/projects/1/rename"),
        ("post", "/api/video/projects/1/duplicate"),
        ("delete", "/api/video/projects/1"),
        ("get", "/api/video/assets"),
        ("delete", "/api/video/assets/1"),
    ],
)
def test_every_studio_route_requires_a_token(client, method, path):
    """A route that forgot its dependency is invisible to service tests."""
    # GET and DELETE take no body in this client; only send one where it is
    # allowed, or the request fails on the client side and proves nothing.
    kwargs = {"json": {}} if method in ("post", "patch", "put") else {}
    response = getattr(client, method)(path, **kwargs)
    assert response.status_code == 401, f"{method.upper()} {path} was reachable"


# ---------------------------------------------------------------------------
# Capabilities and templates
# ---------------------------------------------------------------------------


def test_capabilities_reports_the_real_configuration(client):
    headers = auth(client)

    body = client.get("/api/video/capabilities", headers=headers).json()

    assert body["storage_backend"] == "database"
    # The development backend must not be advertised as persistent — a user
    # would otherwise build a library on bytes sitting in Postgres.
    assert body["storage_is_persistent"] is False
    assert {p["key"] for p in body["presets"]} >= {
        "youtube", "youtube_shorts", "tiktok", "instagram_reels",
        "instagram_post", "facebook", "custom",
    }
    assert body["limits"]["max_duration_seconds"] > 0
    assert body["limits"]["reason"]


def test_templates_are_listed_with_scene_counts(client):
    headers = auth(client)

    body = client.get("/api/video/templates", headers=headers).json()
    templates = body["templates"]

    assert templates, "system templates should be seeded"
    by_key = {t["key"]: t for t in templates}
    assert by_key["listicle_shorts"]["scene_count"] == 7
    assert by_key["blank_shorts"]["scene_count"] == 0
    assert all(t["is_system"] for t in templates)

    # The card renders its own preview from the definition, so a template with
    # no artwork still has something to draw. See TemplateRead.
    assert by_key["listicle_shorts"]["preview"]["accent"]
    assert by_key["listicle_shorts"]["estimated_seconds"] == 31.0


def test_template_categories_come_back_with_the_templates(client):
    """The tab row and the grid are one request, so they cannot disagree."""
    headers = auth(client)

    body = client.get("/api/video/templates", headers=headers).json()
    categories = {entry["key"]: entry for entry in body["categories"]}

    # Every category the model names is populated by the seeder; a tab that
    # leads to an empty grid is worse than no tab.
    for key in ("youtube", "shorts", "tiktok", "reels", "educational",
                "business", "motivation", "facts", "product", "documentary",
                "storytelling", "animated"):
        assert key in categories, f"no templates seeded for {key}"
        assert categories[key]["count"] > 0

    assert categories["tiktok"]["is_surface"] is True
    assert categories["facts"]["is_surface"] is False
    assert categories["youtube"]["label"] == "YouTube"


def test_templates_can_be_filtered_by_category(client):
    headers = auth(client)

    body = client.get(
        "/api/video/templates?category=animated", headers=headers
    ).json()

    assert body["templates"]
    assert all(t["category"] == "animated" for t in body["templates"])
    # The counts stay whole-library so filtering does not strand the user in
    # the one tab they picked.
    counts = {entry["key"]: entry["count"] for entry in body["categories"]}
    assert counts["shorts"] > 0


# ---------------------------------------------------------------------------
# Project CRUD
# ---------------------------------------------------------------------------


def test_create_project_returns_the_preset_canvas(client):
    headers = auth(client)

    project = make_project(client, headers, name="My Short", platform="tiktok")

    assert project["platform"] == "tiktok"
    assert (project["width"], project["height"]) == (1080, 1920)
    assert project["status"] == "draft"
    assert project["revision"] == 0
    assert project["subtitle_count"] == 1


def test_create_project_from_a_template(client):
    headers = auth(client)

    project = make_project(client, headers, template_key="listicle_shorts")

    assert project["template_key"] == "listicle_shorts"
    assert project["scene_count"] == 7


def test_create_project_rejects_an_unknown_template(client):
    headers = auth(client)

    response = client.post(
        "/api/video/projects", headers=headers, json={"template_key": "nope"}
    )

    assert response.status_code == 404


def test_create_project_rejects_an_unknown_type(client):
    headers = auth(client)

    response = client.post(
        "/api/video/projects", headers=headers, json={"project_type": "telepathy"}
    )

    assert response.status_code == 422


def test_list_projects_supports_search_and_filter(client):
    headers = auth(client)
    make_project(client, headers, name="Coffee Reel", platform="instagram_reels")
    make_project(client, headers, name="Bakery Tour", platform="youtube")

    everything = client.get("/api/video/projects", headers=headers).json()
    assert everything["total"] == 2

    searched = client.get("/api/video/projects?search=coffee", headers=headers).json()
    assert [p["name"] for p in searched["projects"]] == ["Coffee Reel"]

    filtered = client.get("/api/video/projects?platform=youtube", headers=headers).json()
    assert [p["name"] for p in filtered["projects"]] == ["Bakery Tour"]

    empty = client.get("/api/video/projects?search=zzzz", headers=headers).json()
    assert empty["projects"] == []
    # `total` is the account's project count, not the filtered count — the UI
    # shows "0 of 2", which would be a lie the other way round.
    assert empty["total"] == 2


def test_get_project_returns_its_documents(client):
    headers = auth(client)
    created = make_project(client, headers)

    detail = client.get(f"/api/video/projects/{created['id']}", headers=headers).json()

    assert "timeline" in detail and "tracks" in detail["timeline"]
    assert [t["id"] for t in detail["timeline"]["tracks"]] == [
        "text", "video", "audio", "subtitles",
    ]


def test_patch_only_touches_what_it_names(client):
    """The editor autosaves a partial patch. An absent field must not be read
    as an explicit null, or every keystroke blanks the rest of the project."""
    headers = auth(client)
    created = make_project(client, headers, name="Keep my name")

    response = client.patch(
        f"/api/video/projects/{created['id']}",
        headers=headers,
        json={"notes": "just the notes", "expected_revision": 0},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["notes"] == "just the notes"
    assert body["name"] == "Keep my name"
    assert body["timeline"]["tracks"]
    assert body["revision"] == 1


def test_a_stale_save_is_a_conflict_not_an_overwrite(client):
    headers = auth(client)
    created = make_project(client, headers)
    path = f"/api/video/projects/{created['id']}"

    client.patch(path, headers=headers, json={"notes": "first", "expected_revision": 0})
    stale = client.patch(
        path, headers=headers, json={"notes": "second", "expected_revision": 0}
    )

    assert stale.status_code == 409
    assert "changed somewhere else" in stale.json()["detail"]
    assert client.get(path, headers=headers).json()["notes"] == "first"


def test_autosave_updates_the_timeline_and_duration(client):
    headers = auth(client)
    created = make_project(client, headers)

    body = client.patch(
        f"/api/video/projects/{created['id']}",
        headers=headers,
        json={
            "timeline": {"tracks": [{"id": "video", "clips": [
                {"start": 0.0, "duration": 7.25}
            ]}]},
            "autosave": True,
            "expected_revision": 0,
        },
    ).json()

    assert body["duration_seconds"] == 7.25
    assert body["last_autosave_at"] is not None


def test_rename_needs_no_revision_and_refuses_an_empty_name(client):
    headers = auth(client)
    created = make_project(client, headers, name="Before")
    path = f"/api/video/projects/{created['id']}/rename"

    assert client.post(path, headers=headers, json={"name": "After"}).json()["name"] == "After"
    assert client.post(path, headers=headers, json={"name": "   "}).status_code == 422


def test_duplicate_creates_a_separate_draft(client):
    headers = auth(client)
    created = make_project(client, headers, name="Original", template_key="listicle_shorts")

    copy = client.post(
        f"/api/video/projects/{created['id']}/duplicate", headers=headers
    ).json()

    assert copy["id"] != created["id"]
    assert copy["name"] == "Original (copy)"
    assert copy["status"] == "draft"
    assert copy["scene_count"] == 7
    assert client.get("/api/video/projects", headers=headers).json()["total"] == 2


def test_delete_removes_the_project(client):
    headers = auth(client)
    created = make_project(client, headers)
    path = f"/api/video/projects/{created['id']}"

    assert client.delete(path, headers=headers).status_code == 204
    assert client.get(path, headers=headers).status_code == 404
    assert client.get("/api/video/projects", headers=headers).json()["total"] == 0


def test_a_missing_project_is_404_on_every_verb(client):
    headers = auth(client)

    assert client.get("/api/video/projects/424242", headers=headers).status_code == 404
    assert client.patch(
        "/api/video/projects/424242", headers=headers, json={"notes": "x"}
    ).status_code == 404
    assert client.delete("/api/video/projects/424242", headers=headers).status_code == 404


# ---------------------------------------------------------------------------
# Authorization across accounts
# ---------------------------------------------------------------------------


def test_one_account_cannot_touch_anothers_project(client):
    """The service enforces this; the point here is that the route does not
    route around it. A 404 rather than a 403 — see `_http` in routes/video."""
    mine = auth(client, "mine@example.com")
    theirs = auth(client, "theirs@example.com")

    their_project = make_project(client, theirs, name="Private")
    path = f"/api/video/projects/{their_project['id']}"

    assert client.get(path, headers=mine).status_code == 404
    assert client.patch(path, headers=mine, json={"name": "Stolen"}).status_code == 404
    assert client.post(f"{path}/rename", headers=mine, json={"name": "Stolen"}).status_code == 404
    assert client.post(f"{path}/duplicate", headers=mine).status_code == 404
    assert client.delete(path, headers=mine).status_code == 404

    # And it is genuinely untouched.
    assert client.get(path, headers=theirs).json()["name"] == "Private"


def test_project_lists_never_cross_accounts(client):
    mine = auth(client, "a@example.com")
    theirs = auth(client, "b@example.com")
    make_project(client, mine, name="Mine")
    make_project(client, theirs, name="Theirs")

    listing = client.get("/api/video/projects", headers=mine).json()

    assert listing["total"] == 1
    assert [p["name"] for p in listing["projects"]] == ["Mine"]


def test_another_accounts_asset_cannot_be_deleted(client):
    from app.services.video import assets as asset_service

    mine = auth(client, "one@example.com")
    theirs = auth(client, "two@example.com")

    # Create an asset owned by the second account, directly.
    db = next(app.dependency_overrides[get_db]())
    from app.models.user import User

    owner = db.query(User).filter_by(email="two@example.com").one()
    asset = asset_service.store_asset(
        db, user_id=owner.id, kind="subtitle", data=b"theirs", content_type="text/vtt"
    )
    asset_id = asset.id
    db.close()

    assert client.delete(f"/api/video/assets/{asset_id}", headers=mine).status_code == 404
    assert client.delete(f"/api/video/assets/{asset_id}", headers=theirs).status_code == 204


# ---------------------------------------------------------------------------
# The public object route
# ---------------------------------------------------------------------------


def test_stored_objects_are_readable_without_a_session(client):
    """Public on purpose: Instagram and Pinterest fetch the URL from their own
    servers, carrying none of our credentials."""
    from app.models.user import User
    from app.services.video import assets as asset_service

    headers = auth(client)
    db = next(app.dependency_overrides[get_db]())
    user = db.query(User).one()
    asset = asset_service.store_asset(
        db,
        user_id=user.id,
        kind="subtitle",
        data=b"WEBVTT\n\n00:00.000 --> 00:02.000\nHello\n",
        content_type="text/vtt",
    )
    token = asset.token
    db.close()

    response = client.get(f"/api/storage/o/{token}")

    assert response.status_code == 200
    assert b"Hello" in response.content
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_an_unknown_object_token_is_404(client):
    assert client.get("/api/storage/o/not-a-real-token").status_code == 404


def test_asset_urls_are_ours_not_the_buckets(client):
    """A presigned URL expires and a public bucket URL pins the row to one
    vendor. Assets are always addressed through our own route."""
    from app.models.user import User
    from app.services.video import assets as asset_service

    headers = auth(client)
    db = next(app.dependency_overrides[get_db]())
    user = db.query(User).one()
    asset_service.store_asset(
        db, user_id=user.id, kind="thumbnail", data=b"x", content_type="image/png"
    )
    db.close()

    listed = client.get("/api/video/assets", headers=headers).json()

    assert len(listed) == 1
    assert "/api/storage/o/" in listed[0]["url"]


# ---------------------------------------------------------------------------
# Range requests
# ---------------------------------------------------------------------------
# Not an optimisation. A browser opens audio and video with `Range: bytes=0-`
# and seeks by asking for byte ranges; a route that answers every one of those
# with a plain 200 leaves Chrome's media pipeline stalled and the file never
# plays. These lock that in.


def _stored_asset(client, headers, data=b"0123456789abcdef", kind="voice"):
    from app.models.user import User
    from app.services.video import assets as asset_service

    db = next(app.dependency_overrides[get_db]())
    user = db.query(User).order_by(User.id.desc()).first()
    asset = asset_service.store_asset(
        db,
        user_id=user.id,
        kind=kind,
        data=data,
        content_type="audio/mpeg",
        filename="take.mp3",
        probe=False,
    )
    token = asset.token
    db.close()
    return token


def test_a_full_read_advertises_range_support(client):
    """`Accept-Ranges` is how the client learns it is allowed to seek at all."""
    headers = auth(client)
    token = _stored_asset(client, headers)

    response = client.get(f"/api/storage/o/{token}")

    assert response.status_code == 200
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-length"] == "16"


def test_a_byte_range_comes_back_as_206(client):
    headers = auth(client)
    token = _stored_asset(client, headers)

    response = client.get(f"/api/storage/o/{token}", headers={"Range": "bytes=4-7"})

    assert response.status_code == 206
    assert response.content == b"4567"
    assert response.headers["content-range"] == "bytes 4-7/16"
    assert response.headers["content-length"] == "4"


def test_an_open_ended_range_runs_to_the_end(client):
    """`bytes=0-` is what a media element opens a file with."""
    headers = auth(client)
    token = _stored_asset(client, headers)

    response = client.get(f"/api/storage/o/{token}", headers={"Range": "bytes=10-"})

    assert response.status_code == 206
    assert response.content == b"abcdef"
    assert response.headers["content-range"] == "bytes 10-15/16"


def test_a_suffix_range_is_the_last_n_bytes_not_the_first(client):
    """Getting this backwards serves the wrong part of the file, and the only
    symptom is audio that starts in the wrong place."""
    headers = auth(client)
    token = _stored_asset(client, headers)

    response = client.get(f"/api/storage/o/{token}", headers={"Range": "bytes=-4"})

    assert response.status_code == 206
    assert response.content == b"cdef"


def test_a_range_past_the_end_is_416_with_the_real_size(client):
    """416 must state the size so the client can ask again correctly."""
    headers = auth(client)
    token = _stored_asset(client, headers)

    response = client.get(f"/api/storage/o/{token}", headers={"Range": "bytes=900-"})

    assert response.status_code == 416
    assert response.headers["content-range"] == "bytes */16"


def test_an_overlong_range_is_clamped_rather_than_refused(client):
    """A client may ask for more than exists; the answer is what there is."""
    headers = auth(client)
    token = _stored_asset(client, headers)

    response = client.get(f"/api/storage/o/{token}", headers={"Range": "bytes=12-999"})

    assert response.status_code == 206
    assert response.content == b"cdef"
    assert response.headers["content-range"] == "bytes 12-15/16"


@pytest.mark.parametrize("header", ["bytes=", "items=0-5", "nonsense", "bytes=a-b"])
def test_an_unparseable_range_falls_back_to_the_whole_file(client, header):
    """The RFC says to answer a malformed Range with the entire representation
    rather than an error."""
    headers = auth(client)
    token = _stored_asset(client, headers)

    response = client.get(f"/api/storage/o/{token}", headers={"Range": header})

    assert response.status_code == 200
    assert response.content == b"0123456789abcdef"
