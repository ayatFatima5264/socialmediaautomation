"""Tests for the Phase 2 template content pipeline.

Covers the parts that fail silently if they drift: slot budgets, the
layout-aware background hint, and the frontend/backend template contract.
"""
from __future__ import annotations

import pytest

from app.services.ai_service import TEMPLATE_SLOTS
from app.services.image_service import compose_prompt

# Slots declared by the frontend templates (frontend/src/lib/brandKit/
# contentTemplates.js — the SLOTS object).
FRONTEND_SLOTS = {"headline", "subtext", "cta", "badge", "price"}


def test_every_frontend_slot_has_a_backend_budget():
    """A slot the layout renders but the backend does not know about is dropped.

    generate_template_content filters to known slots, so a mismatch means the
    template renders an empty box with no error anywhere.
    """
    missing = FRONTEND_SLOTS - set(TEMPLATE_SLOTS)
    assert not missing, f"layout slots with no backend budget: {missing}"


def test_slot_budgets_are_sane():
    """Budgets exist because the layout renders each slot at a fixed size."""
    for name, (description, limit) in TEMPLATE_SLOTS.items():
        assert description, f"{name} has no guidance for the model"
        assert 0 < limit <= 200, f"{name} budget {limit} is implausible"

    # A CTA is a button label; a headline is a statement. If these ever invert,
    # the layout's emphasis is wrong.
    assert TEMPLATE_SLOTS["cta"][1] < TEMPLATE_SLOTS["headline"][1]
    assert TEMPLATE_SLOTS["badge"][1] < TEMPLATE_SLOTS["headline"][1]


# ---- Background hint ------------------------------------------------------

def test_background_hint_reaches_the_prompt():
    out = compose_prompt("a bakery", background_hint="clear space in the lower third")
    assert "clear space in the lower third" in out
    assert "a bakery" in out


def test_background_hint_is_optional():
    assert compose_prompt("a bakery") == "a bakery"
    assert compose_prompt("a bakery", background_hint=None) == "a bakery"


def test_background_hint_composes_with_style_and_branding():
    """All three modifiers must coexist — a template, a style, and branding."""
    out = compose_prompt(
        "a bakery",
        style="luxury",
        background_hint="clear space in the lower half",
        branded=True,
        brand_colors=["#1f8a5b"],
    )
    assert "a bakery" in out
    assert "luxury editorial aesthetic" in out
    assert "clear space in the lower half" in out
    assert "#1f8a5b" in out
    assert "no text" in out


@pytest.mark.parametrize("hint", ["", "   ", None])
def test_blank_hints_add_nothing(hint):
    assert compose_prompt("a bakery", background_hint=hint) == "a bakery"


# ---- Endpoint contract ----------------------------------------------------

def test_unknown_slots_are_ignored(monkeypatch):
    """A typo in a slot name must not crash generation."""
    import asyncio

    from app.services import ai_service

    async def run():
        return await ai_service.generate_template_content(
            "coffee", slots=["not_a_slot"], template_label="Quote"
        )

    # No known slots -> returns early without ever calling a provider, so this
    # passes with no AI credentials configured.
    assert asyncio.run(run()) == {}
