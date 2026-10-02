"""Tests for the substitution count shown above a creative grid (BUG-06).

The badge on each tile was the only signal that a "generated" creative was
actually a stock photograph. A three-version request that came back as one AI
image and two photos looked like three versions until you looked closely at
two small amber labels, so the count is now stated in a line above the grid.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS_JSX = REPO_ROOT / "frontend" / "src" / "components" / "ads" / "workspace" / "CreativeResults.jsx"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="Node is needed to run the ESM frontend modules."
)


def _summary(sources: list[str]) -> str | None:
    """Call `substitutionSummary` in Node, with React stripped.

    The file is a .jsx component, so the function is extracted and evaluated on
    its own rather than through a JSX build.
    """
    source = RESULTS_JSX.read_text(encoding="utf-8")
    match = re.search(
        r"export function substitutionSummary\(sources = \[\]\) \{.*?\n\}", source, re.S
    )
    assert match, "substitutionSummary not found in CreativeResults.jsx"
    body = match.group(0).replace("export function", "function")

    script = f"{body}\nprocess.stdout.write(JSON.stringify(substitutionSummary(__SOURCES__)));"
    script = script.replace("__SOURCES__", json.dumps(sources))
    result = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# The exact mix QA measured: one AI image, two substitutions out of three.
# ---------------------------------------------------------------------------


def test_the_qa_measurement_is_stated():
    text = _summary(["picsum", "pollinations-sana", "picsum"])
    assert "2 of 3 versions fell back to stock photography" in text
    assert "1 is AI-generated" in text, "the generated count must read grammatically"


def test_both_photo_sources_count_as_substitutions():
    assert _summary(["pollinations-sana", "picsum"]) is not None
    assert _summary(["pollinations-sana", "loremflickr"]) is not None


def test_a_fully_generated_result_says_nothing():
    """No warning on the normal path — a banner on every successful generation
    would train the user to ignore it."""
    assert _summary(["pollinations-sana", "pollinations-sana"]) is None


def test_a_single_substitution_is_stated():
    text = _summary(["pollinations-sana", "picsum"])
    assert "1 of 2 versions" in text


def test_no_sources_yields_no_summary():
    assert _summary([]) is None


def test_a_missing_source_counts_as_a_substitution():
    """An unlabelled image is not known to be generated, so it cannot be
    counted as one."""
    assert _summary([None, "pollinations-sana"]) is not None


def test_all_substituted_says_so():
    text = _summary(["picsum", "picsum", "picsum"])
    assert "3 of 3 versions" in text
    assert "None of these are AI-generated" in text


def test_the_summary_names_the_cause():
    text = _summary(["picsum", "picsum", "picsum"])
    assert "rate-limiting" in text
