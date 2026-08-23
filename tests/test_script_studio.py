"""Script Studio — a script as a thing in its own right.

Three claims are checked here, each of which the feature could quietly fail
while still looking finished:

  * **A section can be rewritten alone.** Regenerating the whole script to fix
    one weak hook throws away the lines the user already accepted. So the test
    does not settle for "new text came back" — it asserts every *other* part is
    byte-identical afterwards.
  * **Writing a script creates nothing.** The point of the studio is trying six
    topics without a projects list full of abandoned attempts, so the projects
    list is counted before and after.
  * **Taking a script into a project keeps the edits.** If creation regenerated
    the script, every reason the user kept that one would be gone — so the
    project is read back and the user's own words have to still be in it.
"""
from __future__ import annotations

import pytest

from app.services.providers.mock_provider import MockProvider


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


@pytest.fixture()
def ai_client(studio_client, monkeypatch):
    """A client whose text generation is the offline mock."""
    provider = MockProvider()
    for target in (
        "app.services.providers.factory.get_provider",
        "app.services.video.scripting.get_provider",
    ):
        monkeypatch.setattr(target, lambda *a, **k: provider, raising=False)
    return studio_client


def write(client, headers, **overrides) -> dict:
    response = client.post(
        "/api/video/ai/script", headers=headers, json={**BRIEF, **overrides}
    )
    assert response.status_code == 200, response.text
    return response.json()


def rewrite(client, headers, script, section, point_id="") -> dict:
    response = client.post(
        "/api/video/ai/script/section",
        headers=headers,
        json={"script": script, "section": section, "point_id": point_id},
    )
    assert response.status_code == 200, response.text
    return response.json()


def project_count(client, headers) -> int:
    return len(client.get("/api/video/projects", headers=headers).json()["projects"])


# ---------------------------------------------------------------------------
# Writing one, with nothing else attached
# ---------------------------------------------------------------------------


def test_a_topic_alone_is_enough(ai_client, headers):
    """Everything but the topic has a default, so one field is a whole brief."""
    response = ai_client.post(
        "/api/video/ai/script", headers=headers, json={"topic": "sourdough starters"}
    )

    assert response.status_code == 200, response.text
    script = response.json()
    assert script["hook"]
    assert script["main_points"]
    assert script["cta"]


def test_writing_a_script_creates_nothing(ai_client, headers):
    before = project_count(ai_client, headers)

    write(ai_client, headers)
    write(ai_client, headers, topic="a completely different idea")

    assert project_count(ai_client, headers) == before


def test_the_users_own_instructions_reach_the_model(ai_client, headers):
    """A field the form collects and the prompt drops is a control that lies."""
    from app.services.video import scripting

    brief = scripting.build_brief(
        **{**BRIEF, "instructions": "Mention the free calculator."}
    )
    prompt = scripting.build_prompt(brief)

    assert "Mention the free calculator." in prompt


# ---------------------------------------------------------------------------
# Rewriting one part
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("section", ["title", "hook", "introduction", "ending", "cta"])
def test_rewriting_one_section_leaves_every_other_part_alone(
    ai_client, headers, section
):
    script = write(ai_client, headers)
    updated = rewrite(ai_client, headers, script, section)

    assert updated[section] != script[section], f"{section} was not rewritten"

    untouched = [
        key
        for key in ("title", "hook", "introduction", "ending", "cta")
        if key != section
    ]
    for key in untouched:
        assert updated[key] == script[key], f"{key} changed while rewriting {section}"
    assert updated["main_points"] == script["main_points"]


def test_rewriting_one_main_point_leaves_the_others_alone(ai_client, headers):
    script = write(ai_client, headers)
    points = script["main_points"]
    assert len(points) >= 2, "need more than one point for this to mean anything"

    target = points[0]["id"]
    updated = rewrite(ai_client, headers, script, "point", point_id=target)

    assert updated["main_points"][0]["text"] != points[0]["text"]
    assert updated["main_points"][1:] == points[1:]
    assert updated["hook"] == script["hook"]


def test_rewriting_recomputes_the_estimate(ai_client, headers):
    """Otherwise the runtime shown is the one before the edit."""
    script = write(ai_client, headers)
    script["hook"] = "Tiny."
    updated = rewrite(ai_client, headers, script, "introduction")

    from app.services.video import scripting

    assert updated["estimated_seconds"] == pytest.approx(
        scripting.estimated_duration(updated), rel=0.01
    )


def test_a_section_that_is_not_part_of_a_script_is_refused(ai_client, headers):
    script = write(ai_client, headers)
    response = ai_client.post(
        "/api/video/ai/script/section",
        headers=headers,
        json={"script": script, "section": "chorus"},
    )
    assert response.status_code == 422


def test_a_missing_main_point_is_a_clear_error_not_a_crash(ai_client, headers):
    script = write(ai_client, headers)
    response = ai_client.post(
        "/api/video/ai/script/section",
        headers=headers,
        json={"script": script, "section": "point", "point_id": "p999"},
    )
    assert response.status_code == 422
    assert "no longer in the script" in response.json()["detail"]


def test_a_script_with_no_brief_says_so(ai_client, headers):
    response = ai_client.post(
        "/api/video/ai/script/section",
        headers=headers,
        json={"script": {"hook": "orphaned"}, "section": "hook"},
    )
    assert response.status_code == 422
    assert "brief" in response.json()["detail"].lower()


def test_a_brief_can_be_supplied_for_a_script_from_elsewhere(ai_client, headers):
    """A script that arrived without one is still rewritable."""
    response = ai_client.post(
        "/api/video/ai/script/section",
        headers=headers,
        json={
            "script": {"hook": "orphaned", "main_points": []},
            "section": "hook",
            "brief": BRIEF,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["hook"] != "orphaned"


def test_rewriting_needs_a_token(studio_client):
    response = studio_client.post(
        "/api/video/ai/script/section", json={"script": {}, "section": "hook"}
    )
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Taking it into a project
# ---------------------------------------------------------------------------


def test_a_written_script_carries_its_edits_into_a_new_project(ai_client, headers):
    script = write(ai_client, headers)
    script["hook"] = "The line the user insisted on."
    script["main_points"][0]["text"] = "Words they typed themselves."

    response = ai_client.post(
        "/api/video/ai/projects",
        headers=headers,
        json={**BRIEF, "script": script, "name": "From Script Studio"},
    )
    assert response.status_code == 201, response.text
    created = response.json()

    assert created["script"]["hook"] == "The line the user insisted on."
    assert created["script"]["main_points"][0]["text"] == "Words they typed themselves."

    # And it is the project's real script, not just the response body.
    saved = ai_client.get(
        f"/api/video/projects/{created['project_id']}/script", headers=headers
    ).json()
    assert saved["hook"] == "The line the user insisted on."


def test_a_supplied_script_is_what_the_storyboard_is_cut_from(ai_client, headers):
    """Scenes built from a regenerated script would not match what was approved."""
    script = write(ai_client, headers)
    script["main_points"] = [
        {"id": "p1", "heading": "Only one", "text": "A single point, deliberately."}
    ]

    created = ai_client.post(
        "/api/video/ai/projects", headers=headers, json={**BRIEF, "script": script}
    ).json()

    spoken = " ".join(scene.get("text") or "" for scene in created["scenes"])
    assert "A single point, deliberately." in spoken


def test_creating_without_a_script_still_writes_one(ai_client, headers):
    """The passthrough must not have broken the ordinary path."""
    response = ai_client.post("/api/video/ai/projects", headers=headers, json=BRIEF)

    assert response.status_code == 201, response.text
    assert response.json()["script"]["hook"]


# ---------------------------------------------------------------------------
# A document that arrived malformed
# ---------------------------------------------------------------------------
# Both the save and the rewrite take a script dict straight from the client, so
# the shape is an input, not an invariant. These used to be 500s: the duration
# arithmetic assumed every main point was an object and blew up on anything
# else, three frames below the endpoint that accepted it.


@pytest.mark.parametrize(
    "main_points",
    ["not a list", ["a bare string"], [1, 2], [None], [{"no": "text"}]],
)
def test_a_malformed_main_points_is_not_a_server_error(
    ai_client, headers, main_points
):
    script = write(ai_client, headers)
    response = ai_client.post(
        "/api/video/ai/script/section",
        headers=headers,
        json={"script": {**script, "main_points": main_points}, "section": "hook"},
    )
    assert response.status_code < 500, response.text


@pytest.mark.parametrize("field", ["title", "introduction", "ending", "cta"])
def test_a_non_string_section_is_not_a_server_error(ai_client, headers, field):
    script = write(ai_client, headers)
    response = ai_client.post(
        "/api/video/ai/script/section",
        headers=headers,
        json={"script": {**script, field: {"junk": True}}, "section": "hook"},
    )
    assert response.status_code < 500, response.text


def test_saving_a_malformed_script_is_not_a_server_error(ai_client, headers):
    """The same document reaches the ordinary save, so it needs the same care."""
    created = ai_client.post(
        "/api/video/ai/projects", headers=headers, json=BRIEF
    ).json()

    response = ai_client.put(
        f"/api/video/projects/{created['project_id']}/script",
        headers=headers,
        json={"script": {"hook": "h", "main_points": "not a list"}},
    )
    assert response.status_code < 500, response.text


def test_a_hand_written_script_of_bare_strings_still_works(ai_client, headers):
    """Points as plain strings is what an import or a sloppy client sends."""
    created = ai_client.post(
        "/api/video/ai/projects", headers=headers, json=BRIEF
    ).json()

    response = ai_client.put(
        f"/api/video/projects/{created['project_id']}/script",
        headers=headers,
        json={"script": {"hook": "h", "main_points": ["first line", "second line"]}},
    )

    assert response.status_code == 200, response.text
    assert [p["text"] for p in response.json()["main_points"]] == [
        "first line",
        "second line",
    ]


def test_sanitising_does_not_touch_the_words_a_person_typed():
    """Structure only. `normalize_script` strips markdown and parentheticals —
    running that over a manual edit would silently rewrite deliberate text."""
    from app.services.video import scripting

    typed = "  Two  spaces, (a parenthetical) and **stars** "
    cleaned = scripting.sanitize_document(
        {"hook": typed, "main_points": [{"id": "p1", "text": typed}]}
    )

    assert cleaned["hook"] == typed
    assert cleaned["main_points"][0]["text"] == typed


def test_a_script_document_is_bounded_in_size():
    """The script is JSON on the project row; nothing else limits what a client
    sends to the save endpoint, so a project could become somewhere to park
    megabytes that no reader ever returns."""
    from app.services.video import scripting

    huge = {
        "hook": "x" * 50_000,
        "main_points": [
            {"id": f"p{i}", "text": "y" * 20_000} for i in range(400)
        ],
        "keywords": ["k"] * 200,
        **{f"junk{i}": "z" * 500 for i in range(1000)},
    }

    clean = scripting.sanitize_document(huge)

    assert len(clean["hook"]) == scripting.MAX_SECTION_CHARS
    assert len(clean["main_points"]) == scripting.MAX_POINTS
    assert len(clean["main_points"][0]["text"]) == scripting.MAX_SECTION_CHARS
    assert len(clean["keywords"]) == scripting.MAX_KEYWORDS
    # Unknown keys are dropped: ScriptDocument already ignores them on the way
    # out, so storing them only grows the row with data nothing can read.
    assert not [key for key in clean if key.startswith("junk")]


def test_saving_an_oversized_script_stores_the_bounded_version(ai_client, headers):
    created = ai_client.post(
        "/api/video/ai/projects", headers=headers, json=BRIEF
    ).json()

    response = ai_client.put(
        f"/api/video/projects/{created['project_id']}/script",
        headers=headers,
        json={"script": {"hook": "x" * 50_000, "main_points": [], "junk": "y" * 100_000}},
    )

    assert response.status_code == 200, response.text

    from app.services.video import scripting

    stored = ai_client.get(
        f"/api/video/projects/{created['project_id']}/script", headers=headers
    ).json()
    assert len(stored["hook"]) == scripting.MAX_SECTION_CHARS


# ---------------------------------------------------------------------------
# What the form says it can do
# ---------------------------------------------------------------------------
# `text_available` drives the "no text provider is configured" banner.
# `bool(settings.ai_provider)` could never be false — AI_PROVIDER has a default
# — so on a deployment with no key the banner never appeared and the user
# filled in the whole brief before the generate call failed.


def test_the_form_says_generation_is_unavailable_with_no_provider(
    studio_client, headers, monkeypatch
):
    from app.services.providers.base import ProviderConfigError

    def _no_provider(*args, **kwargs):
        raise ProviderConfigError("No AI provider is configured.")

    monkeypatch.setattr(
        "app.services.providers.factory.get_provider", _no_provider, raising=False
    )

    body = studio_client.get("/api/video/ai/options", headers=headers).json()

    assert body["text_available"] is False


def test_the_form_says_generation_is_available_with_one(ai_client, headers):
    """`ai_client` patches a working provider in."""
    body = ai_client.get("/api/video/ai/options", headers=headers).json()

    assert body["text_available"] is True


# ---------------------------------------------------------------------------
# Long form — a script the length of a talk, not a Reel
# ---------------------------------------------------------------------------
# A "20 minute" script that comes back at four minutes is the failure this
# section exists to catch, and it is not hypothetical: one model call cannot
# return 4,500 words, so asking for one produces a script that stops early and
# reports itself as finished. The tests below assert the length that was asked
# for actually arrives, that it arrives in chapters rather than five monologues,
# and that a single failed call costs one chapter instead of the whole script.


class CountingProvider(MockProvider):
    """The mock, plus a record of what was asked of it."""

    def __init__(self) -> None:
        super().__init__()
        self.features: list[str] = []

    async def complete(self, **kwargs):
        self.features.append(str((kwargs.get("context") or {}).get("feature") or ""))
        return await super().complete(**kwargs)


@pytest.fixture()
def counting(studio_client, monkeypatch):
    """A client whose provider counts its calls."""
    provider = CountingProvider()
    for target in (
        "app.services.providers.factory.get_provider",
        "app.services.video.scripting.get_provider",
    ):
        monkeypatch.setattr(target, lambda *a, **k: provider, raising=False)
    return studio_client, provider


def test_a_twenty_minute_script_is_twenty_minutes_long(ai_client, headers):
    """The whole point. A long script that comes back short is the bug."""
    script = write(ai_client, headers, duration_seconds=1200)

    assert script["estimated_seconds"] > 1000, (
        f"asked for 20 minutes, got {script['estimated_seconds'] / 60:.1f}"
    )
    assert script["fits_budget"] is True


def test_length_still_scales_all_the_way_up(ai_client, headers):
    """Each step up in the dropdown has to produce a longer script."""
    lengths = [
        write(ai_client, headers, duration_seconds=seconds)["estimated_seconds"]
        for seconds in (300, 900, 1800)
    ]

    assert lengths == sorted(lengths), lengths
    assert lengths[-1] > lengths[0] * 3


def test_a_long_script_is_chapters_not_five_monologues(ai_client, headers):
    """Five points across half an hour is six minutes of talking per point."""
    script = write(ai_client, headers, duration_seconds=1800)

    points = script["main_points"]
    assert len(points) >= 12, f"half an hour cut into only {len(points)} points"
    assert all(point["heading"] and point["text"] for point in points)
    # Distinct headings, or the "chapters" are one chapter repeated.
    assert len({point["heading"] for point in points}) == len(points)


def test_a_long_script_is_written_in_passes(counting, headers):
    """Outline first, then chapters — and a bounded number of calls either way."""
    client, provider = counting
    write(client, headers, duration_seconds=1800)

    assert provider.features.count("video_script_outline") == 1
    chapters = provider.features.count("video_script_chapters")
    assert chapters > 1, "half an hour was asked for in a single call"
    assert chapters <= 12, f"{chapters} calls is a request that times out"


def test_a_short_script_is_still_one_call(counting, headers):
    """The extra machinery must not reach the lengths that never needed it."""
    client, provider = counting
    write(client, headers, duration_seconds=30)

    assert provider.features == ["video_script"]


def test_one_failed_chapter_does_not_lose_the_others(studio_client, headers, monkeypatch):
    """A rate limit on call four should cost one chapter, not twenty minutes."""
    from app.services.providers.base import ProviderError

    class FlakyProvider(MockProvider):
        def __init__(self) -> None:
            super().__init__()
            self.batches = 0

        async def complete(self, **kwargs):
            feature = str((kwargs.get("context") or {}).get("feature") or "")
            if feature == "video_script_chapters":
                self.batches += 1
                if self.batches == 1:
                    raise ProviderError("rate limited")
            return await super().complete(**kwargs)

    provider = FlakyProvider()
    for target in (
        "app.services.providers.factory.get_provider",
        "app.services.video.scripting.get_provider",
    ):
        monkeypatch.setattr(target, lambda *a, **k: provider, raising=False)

    script = write(studio_client, headers, duration_seconds=1200)

    # Every chapter is still there and still editable — the failed one carries
    # its outline summary, which is short, not empty.
    assert len(script["main_points"]) >= 12
    assert all(point["text"] for point in script["main_points"])


def test_a_script_may_be_longer_than_a_video(ai_client, headers):
    """Writing half an hour is free. Rendering it is not, and says so."""
    assert (
        ai_client.post(
            "/api/video/ai/script", headers=headers, json={**BRIEF, "duration_seconds": 1800}
        ).status_code
        == 200
    )

    refused = ai_client.post(
        "/api/video/ai/projects", headers=headers, json={**BRIEF, "duration_seconds": 1800}
    )
    assert refused.status_code == 422


def test_the_form_only_offers_lengths_the_server_accepts(ai_client, headers):
    """A length in the dropdown the generator refuses is a control that lies."""
    body = ai_client.get("/api/video/ai/options", headers=headers).json()

    low, high = body["duration_range"]
    assert body["durations"], "the form has no lengths to offer"
    assert all(low <= value <= high for value in body["durations"])
    assert max(body["durations"]) >= 1200, "long form is not reachable from the form"
    # The form for making a video needs to know where the video pipeline stops.
    assert 0 < body["project_max_seconds"] <= high
    assert 0 < body["max_video_seconds"] <= body["project_max_seconds"]
