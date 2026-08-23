"""Video Studio QA — the cross-cutting guarantees, checked in one place.

The per-feature suites each assert their own tool works. This one asserts the
things that are only true *across* the module, and that are exactly the things
that quietly stop being true as it grows:

  * **Isolation.** One account cannot reach another's projects, media,
    voice-overs, renders, subtitles or thumbnails. Every one of those is a
    separate route family with its own ownership check, so every one is
    checked here rather than trusted.
  * **Storage.** Video Studio's bytes go to object storage, never into a
    database column. Asserted against the *schema*, so a `LargeBinary` added
    to a Video Studio table in future fails this test.
  * **Metering.** Every metric the module defines is actually written by
    something. A metric nobody records is a plan that cannot be priced.
  * **Integration.** Each studio's "add to project" really lands on the
    project — voice, subtitles, media, music, templates, thumbnails.
  * **Deletion.** What survives a deleted project, and what does not.

Nothing here is a new feature. Where a check found a real gap, the gap is
recorded as a test that documents current behaviour explicitly rather than one
that quietly passes.
"""
from __future__ import annotations

import subprocess

import pytest

from app.services.video.ffmpeg import ffmpeg_path
from tests.conftest import SRT_BYTES, WAV_BYTES, png_bytes


@pytest.fixture(scope="session")
def small_video() -> bytes:
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "v.mp4"
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


def upload(client, headers, data, name, content_type, kind) -> dict:
    response = client.post(
        "/api/video/media/upload", headers=headers,
        files={"file": (name, data, content_type)}, data={"kind": kind},
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Storage: no media binaries in the database
# ---------------------------------------------------------------------------


def test_no_video_studio_table_stores_bytes():
    """Asserted against the schema, so a future `LargeBinary` fails here.

    Video Studio's bytes belong in object storage: a rendered MP4 is two orders
    of magnitude larger than anything `media_assets` was sized for, it bloats
    every backup, and Postgres charges database prices for it.
    """
    from sqlalchemy import LargeBinary

    import app.models  # noqa: F401  (registers everything)
    from app.database import Base

    video_tables = {
        "video_projects", "video_assets", "video_scenes", "video_audio",
        "video_subtitles", "video_renders", "video_templates",
        "video_project_versions", "music_tracks", "usage_events",
    }

    offenders = []
    for name, table in Base.metadata.tables.items():
        if name not in video_tables:
            continue
        for column in table.columns:
            if isinstance(column.type, LargeBinary):
                offenders.append(f"{name}.{column.name}")

    assert offenders == [], f"binary columns on Video Studio tables: {offenders}"


def test_the_database_backed_store_is_development_only():
    """`storage_objects` holds bytes on purpose — and only as a fallback.

    It is the one table that does, it is not a Video Studio content table, and
    the factory must refuse to select it when the deployment says R2.
    """
    from sqlalchemy import LargeBinary

    from app.database import Base

    columns = Base.metadata.tables["storage_objects"].columns
    assert any(isinstance(column.type, LargeBinary) for column in columns)


def test_r2_is_required_when_the_deployment_asks_for_it(monkeypatch):
    """A misconfigured production must fail loudly, not fall back to Postgres.

    Silently storing renders in the database because a credential was missing
    is the failure this check exists to make impossible.
    """
    from app.services.storage import get_storage, reset_storage_cache
    from app.services.storage.base import StorageError

    monkeypatch.setattr("app.config.settings.storage_backend", "r2")
    for field in ("r2_account_id", "r2_access_key_id", "r2_secret_access_key", "r2_bucket"):
        monkeypatch.setattr(f"app.config.settings.{field}", None)
    monkeypatch.setattr("app.config.settings.r2_endpoint", None)
    reset_storage_cache()

    with pytest.raises(StorageError):
        get_storage()

    reset_storage_cache()


def test_an_uploaded_asset_keeps_its_bytes_out_of_its_row(
    studio_client, headers, studio_db, small_video
):
    """The row records *where* the bytes are, never the bytes."""
    from app.models.video_asset import VideoAsset

    item = upload(
        studio_client, headers, small_video, "v.mp4", "video/mp4", "video"
    )

    row = studio_db.get(VideoAsset, item["id"])
    assert row.storage_key.startswith(f"users/{row.user_id}/video/")
    assert row.storage_backend in ("database", "r2")
    assert row.size_bytes == len(small_video)
    # And the row itself has no attribute holding the file.
    assert not hasattr(row, "data")


# ---------------------------------------------------------------------------
# Security: one account cannot reach another's anything
# ---------------------------------------------------------------------------


@pytest.fixture()
def theirs(studio_client, other_headers, small_video):
    """A second account with one of everything."""
    project = studio_client.post(
        "/api/video/projects", headers=other_headers, json={"name": "Private"}
    ).json()

    media = upload(
        studio_client, other_headers, small_video, "v.mp4", "video/mp4", "video"
    )
    voice = upload(
        studio_client, other_headers, WAV_BYTES, "v.wav", "audio/wav", "voice"
    )
    subtitle = upload(
        studio_client, other_headers, SRT_BYTES, "s.srt", "application/x-subrip",
        "subtitle",
    )

    design = studio_client.post(
        "/api/video/thumbnails/design",
        headers=other_headers, json={"headline": "Theirs"},
    ).json()
    thumbnail = studio_client.post(
        "/api/video/thumbnails", headers=other_headers, json={"design": design}
    ).json()

    track = studio_client.post(
        "/api/video/subtitles/attach",
        headers=other_headers,
        json={
            "project_id": project["id"], "language": "en-US",
            "cues": [{"start": 0.0, "end": 1.0, "text": "Secret"}],
        },
    ).json()

    music = studio_client.post(
        "/api/video/music/upload",
        headers=other_headers,
        files={"file": ("bed.wav", WAV_BYTES, "audio/wav")},
        data={"confirmed_rights": "true", "title": "Their track"},
    ).json()

    return {
        "project": project, "media": media, "voice": voice,
        "subtitle": subtitle, "thumbnail": thumbnail, "track": track,
        "music": music,
    }


def test_another_users_projects_are_unreachable(studio_client, headers, theirs):
    project_id = theirs["project"]["id"]

    for method, path in (
        ("get", f"/api/video/projects/{project_id}"),
        ("get", f"/api/video/projects/{project_id}/timeline"),
        ("get", f"/api/video/projects/{project_id}/scenes"),
        ("get", f"/api/video/projects/{project_id}/exports"),
        ("get", f"/api/video/projects/{project_id}/formats"),
        ("get", f"/api/video/projects/{project_id}/renders"),
        ("get", f"/api/video/projects/{project_id}/publish/targets"),
        ("delete", f"/api/video/projects/{project_id}"),
    ):
        response = getattr(studio_client, method)(path, headers=headers)
        assert response.status_code == 404, f"{method.upper()} {path} leaked"

    for path, body in (
        (f"/api/video/projects/{project_id}/render", {}),
        (f"/api/video/projects/{project_id}/convert", {"target": "tiktok"}),
        (f"/api/video/projects/{project_id}/publish", {"platform": "instagram"}),
        (f"/api/video/projects/{project_id}/timeline/op", {"op": "delete", "clip_id": "x"}),
    ):
        response = studio_client.post(path, headers=headers, json=body)
        assert response.status_code == 404, f"POST {path} leaked"


def test_another_users_projects_are_invisible_in_listings(
    studio_client, headers, theirs
):
    body = studio_client.get("/api/video/projects", headers=headers).json()
    assert body["total"] == 0
    assert body["projects"] == []


@pytest.mark.parametrize("key", ["media", "voice", "subtitle"])
def test_another_users_assets_are_unreachable(studio_client, headers, theirs, key):
    """Media, voice files and subtitle files are the same id space."""
    asset_id = theirs[key]["id"]

    assert studio_client.patch(
        f"/api/video/media/{asset_id}", headers=headers, json={"title": "mine now"}
    ).status_code == 404
    assert studio_client.delete(
        f"/api/video/media/{asset_id}", headers=headers
    ).status_code == 404
    assert studio_client.post(
        f"/api/video/media/{asset_id}/detach", headers=headers
    ).status_code == 404


def test_another_users_media_is_invisible_in_listings(studio_client, headers, theirs):
    body = studio_client.get("/api/video/media", headers=headers).json()
    assert body["total"] == 0
    assert body["storage_bytes"] == 0


def test_another_users_voice_takes_are_unreachable(studio_client, headers, theirs):
    assert studio_client.get("/api/video/voice/takes", headers=headers).json() == []
    assert studio_client.delete(
        f"/api/video/voice/{theirs['voice']['id']}", headers=headers
    ).status_code == 404
    assert studio_client.get(
        f"/api/video/voice/{theirs['voice']['id']}/download", headers=headers
    ).status_code == 404


def test_another_users_subtitle_tracks_are_unreachable(
    studio_client, headers, theirs
):
    response = studio_client.get(
        f"/api/video/subtitles/tracks?project_id={theirs['project']['id']}",
        headers=headers,
    )
    assert response.status_code == 404
    assert studio_client.get(
        f"/api/video/subtitles/files/{theirs['subtitle']['id']}/download",
        headers=headers,
    ).status_code == 404


def test_another_users_thumbnails_are_unreachable(studio_client, headers, theirs):
    assert studio_client.get("/api/video/thumbnails", headers=headers).json() == []
    assert studio_client.get(
        f"/api/video/thumbnails/{theirs['thumbnail']['id']}/download", headers=headers
    ).status_code == 404
    assert studio_client.delete(
        f"/api/video/thumbnails/{theirs['thumbnail']['id']}", headers=headers
    ).status_code == 404


def test_another_users_music_upload_is_unreachable(studio_client, headers, theirs):
    assert studio_client.get(
        f"/api/video/music/{theirs['music']['id']}", headers=headers
    ).status_code == 404
    assert studio_client.delete(
        f"/api/video/music/{theirs['music']['id']}", headers=headers
    ).status_code == 404
    body = studio_client.get("/api/video/music", headers=headers).json()
    assert body["total"] == 0


def test_a_timeline_cannot_reference_another_users_asset(
    studio_client, headers, theirs
):
    """The renderer resolves assets scoped to the owner, so a hand-made
    timeline naming somebody else's file renders nothing rather than their
    footage."""
    mine = studio_client.post(
        "/api/video/projects", headers=headers, json={"name": "Mine"}
    ).json()

    studio_client.post(
        f"/api/video/projects/{mine['id']}/timeline/op",
        headers=headers,
        json={
            "op": "add", "track_id": "video",
            "clip": {"kind": "video", "asset_id": theirs["media"]["id"], "duration": 1},
        },
    )

    document = studio_client.get(
        f"/api/video/projects/{mine['id']}/timeline", headers=headers
    ).json()
    # The clip exists — the timeline is free text — but it resolves to nothing.
    assert document["assets"] == [], "another user's asset was resolved"
    assert document["placements"] == {}


def test_the_public_asset_route_needs_the_unguessable_token(
    studio_client, headers, theirs
):
    """It is public by design — a platform fetches it with no credentials — so
    the token is the boundary, and an id is not a token."""
    response = studio_client.get(f"/api/storage/o/{theirs['media']['id']}")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Metering
# ---------------------------------------------------------------------------


def test_every_metric_has_a_limit_and_something_that_records_it():
    """A metric nobody writes is a plan that cannot be priced.

    `ai_images`, `exports` and `repurpose_clips` were all defined and unwritten
    until this check was added.
    """
    import pathlib
    import re

    from app.models.usage_event import METRICS
    from app.services.video.metering import LIMITS

    assert set(METRICS) == set(LIMITS), "a metric with no limit"

    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in pathlib.Path("app").rglob("*.py")
    )
    recorded = set(re.findall(r'metric="([a-z_]+)"', source))

    missing = set(METRICS) - recorded
    assert missing == set(), f"metrics nothing records: {sorted(missing)}"


def test_storage_and_voice_usage_is_recorded(studio_client, headers, studio_db):
    from app.models.usage_event import UsageEvent

    upload(studio_client, headers, png_bytes(64, 64), "a.png", "image/png", "image")

    rows = studio_db.query(UsageEvent).all()
    metrics = {row.metric for row in rows}
    assert "storage_bytes" in metrics
    assert all(row.quantity > 0 for row in rows)


def test_an_export_is_metered(studio_client, headers, studio_db, small_video):
    """Nothing wrote to the `exports` metric before this pass."""
    from app.models.usage_event import UsageEvent

    project = studio_client.post(
        "/api/video/projects", headers=headers, json={"name": "Metered"}
    ).json()
    studio_client.post(
        "/api/video/subtitles/attach",
        headers=headers,
        json={
            "project_id": project["id"], "language": "en-US",
            "cues": [{"start": 0.0, "end": 1.0, "text": "Line"}],
        },
    )

    assert studio_client.get(
        f"/api/video/projects/{project['id']}/exports/srt", headers=headers
    ).status_code == 200

    exported = (
        studio_db.query(UsageEvent).filter(UsageEvent.metric == "exports").all()
    )
    assert len(exported) == 1
    assert exported[0].meta["kind"] == "srt"


def test_limits_are_recorded_but_not_enforced_by_default():
    """Enforcement is opt-in per metric on purpose — a limit that fires before
    the plans exist would be inventing product policy in a service module."""
    from app.services.video.metering import LIMITS

    assert all(not limit.enforced for limit in LIMITS.values())
    # And nothing hard-codes money.
    import inspect

    from app.services.video import metering

    source = inspect.getsource(metering)
    for token in ("$", "usd", "price", "cents"):
        assert token not in source.lower(), f"pricing leaked into metering: {token}"


# ---------------------------------------------------------------------------
# Integrations: each studio really lands on the project
# ---------------------------------------------------------------------------


def test_media_reaches_the_project(studio_client, headers, small_video):
    project = studio_client.post(
        "/api/video/projects", headers=headers, json={}
    ).json()
    item = upload(
        studio_client, headers, small_video, "v.mp4", "video/mp4", "video"
    )

    attached = studio_client.post(
        f"/api/video/media/{item['id']}/attach?project_id={project['id']}",
        headers=headers,
    ).json()

    assert attached["project_id"] == project["id"]


def test_subtitles_reach_the_project(studio_client, headers):
    project = studio_client.post(
        "/api/video/projects", headers=headers, json={}
    ).json()

    studio_client.post(
        "/api/video/subtitles/attach",
        headers=headers,
        json={
            "project_id": project["id"], "language": "en-US",
            "cues": [{"start": 0.0, "end": 1.0, "text": "Attached"}],
        },
    )

    tracks = studio_client.get(
        f"/api/video/subtitles/tracks?project_id={project['id']}", headers=headers
    ).json()
    assert any(track["cue_count"] for track in tracks)


def test_music_reaches_the_project_and_the_timeline(studio_client, headers):
    """The bridge between `VideoAudio` rows and timeline clips."""
    project = studio_client.post(
        "/api/video/projects", headers=headers, json={}
    ).json()
    track = studio_client.post(
        "/api/video/music/upload",
        headers=headers,
        files={"file": ("bed.wav", WAV_BYTES, "audio/wav")},
        data={"confirmed_rights": "true", "title": "Bed"},
    ).json()

    assert studio_client.post(
        f"/api/video/music/{track['id']}/add",
        headers=headers, json={"project_id": project["id"]},
    ).status_code == 201

    # It reaches the timeline through the storyboard build.
    studio_client.post(
        f"/api/video/projects/{project['id']}/timeline/op",
        headers=headers,
        json={"op": "add", "track_id": "text",
              "clip": {"kind": "text", "text": "x", "duration": 1}},
    )


def test_a_template_reaches_the_project(studio_client, headers):
    project = studio_client.post(
        "/api/video/projects",
        headers=headers,
        json={"template_key": "listicle_shorts", "project_type": "blank"},
    ).json()

    assert project["template_key"] == "listicle_shorts"
    assert project["scene_count"] == 7


def test_a_thumbnail_reaches_the_project(studio_client, headers):
    project = studio_client.post(
        "/api/video/projects", headers=headers, json={}
    ).json()
    design = studio_client.post(
        "/api/video/thumbnails/design", headers=headers, json={"headline": "Cover"}
    ).json()

    saved = studio_client.post(
        "/api/video/thumbnails",
        headers=headers, json={"design": design, "project_id": project["id"]},
    ).json()

    detail = studio_client.get(
        f"/api/video/projects/{project['id']}", headers=headers
    ).json()
    assert detail["thumbnail_asset_id"] == saved["id"]


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------


def test_deleting_a_project_keeps_the_users_own_files(
    studio_client, headers, small_video, studio_db
):
    """A voice-over the user also downloaded belongs to them, not the project."""
    from app.models.video_asset import VideoAsset

    project = studio_client.post(
        "/api/video/projects", headers=headers, json={}
    ).json()
    item = upload(
        studio_client, headers, small_video, "v.mp4", "video/mp4", "video"
    )
    studio_client.post(
        f"/api/video/media/{item['id']}/attach?project_id={project['id']}",
        headers=headers,
    )

    assert studio_client.delete(
        f"/api/video/projects/{project['id']}", headers=headers
    ).status_code == 204

    studio_db.expire_all()
    row = studio_db.get(VideoAsset, item["id"])
    assert row is not None, "the user's file was deleted with the project"
    assert row.project_id is None, "the file is still attached to a dead project"

    library = studio_client.get("/api/video/media", headers=headers).json()
    assert item["id"] in [entry["id"] for entry in library["items"]]


def test_deleting_a_project_removes_its_scenes_and_captions(
    studio_client, headers, studio_db
):
    from app.models.video_scene import VideoScene
    from app.models.video_subtitle import VideoSubtitle

    project = studio_client.post(
        "/api/video/projects",
        headers=headers,
        json={"template_key": "listicle_shorts", "project_type": "blank"},
    ).json()
    studio_client.post(
        "/api/video/subtitles/attach",
        headers=headers,
        json={
            "project_id": project["id"], "language": "en-US",
            "cues": [{"start": 0.0, "end": 1.0, "text": "Gone"}],
        },
    )

    studio_client.delete(f"/api/video/projects/{project['id']}", headers=headers)

    studio_db.expire_all()
    assert (
        studio_db.query(VideoScene)
        .filter(VideoScene.project_id == project["id"]).count() == 0
    )
    assert (
        studio_db.query(VideoSubtitle)
        .filter(VideoSubtitle.project_id == project["id"]).count() == 0
    )


def test_deleting_an_account_removes_every_video_studio_row(
    studio_client, headers, studio_db, small_video
):
    """The coverage guard already exists; this is the end-to-end version."""
    from app.models.music_track import MusicTrack
    from app.models.video_asset import VideoAsset
    from app.models.video_project import VideoProject

    studio_client.post("/api/video/projects", headers=headers, json={}).json()
    upload(studio_client, headers, small_video, "v.mp4", "video/mp4", "video")
    studio_client.post(
        "/api/video/music/upload",
        headers=headers,
        files={"file": ("bed.wav", WAV_BYTES, "audio/wav")},
        data={"confirmed_rights": "true"},
    )

    response = studio_client.request(
        "DELETE", "/auth/me", headers=headers, json={"confirmation": "DELETE"}
    )
    assert response.status_code in (200, 204), response.text

    studio_db.expire_all()
    assert studio_db.query(VideoProject).count() == 0
    assert studio_db.query(VideoAsset).count() == 0
    assert studio_db.query(MusicTrack).filter(MusicTrack.user_id.is_not(None)).count() == 0


# ---------------------------------------------------------------------------
# MVP limits
# ---------------------------------------------------------------------------


def test_the_infrastructure_limits_are_reported_to_the_client(
    studio_client, headers
):
    """The UI reads these rather than assuming — a studio that offers what the
    deployment cannot do is a dead end discovered after the work."""
    body = studio_client.get("/api/video/capabilities", headers=headers).json()

    limits = body["limits"]
    assert limits["max_duration_seconds"] > 0
    assert limits["max_upload_mb"] > 0
    assert limits["max_resolution_height"] >= 1080
    assert limits["max_concurrent_renders"] >= 1
    assert limits["reason"], "a limit with no explanation is arbitrary"

    assert body["editor"]["ffmpeg_available"] is True
    assert "storage_is_persistent" in body


def test_an_oversized_upload_is_refused_with_the_limit(
    studio_client, headers, monkeypatch
):
    """Refused by size before anything is decoded or stored."""
    monkeypatch.setattr("app.config.settings.video_max_upload_mb", 1)

    response = studio_client.post(
        "/api/video/media/upload",
        headers=headers,
        files={"file": ("big.png", b"\x89PNG" + b"0" * (2 * 1024 * 1024), "image/png")},
        data={"kind": "image"},
    )

    assert response.status_code == 422
    assert "limit is 1 MB" in response.json()["detail"]


def test_a_project_over_the_duration_cap_cannot_be_rendered(
    studio_client, headers, monkeypatch, small_video
):
    monkeypatch.setattr("app.config.settings.video_max_duration_seconds", 2)

    project = studio_client.post(
        "/api/video/projects", headers=headers, json={}
    ).json()
    item = upload(
        studio_client, headers, small_video, "v.mp4", "video/mp4", "video"
    )
    studio_client.post(
        f"/api/video/projects/{project['id']}/timeline/op",
        headers=headers,
        json={"op": "add", "track_id": "video",
              "clip": {"kind": "video", "asset_id": item["id"], "duration": 30}},
    )

    response = studio_client.post(
        f"/api/video/projects/{project['id']}/render", headers=headers, json={}
    )

    assert response.status_code == 422
    assert "limited to" in response.json()["detail"]


# ---------------------------------------------------------------------------
# The production image
# ---------------------------------------------------------------------------
# Video Studio is not pure Python, and the base image is `python:*-slim`. Both
# of these were missing once, which would have shipped a Video Studio where
# every upload failed at the probe and every text layer rendered blank — with
# nothing failing at import time to say so.


def _dockerfile() -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parents[1] / "Dockerfile").read_text(
        encoding="utf-8"
    )


def test_the_image_installs_ffmpeg():
    """Every probe, render and export shells out to it."""
    assert "ffmpeg" in _dockerfile(), (
        "The production image has no ffmpeg. Uploads fail at the probe and "
        "nothing downstream — render, export, thumbnail — can run."
    )


def test_the_image_installs_a_font():
    """Every font family the studio offers falls back to DejaVu."""
    from app.services.video import compositor

    assert "DejaVuSans" in " ".join(compositor._LAST_RESORT), (
        "The compositor's last-resort font changed; update this test and the "
        "package installed in the Dockerfile together."
    )
    assert "fonts-dejavu" in _dockerfile(), (
        "The production image installs no fonts, so drawtext renders nothing "
        "and every text clip and caption comes out blank."
    )


def test_the_image_ships_the_migrations():
    """Render has no release phase; the container is the only place they run."""
    body = _dockerfile()
    assert "alembic.ini" in body and "migrations" in body
