"""Smart Repurpose: one long video into shorts, without touching the original.

Two claims carry this feature, and both are asserted here rather than assumed:

  * **The original is unchanged.** Not "we do not mean to change it" — the
    source project's timeline, name, status and revision are captured before
    and compared after, and the source *asset* is checked to still be exactly
    one file. Ten shorts from one recording must be one video in storage.
  * **Every short is an ordinary project.** It opens through the editor's own
    timeline endpoint and its clips can be trimmed and split like any others,
    because a "generated clip" that cannot be edited is the thing this feature
    is not allowed to produce.

Transcription is stubbed — it is a paid vendor call and the test must not
depend on one — but everything downstream of it is real: real assets, real
projects, real timelines.
"""
from __future__ import annotations

import subprocess

import pytest

from app.services.providers.mock_provider import MockProvider
from app.services.video.ffmpeg import ffmpeg_path

# A transcript of a two-minute talk: 24 segments, five seconds each.
SEGMENTS = [
    {
        "start": index * 5.0,
        "end": index * 5.0 + 5.0,
        "text": f"This is sentence {index}, and it makes a complete point.",
    }
    for index in range(24)
]


# The stand-in recording. Genuinely two minutes long, because the whole
# feature is about cutting a long video down — a four-second file with a
# two-minute transcript would make every duration assertion meaningless, and
# the clip-length bounds untestable. Small and low frame rate so encoding it
# once per session stays cheap.
SOURCE_SECONDS = 120


@pytest.fixture(scope="session")
def long_video(tmp_path_factory) -> bytes:
    """A real two-minute recording: video with an audio track."""
    directory = tmp_path_factory.mktemp("repurpose")
    path = directory / "talk.mp4"
    subprocess.run(
        [
            ffmpeg_path(), "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"testsrc=size=320x180:rate=10:duration={SOURCE_SECONDS}",
            "-f", "lavfi", "-i", f"sine=frequency=300:duration={SOURCE_SECONDS}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", "-y", str(path),
        ],
        check=True, capture_output=True, timeout=300,
    )
    return path.read_bytes()


@pytest.fixture()
def rp_client(studio_client, monkeypatch):
    """A client with the offline model and a stubbed transcriber."""
    provider = MockProvider()
    for target in (
        "app.services.providers.factory.get_provider",
        "app.services.video.repurpose.get_provider",
    ):
        monkeypatch.setattr(target, lambda *a, **k: provider, raising=False)

    async def _transcribe(db, *, user_id, data, filename, content_type, **kw):
        return {
            "cues": [dict(segment) for segment in SEGMENTS],
            "text": " ".join(segment["text"] for segment in SEGMENTS),
            "language": "English",
            "duration_seconds": 120.0,
            "provider": "stub",
            "model": "stub-1",
            "word_count": 0,
            "words": [],
        }

    monkeypatch.setattr(
        "app.services.video.transcription.transcribe", _transcribe
    )
    return studio_client


def upload_source(client, headers, data) -> dict:
    response = client.post(
        "/api/video/media/upload",
        headers=headers,
        files={"file": ("talk.mp4", data, "video/mp4")},
        data={"kind": "video"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def analyze(client, headers, asset_id, **body) -> dict:
    response = client.post(
        "/api/video/repurpose/analyze",
        headers=headers,
        json={"asset_id": asset_id, **body},
    )
    assert response.status_code == 200, response.text
    return response.json()


def make_shorts(client, headers, asset_id, moments, targets, **body):
    return client.post(
        "/api/video/repurpose/shorts",
        headers=headers,
        json={
            "asset_id": asset_id,
            "moments": moments,
            "targets": targets,
            **body,
        },
    )


def clips_on(document: dict, track_id: str) -> list[dict]:
    for track in document["timeline"]["tracks"]:
        if track["id"] == track_id:
            return track["clips"]
    raise AssertionError(f"no {track_id} track")


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_every_repurpose_route_requires_a_token(studio_client):
    for method, path in (
        ("get", "/api/video/repurpose/targets"),
        ("post", "/api/video/repurpose/analyze"),
        ("post", "/api/video/repurpose/shorts"),
    ):
        kwargs = {"json": {}} if method == "post" else {}
        response = getattr(studio_client, method)(path, **kwargs)
        assert response.status_code == 401, f"{method.upper()} {path} was reachable"


def test_you_cannot_repurpose_someone_elses_video(
    rp_client, headers, other_headers, long_video
):
    theirs = upload_source(rp_client, other_headers, long_video)

    response = rp_client.post(
        "/api/video/repurpose/analyze", headers=headers, json={"asset_id": theirs["id"]}
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def test_the_targets_are_the_three_short_form_surfaces(rp_client, headers):
    body = rp_client.get("/api/video/repurpose/targets", headers=headers).json()

    assert {entry["key"] for entry in body["targets"]} == {
        "youtube_shorts", "tiktok", "instagram_reels"
    }
    assert all(entry["max_seconds"] <= 90 for entry in body["targets"])


def test_analysis_proposes_editable_moments(rp_client, headers, long_video):
    asset = upload_source(rp_client, headers, long_video)

    result = analyze(rp_client, headers, asset["id"], count=3)

    assert result["moments"], "no moments were proposed"
    for moment in result["moments"]:
        assert moment["end"] > moment["start"]
        assert moment["hook"], "a clip with no hook"
        assert moment["cta"], "a clip with no call to action"
        # Why it was picked, so a reviewer can disagree with a reason.
        assert "reason" in moment
    assert result["segment_count"] == len(SEGMENTS)


def test_moments_respect_the_length_bounds(rp_client, headers, long_video):
    asset = upload_source(rp_client, headers, long_video)

    result = analyze(rp_client, headers, asset["id"], count=5)

    for moment in result["moments"]:
        length = moment["end"] - moment["start"]
        assert 15.0 <= length <= 90.0, f"a {length:.0f}s clip is not a short"


def test_analysis_creates_no_projects(rp_client, headers, long_video):
    """Analyse changes nothing. The user reviews first."""
    asset = upload_source(rp_client, headers, long_video)
    before = rp_client.get("/api/video/projects", headers=headers).json()["total"]

    analyze(rp_client, headers, asset["id"])

    after = rp_client.get("/api/video/projects", headers=headers).json()["total"]
    assert after == before


def test_the_transcript_is_cached_and_not_paid_for_twice(
    rp_client, headers, long_video, monkeypatch
):
    asset = upload_source(rp_client, headers, long_video)
    first = analyze(rp_client, headers, asset["id"])
    assert first["cached"] is False

    calls = []

    async def _explode(db, **kw):
        calls.append(1)
        raise AssertionError("transcription ran again")

    monkeypatch.setattr("app.services.video.transcription.transcribe", _explode)

    second = analyze(rp_client, headers, asset["id"])

    assert second["cached"] is True
    assert not calls
    assert second["segment_count"] == first["segment_count"]


def test_overlapping_moments_are_reported_not_merged(rp_client, headers, long_video):
    """Two shorts from overlapping spans is sometimes what somebody wants."""
    asset = upload_source(rp_client, headers, long_video)

    result = analyze(rp_client, headers, asset["id"], count=5)

    assert isinstance(result["overlaps"], list)
    for pair in result["overlaps"]:
        first, second = result["moments"][pair[0]], result["moments"][pair[1]]
        assert second["start"] < first["end"]


def test_a_file_with_no_audio_is_refused(rp_client, headers):
    from tests.conftest import png_bytes

    image = rp_client.post(
        "/api/video/media/upload",
        headers=headers,
        files={"file": ("photo.png", png_bytes(64, 64), "image/png")},
        data={"kind": "image"},
    ).json()

    response = rp_client.post(
        "/api/video/repurpose/analyze", headers=headers, json={"asset_id": image["id"]}
    )

    assert response.status_code == 422
    assert "video or an audio" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Creating the shorts
# ---------------------------------------------------------------------------


def test_each_moment_becomes_a_project_per_platform(rp_client, headers, long_video):
    asset = upload_source(rp_client, headers, long_video)
    result = analyze(rp_client, headers, asset["id"], count=2)
    moments = result["moments"][:2]

    response = make_shorts(
        rp_client, headers, asset["id"], moments, ["youtube_shorts", "tiktok"]
    )

    assert response.status_code == 201, response.text
    shorts = response.json()["shorts"]
    assert len(shorts) == 4, "two moments for two platforms is four projects"
    assert {short["target"] for short in shorts} == {"youtube_shorts", "tiktok"}
    for short in shorts:
        assert short["aspect_ratio"] == "9:16", "a short that is not vertical"
        assert short["editor_path"].endswith("/edit")


def test_a_short_trims_the_source_rather_than_copying_it(
    rp_client, headers, long_video, studio_db
):
    """Ten shorts from one recording must be one file in storage."""
    from app.models.video_asset import VideoAsset

    asset = upload_source(rp_client, headers, long_video)
    before = studio_db.query(VideoAsset).count()

    result = analyze(rp_client, headers, asset["id"], count=3)
    response = make_shorts(
        rp_client, headers, asset["id"], result["moments"], ["youtube_shorts"]
    )
    assert response.status_code == 201, response.text

    studio_db.expire_all()
    assert studio_db.query(VideoAsset).count() == before, "the source was copied"

    short = response.json()["shorts"][0]
    document = rp_client.get(
        f"/api/video/projects/{short['project_id']}/timeline", headers=headers
    ).json()
    clip = clips_on(document, "video")[0]

    assert clip["asset_id"] == asset["id"], "the short does not use the source"
    assert clip["trim_start"] == short["moment"]["start"]
    assert clip["trim_end"] == short["moment"]["end"]


def test_a_short_is_framed_vertically(rp_client, headers, long_video):
    """A 16:9 source on a 9:16 canvas, filled and centre-cropped."""
    asset = upload_source(rp_client, headers, long_video)
    result = analyze(rp_client, headers, asset["id"], count=1)

    response = make_shorts(
        rp_client, headers, asset["id"], result["moments"], ["tiktok"]
    )
    short = response.json()["shorts"][0]

    document = rp_client.get(
        f"/api/video/projects/{short['project_id']}/timeline", headers=headers
    ).json()
    clip = clips_on(document, "video")[0]
    assert clip["fit"] == "cover"

    # And the geometry is the compositor's own: scaled to fill the vertical
    # canvas, overflowing horizontally.
    placement = document["placements"][clip["id"]]
    assert placement["height"] >= document["height"]
    assert placement["width"] >= document["width"]


def test_a_short_carries_its_hook_and_cta(rp_client, headers, long_video):
    asset = upload_source(rp_client, headers, long_video)
    result = analyze(rp_client, headers, asset["id"], count=1)
    moment = {**result["moments"][0], "hook": "WAIT FOR IT", "cta": "Full video in bio"}

    response = make_shorts(
        rp_client, headers, asset["id"], [moment], ["youtube_shorts"]
    )
    short = response.json()["shorts"][0]

    document = rp_client.get(
        f"/api/video/projects/{short['project_id']}/timeline", headers=headers
    ).json()
    texts = [clip["text"] for clip in clips_on(document, "text")]

    assert "WAIT FOR IT" in texts
    assert "Full video in bio" in texts
    # The hook is at the top of the clip; the CTA at the end.
    hook = next(c for c in clips_on(document, "text") if c["text"] == "WAIT FOR IT")
    cta = next(c for c in clips_on(document, "text") if c["text"] == "Full video in bio")
    assert hook["start"] == 0.0
    assert cta["start"] > hook["start"]


def test_a_short_is_captioned_from_the_transcript(rp_client, headers, long_video):
    """The words are already known — transcribing a slice again would cost
    money to produce a worse answer."""
    asset = upload_source(rp_client, headers, long_video)
    result = analyze(rp_client, headers, asset["id"], count=1)

    response = make_shorts(
        rp_client, headers, asset["id"], result["moments"], ["youtube_shorts"]
    )
    short = response.json()["shorts"][0]

    tracks = rp_client.get(
        f"/api/video/subtitles/tracks?project_id={short['project_id']}",
        headers=headers,
    ).json()

    assert tracks, "the short has no captions"
    assert tracks[0]["cue_count"] > 0
    # Re-timed to start at zero, not left on the original's clock.
    assert tracks[0]["duration_seconds"] <= short["duration_seconds"] + 1


def test_moments_the_user_edited_are_what_gets_made(rp_client, headers, long_video):
    """The review step has to actually matter."""
    asset = upload_source(rp_client, headers, long_video)
    analyze(rp_client, headers, asset["id"], count=1)

    edited = {
        "start": 30.0,
        "end": 55.0,
        "title": "My chosen bit",
        "hook": "My hook",
        "cta": "My CTA",
        "focus_x": 0.2,
        "reason": "",
        "transcript": "",
    }

    response = make_shorts(
        rp_client, headers, asset["id"], [edited], ["youtube_shorts"]
    )
    short = response.json()["shorts"][0]

    assert "My chosen bit" in short["name"]
    document = rp_client.get(
        f"/api/video/projects/{short['project_id']}/timeline", headers=headers
    ).json()
    clip = clips_on(document, "video")[0]
    assert clip["trim_start"] == 30.0
    assert clip["trim_end"] == 55.0
    assert clip["duration"] == 25.0
    assert clip["x"] == 0.2, "the framing the user chose was ignored"


def test_a_clip_too_long_for_its_platform_is_skipped_with_a_reason(
    rp_client, headers, long_video
):
    """Not silently truncated — a clip cut mid-sentence is not what was
    reviewed."""
    asset = upload_source(rp_client, headers, long_video)
    analyze(rp_client, headers, asset["id"])

    long_moment = {
        "start": 0.0, "end": 85.0, "title": "Too long", "hook": "h", "cta": "c",
        "focus_x": 0.0, "reason": "", "transcript": "",
    }

    response = make_shorts(
        rp_client, headers, asset["id"], [long_moment],
        ["youtube_shorts", "instagram_reels"],
    )

    assert response.status_code == 201, response.text
    body = response.json()
    # Reels allows 90s, Shorts allows 60 — so one is made and one is skipped.
    assert [short["target"] for short in body["shorts"]] == ["instagram_reels"]
    assert body["skipped"][0]["target"] == "youtube_shorts"
    assert "60 seconds" in body["skipped"][0]["reason"]


# ---------------------------------------------------------------------------
# The original is untouched
# ---------------------------------------------------------------------------


def test_the_source_project_is_completely_unchanged(
    rp_client, headers, long_video, studio_db
):
    """The requirement, checked field by field rather than assumed."""
    from app.models.video_project import VideoProject

    asset = upload_source(rp_client, headers, long_video)
    source = rp_client.post(
        "/api/video/projects", headers=headers, json={"name": "The long talk"}
    ).json()

    # Give it a timeline of its own so there is something to damage.
    rp_client.post(
        f"/api/video/projects/{source['id']}/timeline/op",
        headers=headers,
        json={
            "op": "add", "track_id": "video",
            "clip": {"kind": "video", "asset_id": asset["id"], "duration": 4.0},
        },
    )

    row = studio_db.get(VideoProject, source["id"])
    studio_db.refresh(row)
    before = {
        "name": row.name,
        "platform": row.platform,
        "status": row.status,
        "revision": row.revision,
        "timeline": rp_client.get(
            f"/api/video/projects/{source['id']}/timeline", headers=headers
        ).json()["timeline"],
    }

    result = analyze(rp_client, headers, asset["id"], count=2)
    response = make_shorts(
        rp_client, headers, asset["id"], result["moments"],
        ["youtube_shorts", "tiktok"], source_project_id=source["id"],
    )
    assert response.status_code == 201, response.text

    studio_db.expire_all()
    after_row = studio_db.get(VideoProject, source["id"])
    after = {
        "name": after_row.name,
        "platform": after_row.platform,
        "status": after_row.status,
        "revision": after_row.revision,
        "timeline": rp_client.get(
            f"/api/video/projects/{source['id']}/timeline", headers=headers
        ).json()["timeline"],
    }

    assert after == before, "repurposing modified the source project"


def test_shorts_are_separate_projects_that_record_where_they_came_from(
    rp_client, headers, long_video
):
    asset = upload_source(rp_client, headers, long_video)
    source = rp_client.post(
        "/api/video/projects", headers=headers, json={"name": "The long talk"}
    ).json()
    result = analyze(rp_client, headers, asset["id"], count=1)

    response = make_shorts(
        rp_client, headers, asset["id"], result["moments"], ["tiktok"],
        source_project_id=source["id"],
    )
    short = response.json()["shorts"][0]

    assert short["project_id"] != source["id"]
    detail = rp_client.get(
        f"/api/video/projects/{short['project_id']}", headers=headers
    ).json()
    assert detail["project_type"] == "repurpose"
    assert detail["script"]["source_project_id"] == source["id"]
    assert detail["script"]["source_asset_id"] == asset["id"]
    assert detail["script"]["moment"]["start"] == result["moments"][0]["start"]


def test_nothing_is_rendered_or_published_automatically(
    rp_client, headers, long_video
):
    asset = upload_source(rp_client, headers, long_video)
    result = analyze(rp_client, headers, asset["id"], count=2)

    response = make_shorts(
        rp_client, headers, asset["id"], result["moments"], ["youtube_shorts"]
    )

    for short in response.json()["shorts"]:
        renders = rp_client.get(
            f"/api/video/projects/{short['project_id']}/renders", headers=headers
        ).json()
        assert renders["renders"] == [], "a short was rendered without being asked"
        detail = rp_client.get(
            f"/api/video/projects/{short['project_id']}", headers=headers
        ).json()
        assert detail["status"] == "draft"


# ---------------------------------------------------------------------------
# The shorts are ordinary, editable projects
# ---------------------------------------------------------------------------


def test_a_generated_short_is_editable_in_the_video_editor(
    rp_client, headers, long_video
):
    """The claim that makes this feature useful rather than a black box."""
    asset = upload_source(rp_client, headers, long_video)
    result = analyze(rp_client, headers, asset["id"], count=1)
    short = make_shorts(
        rp_client, headers, asset["id"], result["moments"], ["youtube_shorts"]
    ).json()["shorts"][0]
    project_id = short["project_id"]

    document = rp_client.get(
        f"/api/video/projects/{project_id}/timeline", headers=headers
    ).json()
    clip = clips_on(document, "video")[0]

    # Split it.
    split = rp_client.post(
        f"/api/video/projects/{project_id}/timeline/op",
        headers=headers,
        json={"op": "split", "clip_id": clip["id"], "at": clip["duration"] / 2},
    )
    assert split.status_code == 200, split.text
    assert len(clips_on(split.json(), "video")) == 2

    # Trim it.
    trimmed = rp_client.post(
        f"/api/video/projects/{project_id}/timeline/op",
        headers=headers,
        json={"op": "trim", "clip_id": clip["id"], "edge": "end", "to": 3.0},
    )
    assert trimmed.status_code == 200, trimmed.text

    # Restyle the hook.
    hook = clips_on(document, "text")[0]
    updated = rp_client.post(
        f"/api/video/projects/{project_id}/timeline/op",
        headers=headers,
        json={"op": "update", "clip_id": hook["id"], "patch": {"font_size": 90}},
    )
    assert updated.status_code == 200, updated.text


def test_a_generated_short_exports(rp_client, headers, long_video, studio_session_factory, monkeypatch):
    """The end of the line: a repurposed clip renders like anything else."""
    import tempfile
    from pathlib import Path

    from app.services.video.ffmpeg import probe

    monkeypatch.setattr(
        "app.routes.video_editor.SessionLocal", studio_session_factory
    )

    asset = upload_source(rp_client, headers, long_video)
    # A moment inside the four seconds the stand-in actually contains, so the
    # export has real frames to work with.
    moment = {
        "start": 0.5, "end": 16.0, "title": "Bit", "hook": "Hook",
        "cta": "CTA", "focus_x": 0.0, "reason": "", "transcript": "",
    }
    analyze(rp_client, headers, asset["id"])
    short = make_shorts(
        rp_client, headers, asset["id"], [moment], ["youtube_shorts"]
    ).json()["shorts"][0]
    project_id = short["project_id"]

    # Shrink the canvas so the encode is quick.
    rp_client.patch(
        f"/api/video/projects/{project_id}",
        headers=headers,
        json={"platform": "custom", "width": 144, "height": 256, "fps": 12},
    )
    # And shorten it — the stand-in is only four seconds long.
    document = rp_client.get(
        f"/api/video/projects/{project_id}/timeline", headers=headers
    ).json()
    clip = clips_on(document, "video")[0]
    rp_client.post(
        f"/api/video/projects/{project_id}/timeline/op",
        headers=headers,
        json={"op": "trim", "clip_id": clip["id"], "edge": "end", "to": 2.0},
    )

    render = rp_client.post(
        f"/api/video/projects/{project_id}/render",
        headers=headers, json={"quality": "draft"},
    )
    assert render.status_code == 202, render.text

    finished = rp_client.get(
        f"/api/video/renders/{render.json()['id']}", headers=headers
    ).json()
    assert finished["status"] == "completed", finished.get("error")

    download = rp_client.get(
        f"/api/video/renders/{render.json()['id']}/download", headers=headers
    )
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "short.mp4"
        path.write_bytes(download.content)
        info = probe(path)

    assert (info.width, info.height) == (144, 256), "the export is not vertical"


# ---------------------------------------------------------------------------
# The "no transcription provider" banner
# ---------------------------------------------------------------------------
# `available_transcription_providers` is a list of the provider names this build
# supports. It was being *called* — `bool(available_transcription_providers())`
# — which raises TypeError, which a bare `except Exception` swallowed into
# `False`. So production told every user transcription was unconfigured no
# matter what was configured, and nothing failed loudly enough to notice.


def test_the_banner_reflects_a_configured_provider(studio_client, headers, monkeypatch):
    from app.config import settings
    from app.services.video.providers import reset_provider_cache

    monkeypatch.setattr(settings, "transcription_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "gsk_a_key_that_is_present")
    reset_provider_cache()

    response = studio_client.get("/api/video/repurpose/targets", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["transcription_available"] is True


def test_the_banner_reflects_a_missing_key(studio_client, headers, monkeypatch):
    from app.config import settings
    from app.services.video.providers import reset_provider_cache

    monkeypatch.setattr(settings, "transcription_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", None)
    reset_provider_cache()

    response = studio_client.get("/api/video/repurpose/targets", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["transcription_available"] is False
