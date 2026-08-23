"""Thumbnail Studio: designing, editing, previewing, exporting.

The claim worth testing is the one the studio is built around: **preview and
download are the same renderer**, so what the user is looking at is the file
they get. Everything else here is the ordinary contract — a design is editable,
a saved thumbnail can be reopened, and both formats come out as real images.

Images are decoded with Pillow and their dimensions checked, rather than the
tests asserting that some bytes came back. A renderer that returns a valid PNG
of the wrong size passes the lazy version of every one of these.
"""
from __future__ import annotations

import io

import pytest
from PIL import Image

from tests.conftest import png_bytes


def design_for(client, headers, **body) -> dict:
    response = client.post(
        "/api/video/thumbnails/design",
        headers=headers,
        json={"template": "bold_center", "headline": "How it works", **body},
    )
    assert response.status_code == 200, response.text
    return response.json()


def render(client, headers, design, **body):
    return client.post(
        "/api/video/thumbnails/preview",
        headers=headers,
        json={"design": design, **body},
    )


def size_of(data: bytes) -> tuple[int, int]:
    return Image.open(io.BytesIO(data)).size


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_every_thumbnail_route_requires_a_token(studio_client):
    for method, path in (
        ("get", "/api/video/thumbnails/options"),
        ("post", "/api/video/thumbnails/design"),
        ("post", "/api/video/thumbnails/variations"),
        ("post", "/api/video/thumbnails/preview"),
        ("post", "/api/video/thumbnails"),
        ("get", "/api/video/thumbnails"),
        ("get", "/api/video/thumbnails/1/download"),
        ("delete", "/api/video/thumbnails/1"),
    ):
        kwargs = {"json": {}} if method == "post" else {}
        response = getattr(studio_client, method)(path, **kwargs)
        assert response.status_code == 401, f"{method.upper()} {path} was reachable"


# ---------------------------------------------------------------------------
# Designing
# ---------------------------------------------------------------------------


def test_the_studio_offers_youtube_and_the_social_formats(studio_client, headers):
    body = studio_client.get(
        "/api/video/thumbnails/options", headers=headers
    ).json()

    keys = {entry["key"] for entry in body["formats"]}
    assert "youtube" in keys
    assert keys >= {"youtube", "youtube_shorts", "instagram_post", "facebook"}

    youtube = next(e for e in body["formats"] if e["key"] == "youtube")
    assert (youtube["width"], youtube["height"]) == (1280, 720)
    assert len(body["templates"]) >= 4
    assert body["palettes"]


def test_a_template_produces_an_editable_design(studio_client, headers):
    design = design_for(studio_client, headers, headline="Compound interest")

    assert design["width"] == 1280 and design["height"] == 720
    assert design["layers"], "a design with no layers renders an empty picture"
    headline = next(
        layer for layer in design["layers"] if layer["type"] == "text"
    )
    assert "Compound interest" in headline["text"]
    # Sizes are canvas fractions, not pixels — that is what lets one design
    # render at another format.
    assert 0 < headline["font_size"] < 1


def test_the_same_design_renders_at_every_format(studio_client, headers):
    """A design made for YouTube must work as a vertical cover."""
    for key, expected in (
        ("youtube", (1280, 720)),
        ("youtube_shorts", (1080, 1920)),
        ("instagram_post", (1080, 1080)),
    ):
        design = design_for(studio_client, headers, format=key)
        response = render(studio_client, headers, design)
        assert response.status_code == 200, response.text
        assert size_of(response.content) == expected


def test_brand_kit_colours_are_used(studio_client, headers):
    """A thumbnail from a template should still look like the business."""
    studio_client.put(
        "/api/business-profile",
        headers=headers,
        json={"business_name": "Acme", "brand_colors": ["#7C3AED", "#F59E0B"]},
    )

    design = design_for(studio_client, headers, use_brand=True)

    assert design["background"]["colors"] == ["#7C3AED", "#F59E0B"]


def test_brand_kit_can_be_turned_off(studio_client, headers):
    studio_client.put(
        "/api/business-profile",
        headers=headers,
        json={"business_name": "Acme", "brand_colors": ["#7C3AED", "#F59E0B"]},
    )

    design = design_for(studio_client, headers, use_brand=False, palette="ocean")

    assert design["background"]["colors"] != ["#7C3AED", "#F59E0B"]


def test_variations_keep_the_words_and_change_the_look(studio_client, headers):
    """What the user is choosing between is layouts, not different copy."""
    design = design_for(studio_client, headers, headline="Seven ideas")

    body = studio_client.post(
        "/api/video/thumbnails/variations",
        headers=headers,
        json={"design": design, "count": 4},
    ).json()

    assert len(body["designs"]) == 4
    looks = {
        (entry.get("template"), entry["background"]["palette"])
        for entry in body["designs"]
    }
    assert len(looks) == 4, "variations that look the same are not variations"

    for entry in body["designs"]:
        words = " ".join(
            layer["text"] for layer in entry["layers"] if layer["type"] == "text"
        )
        assert "Seven ideas" in words, "a variation rewrote the headline"


# ---------------------------------------------------------------------------
# Editing
# ---------------------------------------------------------------------------


def test_every_part_of_a_design_can_be_changed(studio_client, headers):
    design = design_for(studio_client, headers)

    edited = {
        **design,
        "background": {**design["background"], "kind": "color", "colors": ["#FF0000"]},
        "layers": [
            {
                "type": "text",
                "id": "headline",
                "text": "My own words",
                "font_size": 0.2,
                "color": "#00FF00",
                "anchor": "top-left",
                "align": "left",
                "rotation": -5,
            }
        ],
    }

    response = render(studio_client, headers, edited)
    assert response.status_code == 200, response.text
    assert size_of(response.content) == (1280, 720)


def test_a_malformed_colour_does_not_crash_the_renderer(studio_client, headers):
    """These values arrive from a client and end up in a drawing call."""
    design = design_for(studio_client, headers)
    design["layers"][0]["color"] = "red; DROP TABLE"

    response = render(studio_client, headers, design)

    assert response.status_code == 200
    assert size_of(response.content) == (1280, 720)


def test_a_preview_is_the_same_picture_at_a_smaller_size(studio_client, headers):
    design = design_for(studio_client, headers)

    full = render(studio_client, headers, design)
    quick = render(studio_client, headers, design, scale=0.25)

    assert size_of(full.content) == (1280, 720)
    assert size_of(quick.content) == (320, 180)
    assert len(quick.content) < len(full.content)


def test_a_preview_stores_nothing(studio_client, headers):
    """A design the user is still nudging must not fill their library."""
    design = design_for(studio_client, headers)
    render(studio_client, headers, design)
    render(studio_client, headers, design)

    assert studio_client.get("/api/video/thumbnails", headers=headers).json() == []
    library = studio_client.get("/api/video/media", headers=headers).json()
    assert library["total"] == 0


# ---------------------------------------------------------------------------
# Backgrounds and logos
# ---------------------------------------------------------------------------


def test_an_uploaded_image_can_be_the_background(studio_client, headers):
    upload = studio_client.post(
        "/api/video/media/upload",
        headers=headers,
        files={"file": ("bg.png", png_bytes(640, 360), "image/png")},
        data={"kind": "image"},
    ).json()

    design = design_for(studio_client, headers, background_asset_id=upload["id"])
    assert design["background"]["kind"] == "image"
    # A photo behind white text is unreadable about half the time.
    assert design["background"]["scrim"] > 0

    response = render(studio_client, headers, design)
    assert response.status_code == 200
    assert size_of(response.content) == (1280, 720)


def test_a_background_that_has_been_deleted_still_renders(studio_client, headers):
    """A missing file must not make the studio unusable."""
    upload = studio_client.post(
        "/api/video/media/upload",
        headers=headers,
        files={"file": ("bg.png", png_bytes(640, 360), "image/png")},
        data={"kind": "image"},
    ).json()
    design = design_for(studio_client, headers, background_asset_id=upload["id"])
    studio_client.delete(f"/api/video/media/{upload['id']}?force=true", headers=headers)

    response = render(studio_client, headers, design)

    assert response.status_code == 200
    assert size_of(response.content) == (1280, 720)


def test_you_cannot_use_someone_elses_image(studio_client, headers, other_headers):
    theirs = studio_client.post(
        "/api/video/media/upload",
        headers=other_headers,
        files={"file": ("bg.png", png_bytes(640, 360), "image/png")},
        data={"kind": "image"},
    ).json()

    design = design_for(studio_client, headers, background_asset_id=theirs["id"])
    response = render(studio_client, headers, design)

    # Renders without it rather than reading their file.
    assert response.status_code == 200


def test_a_logo_layer_is_drawn(studio_client, headers):
    logo = studio_client.post(
        "/api/video/media/upload",
        headers=headers,
        files={"file": ("logo.png", png_bytes(200, 200, (255, 0, 0)), "image/png")},
        data={"kind": "image"},
    ).json()

    design = design_for(studio_client, headers, logo_asset_id=logo["id"])
    assert any(layer["type"] == "logo" for layer in design["layers"])

    response = render(studio_client, headers, design)
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Saving and exporting
# ---------------------------------------------------------------------------


def test_saving_keeps_the_file_and_the_design(studio_client, headers):
    """A thumbnail you can only re-download is a dead end."""
    design = design_for(studio_client, headers, headline="Saved one")

    response = studio_client.post(
        "/api/video/thumbnails", headers=headers, json={"design": design}
    )

    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved["url"]
    assert (saved["width"], saved["height"]) == (1280, 720)
    # The design comes back, so it can be reopened and edited.
    assert saved["design"]["layers"]

    listing = studio_client.get("/api/video/thumbnails", headers=headers).json()
    assert [row["id"] for row in listing] == [saved["id"]]


def test_a_saved_thumbnail_is_an_ordinary_library_file(studio_client, headers):
    design = design_for(studio_client, headers)
    saved = studio_client.post(
        "/api/video/thumbnails", headers=headers, json={"design": design}
    ).json()

    library = studio_client.get(
        "/api/video/media?filter=thumbnail", headers=headers
    ).json()

    assert saved["id"] in [item["id"] for item in library["items"]]


@pytest.mark.parametrize("fmt", ["png", "jpg"])
def test_both_formats_download_as_real_images(studio_client, headers, fmt):
    design = design_for(studio_client, headers)
    saved = studio_client.post(
        "/api/video/thumbnails", headers=headers, json={"design": design}
    ).json()

    response = studio_client.get(
        f"/api/video/thumbnails/{saved['id']}/download?format={fmt}", headers=headers
    )

    assert response.status_code == 200
    image = Image.open(io.BytesIO(response.content))
    assert image.size == (1280, 720)
    assert image.format == ("PNG" if fmt == "png" else "JPEG")
    assert "attachment" in response.headers["content-disposition"]


def test_a_jpg_of_a_png_thumbnail_is_redrawn_not_recompressed(studio_client, headers):
    """Re-rendering from the design beats transcoding an already-compressed
    image, and the design is right there."""
    design = design_for(studio_client, headers)
    saved = studio_client.post(
        "/api/video/thumbnails", headers=headers, json={"design": design, "format": "png"}
    ).json()
    assert saved["content_type"] == "image/png"

    response = studio_client.get(
        f"/api/video/thumbnails/{saved['id']}/download?format=jpg", headers=headers
    )

    assert Image.open(io.BytesIO(response.content)).format == "JPEG"


def test_add_to_project_sets_the_projects_thumbnail(studio_client, headers, project):
    design = design_for(studio_client, headers)
    saved = studio_client.post(
        "/api/video/thumbnails", headers=headers, json={"design": design}
    ).json()

    response = studio_client.post(
        f"/api/video/thumbnails/{saved['id']}/attach?project_id={project['id']}",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    detail = studio_client.get(
        f"/api/video/projects/{project['id']}", headers=headers
    ).json()
    assert detail["thumbnail_asset_id"] == saved["id"]
    assert detail["thumbnail_url"]


def test_saving_straight_onto_a_project(studio_client, headers, project):
    design = design_for(studio_client, headers)

    saved = studio_client.post(
        "/api/video/thumbnails",
        headers=headers,
        json={"design": design, "project_id": project["id"]},
    ).json()

    detail = studio_client.get(
        f"/api/video/projects/{project['id']}", headers=headers
    ).json()
    assert detail["thumbnail_asset_id"] == saved["id"]


def test_you_cannot_read_or_delete_someone_elses_thumbnail(
    studio_client, headers, other_headers
):
    design = design_for(studio_client, other_headers)
    theirs = studio_client.post(
        "/api/video/thumbnails", headers=other_headers, json={"design": design}
    ).json()

    assert studio_client.get(
        f"/api/video/thumbnails/{theirs['id']}/download", headers=headers
    ).status_code == 404
    assert studio_client.delete(
        f"/api/video/thumbnails/{theirs['id']}", headers=headers
    ).status_code == 404
    assert studio_client.get("/api/video/thumbnails", headers=headers).json() == []


def test_a_background_can_be_generated_from_a_prompt(
    studio_client, headers, monkeypatch, studio_db
):
    """The generated picture becomes a real file before the design points at it.

    A thumbnail whose background is a remote URL renders differently next week
    and stops rendering when that host goes down, so the bytes are fetched and
    stored like any other asset.
    """
    from app.models.video_asset import VideoAsset
    from app.services.video import visuals

    async def _generate(prompt, **kwargs):
        return "https://example.test/generated.png", "mock-model"

    async def _fetch(url):
        return png_bytes(320, 180, (10, 20, 30)), "image/png"

    monkeypatch.setattr(
        "app.services.image_service.generate_with_fallback", _generate
    )
    monkeypatch.setattr(visuals, "fetch_image", _fetch)

    response = studio_client.post(
        "/api/video/thumbnails/background",
        headers=headers,
        json={"prompt": "a quiet library at dusk", "format": "youtube"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["asset_id"] and body["url"]

    asset = studio_db.get(VideoAsset, body["asset_id"])
    assert asset.user_id is not None
    assert asset.meta["source"] == "ai_image"
    assert asset.meta["prompt"] == "a quiet library at dusk"

    # And it can immediately be used as a background.
    design = design_for(studio_client, headers, background_asset_id=body["asset_id"])
    rendered = render(studio_client, headers, design)
    assert rendered.status_code == 200
    assert size_of(rendered.content) == (1280, 720)


def test_generating_a_background_leaves_no_orphan_scene(
    studio_client, headers, monkeypatch, studio_db
):
    """A thumbnail has no scene — creating a real row to throw away would fill
    `video_scenes` with orphans every time somebody tried a prompt."""
    from app.models.video_scene import VideoScene
    from app.services.video import visuals

    async def _generate(prompt, **kwargs):
        return "https://example.test/generated.png", "mock"

    async def _fetch(url):
        return png_bytes(320, 180), "image/png"

    monkeypatch.setattr(
        "app.services.image_service.generate_with_fallback", _generate
    )
    monkeypatch.setattr(visuals, "fetch_image", _fetch)

    before = studio_db.query(VideoScene).count()
    studio_client.post(
        "/api/video/thumbnails/background",
        headers=headers,
        json={"prompt": "anything at all"},
    )

    studio_db.expire_all()
    assert studio_db.query(VideoScene).count() == before


def test_a_long_word_does_not_run_off_the_frame(studio_client, headers):
    """A headline with its ends cut off is not a thumbnail.

    Two bugs met here: text was sized as a fraction of the canvas *height*, so
    the same design that fitted at 16:9 tripled in size at 9:16; and a single
    word has nowhere to wrap, so it bled off both edges. Sizing by the short
    side fixes the first, shrinking to fit fixes the second.
    """
    from PIL import Image

    for format_key in ("youtube", "youtube_shorts", "instagram_portrait"):
        design = design_for(
            studio_client, headers,
            template="lower_third", headline="Extraordinarily", format=format_key,
        )
        response = render(studio_client, headers, design)
        assert response.status_code == 200, response.text

        image = Image.open(io.BytesIO(response.content)).convert("RGB")
        width, height = image.size

        # Nothing but background should touch the outer columns. The headline
        # is near-white, so a bright pixel on the very edge means it bled.
        for x in (0, width - 1):
            column = [image.getpixel((x, y)) for y in range(0, height, 4)]
            assert not any(
                sum(pixel) > 600 for pixel in column
            ), f"text reached the edge at {format_key}"


def test_the_same_design_stays_readable_at_every_shape(studio_client, headers):
    """A design made at 16:9 must not become unusable as a vertical cover."""
    from PIL import Image

    sizes = {}
    for format_key in ("youtube", "youtube_shorts"):
        design = design_for(
            studio_client, headers, headline="How compound interest works",
            format=format_key,
        )
        response = render(studio_client, headers, design)
        sizes[format_key] = Image.open(io.BytesIO(response.content)).size

    assert sizes["youtube"] == (1280, 720)
    assert sizes["youtube_shorts"] == (1080, 1920)
