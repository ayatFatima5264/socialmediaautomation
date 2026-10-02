"""Tests for the A/B Testing workspace.

BUG-05: the tool was an inert shell. Both "Choose creative" buttons and both
result actions were hardcoded `disabled` in the source, while the split, metric
and duration toggles worked. This checks the report module it now builds with,
and that the page is wired to it rather than carrying the old disabled shell.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ABTEST_JS = REPO_ROOT / "frontend" / "src" / "lib" / "ads" / "abTest.js"
ABTEST_JSX = REPO_ROOT / "frontend" / "src" / "pages" / "ads" / "tools" / "AbTesting.jsx"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="Node is needed to run the ESM frontend modules."
)

A = {"id": 1, "title": "Amber serum", "url": "/media/a.jpg", "width": 1024, "height": 768}
B = {"id": 2, "title": "Blue serum", "url": "/media/b.jpg", "width": 1080, "height": 1080}


def _run(expression: str, fn: str):
    """Evaluate `fn(...)` against the abTest module in Node."""
    script = (
        f"import {{ {fn} }} from __MODULE__;\n"
        "process.stdout.write(JSON.stringify(" + expression + "));"
    ).replace("__MODULE__", json.dumps(ABTEST_JS.as_uri()))
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return json.loads(result.stdout)


def _report(**overrides):
    payload = {
        "campaign": {"name": "QA Spring Sale"},
        "variants": {"a": A, "b": B},
        "split": "50 / 50",
        "metric": "Click-through rate",
        "duration": "7 days",
        "generatedAt": "2026-09-26T00:00:00.000Z",
    }
    payload.update(overrides)
    return _node_report(payload)


def _node_report(payload):
    script = (
        "import { buildTestReport } from __MODULE__;\n"
        "process.stdout.write(JSON.stringify(buildTestReport(__PAYLOAD__)));"
    )
    script = script.replace("__MODULE__", json.dumps(ABTEST_JS.as_uri())).replace(
        "__PAYLOAD__", json.dumps(payload)
    )
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# Readiness — what Start Test gates on.
# ---------------------------------------------------------------------------


def test_both_variants_means_ready():
    assert _run(f"isTestReady({json.dumps({'a': A, 'b': B})})", "isTestReady") is True


def test_one_variant_is_not_ready():
    assert _run(f"isTestReady({json.dumps({'a': A, 'b': None})})", "isTestReady") is False
    assert _run("isTestReady({})", "isTestReady") is False
    assert _run("isTestReady(undefined)", "isTestReady") is False


# ---------------------------------------------------------------------------
# The report is a real file with real content.
# ---------------------------------------------------------------------------


def test_report_names_both_creatives():
    report = _report()
    assert "Amber serum" in report["content"]
    assert "Blue serum" in report["content"]


def test_report_states_the_settings():
    content = _report()["content"]
    assert "50 / 50" in content
    assert "Click-through rate" in content
    assert "7 days" in content
    assert "QA Spring Sale" in content


def test_report_says_delivery_data_is_not_included():
    """The old fix would have been to invent results. The file says plainly
    that it does not have any."""
    content = _report()["content"]
    assert "Delivery data is not connected" in content


def test_report_never_claims_a_winner():
    content = _report()["content"].lower()
    assert "winner:" not in content
    assert "significant" not in content


def test_report_filename_follows_the_campaign():
    assert _report()["filename"] == "qa-spring-sale-ab-report.txt"


def test_report_falls_back_to_a_filename_without_a_campaign():
    assert _report(campaign=None)["filename"] == "ab-test-ab-report.txt"


def test_incomplete_test_is_reported_as_incomplete():
    content = _report(variants={"a": A})["content"]
    assert "Not set up" in content
    assert "Not chosen" in content


def test_complete_test_is_reported_as_ready():
    assert "Ready to run." in _report()["content"]


# ---------------------------------------------------------------------------
# The page is wired — no hardcoded disabled shell left.
# ---------------------------------------------------------------------------


def test_creative_pickers_are_not_disabled():
    source = ABTEST_JSX.read_text(encoding="utf-8")
    assert "Choose creative" in source
    # The bug, verbatim from the report: a bare `disabled` on a button that has
    # no handler at all, so clicking it times out and nothing explains why.
    assert not re.search(r"<button(?![^>]*onClick)[^>]*\bdisabled\b", source), (
        "a button with `disabled` and no onClick is the inert control BUG-05 reported"
    )


def test_result_actions_have_click_handlers():
    source = ABTEST_JSX.read_text(encoding="utf-8")
    assert "onClick={promoteWinner}" in source
    assert "onClick={exportReport}" in source
    # Neither action is a dead disabled button any more.
    assert "Promote winner" in source and "Export report" in source


def test_picker_opens_the_media_library_modal():
    source = ABTEST_JSX.read_text(encoding="utf-8")
    assert "MediaLibraryModal" in source
    assert "open={picking !== null}" in source


def test_start_test_gates_on_both_creatives():
    source = ABTEST_JSX.read_text(encoding="utf-8")
    assert "disabled={!ready}" in source
    assert "Choose a creative for Variant A and Variant B first." in source
