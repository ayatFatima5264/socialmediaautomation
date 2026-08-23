"""The timeline editor, end to end — including a real export.

`test_timeline.py` covers the edit arithmetic as pure functions. This suite
drives the HTTP API the editor actually calls, and then **renders an actual
MP4 with ffmpeg and probes it back**, because the one claim that cannot be
proved with mocks is the one that matters most: the exported video matches the
timeline.

The checklist this covers, in order: add media, move, trim, split, delete,
audio, text, preview data, export, timeline persistence, a failed render, and
retry.

The renders are deliberately tiny — a 256x256 canvas, about a second long, at
draft quality — so the suite stays runnable. They are still real encodes
through the real filter graph; nothing is stubbed between the timeline and the
file.
"""
from __future__ import annotations

import subprocess

import pytest

from app.services.video.ffmpeg import ffmpeg_path, probe
from tests.conftest import WAV_BYTES


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def render_client(studio_client, studio_session_factory, monkeypatch):
    """A client whose background render jobs run against the test database.

    `run_render_job` opens its own session on purpose — it runs after the
    response, when the request's session is gone, and that is what lets the
    same function be a queue consumer in another process. Here that means it
    has to be pointed at the test database explicitly, or a render would write
    to the developer's real one.
    """
    monkeypatch.setattr(
        "app.routes.video_editor.SessionLocal", studio_session_factory
    )
    return studio_client


@pytest.fixture(scope="session")
def sample_media(tmp_path_factory) -> dict:
    """Real media, made with ffmpeg once for the whole suite.

    Generated rather than committed: a checked-in MP4 is a binary nobody can
    review, and these have to be decodable by the same ffmpeg that renders
    them.
    """
    directory = tmp_path_factory.mktemp("media")
    ffmpeg = ffmpeg_path()

    clip = directory / "clip.mp4"
    subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=size=320x240:rate=15:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-shortest", "-y", str(clip),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )

    photo = directory / "photo.png"
    subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=#1f6f54:size=320x240:d=1",
            "-frames:v", "1", "-y", str(photo),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )

    return {"clip": clip.read_bytes(), "photo": photo.read_bytes()}


def make_project(client, headers, **body) -> dict:
    """A small custom-canvas project, so the test renders stay cheap."""
    payload = {
        "name": "Editor Test",
        "platform": "custom",
        "width": 256,
        "height": 256,
        "fps": 15,
        **body,
    }
    response = client.post("/api/video/projects", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def upload(client, headers, data, name, content_type, kind) -> dict:
    response = client.post(
        "/api/video/media/upload",
        headers=headers,
        files={"file": (name, data, content_type)},
        data={"kind": kind},
    )
    assert response.status_code == 200, response.text
    return response.json()


def timeline(client, headers, project_id) -> dict:
    response = client.get(
        f"/api/video/projects/{project_id}/timeline", headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def op(client, headers, project_id, **body) -> dict:
    """Apply one edit. Asserts success — use `raw_op` to inspect a refusal."""
    response = raw_op(client, headers, project_id, **body)
    assert response.status_code == 200, response.text
    return response.json()


def raw_op(client, headers, project_id, **body):
    return client.post(
        f"/api/video/projects/{project_id}/timeline/op", headers=headers, json=body
    )


def clips_on(document: dict, track_id: str) -> list[dict]:
    for track in document["timeline"]["tracks"]:
        if track["id"] == track_id:
            return track["clips"]
    raise AssertionError(f"no {track_id} track")


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_every_editor_route_requires_a_token(studio_client):
    for method, path in (
        ("get", "/api/video/projects/1/timeline"),
        ("put", "/api/video/projects/1/timeline"),
        ("post", "/api/video/projects/1/timeline/op"),
        ("post", "/api/video/projects/1/render"),
        ("get", "/api/video/projects/1/renders"),
        ("get", "/api/video/renders/1"),
        ("post", "/api/video/renders/1/cancel"),
        ("post", "/api/video/renders/1/retry"),
    ):
        kwargs = {"json": {}} if method in ("post", "put") else {}
        response = getattr(studio_client, method)(path, **kwargs)
        assert response.status_code == 401, f"{method.upper()} {path} was reachable"


def test_you_cannot_edit_someone_elses_timeline(studio_client, headers, other_headers):
    theirs = make_project(studio_client, other_headers)

    assert studio_client.get(
        f"/api/video/projects/{theirs['id']}/timeline", headers=headers
    ).status_code == 404
    assert raw_op(
        studio_client, headers, theirs["id"], op="delete", clip_id="x"
    ).status_code == 404


# ---------------------------------------------------------------------------
# The document
# ---------------------------------------------------------------------------


def test_a_new_project_opens_with_three_empty_tracks(studio_client, headers):
    project = make_project(studio_client, headers)

    document = timeline(studio_client, headers, project["id"])

    assert [t["id"] for t in document["timeline"]["tracks"]] == [
        "video", "audio", "text"
    ]
    assert document["summary"]["total_clips"] == 0
    # The canvas travels with the document: every position in it is a fraction
    # of the canvas, so a preview that guessed would frame clips differently
    # from the export.
    assert (document["width"], document["height"], document["fps"]) == (256, 256, 15)


# ---------------------------------------------------------------------------
# Add
# ---------------------------------------------------------------------------


def test_adding_media_puts_a_clip_on_the_timeline(
    studio_client, headers, sample_media
):
    project = make_project(studio_client, headers)
    asset = upload(
        studio_client, headers, sample_media["clip"], "clip.mp4", "video/mp4", "video"
    )

    document = op(
        studio_client, headers, project["id"],
        op="add",
        track_id="video",
        clip={"kind": "video", "asset_id": asset["id"], "duration": 2.0},
    )

    clips = clips_on(document, "video")
    assert len(clips) == 1
    assert clips[0]["asset_id"] == asset["id"]
    assert document["summary"]["duration_seconds"] == 2.0
    # The asset comes back resolved, so the preview can draw it immediately.
    assert document["assets"][0]["url"]


def test_adding_appends_after_the_last_clip(studio_client, headers, sample_media):
    project = make_project(studio_client, headers)
    asset = upload(
        studio_client, headers, sample_media["clip"], "clip.mp4", "video/mp4", "video"
    )

    for _ in range(2):
        document = op(
            studio_client, headers, project["id"],
            op="add", track_id="video",
            clip={"kind": "video", "asset_id": asset["id"], "duration": 1.5},
        )

    starts = [clip["start"] for clip in clips_on(document, "video")]
    assert starts == [0.0, 1.5]


def test_adding_over_an_existing_video_clip_is_refused(
    studio_client, headers, sample_media
):
    project = make_project(studio_client, headers)
    asset = upload(
        studio_client, headers, sample_media["clip"], "clip.mp4", "video/mp4", "video"
    )
    op(studio_client, headers, project["id"], op="add", track_id="video",
       clip={"kind": "video", "asset_id": asset["id"], "duration": 4.0})

    response = raw_op(
        studio_client, headers, project["id"], op="add", track_id="video",
        clip={"kind": "video", "asset_id": asset["id"], "duration": 1.0}, at=2.0,
    )

    assert response.status_code == 422
    assert "already a clip" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Move, trim, split, delete
# ---------------------------------------------------------------------------


@pytest.fixture()
def loaded(studio_client, headers, sample_media):
    """A project with one video clip on it, ready to edit."""
    project = make_project(studio_client, headers)
    asset = upload(
        studio_client, headers, sample_media["clip"], "clip.mp4", "video/mp4", "video"
    )
    document = op(
        studio_client, headers, project["id"], op="add", track_id="video",
        clip={"kind": "video", "asset_id": asset["id"], "duration": 2.0},
    )
    return {
        "project": project,
        "asset": asset,
        "clip_id": clips_on(document, "video")[0]["id"],
    }


def test_moving_a_clip(studio_client, headers, loaded):
    document = op(
        studio_client, headers, loaded["project"]["id"],
        op="move", clip_id=loaded["clip_id"], start=3.0,
    )

    clip = clips_on(document, "video")[0]
    assert clip["start"] == 3.0
    assert clip["duration"] == 2.0
    assert document["summary"]["duration_seconds"] == 5.0


def test_trimming_a_clip(studio_client, headers, loaded):
    document = op(
        studio_client, headers, loaded["project"]["id"],
        op="trim", clip_id=loaded["clip_id"], edge="end", to=1.2,
    )

    clip = clips_on(document, "video")[0]
    assert clip["duration"] == 1.2
    assert clip["trim_end"] == 1.2


def test_splitting_a_clip(studio_client, headers, loaded):
    document = op(
        studio_client, headers, loaded["project"]["id"],
        op="split", clip_id=loaded["clip_id"], at=0.8,
    )

    clips = clips_on(document, "video")
    assert len(clips) == 2
    assert [c["duration"] for c in clips] == [0.8, 1.2]
    # Both halves are reported, so the editor can keep the selection.
    assert len(document["affected_clip_ids"]) == 2


def test_deleting_a_clip(studio_client, headers, loaded):
    document = op(
        studio_client, headers, loaded["project"]["id"],
        op="delete", clip_id=loaded["clip_id"],
    )

    assert clips_on(document, "video") == []
    assert document["summary"]["duration_seconds"] == 0.0


def test_a_refused_edit_leaves_the_timeline_untouched(studio_client, headers, loaded):
    before = timeline(studio_client, headers, loaded["project"]["id"])

    response = raw_op(
        studio_client, headers, loaded["project"]["id"],
        op="split", clip_id=loaded["clip_id"], at=0.01,
    )
    assert response.status_code == 422

    after = timeline(studio_client, headers, loaded["project"]["id"])
    assert after["timeline"] == before["timeline"]


def test_reordering_the_video_track(studio_client, headers, sample_media):
    project = make_project(studio_client, headers)
    asset = upload(
        studio_client, headers, sample_media["clip"], "clip.mp4", "video/mp4", "video"
    )
    for duration in (1.0, 2.0):
        document = op(
            studio_client, headers, project["id"], op="add", track_id="video",
            clip={"kind": "video", "asset_id": asset["id"], "duration": duration},
        )
    first, second = [clip["id"] for clip in clips_on(document, "video")]

    document = op(
        studio_client, headers, project["id"],
        op="reorder", track_id="video", clip_ids=[second, first],
    )

    assert [(c["id"], c["start"]) for c in clips_on(document, "video")] == [
        (second, 0.0),
        (first, 2.0),
    ]


# ---------------------------------------------------------------------------
# Audio and text
# ---------------------------------------------------------------------------


def test_audio_clips_carry_their_mixing_controls(studio_client, headers):
    project = make_project(studio_client, headers)
    asset = upload(studio_client, headers, WAV_BYTES, "bed.wav", "audio/wav", "music")

    document = op(
        studio_client, headers, project["id"], op="add", track_id="audio",
        clip={
            "kind": "audio", "asset_id": asset["id"], "duration": 2.0,
            "volume": 0.25, "fade_in": 0.4, "fade_out": 0.6, "role": "music",
        },
    )

    clip = clips_on(document, "audio")[0]
    assert (clip["volume"], clip["fade_in"], clip["fade_out"]) == (0.25, 0.4, 0.6)
    assert clip["role"] == "music"


def test_a_fade_longer_than_the_clip_is_clamped(studio_client, headers):
    """`afade` given a fade longer than the audio produces silence."""
    project = make_project(studio_client, headers)
    asset = upload(studio_client, headers, WAV_BYTES, "bed.wav", "audio/wav", "music")

    document = op(
        studio_client, headers, project["id"], op="add", track_id="audio",
        clip={"kind": "audio", "asset_id": asset["id"], "duration": 2.0, "fade_in": 10},
    )

    assert clips_on(document, "audio")[0]["fade_in"] <= 1.0


def test_text_clips_carry_their_styling(studio_client, headers):
    project = make_project(studio_client, headers)

    document = op(
        studio_client, headers, project["id"], op="add", track_id="text",
        clip={
            "kind": "text", "text": "Hello", "duration": 2.0,
            "font_family": "Roboto", "font_size": 64, "color": "#FF0000",
            "position": "bottom", "animation": "fade",
        },
    )

    clip = clips_on(document, "text")[0]
    assert clip["text"] == "Hello"
    assert (clip["font_size"], clip["color"]) == (64, "#FF0000")
    assert clip["animation"] == "fade"
    # A text clip needs no asset.
    assert clip["asset_id"] is None


def test_updating_a_clips_video_controls(studio_client, headers, loaded):
    document = op(
        studio_client, headers, loaded["project"]["id"],
        op="update", clip_id=loaded["clip_id"],
        patch={
            "scale": 1.5, "x": 0.1, "y": -0.05, "rotation": 15,
            "speed": 1.5, "volume": 0.4,
            "crop": {"left": 0.1, "right": 0.1, "top": 0.0, "bottom": 0.0},
        },
    )

    clip = clips_on(document, "video")[0]
    assert (clip["scale"], clip["x"], clip["y"]) == (1.5, 0.1, -0.05)
    assert (clip["rotation"], clip["speed"], clip["volume"]) == (15.0, 1.5, 0.4)
    assert clip["crop"]["left"] == 0.1


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_the_timeline_survives_a_reload(studio_client, headers, loaded):
    """Autosave is worthless if what comes back is not what went in."""
    op(
        studio_client, headers, loaded["project"]["id"],
        op="update", clip_id=loaded["clip_id"], patch={"scale": 1.25},
    )

    reloaded = timeline(studio_client, headers, loaded["project"]["id"])

    assert clips_on(reloaded, "video")[0]["scale"] == 1.25


def test_a_full_save_replaces_the_document(studio_client, headers, loaded):
    """The path undo and redo use."""
    project_id = loaded["project"]["id"]
    before = timeline(studio_client, headers, project_id)

    op(studio_client, headers, project_id, op="delete", clip_id=loaded["clip_id"])
    assert clips_on(timeline(studio_client, headers, project_id), "video") == []

    response = studio_client.put(
        f"/api/video/projects/{project_id}/timeline",
        headers=headers,
        json={"timeline": before["timeline"], "autosave": False},
    )
    assert response.status_code == 200, response.text

    assert len(clips_on(timeline(studio_client, headers, project_id), "video")) == 1


def test_a_stale_save_is_refused(studio_client, headers, loaded):
    """A second tab's autosave must not silently revert this one."""
    project_id = loaded["project"]["id"]
    stale = timeline(studio_client, headers, project_id)

    op(studio_client, headers, project_id, op="move", clip_id=loaded["clip_id"], start=1)

    response = studio_client.put(
        f"/api/video/projects/{project_id}/timeline",
        headers=headers,
        json={
            "timeline": stale["timeline"],
            "expected_revision": stale["revision"],
        },
    )

    assert response.status_code == 409


def test_a_saved_document_is_normalized_before_it_is_stored(
    studio_client, headers, sample_media
):
    """A hand-made request must not put something unrenderable in the database."""
    project = make_project(studio_client, headers)

    response = studio_client.put(
        f"/api/video/projects/{project['id']}/timeline",
        headers=headers,
        json={
            "timeline": {
                "tracks": [
                    {"id": "video", "clips": [
                        {"kind": "video", "asset_id": 1, "duration": "nonsense",
                         "scale": None, "crop": {"left": 5}},
                    ]},
                    {"id": "nonexistent", "clips": [{"kind": "video"}]},
                ]
            },
            "autosave": False,
        },
    )

    assert response.status_code == 200
    clip = clips_on(response.json(), "video")[0]
    assert clip["duration"] == 5.0
    assert clip["scale"] == 1.0
    assert clip["crop"]["left"] <= 0.95
    assert [t["id"] for t in response.json()["timeline"]["tracks"]] == [
        "video", "audio", "text"
    ]


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def test_exporting_produces_a_video_that_matches_the_timeline(
    render_client, headers, sample_media
):
    """The claim the whole module rests on, checked against a real file.

    A video clip, an image, a music bed and a title — rendered by ffmpeg and
    probed back. The duration, the canvas and the presence of an audio stream
    all have to come from the timeline, not from any source file.
    """
    project = make_project(render_client, headers)
    video_asset = upload(
        render_client, headers, sample_media["clip"], "clip.mp4", "video/mp4", "video"
    )
    photo_asset = upload(
        render_client, headers, sample_media["photo"], "photo.png", "image/png", "image"
    )
    music_asset = upload(
        render_client, headers, WAV_BYTES, "bed.wav", "audio/wav", "music"
    )

    op(render_client, headers, project["id"], op="add", track_id="video",
       clip={"kind": "video", "asset_id": video_asset["id"], "duration": 1.0})
    op(render_client, headers, project["id"], op="add", track_id="video",
       clip={"kind": "image", "asset_id": photo_asset["id"], "duration": 1.0})
    op(render_client, headers, project["id"], op="add", track_id="audio",
       clip={"kind": "audio", "asset_id": music_asset["id"], "duration": 2.0,
             "volume": 0.4, "fade_in": 0.2})
    op(render_client, headers, project["id"], op="add", track_id="text",
       clip={"kind": "text", "text": "100% real", "duration": 1.5, "font_size": 28})

    expected = timeline(render_client, headers, project["id"])["summary"][
        "duration_seconds"
    ]
    assert expected == 2.0

    response = render_client.post(
        f"/api/video/projects/{project['id']}/render",
        headers=headers,
        json={"quality": "draft"},
    )
    assert response.status_code == 202, response.text
    render = response.json()

    # TestClient runs background tasks before returning, so the job is done.
    finished = render_client.get(
        f"/api/video/renders/{render['id']}", headers=headers
    ).json()

    assert finished["status"] == "completed", finished.get("error")
    assert finished["progress"] == 1.0
    assert finished["stage"] == "done"
    assert finished["output_url"]

    # ---- the actual file --------------------------------------------------
    download = render_client.get(
        f"/api/video/renders/{render['id']}/download", headers=headers
    )
    assert download.status_code == 200
    assert download.content[:12], "the export is empty"

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "export.mp4"
        path.write_bytes(download.content)
        info = probe(path)

    assert abs(info.duration_seconds - expected) < 0.4, (
        f"the export is {info.duration_seconds}s but the timeline is {expected}s"
    )
    assert (info.width, info.height) == (256, 256), "the export ignored the canvas"
    assert info.has_audio, "the audio track did not reach the export"


def test_exporting_an_empty_timeline_is_refused_immediately(render_client, headers):
    """With a reason, rather than as a failed job minutes later."""
    project = make_project(render_client, headers)

    response = render_client.post(
        f"/api/video/projects/{project['id']}/render", headers=headers, json={}
    )

    assert response.status_code == 422
    assert "nothing on its timeline" in response.json()["detail"]


def test_a_render_snapshots_the_timeline(render_client, headers, sample_media):
    """Editing while it exports must not change what is being encoded."""
    project = make_project(render_client, headers)
    asset = upload(
        render_client, headers, sample_media["clip"], "clip.mp4", "video/mp4", "video"
    )
    document = op(
        render_client, headers, project["id"], op="add", track_id="video",
        clip={"kind": "video", "asset_id": asset["id"], "duration": 1.0},
    )
    clip_id = clips_on(document, "video")[0]["id"]

    render = render_client.post(
        f"/api/video/projects/{project['id']}/render",
        headers=headers, json={"quality": "draft"},
    ).json()

    # The job has already finished here; change the project afterwards.
    op(render_client, headers, project["id"], op="delete", clip_id=clip_id)

    finished = render_client.get(
        f"/api/video/renders/{render['id']}", headers=headers
    ).json()
    assert finished["status"] == "completed", finished.get("error")
    assert finished["duration_seconds"] == 1.0


# ---------------------------------------------------------------------------
# Failure and retry
# ---------------------------------------------------------------------------


def test_a_render_whose_media_is_gone_fails_with_a_usable_reason(
    render_client, headers, sample_media
):
    """`missing_asset`, so the UI can offer to open the project."""
    project = make_project(render_client, headers)
    asset = upload(
        render_client, headers, sample_media["clip"], "clip.mp4", "video/mp4", "video"
    )
    op(render_client, headers, project["id"], op="add", track_id="video",
       clip={"kind": "video", "asset_id": asset["id"], "duration": 1.0})

    # Delete the media out from under the timeline, the way a tidy-up would.
    assert render_client.delete(
        f"/api/video/media/{asset['id']}?force=true", headers=headers
    ).status_code == 204

    render = render_client.post(
        f"/api/video/projects/{project['id']}/render",
        headers=headers, json={"quality": "draft"},
    ).json()

    finished = render_client.get(
        f"/api/video/renders/{render['id']}", headers=headers
    ).json()

    assert finished["status"] == "failed"
    assert finished["error_code"] == "missing_asset"
    assert finished["error"], "a failure with no message is unsupportable"
    assert finished["error_stage"], "a failure must say how far it got"


def test_a_failed_render_leaves_the_project_editable(
    render_client, headers, sample_media
):
    """A failed export must never damage the project."""
    project = make_project(render_client, headers)
    asset = upload(
        render_client, headers, sample_media["clip"], "clip.mp4", "video/mp4", "video"
    )
    op(render_client, headers, project["id"], op="add", track_id="video",
       clip={"kind": "video", "asset_id": asset["id"], "duration": 1.0})
    render_client.delete(f"/api/video/media/{asset['id']}?force=true", headers=headers)

    render_client.post(
        f"/api/video/projects/{project['id']}/render",
        headers=headers, json={"quality": "draft"},
    )

    document = timeline(render_client, headers, project["id"])
    assert len(clips_on(document, "video")) == 1, "the failure ate the timeline"

    detail = render_client.get(
        f"/api/video/projects/{project['id']}", headers=headers
    ).json()
    assert detail["status"] == "failed"


def test_retrying_a_failed_render_is_a_new_attempt(
    render_client, headers, sample_media
):
    """A new job, so "it failed twice" is visible rather than overwritten."""
    project = make_project(render_client, headers)
    asset = upload(
        render_client, headers, sample_media["clip"], "clip.mp4", "video/mp4", "video"
    )
    op(render_client, headers, project["id"], op="add", track_id="video",
       clip={"kind": "video", "asset_id": asset["id"], "duration": 1.0})
    render_client.delete(f"/api/video/media/{asset['id']}?force=true", headers=headers)

    first = render_client.post(
        f"/api/video/projects/{project['id']}/render",
        headers=headers, json={"quality": "draft"},
    ).json()
    assert render_client.get(
        f"/api/video/renders/{first['id']}", headers=headers
    ).json()["status"] == "failed"

    second = render_client.post(
        f"/api/video/renders/{first['id']}/retry", headers=headers, json={}
    )

    assert second.status_code == 202, second.text
    assert second.json()["id"] != first["id"]
    assert second.json()["attempt"] == first["attempt"] + 1

    # Both attempts survive in the history.
    history = render_client.get(
        f"/api/video/projects/{project['id']}/renders", headers=headers
    ).json()
    assert len(history["renders"]) == 2


def test_retrying_after_fixing_the_problem_succeeds(
    render_client, headers, sample_media
):
    """The retry snapshots the timeline as it is now — that is the point."""
    project = make_project(render_client, headers)
    asset = upload(
        render_client, headers, sample_media["clip"], "clip.mp4", "video/mp4", "video"
    )
    document = op(
        render_client, headers, project["id"], op="add", track_id="video",
        clip={"kind": "video", "asset_id": asset["id"], "duration": 1.0},
    )
    broken_clip = clips_on(document, "video")[0]["id"]
    render_client.delete(f"/api/video/media/{asset['id']}?force=true", headers=headers)

    failed = render_client.post(
        f"/api/video/projects/{project['id']}/render",
        headers=headers, json={"quality": "draft"},
    ).json()

    # Fix it: drop the broken clip and add a working one.
    op(render_client, headers, project["id"], op="delete", clip_id=broken_clip)
    replacement = upload(
        render_client, headers, sample_media["photo"], "photo.png", "image/png", "image"
    )
    op(render_client, headers, project["id"], op="add", track_id="video",
       clip={"kind": "image", "asset_id": replacement["id"], "duration": 1.0})

    retried = render_client.post(
        f"/api/video/renders/{failed['id']}/retry", headers=headers, json={}
    ).json()

    finished = render_client.get(
        f"/api/video/renders/{retried['id']}", headers=headers
    ).json()
    assert finished["status"] == "completed", finished.get("error")


def test_a_second_render_while_one_is_running_is_refused(
    render_client, headers, sample_media, studio_db
):
    """Two encodes of one project would race for the same output."""
    from app.models.video_render import VideoRender

    project = make_project(render_client, headers)
    asset = upload(
        render_client, headers, sample_media["clip"], "clip.mp4", "video/mp4", "video"
    )
    op(render_client, headers, project["id"], op="add", track_id="video",
       clip={"kind": "video", "asset_id": asset["id"], "duration": 1.0})

    first = render_client.post(
        f"/api/video/projects/{project['id']}/render",
        headers=headers, json={"quality": "draft"},
    ).json()

    # Put the finished job back into a running state, which is what the API
    # would see while a real encode was in flight.
    row = studio_db.get(VideoRender, first["id"])
    row.status = "processing"
    studio_db.commit()

    response = render_client.post(
        f"/api/video/projects/{project['id']}/render", headers=headers, json={}
    )

    assert response.status_code == 422
    assert "already being rendered" in response.json()["detail"]


def test_cancelling_returns_the_project_to_draft(
    render_client, headers, sample_media, studio_db
):
    from app.models.video_render import VideoRender

    project = make_project(render_client, headers)
    asset = upload(
        render_client, headers, sample_media["clip"], "clip.mp4", "video/mp4", "video"
    )
    op(render_client, headers, project["id"], op="add", track_id="video",
       clip={"kind": "video", "asset_id": asset["id"], "duration": 1.0})

    render = render_client.post(
        f"/api/video/projects/{project['id']}/render",
        headers=headers, json={"quality": "draft"},
    ).json()

    row = studio_db.get(VideoRender, render["id"])
    row.status = "processing"
    row.finished_at = None
    studio_db.commit()

    cancelled = render_client.post(
        f"/api/video/renders/{render['id']}/cancel", headers=headers
    ).json()

    assert cancelled["status"] == "cancelled"
    # A project is never in a cancelled condition — one attempt at exporting
    # it was.
    detail = render_client.get(
        f"/api/video/projects/{project['id']}", headers=headers
    ).json()
    assert detail["status"] == "draft"


@pytest.mark.parametrize("animation", ["none", "fade", "slide-up", "pop"])
def test_every_text_animation_actually_encodes(
    render_client, headers, sample_media, animation
):
    """Each animation the editor offers must survive the filter graph.

    `slide-up` and `pop` build a `y` expression containing commas, and an
    unquoted comma inside a filter argument is the separator between two
    filters — so those two produced a graph ffmpeg refused, while `none` and
    `fade` rendered fine. A vocabulary the editor offers and the renderer
    cannot draw is exactly what `TEXT_ANIMATIONS` exists to prevent, so every
    value in it is encoded here.
    """
    project = make_project(render_client, headers)
    asset = upload(
        render_client, headers, sample_media["photo"], "photo.png", "image/png", "image"
    )
    op(render_client, headers, project["id"], op="add", track_id="video",
       clip={"kind": "image", "asset_id": asset["id"], "duration": 1.0})
    op(render_client, headers, project["id"], op="add", track_id="text",
       clip={"kind": "text", "text": "Hello", "duration": 1.0,
             "animation": animation, "font_size": 24})

    render = render_client.post(
        f"/api/video/projects/{project['id']}/render",
        headers=headers, json={"quality": "draft"},
    )
    assert render.status_code == 202, render.text

    finished = render_client.get(
        f"/api/video/renders/{render.json()['id']}", headers=headers
    ).json()
    assert finished["status"] == "completed", (
        f"{animation} did not encode: {finished.get('error')}"
    )


# ---------------------------------------------------------------------------
# Compositor geometry
# ---------------------------------------------------------------------------


def test_tightening_keeps_the_same_visible_region():
    """`tighten` exists to stop the renderer scaling pixels it throws away.

    A 1280x720 clip covering a 1080x1920 canvas was being scaled to 3414x1920
    — 6.5 megapixels per frame to keep 2.1 — which made a vertical render take
    four times as long as the same edit in landscape.

    The invariant that matters is that the tightened placement still covers the
    canvas and still shows the same part of the source. Bit-equality is not
    achievable at these upscale factors and is not claimed; see the docstring.
    """
    from app.services.video.compositor import Source, place, tighten

    source = Source(path="", width=1280, height=720, has_video=True)

    for label, clip, canvas in (
        ("cover 9:16", {"fit": "cover"}, (1080, 1920)),
        ("cover zoomed", {"fit": "cover", "scale": 1.3, "x": 0.15}, (1080, 1920)),
        ("cover 1:1", {"fit": "cover"}, (1080, 1080)),
    ):
        full = place(clip, source, canvas_w=canvas[0], canvas_h=canvas[1])
        tight = tighten(full, canvas_w=canvas[0], canvas_h=canvas[1])

        assert tight.scaled_w * tight.scaled_h < full.scaled_w * full.scaled_h, (
            f"{label}: tightening did not reduce the work"
        )
        # Still covers the whole canvas.
        assert tight.pos_x <= 0 or tight.pos_x + tight.scaled_w >= canvas[0]
        assert tight.pos_y <= 0 or tight.pos_y + tight.scaled_h >= canvas[1]
        # The scale factor is preserved to within rounding.
        assert abs(
            (tight.scaled_w / tight.crop_w) - (full.scaled_w / full.crop_w)
        ) < 0.02, f"{label}: the scale factor moved"
        # And the crop stays inside the source.
        assert tight.crop_x >= 0 and tight.crop_y >= 0
        assert tight.crop_x + tight.crop_w <= source.width
        assert tight.crop_y + tight.crop_h <= source.height


def test_a_clip_that_fits_is_left_alone():
    """`contain`, and `cover` on a matching ratio, must be bit-identical."""
    from app.services.video.compositor import Source, place, tighten

    source = Source(path="", width=1280, height=720, has_video=True)

    for clip, canvas in (
        ({"fit": "contain"}, (1080, 1920)),
        ({"fit": "cover"}, (640, 360)),
    ):
        full = place(clip, source, canvas_w=canvas[0], canvas_h=canvas[1])
        assert tighten(full, canvas_w=canvas[0], canvas_h=canvas[1]) == full


def test_a_rotated_clip_is_never_tightened(studio_client, headers, sample_media):
    """Rotation happens after the scale, so the visible region is not a
    rectangle in source space and the substitution would not be equivalent."""
    from app.services.video import compositor

    project = make_project(studio_client, headers)
    asset = upload(
        studio_client, headers, sample_media["clip"], "c.mp4", "video/mp4", "video"
    )
    op(studio_client, headers, project["id"], op="add", track_id="video",
       clip={"kind": "video", "asset_id": asset["id"], "duration": 1.0,
             "rotation": 30, "fit": "cover"})

    document = timeline(studio_client, headers, project["id"])
    clip = clips_on(document, "video")[0]
    assert clip["rotation"] == 30.0

    sources = {
        asset["id"]: compositor.Source(
            path="x", width=320, height=240, duration=2.0, has_video=True
        )
    }
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        plan = compositor.build_command(
            timeline=document["timeline"], width=1080, height=1920, fps=15,
            sources=sources, output_path=f"{directory}/o.mp4", work_dir=directory,
        )
    graph = plan.args[plan.args.index("-filter_complex") + 1]
    assert "rotate=" in graph
    # The untightened, overflowing scale is still there for the rotated clip.
    full = compositor.place(
        {"fit": "cover", "rotation": 30}, sources[asset["id"]],
        canvas_w=1080, canvas_h=1920,
    )
    assert f"scale={full.scaled_w}:{full.scaled_h}" in graph


# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------
# The timeline is stored as JSON on the project row and becomes one ffmpeg
# filter chain at render time. Nothing used to bound how many clips a track
# could hold, so a client could grow both without limit.


def test_a_track_will_not_take_unlimited_clips():
    from app.services.video import timeline as tl

    document = tl.normalize({})
    for index in range(tl.MAX_CLIPS_PER_TRACK):
        document, _ = tl.add_clip(
            document,
            track_id="text",
            clip={"kind": "text", "text": "x", "duration": 0.1},
            at=index * 0.2,
        )

    with pytest.raises(tl.TimelineError) as excinfo:
        tl.add_clip(
            document,
            track_id="text",
            clip={"kind": "text", "text": "one too many", "duration": 0.1},
            at=9999,
        )

    assert str(tl.MAX_CLIPS_PER_TRACK) in str(excinfo.value)


def test_loading_a_document_applies_the_same_cap():
    """Otherwise a PUT of the whole timeline walks straight past `add_clip`."""
    from app.services.video import timeline as tl

    document = tl.normalize(
        {
            "tracks": [
                {
                    "id": "text",
                    "clips": [
                        {"kind": "text", "text": f"t{i}", "start": i, "duration": 1}
                        for i in range(tl.MAX_CLIPS_PER_TRACK * 3)
                    ],
                }
            ]
        }
    )

    assert len(tl.get_track(document, "text")["clips"]) == tl.MAX_CLIPS_PER_TRACK
