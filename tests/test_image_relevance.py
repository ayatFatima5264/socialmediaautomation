"""Tests for image relevance and layout-aware prompting.

Two failure modes these guard against, both of which are silent:

  • the layout's safe zone never reaching the image model, so text lands on a
    busy area with nothing to sit on;
  • the post never being turned into a visual brief, so the raw marketing copy
    goes to a diffusion model and comes back as generic stock.

All offline: prompt composition is pure string work, and the endpoint builds
URLs without fetching anything (verify defaults to False).
"""
from __future__ import annotations

from urllib.parse import unquote, urlparse

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import ai_service
from app.services.ai_service import TEMPLATE_SLOTS, _slot_limits
from app.services.image_service import (
    DESIGN_DIRECTION,
    MAX_PROMPT_CHARS,
    SAFE_ZONES,
    build_image_candidates,
    compose_prompt,
    safe_zone_fragment,
)

client = TestClient(app)

# Safe zones declared by the frontend layouts (frontend/src/lib/brandKit/
# contentTemplates.js — the `zone` and `altZones` of each template's layout).
FRONTEND_ZONES = {"bottom", "top", "center"}


def _prompt_of(url: str) -> str:
    """The prompt actually sent to the image provider, decoded from its URL."""
    return unquote(urlparse(url).path.split("/prompt/", 1)[-1])


# ---- Safe zones ------------------------------------------------------------

def test_every_frontend_zone_has_a_backend_fragment():
    """A zone the layout uses but the backend ignores fails silently.

    The prompt would simply carry no composition rule, and the image would come
    back with the subject exactly where the text is about to go.
    """
    missing = FRONTEND_ZONES - set(SAFE_ZONES)
    assert not missing, f"layout zones with no composition rule: {missing}"


@pytest.mark.parametrize("zone", sorted(SAFE_ZONES))
def test_zone_fragments_describe_negative_space(zone):
    fragment = SAFE_ZONES[zone]
    assert "space" in fragment or "calm" in fragment or "minimal" in fragment


def test_safe_zone_reaches_the_prompt():
    out = compose_prompt("a dental clinic", safe_zone="bottom")
    assert "a dental clinic" in out
    assert SAFE_ZONES["bottom"] in out


def test_unknown_safe_zone_is_ignored_not_injected():
    assert safe_zone_fragment("nowhere") == ""
    assert compose_prompt("a bakery", safe_zone="nowhere") == "a bakery"


def test_safe_zone_adds_layout_negatives():
    """Composing for a design surface must suppress clutter and lettering."""
    out = compose_prompt("a bakery", safe_zone="bottom")
    assert "without" in out
    assert "cluttered background" in out
    assert "text" in out


def test_plain_generation_is_unchanged():
    """No layout, no design constraints — the old behaviour, verbatim."""
    assert compose_prompt("a bakery") == "a bakery"


def test_user_negatives_are_not_duplicated_by_layout_defaults():
    out = compose_prompt("a bakery", safe_zone="bottom", negative="text, people")
    assert out.count("without") == 1
    # "text" is both a user term and a layout default; it must appear once.
    avoid = out.split("without", 1)[1]
    assert avoid.count(" text,") + avoid.count(" text.") <= 1
    assert "people" in avoid


def test_design_direction_is_opt_in():
    assert DESIGN_DIRECTION not in compose_prompt("a bakery")
    assert DESIGN_DIRECTION in compose_prompt("a bakery", design_direction=True)


def test_prompt_is_capped_and_ends_on_a_clause():
    long_topic = "a sweeping panoramic scene of something, " * 60
    out = compose_prompt(
        long_topic, style="luxury", safe_zone="bottom", design_direction=True
    )
    assert len(out) <= MAX_PROMPT_CHARS
    assert not out.endswith(",")


# ---- Fallback relevance ----------------------------------------------------

def test_photo_fallback_searches_the_topic_not_the_art_direction():
    """The keyword fallback is a photo search; art direction is not a subject.

    Searching the composed prompt returns abstract stock ("negative space",
    "soft light"), which is exactly the unrelated look being fixed.
    """
    composed = compose_prompt("artisan sourdough bakery", safe_zone="bottom", style="luxury")
    urls = build_image_candidates(composed, keyword_source="artisan sourdough bakery")
    flickr = next(u for u in urls if "loremflickr" in u)
    assert "sourdough" in flickr or "bakery" in flickr
    assert "negative" not in flickr


# ---- Slot budgets ----------------------------------------------------------

def test_layout_may_tighten_a_slot_budget():
    limits = _slot_limits(["headline"], {"headline": 40})
    assert limits["headline"] == 40


def test_layout_may_not_loosen_a_slot_budget():
    """The renderers are sized for the defaults; a bigger budget overflows."""
    limits = _slot_limits(["headline"], {"headline": 9999})
    assert limits["headline"] == TEMPLATE_SLOTS["headline"][1]


@pytest.mark.parametrize("bad", [{"headline": 0}, {"headline": -5}, {"headline": "x"}, {}, None])
def test_malformed_budgets_fall_back_to_the_default(bad):
    limits = _slot_limits(["headline"], bad)
    assert limits["headline"] == TEMPLATE_SLOTS["headline"][1]


# ---- Endpoint --------------------------------------------------------------

def test_endpoint_rejects_an_unknown_safe_zone():
    r = client.post(
        "/api/generate-images",
        json={"prompt": "a dental clinic", "safe_zone": "diagonal"},
    )
    assert r.status_code == 422
    assert "safe zone" in r.json()["detail"].lower()


def test_endpoint_briefs_the_image_from_the_post(monkeypatch):
    """The image model must receive a scene, not the post's marketing copy."""
    seen = {}

    async def fake_brief(topic, **kwargs):
        seen.update(kwargs, topic=topic)
        return "a dentist in a bright clinic, soft daylight, wide shot"

    monkeypatch.setattr("app.routes.posts.build_visual_prompt", fake_brief)

    r = client.post(
        "/api/generate-images",
        json={
            "prompt": "Book your check-up today and keep that smile healthy!",
            "safe_zone": "bottom",
            "template_label": "Instagram Post",
            "style": "healthcare",
            "headline": "Healthy smiles start here",
        },
    )
    assert r.status_code == 200
    prompt = r.json()["images"][0]["prompt"]
    assert "dentist" in prompt
    # The raw marketing line must not be what the image model is asked to draw.
    assert "Book your check-up today" not in prompt
    # Layout and style context reach the brief writer.
    assert seen["safe_zone"] == "bottom"
    assert seen["template_label"] == "Instagram Post"
    assert seen["headline"] == "Healthy smiles start here"
    assert seen["style_label"]


def test_analyze_off_uses_the_prompt_as_written(monkeypatch):
    """An explicit image prompt is the user's, and is not rewritten."""
    async def fail(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("analyze=False must not call the brief writer")

    monkeypatch.setattr("app.routes.posts.build_visual_prompt", fail)

    r = client.post(
        "/api/generate-images",
        json={"prompt": "a red bicycle against a white wall", "analyze": False},
    )
    assert r.status_code == 200
    assert "red bicycle" in r.json()["images"][0]["prompt"]


def test_a_failing_brief_writer_still_yields_an_image(monkeypatch):
    """Image generation needs no LLM; losing one must not cost the user a post."""
    def boom(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(ai_service, "get_provider", boom)

    r = client.post(
        "/api/generate-images",
        json={"prompt": "a cozy coffee shop", "safe_zone": "bottom"},
    )
    assert r.status_code == 200
    assert "coffee shop" in _prompt_of(r.json()["images"][0]["url"]).lower()


def test_layout_context_reaches_the_generated_url():
    r = client.post(
        "/api/generate-images",
        json={
            "prompt": "a cozy coffee shop",
            "safe_zone": "bottom",
            "analyze": False,
            "background_hint": "clear space in the lower third",
        },
    )
    assert r.status_code == 200
    # Punctuation is stripped for URL safety, so match on words.
    prompt = _prompt_of(r.json()["images"][0]["url"])
    assert "lower third" in prompt
    assert "negative space" in prompt


def test_long_posts_are_accepted():
    """A pasted article is a legitimate description of what to depict."""
    r = client.post(
        "/api/generate-images",
        json={"prompt": "Sustainable coffee sourcing. " * 60, "analyze": False},
    )
    assert r.status_code == 200
