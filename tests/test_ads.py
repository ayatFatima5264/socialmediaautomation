"""Tests for the AI Ads Studio endpoints.

Mostly offline: `/api/ads/creative` is exercised with `generate_with_fallback`
replaced, so nothing here reaches an image host or an LLM. The point of the
creative tests is the *limit* rather than the pixels — see
`test_every_carousel_slide_count_is_accepted`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.ads import MAX_CREATIVE_IMAGES, CreativeRequest

# No `with` block -> lifespan (DB + scheduler) is not started. `/ads/creative`
# takes an optional user, so it answers without one.
client = TestClient(app)

REPO_ROOT = Path(__file__).resolve().parents[1]
CONSTANTS_JS = REPO_ROOT / "frontend" / "src" / "lib" / "ads" / "constants.js"


def _frontend_carousel_counts() -> list[int]:
    """The slide counts the Carousel Ads dropdown actually offers.

    Read out of the frontend source rather than restated here, so this test
    fails when the dropdown and the API disagree instead of quietly testing two
    copies of a number that happens to match today.
    """
    source = CONSTANTS_JS.read_text(encoding="utf-8")
    match = re.search(
        r"export const CAROUSEL_SLIDE_COUNTS\s*=\s*\[([^\]]*)\]", source
    )
    assert match, "CAROUSEL_SLIDE_COUNTS not found in frontend/src/lib/ads/constants.js"
    return [int(n) for n in re.findall(r"\d+", match.group(1))]


# ---------------------------------------------------------------------------
# BUG-01 — the Carousel Ads slide count is accepted by the API.
# ---------------------------------------------------------------------------


def test_backend_limit_matches_documented_ceiling():
    # Ten is the Instagram/Facebook carousel ceiling; the schema constant is what
    # the endpoint validates against, so it is the number that has to be right.
    assert MAX_CREATIVE_IMAGES == 10


def test_every_carousel_slide_count_is_accepted():
    """Every option in the dropdown generates. The bug was 5, 6, 7, 8 and 10
    all returning 422 because the schema capped `count` at 4 — including the
    tool's own default of 5."""
    offered = _frontend_carousel_counts()
    assert offered, "the dropdown offers no slide counts"

    for count in offered:
        request = CreativeRequest(subject="Organic skincare serum", count=count)
        # Pydantic is what turns this into a 422, so a failure here is the bug.
        assert request.count == count, count
        assert 1 <= request.count <= MAX_CREATIVE_IMAGES, count


def test_frontend_slide_counts_are_all_within_the_backend_limit():
    for count in _frontend_carousel_counts():
        assert 1 <= count <= MAX_CREATIVE_IMAGES, (
            f"the UI offers {count} slides but the API refuses anything above "
            f"{MAX_CREATIVE_IMAGES}"
        )


def test_frontend_default_slide_count_is_valid():
    """CarouselAds.jsx opens with `useState(5)`. The default has to survive the
    same validation the dropdown does, or the tool fails before the user
    touches anything."""
    source = (REPO_ROOT / "frontend" / "src" / "pages" / "ads" / "tools" / "CarouselAds.jsx").read_text(
        encoding="utf-8"
    )
    match = re.search(r"useState\((\d+)\)\s*//?\s*slides", source) or re.search(
        r"const \[slides, setSlides\] = useState\((\d+)\)", source
    )
    assert match, "could not find the Carousel Ads default slide count"
    default = int(match.group(1))
    assert default in _frontend_carousel_counts()
    assert CreativeRequest(subject="Organic skincare serum", count=default).count == default


def test_count_above_the_ceiling_is_rejected():
    with pytest.raises(ValueError):
        CreativeRequest(subject="Organic skincare serum", count=MAX_CREATIVE_IMAGES + 1)
    with pytest.raises(ValueError):
        CreativeRequest(subject="Organic skincare serum", count=0)


def test_creative_endpoint_accepts_the_default_slide_count(monkeypatch):
    """End to end through the route: a five-slide carousel returns five images
    and a 200, not a 422."""
    calls: list[int] = []

    async def fake_generate_with_fallback(prompt, **kwargs):
        seed = kwargs.get("seed", 0)
        calls.append(seed)
        return f"https://example.test/slide-{seed}.png", "pollinations-test"

    monkeypatch.setattr(
        "app.services.ads_service.generate_with_fallback", fake_generate_with_fallback
    )

    response = client.post(
        "/api/ads/creative",
        json={
            "subject": "A 5-slide carousel running: Feature -> Benefit -> Close-up",
            "aspect_ratio": "4:5",
            "count": 5,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["images"]) == 5
    assert len(body["sources"]) == 5
    # Distinct seed per slide, so a deck is not the same image five times.
    assert sorted(calls) == [0, 1, 2, 3, 4]


@pytest.mark.parametrize("count", [3, 4, 5, 6, 7, 8, 10])
def test_route_accepts_each_offered_count(monkeypatch, count):
    async def fake_generate_with_fallback(prompt, **kwargs):
        seed = kwargs.get("seed", 0)
        return f"https://example.test/slide-{seed}.png", "pollinations-test"

    monkeypatch.setattr(
        "app.services.ads_service.generate_with_fallback", fake_generate_with_fallback
    )

    response = client.post(
        "/api/ads/creative",
        json={"subject": "Five reasons to switch", "count": count},
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["images"]) == count


def test_route_rejects_more_than_the_ceiling():
    response = client.post(
        "/api/ads/creative",
        json={"subject": "Too many slides", "count": MAX_CREATIVE_IMAGES + 1},
    )
    assert response.status_code == 422, response.text
