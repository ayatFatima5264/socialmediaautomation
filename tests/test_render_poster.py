"""A finished render has to leave the project with a usable thumbnail.

The bug this file exists for: `renders.complete` pointed
`video_projects.thumbnail_asset_id` at the rendered MP4. A video has no *stored*
poster frame, so every project rendered that way came out of the render screen
with a "thumbnail" that was a video, and the PNG and JPG exports — which the
manifest cheerfully advertised as available — failed when they tried to decode
MP4 bytes as an image.

The existing export suite did not catch it because its `rendered` fixture saves
a Thumbnail Studio design *before* rendering, so the buggy branch never ran.
Every test here renders a project that has no thumbnail of its own, which is
what a user who has just built their first video actually has.

The downloads are opened with Pillow and the bytes are checked, not merely
counted: a 200 that returns the MP4 under an `image/png` header is the exact
failure being guarded against.
"""
from __future__ import annotations

import io
import subprocess

import pytest
from PIL import Image

from app.services.video.ffmpeg import ffmpeg_path


@pytest.fixture()
def poster_client(studio_client, studio_session_factory, monkeypatch):
    monkeypatch.setattr(
        "app.routes.video_editor.SessionLocal", studio_session_factory
    )
    return studio_client


@pytest.fixture(scope="session")
def source_clip(tmp_path_factory) -> bytes:
    """A real one-second clip, so the render has something to encode."""
    path = tmp_path_factory.mktemp("poster") / "clip.mp4"
    subprocess.run(
        [
            ffmpeg_path(), "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=size=256x256:rate=15:duration=1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(path),
        ],
        check=True, capture_output=True, timeout=120,
    )
    return path.read_bytes()


@pytest.fixture()
def freshly_rendered(poster_client, headers, source_clip) -> dict:
    """A project with one clip, rendered, and NO thumbnail set beforehand.

    The absence of a Thumbnail Studio design is the whole point of the fixture.
    """
    project = poster_client.post(
        "/api/video/projects",
        headers=headers,
        json={
            "name": "Poster Test", "platform": "custom",
            "width": 256, "height": 256, "fps": 15,
        },
    ).json()

    asset = poster_client.post(
        "/api/video/media/upload",
        headers=headers,
        files={"file": ("clip.mp4", source_clip, "video/mp4")},
        data={"kind": "video"},
    ).json()

    poster_client.post(
        f"/api/video/projects/{project['id']}/timeline/op",
        headers=headers,
        json={
            "op": "add", "track_id": "video",
            "clip": {"kind": "video", "asset_id": asset["id"], "duration": 1.0},
        },
    )

    queued = poster_client.post(
        f"/api/video/projects/{project['id']}/render",
        headers=headers, json={"quality": "draft"},
    )
    assert queued.status_code == 202, queued.text
    finished = poster_client.get(
        f"/api/video/renders/{queued.json()['id']}", headers=headers
    ).json()
    assert finished["status"] == "completed", finished.get("error")

    detail = poster_client.get(
        f"/api/video/projects/{project['id']}", headers=headers
    ).json()
    return {"project": project, "render": finished, "detail": detail, "asset": asset}


def _download(client, headers, project_id, kind):
    return client.get(
        f"/api/video/projects/{project_id}/exports/{kind}", headers=headers
    )


# ---------------------------------------------------------------------------
# The project comes out of the render with a real image attached
# ---------------------------------------------------------------------------


def test_the_render_leaves_a_thumbnail_that_is_not_the_video(
    poster_client, headers, freshly_rendered
):
    detail = freshly_rendered["detail"]
    output_asset_id = freshly_rendered["render"]["output_asset_id"]
    thumbnail_asset_id = detail.get("thumbnail_asset_id")

    assert thumbnail_asset_id is not None, (
        "a completed render must give the project a thumbnail; without one the "
        "PNG/JPG exports are permanently unavailable"
    )
    assert thumbnail_asset_id != output_asset_id, (
        "the rendered video was assigned as the thumbnail again"
    )


def test_the_stored_thumbnail_is_a_real_decodable_image(
    poster_client, headers, freshly_rendered
):
    detail = freshly_rendered["detail"]
    response = _download(
        poster_client, headers, freshly_rendered["project"]["id"], "png"
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/png"

    # Decoded, not just length-checked: MP4 bytes served under an image header
    # is precisely the failure this file guards against.
    image = Image.open(io.BytesIO(response.content))
    image.load()
    assert image.format == "PNG"
    assert image.width > 0 and image.height > 0


# ---------------------------------------------------------------------------
# The P0 flow: render, then download immediately, with no waiting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("kind", "media_type", "image_format"), [
    ("png", "image/png", "PNG"),
    ("jpg", "image/jpeg", "JPEG"),
])
def test_image_exports_download_immediately_after_a_fresh_render(
    poster_client, headers, freshly_rendered, kind, media_type, image_format
):
    """No sleep, no second render, no manual thumbnail step.

    The original report was a *delayed* failure: the file only turned out to be
    unusable once object storage had settled, which is why a test that only
    checks the manifest passed.
    """
    response = _download(
        poster_client, headers, freshly_rendered["project"]["id"], kind
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == media_type
    assert "attachment" in response.headers["content-disposition"]

    image = Image.open(io.BytesIO(response.content))
    image.load()
    assert image.format == image_format
    assert len(response.content) > 0


def test_the_manifest_advertises_the_image_exports_after_a_fresh_render(
    poster_client, headers, freshly_rendered
):
    response = poster_client.get(
        f"/api/video/projects/{freshly_rendered['project']['id']}/exports",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    by_kind = {item["kind"]: item for item in response.json()["items"]}

    for kind in ("png", "jpg"):
        assert by_kind[kind]["available"] is True, by_kind[kind]
        assert by_kind[kind]["reason"] is None, by_kind[kind]

    # The MP4 must still be offered too — the poster did not replace it.
    assert by_kind["mp4"]["available"] is True


# ---------------------------------------------------------------------------
# A user-chosen thumbnail is never overwritten
# ---------------------------------------------------------------------------


def test_a_thumbnail_the_user_chose_is_left_alone(poster_client, headers, source_clip):
    project = poster_client.post(
        "/api/video/projects",
        headers=headers,
        json={"name": "Chosen Cover", "platform": "custom",
              "width": 256, "height": 256, "fps": 15},
    ).json()

    design = poster_client.post(
        "/api/video/thumbnails/design",
        headers=headers,
        json={"headline": "Mine", "format": "youtube"},
    ).json()
    chosen = poster_client.post(
        "/api/video/thumbnails",
        headers=headers,
        json={"design": design, "project_id": project["id"]},
    ).json()

    asset = poster_client.post(
        "/api/video/media/upload",
        headers=headers,
        files={"file": ("clip.mp4", source_clip, "video/mp4")},
        data={"kind": "video"},
    ).json()
    poster_client.post(
        f"/api/video/projects/{project['id']}/timeline/op",
        headers=headers,
        json={"op": "add", "track_id": "video",
              "clip": {"kind": "video", "asset_id": asset["id"], "duration": 1.0}},
    )

    queued = poster_client.post(
        f"/api/video/projects/{project['id']}/render",
        headers=headers, json={"quality": "draft"},
    )
    assert queued.status_code == 202, queued.text
    assert poster_client.get(
        f"/api/video/renders/{queued.json()['id']}", headers=headers
    ).json()["status"] == "completed"

    detail = poster_client.get(
        f"/api/video/projects/{project['id']}", headers=headers
    ).json()
    assert detail["thumbnail_asset_id"] == chosen["id"], (
        "a render replaced a thumbnail the user made in Thumbnail Studio"
    )


# ---------------------------------------------------------------------------
# Rows written before the fix explain themselves instead of failing obscurely
# ---------------------------------------------------------------------------


def test_a_legacy_thumbnail_pointing_at_a_video_says_what_to_do(
    poster_client, headers, freshly_rendered, studio_session_factory
):
    """A project saved by the buggy code must not answer with a Pillow error.

    The 0004 migration clears these rows, but a deployment that has not run it
    yet — and anything created between the deploy and the migration — still has
    them, so the download has to be honest about the cause and the fix.
    """
    project_id = freshly_rendered["project"]["id"]
    output_asset_id = freshly_rendered["render"]["output_asset_id"]

    session = studio_session_factory()
    try:
        from app.models.video_project import VideoProject

        row = session.get(VideoProject, project_id)
        row.thumbnail_asset_id = output_asset_id
        session.commit()
    finally:
        session.close()

    response = _download(poster_client, headers, project_id, "png")
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert "not an image" in detail
    assert "Thumbnail Studio" in detail, (
        "the message has to name the next action, not just the fault"
    )

    # And the manifest must not advertise a file it cannot produce.
    manifest = poster_client.get(
        f"/api/video/projects/{project_id}/exports", headers=headers
    ).json()
    png = next(item for item in manifest["items"] if item["kind"] == "png")
    assert png["available"] is False
    assert png["reason"]
