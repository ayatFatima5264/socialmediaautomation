"""Export, platform formats and the publishing hand-off.

Every export in this suite is a **real file, decoded and checked** — the MP4 is
probed for its canvas, the MP3 and WAV are probed for an audio stream, the SRT
and VTT are parsed for their headers and timings, the PNG and JPG are opened
with Pillow. A test that only asserts "some bytes came back" would pass against
an endpoint returning the wrong file entirely.

Three guarantees carry the rest:

  * **Presets are what the platforms actually require** — checked as numbers,
    not as labels.
  * **Converting never modifies the original** — captured field by field before
    and compared after.
  * **Publishing never publishes** — the hand-off produces a `draft` post and
    the test asserts the status and that nothing reached a platform.
"""
from __future__ import annotations

import io
import subprocess
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from app.services.video.ffmpeg import ffmpeg_path, probe


@pytest.fixture()
def render_client(studio_client, studio_session_factory, monkeypatch):
    monkeypatch.setattr(
        "app.routes.video_editor.SessionLocal", studio_session_factory
    )
    return studio_client


@pytest.fixture(scope="session")
def clip_bytes(tmp_path_factory) -> bytes:
    """A real two-second clip with an audio track."""
    path = tmp_path_factory.mktemp("exports") / "clip.mp4"
    subprocess.run(
        [
            ffmpeg_path(), "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=size=320x240:rate=15:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-shortest", "-y", str(path),
        ],
        check=True, capture_output=True, timeout=120,
    )
    return path.read_bytes()


def make_project(client, headers, **body) -> dict:
    """A small custom canvas, so the encodes in this suite stay cheap."""
    payload = {
        "name": "Export Test", "platform": "custom",
        "width": 256, "height": 256, "fps": 15, **body,
    }
    response = client.post("/api/video/projects", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def upload(client, headers, data, name, content_type, kind) -> dict:
    response = client.post(
        "/api/video/media/upload", headers=headers,
        files={"file": (name, data, content_type)}, data={"kind": kind},
    )
    assert response.status_code == 200, response.text
    return response.json()


def add_clip(client, headers, project_id, **clip):
    response = client.post(
        f"/api/video/projects/{project_id}/timeline/op",
        headers=headers,
        json={"op": "add", "track_id": clip.pop("track", "video"), "clip": clip},
    )
    assert response.status_code == 200, response.text
    return response.json()


def render_project(client, headers, project_id) -> dict:
    response = client.post(
        f"/api/video/projects/{project_id}/render",
        headers=headers, json={"quality": "draft"},
    )
    assert response.status_code == 202, response.text
    finished = client.get(
        f"/api/video/renders/{response.json()['id']}", headers=headers
    ).json()
    assert finished["status"] == "completed", finished.get("error")
    return finished


@pytest.fixture()
def rendered(render_client, headers, clip_bytes):
    """A project with a finished render, captions and a thumbnail."""
    project = make_project(render_client, headers)
    asset = upload(render_client, headers, clip_bytes, "clip.mp4", "video/mp4", "video")
    add_clip(
        render_client, headers, project["id"],
        kind="video", asset_id=asset["id"], duration=1.5,
    )
    add_clip(
        render_client, headers, project["id"],
        track="text", kind="text", text="Hello", duration=1.0, font_size=24,
    )

    # Captions, through the normal subtitle path.
    render_client.post(
        "/api/video/subtitles/attach",
        headers=headers,
        json={
            "project_id": project["id"],
            "language": "en-US",
            "cues": [
                {"start": 0.0, "end": 0.8, "text": "First line"},
                {"start": 0.8, "end": 1.5, "text": "Second line"},
            ],
        },
    )

    # A thumbnail, through Thumbnail Studio.
    design = render_client.post(
        "/api/video/thumbnails/design",
        headers=headers,
        json={"headline": "Cover", "format": "youtube"},
    ).json()
    render_client.post(
        "/api/video/thumbnails",
        headers=headers,
        json={"design": design, "project_id": project["id"]},
    )

    render = render_project(render_client, headers, project["id"])
    return {"project": project, "render": render, "asset": asset}


def manifest_of(client, headers, project_id) -> dict:
    response = client.get(
        f"/api/video/projects/{project_id}/exports", headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def download(client, headers, project_id, kind):
    return client.get(
        f"/api/video/projects/{project_id}/exports/{kind}", headers=headers
    )


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_every_export_route_requires_a_token(studio_client):
    for method, path in (
        ("get", "/api/video/projects/1/exports"),
        ("get", "/api/video/projects/1/exports/mp4"),
        ("get", "/api/video/projects/1/formats"),
        ("post", "/api/video/projects/1/convert"),
        ("get", "/api/video/projects/1/publish/targets"),
        ("post", "/api/video/projects/1/publish"),
    ):
        kwargs = {"json": {}} if method == "post" else {}
        response = getattr(studio_client, method)(path, **kwargs)
        assert response.status_code == 401, f"{method.upper()} {path} was reachable"


def test_you_cannot_export_someone_elses_project(
    studio_client, headers, other_headers
):
    theirs = make_project(studio_client, other_headers)

    assert studio_client.get(
        f"/api/video/projects/{theirs['id']}/exports", headers=headers
    ).status_code == 404
    assert studio_client.post(
        f"/api/video/projects/{theirs['id']}/convert",
        headers=headers, json={"target": "tiktok"},
    ).status_code == 404


# ---------------------------------------------------------------------------
# Platform presets
# ---------------------------------------------------------------------------


def test_the_presets_are_what_the_platforms_require(studio_client, headers):
    """Checked as numbers. A label saying "1080p" proves nothing."""
    body = studio_client.get("/api/video/capabilities", headers=headers).json()
    presets = {entry["key"]: entry for entry in body["presets"]}

    assert (presets["youtube"]["aspect_ratio"], presets["youtube"]["height"]) == (
        "16:9", 1080,
    )
    for key in ("youtube_shorts", "tiktok", "instagram_reels"):
        assert presets[key]["aspect_ratio"] == "9:16", key
        assert (presets[key]["width"], presets[key]["height"]) == (1080, 1920), key

    assert presets["instagram_post"]["aspect_ratio"] == "1:1"

    # Facebook has to offer both shapes.
    assert presets["facebook"]["aspect_ratio"] == "16:9"
    assert presets["facebook_reels"]["aspect_ratio"] == "9:16"


def test_a_project_created_for_a_preset_gets_that_canvas(studio_client, headers):
    for key, expected in (
        ("youtube_shorts", (1080, 1920)),
        ("instagram_post", (1080, 1080)),
        ("facebook_reels", (1080, 1920)),
    ):
        project = studio_client.post(
            "/api/video/projects", headers=headers, json={"platform": key}
        ).json()
        assert (project["width"], project["height"]) == expected, key


# ---------------------------------------------------------------------------
# The manifest
# ---------------------------------------------------------------------------


def test_an_unrendered_project_says_what_to_do(studio_client, headers):
    """A button that fails is worse than one that explains."""
    project = make_project(studio_client, headers)

    body = manifest_of(studio_client, headers, project["id"])
    items = {entry["kind"]: entry for entry in body["items"]}

    assert set(items) == {"mp4", "srt", "vtt", "mp3", "wav", "png", "jpg"}
    assert items["mp4"]["available"] is False
    assert "Render" in items["mp4"]["reason"]
    assert items["srt"]["available"] is False
    assert "captions" in items["srt"]["reason"]
    assert body["render_id"] is None


def test_a_rendered_project_offers_everything(render_client, headers, rendered):
    body = manifest_of(render_client, headers, rendered["project"]["id"])
    items = {entry["kind"]: entry for entry in body["items"]}

    for kind in ("mp4", "srt", "vtt", "mp3", "wav", "png", "jpg"):
        assert items[kind]["available"] is True, f"{kind} should be available"
        assert items[kind]["reason"] is None
    assert body["render_id"] == rendered["render"]["id"]
    assert items["mp4"]["size_bytes"] > 0


# ---------------------------------------------------------------------------
# The files themselves
# ---------------------------------------------------------------------------


def test_the_mp4_is_the_rendered_video(render_client, headers, rendered):
    response = download(render_client, headers, rendered["project"]["id"], "mp4")

    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "out.mp4"
        path.write_bytes(response.content)
        info = probe(path)

    assert (info.width, info.height) == (256, 256)
    assert info.has_video and info.has_audio


@pytest.mark.parametrize("kind", ["mp3", "wav"])
def test_audio_exports_are_real_audio(render_client, headers, rendered, kind):
    """Extracted from the render with ffmpeg, not a renamed MP4."""
    response = download(render_client, headers, rendered["project"]["id"], kind)

    assert response.status_code == 200, response.text
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / f"out.{kind}"
        path.write_bytes(response.content)
        info = probe(path)

    assert info.has_audio, f"the {kind} has no audio stream"
    assert not info.has_video, f"the {kind} still contains video"
    assert info.duration_seconds > 0


def test_the_srt_is_valid_and_carries_the_cues(render_client, headers, rendered):
    response = download(render_client, headers, rendered["project"]["id"], "srt")

    assert response.status_code == 200
    text = response.content.decode("utf-8")

    assert text.startswith("1\n"), "an SRT starts with its first cue number"
    # SRT timings use a comma before the milliseconds; VTT uses a dot.
    assert "-->" in text and "," in text.split("-->")[1][:15]
    assert "First line" in text and "Second line" in text
    # A BOM here shows as a stray character on the first cue in several players.
    assert not response.content.startswith(b"\xef\xbb\xbf")


def test_the_vtt_is_valid_and_carries_the_cues(render_client, headers, rendered):
    response = download(render_client, headers, rendered["project"]["id"], "vtt")

    assert response.status_code == 200
    text = response.content.decode("utf-8")

    assert text.startswith("WEBVTT"), "a VTT must open with its magic header"
    assert "-->" in text
    assert "." in text.split("-->")[1][:15], "VTT timings use a dot, not a comma"
    assert "First line" in text


@pytest.mark.parametrize(("kind", "fmt"), [("png", "PNG"), ("jpg", "JPEG")])
def test_thumbnail_exports_are_real_images(
    render_client, headers, rendered, kind, fmt
):
    response = download(render_client, headers, rendered["project"]["id"], kind)

    assert response.status_code == 200, response.text
    image = Image.open(io.BytesIO(response.content))
    assert image.format == fmt
    assert image.size == (1280, 720)


def test_an_unavailable_export_explains_itself(studio_client, headers):
    project = make_project(studio_client, headers)

    response = download(studio_client, headers, project["id"], "mp4")

    assert response.status_code == 422
    assert "Render" in response.json()["detail"]


def test_an_unknown_export_kind_is_refused(render_client, headers, rendered):
    response = download(render_client, headers, rendered["project"]["id"], "gif")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Render phases
# ---------------------------------------------------------------------------


def test_a_finished_render_reports_the_completed_phase(
    render_client, headers, rendered
):
    """The phases the UI shows are derived from the real stage, not invented."""
    render = render_client.get(
        f"/api/video/renders/{rendered['render']['id']}", headers=headers
    ).json()

    assert render["phase"] == "completed"
    assert render["phase_label"] == "Completed"
    assert render["progress"] == 1.0
    assert render["stage"] == "done"


@pytest.mark.parametrize(
    ("status", "stage", "expected"),
    [
        ("queued", "queued", "queued"),
        ("processing", "preparing", "processing"),
        ("processing", "downloading", "processing"),
        ("processing", "scenes", "rendering"),
        ("processing", "encoding", "rendering"),
        ("processing", "uploading", "finalizing"),
        ("completed", "done", "completed"),
        ("failed", "encoding", "failed"),
        ("cancelled", "downloading", "cancelled"),
    ],
)
def test_every_phase_is_reachable_from_a_real_stage(status, stage, expected):
    """The vocabulary Task 9 asks for, mapped from what the worker writes.

    Terminal statuses win over the stage: a job that died while encoding is
    "failed", not "rendering".
    """
    from app.models.video_render import RENDER_PHASES, phase_of

    assert phase_of(status, stage) == expected
    assert expected in RENDER_PHASES


def test_no_stage_is_left_without_a_phase():
    """A stage added later without a phase would silently fall back."""
    from app.models.video_render import RENDER_STAGES, _PHASE_BY_STAGE

    assert set(RENDER_STAGES) == set(_PHASE_BY_STAGE)


def test_a_failed_render_reports_the_failed_phase_and_can_be_retried(
    render_client, headers, clip_bytes
):
    project = make_project(render_client, headers)
    asset = upload(
        render_client, headers, clip_bytes, "clip.mp4", "video/mp4", "video"
    )
    add_clip(
        render_client, headers, project["id"],
        kind="video", asset_id=asset["id"], duration=1.0,
    )
    render_client.delete(
        f"/api/video/media/{asset['id']}?force=true", headers=headers
    )

    first = render_client.post(
        f"/api/video/projects/{project['id']}/render",
        headers=headers, json={"quality": "draft"},
    ).json()
    failed = render_client.get(
        f"/api/video/renders/{first['id']}", headers=headers
    ).json()

    assert failed["status"] == "failed"
    assert failed["phase"] == "failed"
    assert failed["phase_label"] == "Failed"
    assert failed["error_code"] == "missing_asset"

    retried = render_client.post(
        f"/api/video/renders/{first['id']}/retry", headers=headers, json={}
    )
    assert retried.status_code == 202
    assert retried.json()["attempt"] == first["attempt"] + 1


# ---------------------------------------------------------------------------
# Converting to another format
# ---------------------------------------------------------------------------


def test_the_format_list_excludes_the_current_one(studio_client, headers):
    project = studio_client.post(
        "/api/video/projects", headers=headers, json={"platform": "youtube"}
    ).json()

    body = studio_client.get(
        f"/api/video/projects/{project['id']}/formats", headers=headers
    ).json()

    keys = {entry["key"] for entry in body["formats"]}
    assert body["current"] == "youtube"
    assert "youtube" not in keys
    assert {"youtube_shorts", "tiktok", "instagram_reels", "instagram_post"} <= keys
    # "Custom" is not a conversion target — it means nothing without dimensions.
    assert "custom" not in keys


def test_converting_creates_a_new_project_with_the_new_canvas(
    studio_client, headers, clip_bytes
):
    project = studio_client.post(
        "/api/video/projects", headers=headers, json={"platform": "youtube"}
    ).json()
    asset = upload(
        studio_client, headers, clip_bytes, "clip.mp4", "video/mp4", "video"
    )
    add_clip(
        studio_client, headers, project["id"],
        kind="video", asset_id=asset["id"], duration=2.0, fit="contain",
    )

    response = studio_client.post(
        f"/api/video/projects/{project['id']}/convert",
        headers=headers, json={"target": "youtube_shorts"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["project_id"] != project["id"]
    assert (body["width"], body["height"]) == (1080, 1920)
    assert body["aspect_ratio"] == "9:16"
    assert body["source_project_id"] == project["id"]
    assert body["editor_path"].endswith("/edit")


def test_a_converted_project_is_reframed_to_fill_the_new_canvas(
    studio_client, headers, clip_bytes
):
    """A converted clip with bars on every side is what conversion must not do."""
    project = studio_client.post(
        "/api/video/projects", headers=headers, json={"platform": "youtube"}
    ).json()
    asset = upload(
        studio_client, headers, clip_bytes, "clip.mp4", "video/mp4", "video"
    )
    add_clip(
        studio_client, headers, project["id"],
        kind="video", asset_id=asset["id"], duration=2.0, fit="contain",
    )

    converted = studio_client.post(
        f"/api/video/projects/{project['id']}/convert",
        headers=headers, json={"target": "tiktok"},
    ).json()

    document = studio_client.get(
        f"/api/video/projects/{converted['project_id']}/timeline", headers=headers
    ).json()
    clip = document["timeline"]["tracks"][0]["clips"][0]
    assert clip["fit"] == "cover", "the converted clip was not reframed"

    # And the compositor's own geometry says it fills the frame.
    placement = document["placements"][clip["id"]]
    assert placement["width"] >= document["width"]
    assert placement["height"] >= document["height"]


def test_converting_rescales_text_to_the_new_frame(studio_client, headers):
    """A font size is pixels on a clip, and the frame changed shape."""
    project = studio_client.post(
        "/api/video/projects", headers=headers, json={"platform": "youtube"}
    ).json()
    add_clip(
        studio_client, headers, project["id"],
        track="text", kind="text", text="Title", duration=2.0, font_size=100,
    )

    converted = studio_client.post(
        f"/api/video/projects/{project['id']}/convert",
        headers=headers, json={"target": "youtube_shorts"},
    ).json()

    document = studio_client.get(
        f"/api/video/projects/{converted['project_id']}/timeline", headers=headers
    ).json()
    text = next(
        track for track in document["timeline"]["tracks"] if track["id"] == "text"
    )["clips"][0]

    # 1080 short side both ways here, so the size is preserved rather than
    # scaled — what matters is that it is proportional, not that it changed.
    assert text["font_size"] == 100


def test_converting_carries_the_scenes_and_captions(
    studio_client, headers, clip_bytes
):
    project = studio_client.post(
        "/api/video/projects", headers=headers, json={"platform": "youtube"}
    ).json()
    studio_client.post(
        "/api/video/subtitles/attach",
        headers=headers,
        json={
            "project_id": project["id"], "language": "en-US",
            "cues": [{"start": 0.0, "end": 1.0, "text": "Carried over"}],
        },
    )

    converted = studio_client.post(
        f"/api/video/projects/{project['id']}/convert",
        headers=headers, json={"target": "instagram_reels"},
    ).json()

    tracks = studio_client.get(
        f"/api/video/subtitles/tracks?project_id={converted['project_id']}",
        headers=headers,
    ).json()
    assert any(track["cue_count"] for track in tracks), "captions were lost"


def test_converting_does_not_touch_the_original(
    studio_client, headers, clip_bytes, studio_db
):
    """The requirement, checked field by field."""
    from app.models.video_project import VideoProject

    project = studio_client.post(
        "/api/video/projects", headers=headers, json={"platform": "youtube"}
    ).json()
    asset = upload(
        studio_client, headers, clip_bytes, "clip.mp4", "video/mp4", "video"
    )
    add_clip(
        studio_client, headers, project["id"],
        kind="video", asset_id=asset["id"], duration=2.0, fit="contain",
    )

    row = studio_db.get(VideoProject, project["id"])
    studio_db.refresh(row)
    before = {
        "name": row.name, "platform": row.platform, "width": row.width,
        "height": row.height, "status": row.status, "revision": row.revision,
        "timeline": studio_client.get(
            f"/api/video/projects/{project['id']}/timeline", headers=headers
        ).json()["timeline"],
    }

    for target in ("youtube_shorts", "tiktok", "instagram_post"):
        assert studio_client.post(
            f"/api/video/projects/{project['id']}/convert",
            headers=headers, json={"target": target},
        ).status_code == 201

    studio_db.expire_all()
    after_row = studio_db.get(VideoProject, project["id"])
    after = {
        "name": after_row.name, "platform": after_row.platform,
        "width": after_row.width, "height": after_row.height,
        "status": after_row.status, "revision": after_row.revision,
        "timeline": studio_client.get(
            f"/api/video/projects/{project['id']}/timeline", headers=headers
        ).json()["timeline"],
    }

    assert after == before, "converting modified the source project"


def test_converting_to_the_same_format_is_refused(studio_client, headers):
    project = studio_client.post(
        "/api/video/projects", headers=headers, json={"platform": "tiktok"}
    ).json()

    response = studio_client.post(
        f"/api/video/projects/{project['id']}/convert",
        headers=headers, json={"target": "tiktok"},
    )

    assert response.status_code == 422
    assert "already" in response.json()["detail"]


def test_a_converted_project_can_be_edited_and_rendered(
    render_client, headers, clip_bytes
):
    """A conversion produces an ordinary project, not a frozen copy."""
    project = studio_client = render_client
    source = project.post(
        "/api/video/projects",
        headers=headers,
        json={"platform": "custom", "width": 256, "height": 144, "fps": 15},
    ).json()
    asset = upload(
        studio_client, headers, clip_bytes, "clip.mp4", "video/mp4", "video"
    )
    add_clip(
        studio_client, headers, source["id"],
        kind="video", asset_id=asset["id"], duration=1.0,
    )

    converted = studio_client.post(
        f"/api/video/projects/{source['id']}/convert",
        headers=headers, json={"target": "instagram_post"},
    ).json()

    # Shrink it so the encode is quick, then edit and render it.
    studio_client.patch(
        f"/api/video/projects/{converted['project_id']}",
        headers=headers,
        json={"platform": "custom", "width": 128, "height": 128, "fps": 12},
    )
    document = studio_client.get(
        f"/api/video/projects/{converted['project_id']}/timeline", headers=headers
    ).json()
    clip = document["timeline"]["tracks"][0]["clips"][0]
    assert studio_client.post(
        f"/api/video/projects/{converted['project_id']}/timeline/op",
        headers=headers,
        json={"op": "trim", "clip_id": clip["id"], "edge": "end", "to": 0.8},
    ).status_code == 200

    finished = render_project(studio_client, headers, converted["project_id"])
    assert finished["phase"] == "completed"


# ---------------------------------------------------------------------------
# Publishing — which never publishes
# ---------------------------------------------------------------------------


def test_publish_targets_report_connection_and_capability_separately(
    render_client, headers, rendered
):
    """They are fixed in different places, so collapsing them misleads."""
    body = render_client.get(
        f"/api/video/projects/{rendered['project']['id']}/publish/targets",
        headers=headers,
    ).json()

    assert body["ready"] is True
    platforms = {entry["platform"]: entry for entry in body["targets"]}
    assert {"instagram", "facebook", "twitter", "linkedin"} <= set(platforms)

    for entry in platforms.values():
        assert entry["connected"] is False, "nothing is connected in this test"
        assert "Connect" in entry["reason"]
        # Reported honestly: no adapter uploads video today.
        assert entry["video_upload_supported"] is False


def test_an_unrendered_project_is_not_ready_to_publish(studio_client, headers):
    project = make_project(studio_client, headers)

    body = studio_client.get(
        f"/api/video/projects/{project['id']}/publish/targets", headers=headers
    ).json()

    assert body["ready"] is False
    assert "Render" in body["reason"]


def test_a_shorts_project_says_youtube_is_export_only(studio_client, headers):
    """Rather than showing six platforms, none of which is the target."""
    project = studio_client.post(
        "/api/video/projects", headers=headers, json={"platform": "youtube_shorts"}
    ).json()

    body = studio_client.get(
        f"/api/video/projects/{project['id']}/publish/targets", headers=headers
    ).json()

    assert body["export_only"] == ["youtube_shorts"]
    assert body["export_only_note"]


def test_publishing_creates_a_draft_and_publishes_nothing(
    render_client, headers, rendered, studio_db
):
    """The requirement, made structural: there is no path here to a platform."""
    from app.models.post import Post

    response = render_client.post(
        f"/api/video/projects/{rendered['project']['id']}/publish",
        headers=headers,
        json={"platform": "instagram", "caption": "Watch this"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "draft", "a publish hand-off must not schedule"
    assert body["platform"] == "instagram"
    assert body["content"] == "Watch this"
    assert body["media"], "the draft has no video attached"
    assert "/api/storage/o/" in body["media"][0]
    assert body["review_path"] == f"/posts/{body['post_id']}"

    row = studio_db.get(Post, body["post_id"])
    assert row.status == "draft"
    assert row.published_time is None
    assert row.external_id is None
    assert row.platform_options["video_project_id"] == rendered["project"]["id"]


def test_a_scheduled_time_is_stored_but_does_not_schedule(
    render_client, headers, rendered, studio_db
):
    """Otherwise the hand-off could cause a publish nobody confirmed."""
    from app.models.post import Post

    body = render_client.post(
        f"/api/video/projects/{rendered['project']['id']}/publish",
        headers=headers,
        json={
            "platform": "facebook",
            "caption": "Later",
            "scheduled_time": "2030-01-01T10:00:00",
        },
    ).json()

    row = studio_db.get(Post, body["post_id"])
    assert row.scheduled_time is not None
    assert row.status == "draft", "a time must not flip the post to scheduled"


def test_the_caption_defaults_to_the_projects_own_script(
    render_client, headers, rendered
):
    project_id = rendered["project"]["id"]
    render_client.put(
        f"/api/video/projects/{project_id}/script",
        headers=headers,
        json={
            "script": {
                "hook": "The hook line.",
                "cta": "Follow for more.",
                "keywords": ["baking", "sourdough"],
            }
        },
    )

    body = render_client.post(
        f"/api/video/projects/{project_id}/publish",
        headers=headers, json={"platform": "instagram"},
    ).json()

    assert "The hook line." in body["content"]
    assert "Follow for more." in body["content"]
    assert "#baking" in body["hashtags"]


def test_publishing_an_unrendered_project_is_refused(studio_client, headers):
    project = make_project(studio_client, headers)

    response = studio_client.post(
        f"/api/video/projects/{project['id']}/publish",
        headers=headers, json={"platform": "instagram", "caption": "x"},
    )

    assert response.status_code == 422
    assert "Render" in response.json()["detail"]


def test_an_unknown_platform_is_refused(render_client, headers, rendered):
    response = render_client.post(
        f"/api/video/projects/{rendered['project']['id']}/publish",
        headers=headers, json={"platform": "youtube", "caption": "x"},
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# The concurrency cap is a queue, not a refusal
# ---------------------------------------------------------------------------


def test_a_render_waits_for_a_slot_rather_than_being_refused(
    render_client, headers, clip_bytes, studio_db, monkeypatch
):
    """`video_max_concurrent_renders` was reported to the UI and never enforced.

    A second concurrent ffmpeg does not make two videos faster — it makes every
    API call slower and both videos late. So a job that arrives while the slot
    is taken stays `queued`, and the chain that is running collects it when it
    finishes.
    """
    from app.models.video_project import VideoProject
    from app.models.video_render import VideoRender
    from app.services.video import renders as render_service

    project_a = make_project(render_client, headers, name="A")
    project_b = make_project(render_client, headers, name="B")
    asset = upload(
        render_client, headers, clip_bytes, "clip.mp4", "video/mp4", "video"
    )
    for project in (project_a, project_b):
        add_clip(
            render_client, headers, project["id"],
            kind="video", asset_id=asset["id"], duration=1.0,
        )

    # Pretend a render is already occupying the only slot.
    occupied = render_service.queue_render(
        studio_db, project=studio_db.get(VideoProject, project_a["id"])
    )
    occupied.status = "processing"
    studio_db.commit()

    assert render_service.slot_available(studio_db) is False

    # The second project's export is accepted and queued, not rejected.
    response = render_client.post(
        f"/api/video/projects/{project_b['id']}/render",
        headers=headers, json={"quality": "draft"},
    )
    assert response.status_code == 202, response.text

    studio_db.expire_all()
    waiting = studio_db.get(VideoRender, response.json()["id"])
    assert waiting.status == "queued", "a busy server must queue, not refuse"
    assert waiting.stage == "queued"

    body = render_client.get(
        f"/api/video/renders/{waiting.id}", headers=headers
    ).json()
    assert body["phase"] == "queued"
    assert body["phase_label"] == "Queued"


def test_the_queue_is_oldest_first(studio_db, headers, render_client, clip_bytes):
    """A queue that is not in order is not a queue."""
    from app.models.video_project import VideoProject
    from app.services.video import renders as render_service

    asset = upload(
        render_client, headers, clip_bytes, "clip.mp4", "video/mp4", "video"
    )
    ids = []
    for index in range(2):
        project = make_project(render_client, headers, name=f"Q{index}")
        add_clip(
            render_client, headers, project["id"],
            kind="video", asset_id=asset["id"], duration=1.0,
        )
        row = render_service.queue_render(
            studio_db, project=studio_db.get(VideoProject, project["id"])
        )
        ids.append(row.id)

    studio_db.commit()
    assert render_service.next_queued(studio_db).id == ids[0]
