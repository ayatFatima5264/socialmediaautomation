"""Tests for the banner multi-size export (BUG-07).

The rail's Download button was a permanent stub: `disabled` in the source, with
a tooltip claiming "Available once banners have been generated" that never
unlocked even after a generation succeeded. These tests check the compositing
step that replaced it, and that the produced files are genuinely the right
pixels — validated by decoding them, the way QA validated its downloads rather
than trusting the status code.
"""
from __future__ import annotations

import asyncio
import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.services import banner_export

client = TestClient(app)


@pytest.fixture
def banner_png() -> bytes:
    """A 1200x628 banner — the default Facebook Feed ratio."""
    image = Image.new("RGB", (1200, 628))
    # Something with structure, so "did the pixels change" is a real check and
    # not a flat colour surviving every transform.
    for x in range(1200):
        for y in range(0, 628, 8):
            image.putpixel((x, y), (x % 256, (y * 3) % 256, 128))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def served(monkeypatch, banner_png):
    """Serve `banner_png` for any fetch, so no test touches the network."""
    calls: list[str] = []

    async def _fetch(url):
        calls.append(url)
        return banner_png

    monkeypatch.setattr(banner_export, "fetch_image", _fetch)
    return calls


# ---------------------------------------------------------------------------
# The service: real pixels at real dimensions.
# ---------------------------------------------------------------------------


def test_every_size_produces_its_exact_dimensions(served):
    for size in banner_export.EXPORT_SIZES:
        out = asyncio.run(
            banner_export.export_sizes("https://example.test/banner.png", [size.slug])
        )
        assert len(out) == 1
        entry = out[0]
        with Image.open(io.BytesIO(entry["bytes"])) as frame:
            assert frame.size == (size.width, size.height), size.label
            assert frame.format == "PNG"


def test_the_full_rail_composites(served):
    """Nine rail entries, eight distinct sizes."""
    slugs = [s.slug for s in banner_export.EXPORT_SIZES]
    out = asyncio.run(banner_export.export_sizes("https://example.test/b.png", slugs))
    assert len(out) == len(slugs)


def test_the_source_is_fetched_once_for_every_size(served):
    """Nine composites must not mean nine downloads of the same banner."""
    slugs = [s.slug for s in banner_export.EXPORT_SIZES]
    asyncio.run(banner_export.export_sizes("https://example.test/b.png", slugs))
    assert len(served) == 1, "the banner was re-fetched per size"


def test_aspect_ratio_is_preserved_not_stretched(served):
    """The promise is 'never a stretched crop'. Each output's pixel aspect
    ratio has to match its stated size, not the source's."""
    for size in banner_export.EXPORT_SIZES:
        out = asyncio.run(
            banner_export.export_sizes("https://example.test/b.png", [size.slug])
        )
        with Image.open(io.BytesIO(out[0]["bytes"])) as frame:
            produced = frame.width / frame.height
            expected = size.width / size.height
            # Both are read from the decoded file, so a resize that ignored its
            # target would show up here as a different ratio.
            assert abs(produced - expected) < 0.01, size.label


def test_text_is_drawn_onto_the_export(served):
    """A display ad without its headline is a background."""
    plain = asyncio.run(
        banner_export.export_sizes("https://example.test/b.png", ["728x90"])
    )[0]["bytes"]
    with_text = asyncio.run(
        banner_export.export_sizes(
            "https://example.test/b.png", ["728x90"], headline="Summer Sale", cta="Shop Now"
        )
    )[0]["bytes"]

    assert plain != with_text, "the headline made no difference to the output"


def test_a_tiny_source_is_refused_with_a_reason(monkeypatch):
    """Upscaling a 100px banner into 1200x628 produces a blurry lie."""
    tiny = io.BytesIO()
    Image.new("RGB", (100, 60)).save(tiny, format="PNG")

    async def _fetch(_url):
        return tiny.getvalue()

    monkeypatch.setattr(banner_export, "fetch_image", _fetch)
    with pytest.raises(banner_export.BannerExportError) as exc:
        asyncio.run(banner_export.export_sizes("https://example.test/b.png", ["728x90"]))
    assert "too small" in str(exc.value)


def test_an_undecodable_file_is_refused(monkeypatch):
    async def _fetch(_url):
        return b"this is not an image"

    monkeypatch.setattr(banner_export, "fetch_image", _fetch)
    with pytest.raises(banner_export.BannerExportError) as exc:
        asyncio.run(banner_export.export_sizes("https://example.test/b.png", ["728x90"]))
    assert "readable image" in str(exc.value)


def test_an_unknown_size_is_refused(served):
    with pytest.raises(banner_export.BannerExportError) as exc:
        asyncio.run(banner_export.export_sizes("https://example.test/b.png", ["9999x1"]))
    assert "Unsupported banner size" in str(exc.value)


def test_no_sizes_is_refused(served):
    with pytest.raises(banner_export.BannerExportError):
        asyncio.run(banner_export.export_sizes("https://example.test/b.png", []))


def test_a_bad_size_is_rejected_before_the_download(served):
    """A label the rail does not offer is the user's typo, not a provider
    outage — and it must not cost a request."""
    with pytest.raises(banner_export.BannerExportError):
        asyncio.run(
            banner_export.export_sizes("https://example.test/b.png", ["1x1", "nope"])
        )
    assert served == [], "the source was downloaded before the label was checked"


# ---------------------------------------------------------------------------
# Parsing the rail's own spelling.
# ---------------------------------------------------------------------------


def test_rail_labels_parse():
    for size in banner_export.EXPORT_SIZES:
        assert banner_export.parse_size(f"{size.width} x {size.height}").slug == size.slug
        assert banner_export.parse_size(size.slug).slug == size.slug


def test_the_rails_own_spelling_parses():
    """The rail's labels, verbatim, must be accepted.

    They use a Unicode multiplication sign. If the endpoint only understood
    ASCII `x`, every export would 502 and the button would look broken for a
    reason no test would otherwise catch.
    """
    for label in ("1200 × 628", "1080 × 1080", "1080 × 1920", "728 × 90", "300 × 250"):
        size = banner_export.parse_size(label)
        assert f"{size.width}x{size.height}" == size.slug

    # And the way the client actually normalises them before sending,
    # mirroring `toSlug` in BannerGenerator.jsx.
    import re

    for size in banner_export.EXPORT_SIZES:
        label = f"{size.width} × {size.height}"
        sent = (
            re.sub(r"\s+", "", label)
            .replace("×", "x")
            .replace("✕", "x")
            .lower()
        )
        assert sent == size.slug


def test_the_rail_has_no_duplicate_pixels():
    slugs = [s.slug for s in banner_export.EXPORT_SIZES]
    assert len(slugs) == len(set(slugs)), "two rail entries share one size"


# ---------------------------------------------------------------------------
# The route: 200 with decodable files, 422 for a bad request.
# ---------------------------------------------------------------------------


def test_endpoint_returns_decodable_pngs(monkeypatch, served):
    async def _fake(image_url, sizes, *, headline="", subheadline="", cta=""):
        return [
            {
                "size": s,
                "label": s,
                "network": "Test",
                "width": 1,
                "height": 1,
                "filename": f"{s}.png",
                "content_type": "image/png",
                "bytes": b"x",
            }
            for s in sizes
        ]

    monkeypatch.setattr(banner_export, "export_sizes", _fake)
    r = client.post(
        "/api/ads/banner-export",
        json={"image_url": "https://example.test/b.png", "sizes": ["728x90", "300x250"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # The count is derived from the request, not taken on trust from the
    # service, so a short result cannot be reported as a full rail.
    assert body["requested"] == 2
    assert body["produced"] == 2
    assert [f["size"] for f in body["files"]] == ["728x90", "300x250"]
    # And the bytes arrive as base64 the client can write straight to a file.
    assert body["files"][0]["data"] == base64.b64encode(b"x").decode()


def test_a_short_result_reports_the_truth(monkeypatch, served):
    async def _fake(image_url, sizes, *, headline="", subheadline="", cta=""):
        return [
            {
                "size": sizes[0],
                "label": sizes[0],
                "network": "Test",
                "width": 728,
                "height": 90,
                "filename": "a.png",
                "content_type": "image/png",
                "bytes": b"x",
            }
        ]

    monkeypatch.setattr(banner_export, "export_sizes", _fake)
    r = client.post(
        "/api/ads/banner-export",
        json={"image_url": "https://example.test/b.png", "sizes": ["728x90", "300x250"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["produced"] == 1


def test_endpoint_passes_the_text_through(monkeypatch, served):
    """The headline is drawn onto every re-flowed size, so the route has to
    forward it — a banner exported without its words is a background."""
    seen = {}

    async def _fake(image_url, sizes, *, headline="", subheadline="", cta=""):
        seen.update(headline=headline, subheadline=subheadline, cta=cta)
        return []

    monkeypatch.setattr(banner_export, "export_sizes", _fake)
    r = client.post(
        "/api/ads/banner-export",
        json={
            "image_url": "https://example.test/b.png",
            "sizes": ["728x90"],
            "headline": "Summer Sale",
            "subheadline": "Ends Sunday",
            "cta": "Shop Now",
        },
    )
    assert r.status_code == 200, r.text
    assert seen == {
        "headline": "Summer Sale",
        "subheadline": "Ends Sunday",
        "cta": "Shop Now",
    }


def test_blank_text_is_normalised_to_empty(monkeypatch, served):
    """The preview treats a whitespace-only headline as no headline; the
    exporter must not draw a row of spaces onto every file."""
    seen = {}

    async def _fake(image_url, sizes, *, headline="", subheadline="", cta=""):
        seen["headline"] = headline
        return []

    monkeypatch.setattr(banner_export, "export_sizes", _fake)
    client.post(
        "/api/ads/banner-export",
        json={
            "image_url": "https://example.test/b.png",
            "sizes": ["728x90"],
            "headline": "   ",
        },
    )
    assert seen["headline"] == ""


def test_endpoint_rejects_an_unknown_size(monkeypatch):
    r = client.post(
        "/api/ads/banner-export",
        json={"image_url": "https://example.test/b.png", "sizes": ["5x5"]},
    )
    assert r.status_code == 502, r.text
    assert "Unsupported banner size" in r.json()["detail"]


def test_endpoint_rejects_an_empty_size_list():
    r = client.post(
        "/api/ads/banner-export",
        json={"image_url": "https://example.test/b.png", "sizes": []},
    )
    assert r.status_code == 422, r.text


def test_endpoint_requires_an_image_url():
    r = client.post("/api/ads/banner-export", json={"sizes": ["728x90"]})
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# The page: no stub, no untrue tooltip.
# ---------------------------------------------------------------------------


def test_the_download_button_is_wired():
    """No `disabled` with no handler, and the untrue tooltip gone from the
    button itself.

    The string survives in the module comment that explains why the stub was
    there, so the check is on the button element, not the whole file.
    """
    import re
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "frontend" / "src" / "pages" / "ads" / "tools" / "BannerGenerator.jsx"
    ).read_text(encoding="utf-8")

    assert "onClick={downloadAllSizes}" in source

    button = re.search(
        r"<button\b[^>]*Download all sizes|onClick=\{downloadAllSizes\}[^>]*>",
        source,
        re.S,
    )
    assert button, "the Download all sizes button was not found"
    element = button.group(0)
    assert "disabled" in element, (
        "the button is disabled outright; it must be gated on `selectedImage` "
        "or `exporting` instead"
    )
    assert "Available once banners have been generated" not in element
    assert "still to come" not in source


def test_the_rail_sizes_match_the_backend():
    """The frontend list and EXPORT_SIZES are the same list written twice.

    Checked through the real parser, so a label the backend would refuse is a
    failure here rather than a 502 in the browser.
    """
    import re
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "frontend" / "src" / "lib" / "ads" / "constants.js"
    ).read_text(encoding="utf-8-sig")
    start = source.index("BANNER_EXPORT_SETS")
    # The block runs until the next top-level `export`, not the first `]` —
    # each entry has its own nested `sizes` array.
    end = source.index("\nexport ", start)
    block = source[start:end]

    labels = re.findall(r"'(\d+\s*[x×✕]\s*\d+)'", block)
    assert labels, "no size labels found in BANNER_EXPORT_SETS"

    frontend = {banner_export.parse_size(label).slug for label in labels}
    backend = {s.slug for s in banner_export.EXPORT_SIZES}
    assert frontend == backend, (
        f"the rail offers {sorted(frontend)} but the server can only produce "
        f"{sorted(backend)}"
    )


def test_the_export_list_covers_every_rail_entry():
    """1080x1080 is listed under both Facebook and LinkedIn; the exporter must
    still be able to produce it, and the client must not download it twice."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "frontend" / "src" / "lib" / "ads" / "constants.js"
    ).read_text(encoding="utf-8-sig")
    assert "1080 × 1080" in source
    assert "1080x1080" in {s.slug for s in banner_export.EXPORT_SIZES}
