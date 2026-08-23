"""AI video creation, end to end — and into the real editor.

The claim this suite exists to check is the one the feature could most easily
cheat on: **AI generation populates the real Video Project, not a separate
uneditable output.** So the tests do not stop at "a script came back". They
run the whole pipeline and then assert that what it produced is an ordinary
project — the same timeline the hand-built editor loads, the same scenes the
scene editor edits, the same assets in the user's own library — and finally
that it renders.

    topic → script → scenes → voice → visuals → subtitles → build → EDITOR

Everything reaches a real database and a real timeline. What is stubbed is only
the outside world: the text provider is the offline `MockProvider` and speech
is a fixed WAV, because a test must not depend on a model API or a TTS vendor
being up. Visuals use the generated-card path, which needs no network by
design.
"""
from __future__ import annotations

import pytest

from app.services.providers.mock_provider import MockProvider
from tests.conftest import WAV_BYTES


@pytest.fixture()
def ai_client(studio_client, monkeypatch):
    """A client whose text generation is the offline mock.

    Patched at `get_provider` rather than by setting a config value, so this
    holds no matter which provider the deployment is configured for.
    """
    provider = MockProvider()
    for target in (
        "app.services.providers.factory.get_provider",
        "app.services.video.scripting.get_provider",
    ):
        monkeypatch.setattr(target, lambda *a, **k: provider, raising=False)
    return studio_client


@pytest.fixture()
def spoken(monkeypatch):
    """Speech synthesis, replaced by a fixed WAV stored as a real asset.

    The asset is real — it goes through `store_asset` into object storage — so
    everything downstream (the timeline clip, the renderer's resolution of it)
    is exercised for real. Only the vendor call is faked.
    """
    from app.services.video import assets as asset_service

    async def _synthesize(db, *, user_id, text, voice_id, project_id=None, title=None, **kw):
        asset = asset_service.store_asset(
            db,
            user_id=user_id,
            kind="voice",
            data=WAV_BYTES,
            content_type="audio/wav",
            title=title or "narration",
            filename="narration.wav",
            project_id=project_id,
            probe=False,
            # A plausible length for the line, so the scene-stretching logic
            # has something real to react to.
            duration_seconds=max(1.0, len(text.split()) / 2.5),
            meta={"voice_id": voice_id, "text": text},
        )
        return asset, None

    monkeypatch.setattr("app.services.video.voice.synthesize", _synthesize)
    return _synthesize


BRIEF = {
    "topic": "how compound interest works",
    "language": "en-US",
    "tone": "friendly",
    "audience": "people in their twenties",
    "duration_seconds": 30,
    "platform": "youtube_shorts",
    "content_type": "educational",
    "instructions": "Use one concrete example.",
    "visual_mode": "natural",
}


def create_project(client, headers, **overrides) -> dict:
    response = client.post(
        "/api/video/ai/projects", headers=headers, json={**BRIEF, **overrides}
    )
    assert response.status_code == 201, response.text
    return response.json()


def scenes_of(client, headers, project_id) -> list[dict]:
    response = client.get(f"/api/video/projects/{project_id}/scenes", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["scenes"]


def timeline_of(client, headers, project_id) -> dict:
    response = client.get(f"/api/video/projects/{project_id}/timeline", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def clips_on(document: dict, track_id: str) -> list[dict]:
    for track in document["timeline"]["tracks"]:
        if track["id"] == track_id:
            return track["clips"]
    raise AssertionError(f"no {track_id} track")


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_every_ai_route_requires_a_token(studio_client):
    for method, path in (
        ("get", "/api/video/ai/options"),
        ("post", "/api/video/ai/script"),
        ("post", "/api/video/ai/projects"),
        ("get", "/api/video/projects/1/script"),
        ("put", "/api/video/projects/1/script"),
        ("get", "/api/video/projects/1/scenes"),
        ("post", "/api/video/projects/1/scenes/generate"),
        ("patch", "/api/video/projects/1/scenes/1"),
        ("post", "/api/video/projects/1/scenes/1/visual"),
        ("post", "/api/video/projects/1/scenes/1/voice"),
        ("post", "/api/video/projects/1/ai/subtitles"),
        ("post", "/api/video/projects/1/ai/build"),
    ):
        kwargs = {"json": {}} if method in ("post", "put", "patch") else {}
        response = getattr(studio_client, method)(path, **kwargs)
        assert response.status_code == 401, f"{method.upper()} {path} was reachable"


def test_you_cannot_touch_someone_elses_ai_project(
    ai_client, headers, other_headers
):
    theirs = create_project(ai_client, other_headers)["project_id"]

    assert ai_client.get(
        f"/api/video/projects/{theirs}/scenes", headers=headers
    ).status_code == 404
    assert ai_client.post(
        f"/api/video/projects/{theirs}/ai/build", headers=headers, json={}
    ).status_code == 404


# ---------------------------------------------------------------------------
# Script
# ---------------------------------------------------------------------------


def test_the_form_options_come_from_the_server(ai_client, headers):
    """The generator has to understand every value the form can produce."""
    body = ai_client.get("/api/video/ai/options", headers=headers).json()

    assert "friendly" in body["tones"]
    assert "educational" in body["content_types"]
    assert body["visual_modes"] == ["natural", "animated"]
    assert any(entry["code"] == "ur-PK" for entry in body["languages"])
    assert any(entry["key"] == "tiktok" for entry in body["platforms"])


def test_a_script_has_every_named_part(ai_client, headers):
    """Hook, introduction, main points, ending, CTA — all separately present."""
    body = ai_client.post("/api/video/ai/script", headers=headers, json=BRIEF).json()

    assert body["hook"]
    assert body["introduction"]
    assert body["main_points"]
    assert body["ending"]
    assert body["cta"]
    assert all(point["heading"] and point["text"] for point in body["main_points"])
    # Not narration, but needed by the visual step.
    assert body["keywords"]


def test_the_script_is_sized_to_the_requested_duration(ai_client, headers):
    """A 30-second video must not come back as 90 seconds of narration."""
    short = ai_client.post(
        "/api/video/ai/script", headers=headers, json={**BRIEF, "duration_seconds": 15}
    ).json()
    long = ai_client.post(
        "/api/video/ai/script", headers=headers, json={**BRIEF, "duration_seconds": 120}
    ).json()

    assert len(short["main_points"]) < len(long["main_points"])
    assert short["estimated_seconds"] < long["estimated_seconds"]
    assert short["fits_budget"] is True


def test_a_script_needs_a_topic(ai_client, headers):
    response = ai_client.post(
        "/api/video/ai/script", headers=headers, json={**BRIEF, "topic": "x"}
    )
    assert response.status_code == 422


def test_the_script_can_be_edited_and_saved(ai_client, headers):
    """The requirement that every generated component stays editable."""
    created = create_project(ai_client, headers)
    project_id = created["project_id"]

    edited = {**created["script"], "hook": "A completely different hook."}
    edited["main_points"] = [
        {"id": "p1", "heading": "Mine", "text": "Words I wrote myself."}
    ]

    response = ai_client.put(
        f"/api/video/projects/{project_id}/script",
        headers=headers,
        json={"script": edited},
    )

    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["hook"] == "A completely different hook."
    assert [p["text"] for p in saved["main_points"]] == ["Words I wrote myself."]
    # The estimate follows the words actually in it, not what was asked for.
    assert saved["estimated_seconds"] < created["script"]["estimated_seconds"]

    # And it persists.
    again = ai_client.get(
        f"/api/video/projects/{project_id}/script", headers=headers
    ).json()
    assert again["hook"] == "A completely different hook."


def test_regenerating_a_script_leaves_the_scenes_alone(ai_client, headers):
    """Otherwise it silently throws away pictures the user already chose."""
    created = create_project(ai_client, headers)
    project_id = created["project_id"]
    before = len(scenes_of(ai_client, headers, project_id))

    response = ai_client.post(
        f"/api/video/projects/{project_id}/script/regenerate", headers=headers, json=BRIEF
    )

    assert response.status_code == 200, response.text
    assert len(scenes_of(ai_client, headers, project_id)) == before


# ---------------------------------------------------------------------------
# Scenes
# ---------------------------------------------------------------------------


def test_creating_an_ai_project_makes_a_real_project_with_scenes(ai_client, headers):
    """It appears in the projects list like anything else."""
    created = create_project(ai_client, headers)

    assert created["project"]["aspect_ratio"] == "9:16"
    assert created["scenes"], "no storyboard was produced"
    assert created["next_steps"] == ["visuals", "voice", "subtitles", "build"]

    listing = ai_client.get("/api/video/projects", headers=headers).json()
    assert created["project_id"] in [row["id"] for row in listing["projects"]]


def test_every_scene_carries_what_a_scene_needs(ai_client, headers):
    created = create_project(ai_client, headers)

    for scene in created["scenes"]:
        assert scene["text"], "a scene with no narration"
        assert scene["duration_seconds"] > 0
        assert scene["visual_prompt"], "a scene with nothing to search for"
        assert scene["source"] in (
            "pending", "ai_image", "stock", "upload", "color", "asset"
        )
        assert scene["transition"] in ("cut", "fade", "slide", "zoom", "wipe", "dissolve")
        assert "overlay_text" in scene["settings"]


def test_the_scenes_add_up_to_the_requested_duration(ai_client, headers):
    created = create_project(ai_client, headers, duration_seconds=45)

    total = sum(scene["duration_seconds"] for scene in created["scenes"])

    assert abs(total - 45) < 1.0, f"scenes total {total}s for a 45s brief"


def test_scenes_are_ordered_and_contiguous(ai_client, headers):
    created = create_project(ai_client, headers)
    scenes = created["scenes"]

    assert [scene["position"] for scene in scenes] == list(range(len(scenes)))
    cursor = 0.0
    for scene in scenes:
        assert abs(scene["start_seconds"] - cursor) < 0.02, "a gap in the storyboard"
        cursor += scene["duration_seconds"]


def test_the_first_scene_does_not_fade_in(ai_client, headers):
    """A fade from black at the top of a short wastes the second that matters."""
    created = create_project(ai_client, headers)
    assert created["scenes"][0]["transition"] == "cut"


def test_a_scene_can_be_edited(ai_client, headers):
    created = create_project(ai_client, headers)
    project_id = created["project_id"]
    scene = created["scenes"][1]

    response = ai_client.patch(
        f"/api/video/projects/{project_id}/scenes/{scene['id']}",
        headers=headers,
        json={
            "text": "Narration I rewrote.",
            "visual_prompt": "a lighthouse at dusk",
            "duration_seconds": 6.5,
            "transition": "zoom",
            "overlay_text": "MY WORDS",
        },
    )

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["text"] == "Narration I rewrote."
    assert updated["visual_prompt"] == "a lighthouse at dusk"
    assert updated["duration_seconds"] == 6.5
    assert updated["transition"] == "zoom"
    assert updated["settings"]["overlay_text"] == "MY WORDS"


def test_changing_a_scenes_length_moves_the_ones_after_it(ai_client, headers):
    created = create_project(ai_client, headers)
    project_id = created["project_id"]
    first = created["scenes"][0]

    ai_client.patch(
        f"/api/video/projects/{project_id}/scenes/{first['id']}",
        headers=headers,
        json={"duration_seconds": 10.0},
    )

    scenes = scenes_of(ai_client, headers, project_id)
    assert scenes[0]["duration_seconds"] == 10.0
    assert scenes[1]["start_seconds"] == 10.0


def test_scenes_can_be_reordered_and_deleted(ai_client, headers):
    created = create_project(ai_client, headers)
    project_id = created["project_id"]
    ids = [scene["id"] for scene in created["scenes"]]

    reordered = ai_client.post(
        f"/api/video/projects/{project_id}/scenes/reorder",
        headers=headers,
        json={"scene_ids": list(reversed(ids))},
    )
    assert reordered.status_code == 200
    assert [s["id"] for s in reordered.json()["scenes"]] == list(reversed(ids))

    assert ai_client.delete(
        f"/api/video/projects/{project_id}/scenes/{ids[0]}", headers=headers
    ).status_code == 204
    remaining = scenes_of(ai_client, headers, project_id)
    assert ids[0] not in [s["id"] for s in remaining]
    assert [s["position"] for s in remaining] == list(range(len(remaining)))


def test_rebuilding_the_scenes_follows_an_edited_script(ai_client, headers):
    created = create_project(ai_client, headers)
    project_id = created["project_id"]

    ai_client.put(
        f"/api/video/projects/{project_id}/script",
        headers=headers,
        json={
            "script": {
                **created["script"],
                "main_points": [
                    {"id": "p1", "heading": "Only one", "text": "A single point now."}
                ],
            }
        },
    )

    response = ai_client.post(
        f"/api/video/projects/{project_id}/scenes/generate",
        headers=headers,
        json={"describe_visuals": False},
    )

    assert response.status_code == 200, response.text
    titles = [scene["title"] for scene in response.json()["scenes"]]
    assert "Only one" in titles


# ---------------------------------------------------------------------------
# Visual modes
# ---------------------------------------------------------------------------


def test_animated_mode_puts_the_words_on_screen(ai_client, headers):
    """With no footage, the narration is the video."""
    created = create_project(ai_client, headers, visual_mode="animated")

    for scene in created["scenes"]:
        assert scene["settings"]["visual_mode"] == "animated"
        assert scene["settings"]["overlay_text"], "an animated scene with no text"
        # Nothing to search for — its background is generated.
        assert scene["source"] == "color"


def test_natural_mode_only_captions_the_beats_that_need_it(ai_client, headers):
    """A full transcript over footage fights the picture."""
    created = create_project(ai_client, headers, visual_mode="natural")
    overlays = [s["settings"]["overlay_text"] for s in created["scenes"]]

    assert any(overlays), "the hook and CTA should carry text"
    assert not all(overlays), "every scene captioned in natural mode"


def test_a_scene_gets_a_real_generated_card(ai_client, headers, studio_db):
    """The card is a real asset in the user's library, not a placeholder."""
    from app.models.video_asset import VideoAsset

    created = create_project(ai_client, headers, visual_mode="animated")
    project_id = created["project_id"]
    scene = created["scenes"][0]

    response = ai_client.post(
        f"/api/video/projects/{project_id}/scenes/{scene['id']}/visual",
        headers=headers,
        json={"strategy": "color"},
    )

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["source"] == "color"
    assert updated["asset_id"]
    assert updated["asset_url"]

    asset = studio_db.get(VideoAsset, updated["asset_id"])
    assert asset.user_id is not None
    assert asset.content_type == "image/png"
    assert asset.width == created["project"]["width"]
    # And it is in the Media Library like any other file.
    library = ai_client.get("/api/video/media", headers=headers).json()
    assert updated["asset_id"] in [item["id"] for item in library["items"]]


def test_a_failed_visual_falls_back_rather_than_leaving_a_hole(
    ai_client, headers, monkeypatch
):
    """A scene with a card is finished-looking; a scene with nothing is a gap."""
    from app.services.video import visuals

    async def _no_stock(*args, **kwargs):
        raise visuals.VisualError("no stock today")

    async def _no_ai(*args, **kwargs):
        raise visuals.VisualError("no generator today")

    monkeypatch.setattr(visuals, "attach_stock", _no_stock)
    monkeypatch.setattr(visuals, "attach_ai_image", _no_ai)

    created = create_project(ai_client, headers, visual_mode="natural")
    scene = created["scenes"][0]

    response = ai_client.post(
        f"/api/video/projects/{created['project_id']}/scenes/{scene['id']}/visual",
        headers=headers,
        json={},
    )

    assert response.status_code == 200, response.text
    assert response.json()["source"] == "color"


# ---------------------------------------------------------------------------
# Voice and subtitles
# ---------------------------------------------------------------------------


def test_narration_is_generated_per_scene(ai_client, headers, spoken):
    created = create_project(ai_client, headers)
    project_id = created["project_id"]
    scene = created["scenes"][0]

    response = ai_client.post(
        f"/api/video/projects/{project_id}/scenes/{scene['id']}/voice",
        headers=headers,
        json={},
    )

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["voice_asset_id"]
    assert updated["voice_url"]
    # Only this scene got audio — the others are untouched, which is what
    # makes one line re-recordable.
    others = scenes_of(ai_client, headers, project_id)[1:]
    assert all(row["voice_asset_id"] is None for row in others)


def test_a_scene_stretches_to_fit_narration_that_ran_long(
    ai_client, headers, monkeypatch
):
    """A voice-over cut off mid-sentence is the most obvious way this breaks."""
    from app.services.video import assets as asset_service

    async def _long(db, *, user_id, text, voice_id, project_id=None, title=None, **kw):
        asset = asset_service.store_asset(
            db, user_id=user_id, kind="voice", data=WAV_BYTES,
            content_type="audio/wav", title="long", filename="l.wav",
            project_id=project_id, probe=False, duration_seconds=12.0,
        )
        return asset, None

    monkeypatch.setattr("app.services.video.voice.synthesize", _long)

    created = create_project(ai_client, headers)
    scene = created["scenes"][0]
    assert scene["duration_seconds"] < 12.0

    response = ai_client.post(
        f"/api/video/projects/{created['project_id']}/scenes/{scene['id']}/voice",
        headers=headers, json={},
    )

    assert response.json()["duration_seconds"] >= 12.0


def test_subtitles_are_timed_from_the_scenes(ai_client, headers):
    """The storyboard knows when each line is spoken — estimating would throw
    that away."""
    created = create_project(ai_client, headers)
    project_id = created["project_id"]

    response = ai_client.post(
        f"/api/video/projects/{project_id}/ai/subtitles", headers=headers, json={}
    )

    assert response.status_code == 200, response.text
    track = response.json()
    assert track["cue_count"] > 0

    scenes = scenes_of(ai_client, headers, project_id)
    last_end = scenes[-1]["start_seconds"] + scenes[-1]["duration_seconds"]
    assert track["duration_seconds"] <= last_end + 0.5


# ---------------------------------------------------------------------------
# The join: into the real editor
# ---------------------------------------------------------------------------


def test_building_produces_an_ordinary_timeline(ai_client, headers, spoken):
    """The whole point: what comes out is the editor's own document."""
    created = create_project(ai_client, headers, visual_mode="animated")
    project_id = created["project_id"]

    for scene in created["scenes"]:
        ai_client.post(
            f"/api/video/projects/{project_id}/scenes/{scene['id']}/visual",
            headers=headers, json={"strategy": "color"},
        )
        ai_client.post(
            f"/api/video/projects/{project_id}/scenes/{scene['id']}/voice",
            headers=headers, json={},
        )

    response = ai_client.post(
        f"/api/video/projects/{project_id}/ai/build", headers=headers, json={}
    )
    assert response.status_code == 200, response.text
    assert response.json()["editor_path"] == f"/video/projects/{project_id}/edit"

    # ---- and now read it through the *editor's* endpoint ----
    document = timeline_of(ai_client, headers, project_id)

    assert [t["id"] for t in document["timeline"]["tracks"]] == [
        "video", "audio", "text"
    ]
    scenes = scenes_of(ai_client, headers, project_id)
    assert len(clips_on(document, "video")) == len(scenes)
    assert len(clips_on(document, "audio")) == len(scenes)
    assert clips_on(document, "text"), "animated mode should put text on screen"

    # Every visual clip resolves to a real asset the preview can draw, with
    # geometry computed by the compositor's own placement function.
    assert document["assets"], "the timeline references no assets"
    for clip in clips_on(document, "video"):
        assert clip["id"] in document["placements"]


def test_the_generated_timeline_is_editable_like_any_other(
    ai_client, headers, spoken
):
    """Trim, split and delete work on generated clips — they are just clips."""
    created = create_project(ai_client, headers, visual_mode="animated")
    project_id = created["project_id"]
    for scene in created["scenes"]:
        ai_client.post(
            f"/api/video/projects/{project_id}/scenes/{scene['id']}/visual",
            headers=headers, json={"strategy": "color"},
        )
    ai_client.post(f"/api/video/projects/{project_id}/ai/build", headers=headers, json={})

    clip = clips_on(timeline_of(ai_client, headers, project_id), "video")[0]

    split = ai_client.post(
        f"/api/video/projects/{project_id}/timeline/op",
        headers=headers,
        json={"op": "split", "clip_id": clip["id"], "at": clip["duration"] / 2},
    )
    assert split.status_code == 200, split.text
    assert len(split.json()["affected_clip_ids"]) == 2

    trimmed = ai_client.post(
        f"/api/video/projects/{project_id}/timeline/op",
        headers=headers,
        json={"op": "trim", "clip_id": clip["id"], "edge": "end", "to": 1.0},
    )
    assert trimmed.status_code == 200, trimmed.text


def test_rebuilding_keeps_music_the_user_chose(ai_client, headers):
    """Rebuilding the visuals is not a reason to delete somebody's music."""
    created = create_project(ai_client, headers, visual_mode="animated")
    project_id = created["project_id"]
    for scene in created["scenes"]:
        ai_client.post(
            f"/api/video/projects/{project_id}/scenes/{scene['id']}/visual",
            headers=headers, json={"strategy": "color"},
        )
    ai_client.post(f"/api/video/projects/{project_id}/ai/build", headers=headers, json={})

    # Add a music bed by hand, the way the editor would.
    music = ai_client.post(
        "/api/video/media/upload", headers=headers,
        files={"file": ("bed.wav", WAV_BYTES, "audio/wav")}, data={"kind": "music"},
    ).json()
    ai_client.post(
        f"/api/video/projects/{project_id}/timeline/op",
        headers=headers,
        json={
            "op": "add", "track_id": "audio",
            "clip": {"kind": "audio", "asset_id": music["id"], "duration": 8,
                     "role": "music"},
        },
    )

    ai_client.post(f"/api/video/projects/{project_id}/ai/build", headers=headers, json={})

    roles = [clip["role"] for clip in clips_on(timeline_of(ai_client, headers, project_id), "audio")]
    assert "music" in roles, "the rebuild deleted the music"


def test_building_before_there_are_scenes_is_refused(ai_client, headers):
    project = ai_client.post(
        "/api/video/projects", headers=headers, json={"name": "Empty"}
    ).json()

    response = ai_client.post(
        f"/api/video/projects/{project['id']}/ai/build", headers=headers, json={}
    )

    assert response.status_code == 422
    assert "no scenes" in response.json()["detail"]


# ---------------------------------------------------------------------------
# …and it renders
# ---------------------------------------------------------------------------


def test_a_generated_project_exports_to_a_real_video(
    studio_client, headers, spoken, studio_session_factory, monkeypatch
):
    """The end of the pipeline: the AI project renders like any other.

    Small on purpose — a 256x256 canvas and a couple of scenes — but it is a
    real ffmpeg encode of a timeline the AI pipeline produced, probed back to
    check it matches.
    """
    import tempfile
    from pathlib import Path

    from app.services.video.ffmpeg import probe

    provider = MockProvider()
    monkeypatch.setattr(
        "app.services.video.scripting.get_provider", lambda *a, **k: provider
    )
    monkeypatch.setattr(
        "app.services.providers.factory.get_provider", lambda *a, **k: provider
    )
    monkeypatch.setattr(
        "app.routes.video_editor.SessionLocal", studio_session_factory
    )

    created = studio_client.post(
        "/api/video/ai/projects",
        headers=headers,
        json={**BRIEF, "duration_seconds": 8, "visual_mode": "animated"},
    ).json()
    project_id = created["project_id"]

    # Shrink the canvas so the encode is quick; the pipeline does not care.
    studio_client.patch(
        f"/api/video/projects/{project_id}",
        headers=headers,
        json={"platform": "custom", "width": 256, "height": 256, "fps": 15},
    )

    for scene in created["scenes"]:
        studio_client.post(
            f"/api/video/projects/{project_id}/scenes/{scene['id']}/visual",
            headers=headers, json={"strategy": "color"},
        )
    studio_client.post(
        f"/api/video/projects/{project_id}/ai/build", headers=headers, json={}
    )

    document = timeline_of(studio_client, headers, project_id)
    expected = document["summary"]["duration_seconds"]
    assert expected > 0

    render = studio_client.post(
        f"/api/video/projects/{project_id}/render",
        headers=headers,
        json={"quality": "draft"},
    )
    assert render.status_code == 202, render.text

    finished = studio_client.get(
        f"/api/video/renders/{render.json()['id']}", headers=headers
    ).json()
    assert finished["status"] == "completed", finished.get("error")

    download = studio_client.get(
        f"/api/video/renders/{render.json()['id']}/download", headers=headers
    )
    assert download.status_code == 200

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "ai.mp4"
        path.write_bytes(download.content)
        info = probe(path)

    assert abs(info.duration_seconds - expected) < 0.5, (
        f"the export is {info.duration_seconds}s, the timeline is {expected}s"
    )
    assert (info.width, info.height) == (256, 256)


def test_equal_length_points_get_equal_screen_time(ai_client, headers):
    """Trimming to the budget must not make a balanced script lopsided.

    The budget is itself an estimate and the smallest cut is a whole sentence,
    so trimming to the exact word count means routinely dropping fifteen words
    to save four — which showed up as two identically-written main points
    running 4 seconds and 11. `fit_to_budget` absorbs a small overrun instead.
    """
    created = create_project(ai_client, headers)

    points = [
        scene for scene in created["scenes"] if scene["title"].startswith("Point")
    ]
    assert len(points) >= 2, "need at least two points to compare"

    lengths = {round(scene["duration_seconds"], 1) for scene in points}
    assert len(lengths) == 1, (
        f"identically-written points got different durations: {lengths}"
    )


def test_music_added_from_the_library_reaches_the_timeline(ai_client, headers):
    """The bridge between the two places audio can legitimately live.

    "Add to project" in the Music Library writes a `VideoAudio` row — it has to
    work before a timeline exists. The compositor only renders timeline clips.
    Without the bridge in `storyboard._music_layers`, a track chosen from the
    library would be attached to the project, visible in its audio layers, and
    silently missing from the export.
    """
    created = create_project(ai_client, headers, visual_mode="animated")
    project_id = created["project_id"]
    for scene in created["scenes"]:
        ai_client.post(
            f"/api/video/projects/{project_id}/scenes/{scene['id']}/visual",
            headers=headers, json={"strategy": "color"},
        )

    # Upload a track and add it through the Music Library, as the user would.
    track = ai_client.post(
        "/api/video/music/upload",
        headers=headers,
        files={"file": ("bed.wav", WAV_BYTES, "audio/wav")},
        data={"confirmed_rights": "true", "title": "My Bed"},
    ).json()
    added = ai_client.post(
        f"/api/video/music/{track['id']}/add",
        headers=headers,
        json={"project_id": project_id},
    )
    assert added.status_code == 201, added.text

    ai_client.post(f"/api/video/projects/{project_id}/ai/build", headers=headers, json={})

    music = [
        clip
        for clip in clips_on(timeline_of(ai_client, headers, project_id), "audio")
        if clip["role"] == "music"
    ]
    assert len(music) == 1, "the library track never reached the timeline"
    # Its mixing settings came across, not defaults.
    assert music[0]["volume"] == added.json()["volume"]

    # And a second build does not stack a duplicate.
    ai_client.post(f"/api/video/projects/{project_id}/ai/build", headers=headers, json={})
    again = [
        clip
        for clip in clips_on(timeline_of(ai_client, headers, project_id), "audio")
        if clip["role"] == "music"
    ]
    assert len(again) == 1, "rebuilding duplicated the music layer"
