"""Tests for Brand Kit prompt handling and the extended style presets.

Pure functions over prompt strings — no network, no database.
"""
from __future__ import annotations

import pytest

from app.services.image_service import (
    IMAGE_STYLES,
    brand_prompt_fragment,
    compose_prompt,
)
from app.schemas.business_profile import BusinessProfileUpdate

# Every style offered in the frontend dropdown (frontend/src/lib/constants.js).
FRONTEND_STYLES = [
    "corporate", "realistic", "illustration", "minimal", "3d", "cartoon",
    "watercolor", "luxury", "anime", "startup", "healthcare", "restaurant",
    "real_estate", "fitness", "ecommerce",
]


def test_every_frontend_style_has_a_backend_fragment():
    """A style the UI offers but the backend ignores fails silently.

    compose_prompt drops unknown keys, so a typo in either list would mean the
    user picks a style and simply gets no styling — with no error anywhere.
    """
    missing = [s for s in FRONTEND_STYLES if s not in IMAGE_STYLES]
    assert not missing, f"styles offered in the UI with no backend fragment: {missing}"


def test_style_is_applied_to_the_prompt():
    out = compose_prompt("a coffee shop", style="luxury")
    assert "a coffee shop" in out
    assert IMAGE_STYLES["luxury"] in out


def test_unknown_style_is_ignored_not_injected():
    out = compose_prompt("a coffee shop", style="not-a-real-style")
    assert out == "a coffee shop"


# ---- Brand fragment -------------------------------------------------------

def test_brand_fragment_always_suppresses_generated_text():
    """The overlay draws real text, so generated lettering is pure noise."""
    assert "no text" in brand_prompt_fragment([])


def test_brand_fragment_includes_valid_colours_only():
    out = brand_prompt_fragment(["#1f8a5b", "not-a-colour", "#6EE7B7"])
    assert "#1f8a5b" in out
    assert "#6EE7B7" in out
    assert "not-a-colour" not in out


def test_brand_fragment_reserves_space_when_asked():
    assert "bottom" in brand_prompt_fragment(["#1f8a5b"], reserve_space="bottom")


def test_branded_flag_gates_the_fragment():
    plain = compose_prompt("a bakery", branded=False, brand_colors=["#1f8a5b"])
    branded = compose_prompt("a bakery", branded=True, brand_colors=["#1f8a5b"])
    assert "no text" not in plain
    assert "no text" in branded
    assert "#1f8a5b" in branded


def test_negative_prompt_still_applies_alongside_branding():
    out = compose_prompt("a bakery", branded=True, negative="people, crowds")
    assert "without people, crowds" in out
    assert "no text" in out


# ---- Colour validation ----------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (["#1F8A5B"], ["#1f8a5b"]),      # normalised to lowercase
        (["1f8a5b"], ["#1f8a5b"]),        # missing hash is added
        (["#abc"], ["#aabbcc"]),          # shorthand expanded
        (["#12345"], []),                 # wrong length dropped
        (["#gggggg"], []),                # non-hex dropped
        ("#1f8a5b", ["#1f8a5b"]),         # bare string accepted
        ([], []),
    ],
)
def test_brand_colour_normalisation(raw, expected):
    """Colours land in SVG fill attributes, so malformed values are dropped."""
    assert BusinessProfileUpdate(brand_colors=raw).brand_colors == expected


def test_brand_colours_are_capped():
    many = [f"#{i:02x}0000" for i in range(20)]
    assert len(BusinessProfileUpdate(brand_colors=many).brand_colors) == 6


def test_brand_kit_fields_round_trip():
    profile = BusinessProfileUpdate(
        business_name="Croyten",
        logo_url="data:image/png;base64,iVBORw0KGgo=",
        brand_colors=["#1f8a5b"],
        phone=" +92 300 1234567 ",
        email="hello@example.com",
        address="  ",
    )
    assert profile.logo_url.startswith("data:image/png")
    assert profile.phone == "+92 300 1234567"   # trimmed
    assert profile.address is None              # whitespace-only -> None
