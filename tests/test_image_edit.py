"""Tests for the AI image-edit interpreter.

The model's output is untrusted input: it can name an operation the client
cannot execute, or a target that does not exist. These cover the sanitising
layer, which is what stops a bad completion becoming a silent no-op edit.
"""
from __future__ import annotations

import asyncio

import pytest

from app.services import ai_service
from app.services.ai_service import (
    IMAGE_EDIT_OPS,
    IMAGE_EDIT_TARGETS,
    REGENERATING_OPS,
    interpret_image_edit,
)

# Operations the client-side executor implements (frontend/src/lib/brandKit/
# editor/aiOps.js — the OPS object).
FRONTEND_OPS = {
    "move", "recolor", "resize", "spacing", "theme",
    "add_text", "add_cta", "remove", "restyle", "regenerate",
}


def _interpret(payload, **kwargs):
    """Run the interpreter against a canned provider completion."""

    class FakeProvider:
        name, model = "fake", "fake"

        async def complete(self, **_):
            return payload

    original = ai_service.get_provider
    ai_service.get_provider = lambda *_a, **_k: FakeProvider()
    try:
        return asyncio.run(interpret_image_edit("do the thing", layers=[], **kwargs))
    finally:
        ai_service.get_provider = original


def test_backend_and_frontend_agree_on_operations():
    """An op only one side knows about is dropped or silently ignored."""
    assert set(IMAGE_EDIT_OPS) == FRONTEND_OPS


def test_regenerating_ops_are_a_subset():
    assert REGENERATING_OPS <= set(IMAGE_EDIT_OPS)


def test_valid_operations_pass_through():
    out = _interpret(
        '{"operations": [{"op": "move", "target": "logo", "anchor": "top-right"}],'
        ' "explanation": "Moved the logo."}'
    )
    assert out["operations"] == [{"op": "move", "target": "logo", "anchor": "top-right"}]
    assert out["explanation"] == "Moved the logo."
    assert out["needs_regeneration"] is False


def test_unknown_operations_are_dropped():
    """An op the client cannot run would look like a failed edit."""
    out = _interpret(
        '{"operations": [{"op": "teleport", "target": "logo"},'
        ' {"op": "spacing", "delta": 0.02}], "explanation": ""}'
    )
    assert [o["op"] for o in out["operations"]] == ["spacing"]


def test_unknown_targets_fall_back_to_all():
    out = _interpret('{"operations": [{"op": "recolor", "target": "banana"}]}')
    assert out["operations"][0]["target"] == "all"


def test_regeneration_is_flagged():
    out = _interpret('{"operations": [{"op": "restyle", "style": "luxury"}]}')
    assert out["needs_regeneration"] is True
    assert out["operations"][0]["style"] == "luxury"


def test_layer_edits_do_not_trigger_regeneration():
    """The whole point: most edits must not discard the artwork."""
    out = _interpret(
        '{"operations": [{"op": "move", "target": "logo", "anchor": "top-right"},'
        ' {"op": "recolor", "target": "text", "palette": "brand"},'
        ' {"op": "add_cta", "text": "Book now"}]}'
    )
    assert out["needs_regeneration"] is False
    assert len(out["operations"]) == 3


def test_operations_are_capped():
    ops = ",".join('{"op": "spacing", "delta": 0.01}' for _ in range(10))
    out = _interpret('{"operations": [' + ops + ']}')
    assert len(out["operations"]) == 4


def test_malformed_output_degrades_to_no_operations():
    """A provider returning prose instead of JSON must not raise."""
    out = _interpret("I'm sorry, I can't do that.")
    assert out["operations"] == []
    assert out["needs_regeneration"] is False


@pytest.mark.parametrize("payload", ['{"operations": null}', '{}', '{"operations": [1, "x"]}'])
def test_junk_shapes_are_tolerated(payload):
    assert _interpret(payload)["operations"] == []


def test_all_documented_targets_are_lowercase_words():
    for t in IMAGE_EDIT_TARGETS:
        assert t.islower() and " " not in t
