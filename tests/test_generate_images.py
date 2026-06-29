"""Tests for the /api/generate-images composition endpoint.

These run fully offline: image URLs are built without any network call
(verify defaults to False) and the carousel outline falls back to
deterministic labels when no LLM provider key is configured.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.main import app
from app.services.image_service import ASPECT_RATIOS

# No `with` block -> lifespan (DB + scheduler) is not started; these endpoints
# are stateless and need neither.
client = TestClient(app)


def _dims(url: str) -> tuple[int, int]:
    q = parse_qs(urlparse(url).query)
    return int(q["width"][0]), int(q["height"][0])


def test_single_image_defaults_to_square():
    r = client.post("/api/generate-images", json={"prompt": "a cozy coffee shop"})
    assert r.status_code == 200
    body = r.json()
    assert body["carousel"] is False
    assert len(body["images"]) == 1
    assert body["aspect_ratio"] == "1:1"
    assert (body["width"], body["height"]) == (1080, 1080)
    assert _dims(body["images"][0]["url"]) == (1080, 1080)


def test_aspect_ratio_drives_dimensions():
    cases = {"9:16": (1080, 1920), "16:9": (1920, 1080), "2:3": (1080, 1620)}
    for ratio, expected in cases.items():
        r = client.post(
            "/api/generate-images",
            json={"prompt": "mountains at sunrise", "aspect_ratio": ratio},
        )
        assert r.status_code == 200, ratio
        body = r.json()
        assert (body["width"], body["height"]) == expected
        assert _dims(body["images"][0]["url"]) == expected


def test_carousel_returns_distinct_slides():
    r = client.post(
        "/api/generate-images",
        json={
            "prompt": "Benefits of AI in Healthcare",
            "carousel": True,
            "slides": 5,
            "aspect_ratio": "4:5",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["carousel"] is True
    urls = [img["url"] for img in body["images"]]
    assert len(urls) == 5
    # Distinct seed + distinct slide text => no duplicate images.
    assert len(set(urls)) == 5
    for url in urls:
        assert _dims(url) == (1080, 1350)


def test_invalid_aspect_ratio_is_rejected():
    r = client.post(
        "/api/generate-images",
        json={"prompt": "a dog", "aspect_ratio": "5:7"},
    )
    assert r.status_code == 422
    assert "aspect ratio" in r.json()["detail"].lower()


def test_carousel_slides_must_be_2_to_10():
    too_few = client.post(
        "/api/generate-images",
        json={"prompt": "a dog", "carousel": True, "slides": 1},
    )
    assert too_few.status_code == 422

    too_many = client.post(
        "/api/generate-images",
        json={"prompt": "a dog", "carousel": True, "slides": 11},
    )
    # 11 is out of the field bound (le=10) -> pydantic validation 422.
    assert too_many.status_code == 422


def test_empty_prompt_is_rejected():
    r = client.post("/api/generate-images", json={"prompt": ""})
    assert r.status_code == 422


def test_hd_quality_requests_enhancement():
    standard = client.post(
        "/api/generate-images", json={"prompt": "a city skyline", "quality": "standard"}
    ).json()
    hd = client.post(
        "/api/generate-images", json={"prompt": "a city skyline", "quality": "hd"}
    ).json()
    assert "enhance=true" not in standard["images"][0]["url"]
    assert "enhance=true" in hd["images"][0]["url"]


def test_invalid_quality_is_rejected():
    r = client.post(
        "/api/generate-images", json={"prompt": "a dog", "quality": "ultra"}
    )
    assert r.status_code == 422


def test_meta_exposes_image_options():
    body = client.get("/api/meta").json()
    assert set(body["aspect_ratios"]) == set(ASPECT_RATIOS)
    assert "realistic" in body["image_styles"]
    assert body["image_qualities"] == ["standard", "hd"]


def test_every_platform_has_a_caption_spec():
    """Guard: a new Platform without a PLATFORM_SPEC would crash caption gen."""
    from app.schemas.post import Platform
    from app.services.prompt_templates import PLATFORM_SPECS

    missing = [p.value for p in Platform if p not in PLATFORM_SPECS]
    assert not missing, f"Platforms missing a spec: {missing}"


def test_extract_file_reads_plain_text():
    from app.services.extract_service import extract_file

    out = extract_file("notes.txt", b"Eco-friendly coffee beans, small-batch roasted.")
    assert "coffee beans" in out["text"]
    assert out["source"] == "file"


def test_extract_file_reads_docx():
    import io
    import zipfile

    from app.services.extract_service import extract_file

    # Minimal DOCX: a zip whose word/document.xml holds <w:t> runs.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "word/document.xml",
            "<w:document><w:body><w:p><w:r><w:t>Hello</w:t></w:r>"
            "<w:r><w:t> world</w:t></w:r></w:p></w:body></w:document>",
        )
    out = extract_file("doc.docx", buf.getvalue())
    assert "Hello world" in out["text"]


def test_extract_file_rejects_unknown_type():
    from app.services.extract_service import ExtractError, extract_file

    try:
        extract_file("archive.zip", b"PK\x03\x04whatever")
    except ExtractError as exc:
        assert "Unsupported" in str(exc)
    else:
        raise AssertionError("expected ExtractError for unsupported type")


def test_extract_url_requires_a_url():
    r = client.post("/api/extract", json={"url": ""})
    assert r.status_code == 422  # min_length on the field


def test_assist_rejects_unknown_action():
    # Validation happens before any provider/network call.
    r = client.post("/api/assist", json={"text": "hello world", "action": "bogus"})
    assert r.status_code == 422


def test_assist_requires_text():
    r = client.post("/api/assist", json={"text": "", "action": "improve"})
    assert r.status_code == 422


def test_generate_article_requires_a_topic():
    r = client.post("/api/generate-article", json={"topic": ""})
    assert r.status_code == 422


def test_normalize_list_keeps_phrases():
    from app.services.ai_service import _normalize_list

    assert _normalize_list(["#AI in HR", " recruiting ", ""]) == ["AI in HR", "recruiting"]
    assert _normalize_list("ai, future of work") == ["ai", "future of work"]


def test_assist_action_set_is_complete():
    from app.services.ai_service import ASSIST_INSTRUCTIONS

    for action in ("improve", "rewrite", "shorten", "expand", "grammar",
                   "tone", "hashtags", "cta", "translate"):
        assert action in ASSIST_INSTRUCTIONS


def test_pinterest_is_available_end_to_end():
    # Exposed to the frontend...
    assert "pinterest" in client.get("/api/meta").json()["platforms"]
    # ...and usable for image composition at its recommended ratio.
    r = client.post(
        "/api/generate-images",
        json={"prompt": "DIY home office ideas", "platform": "pinterest",
              "aspect_ratio": "2:3"},
    )
    assert r.status_code == 200
    assert _dims(r.json()["images"][0]["url"]) == (1080, 1620)
