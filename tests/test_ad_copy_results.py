"""Tests for the frontend decision helpers the ad tools share.

The frontend has no test runner, so these read the ESM module and execute it
with Node. The logic under test is what the page does with a response, not what
it looks like on screen, which is exactly the part a browser check cannot pin
down: a rejected provider call and a fulfilled-but-empty one are the same value
once the reasons are thrown away (BUG-04).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
COPY_RESULTS_JS = REPO_ROOT / "frontend" / "src" / "lib" / "ads" / "copyResults.js"
AD_COPY_JSX = REPO_ROOT / "frontend" / "src" / "pages" / "ads" / "tools" / "AdCopy.jsx"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="Node is needed to run the ESM frontend modules."
)


def _collect(settled, platforms, label_for: dict[str, str] | None = None):
    """Run `collectCopyResults` in Node and return its result as Python."""
    labels = json.dumps(label_for or {})
    # str.format cannot be used here: the script is JavaScript and its own braces
    # would be read as placeholders.
    script = (
        "import { collectCopyResults } from __MODULE__;"
        "const settled = __SETTLED__;"
        "const platforms = __PLATFORMS__;"
        "const labels = __LABELS__;"
        "process.stdout.write(JSON.stringify(collectCopyResults("
        "  settled, platforms, (p) => labels[p] || p"
        ")));"
    )
    script = (
        script.replace("__MODULE__", json.dumps(COPY_RESULTS_JS.as_uri()))
        .replace("__SETTLED__", json.dumps(settled))
        .replace("__PLATFORMS__", json.dumps(platforms))
        .replace("__LABELS__", labels)
    )
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return json.loads(result.stdout)


def _fulfilled(*variants_per_platform):
    return [{"status": "fulfilled", "value": {"variants": v}} for v in variants_per_platform]


def _rejected(message):
    return {"status": "rejected", "reason": {"message": message}}


# ---------------------------------------------------------------------------
# BUG-04 — a provider outage is reported as the provider's own error.
# ---------------------------------------------------------------------------


def test_total_outage_surfaces_the_provider_error():
    """Every platform failing reported 'no usable copy' regardless of why. The
    server's 502 detail is now what the user sees."""
    settled = [_rejected("Provider chain error: groq 404 model_not_found")]
    result = _collect(settled, ["facebook"])

    assert result["empty"] is True
    assert result["variants"] == {}
    assert result["error"] == "Provider chain error: groq 404 model_not_found"
    # The generic message is for empty results only, never for a failure.
    assert "no usable copy" not in result["error"]


def test_outage_error_is_not_the_empty_result_message():
    settled = [_rejected("rate limited"), _rejected("rate limited")]
    result = _collect(settled, ["facebook", "instagram"])
    assert result["error"] != "The model returned no usable copy. Try again."


def test_fulfilled_but_empty_keeps_the_generic_message():
    """The one case the generic copy was written for: the provider answered and
    the answer held no variants."""
    settled = _fulfilled([])
    result = _collect(settled, ["facebook"])

    assert result["empty"] is True
    assert result["error"] == "The model returned no usable copy. Try again."


def test_rejection_without_a_message_still_names_the_platform():
    settled = [{"status": "rejected", "reason": {}}]
    result = _collect(settled, ["facebook"], {"facebook": "Facebook"})

    assert result["error"] == "Copy failed for Facebook. Try again."


def test_the_first_rejection_is_the_reported_one():
    settled = [_rejected("groq: model_not_found"), _rejected("gemini: quota exceeded")]
    result = _collect(settled, ["facebook", "instagram"])
    assert result["error"] == "groq: model_not_found"


# ---------------------------------------------------------------------------
# Partial success — copy written, and every failure still named.
# ---------------------------------------------------------------------------


def test_partial_success_keeps_the_variants_that_landed():
    settled = _fulfilled([{"angle": "Benefit"}]) + [_rejected("gemini: 503")]
    result = _collect(settled, ["facebook", "instagram"])

    assert result["empty"] is False
    assert list(result["variants"]) == ["facebook"]
    assert result["info"] == "Copy written for 1 of 2 platforms."
    assert result["failures"] == [
        {"platform": "instagram", "message": "gemini: 503"}
    ]


def test_full_success_has_no_failures_and_no_info():
    settled = _fulfilled([{"angle": "Benefit"}], [{"angle": "Urgency"}])
    result = _collect(settled, ["facebook", "instagram"])

    assert result["empty"] is False
    assert result["info"] is None
    assert result["failures"] == []
    assert result["error"] is None


def test_variants_are_keyed_by_platform():
    settled = _fulfilled([], [{"angle": "Benefit"}])
    result = _collect(settled, ["facebook", "instagram"])

    # An empty fulfillment does not register as written; the other platform does.
    assert list(result["variants"]) == ["instagram"]


# ---------------------------------------------------------------------------
# The page has to use the helper, not re-inline the old allSettled reading.
# ---------------------------------------------------------------------------


def test_ad_copy_uses_the_helper():
    source = AD_COPY_JSX.read_text(encoding="utf-8")
    assert "collectCopyResults" in source, "AdCopy.jsx must classify the settled results"
    # The old shape kept only fulfilled results, which is the bug.
    assert "outcome.status === 'fulfilled' && outcome.value?.variants?.length" not in source
