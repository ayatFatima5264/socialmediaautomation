"""Tests for toast accessibility and dismissal (BUG-08).

The QA report found error and validation toasts invisible: a screen reader
announced nothing, because the stack had no live region at all, and the only
signal was a panel appearing in the corner of the viewport. Every toast also
lived exactly 4s — long enough to read "Saved", not long enough to read a
provider error and decide what to do about it.

The frontend has no test runner, so the behaviour lives in two pure ESM modules
that pytest drives through Node, with the wiring checked against the component.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_JS = REPO_ROOT / "frontend" / "src" / "lib" / "toastPolicy.js"
TIMERS_JS = REPO_ROOT / "frontend" / "src" / "lib" / "toastTimers.js"
CONTEXT_JSX = REPO_ROOT / "frontend" / "src" / "context" / "ToastContext.jsx"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="Node is needed to run the ESM frontend modules."
)


def run_node(body: str, *modules: Path) -> str:
    """Run `body` in Node with the given ESM modules imported."""
    imports = "\n".join(
        f"import * as M{i} from {json.dumps(path.as_uri())};" for i, path in enumerate(modules)
    )
    script = f"{imports}\n{body}"
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


# ---------------------------------------------------------------------------
# Duration policy.
# ---------------------------------------------------------------------------


def test_an_error_outlives_a_success():
    """The bug: one duration for everything."""
    policy = json.loads(
        run_node(
            "process.stdout.write(JSON.stringify([M0.durationFor('error'),"
            " M0.durationFor('success'), M0.durationFor('info')]))",
            POLICY_JS,
        )
    )
    error, success, info = policy
    assert error > success, f"an error lasted {error}ms and a success {success}ms"
    assert error >= 10000, "an error is gone before it can be read and acted on"


def test_an_unknown_type_still_gets_a_duration():
    """A typo in a call site must not produce a toast that never expires."""
    assert json.loads(
        run_node(
            "process.stdout.write(JSON.stringify(M0.durationFor('warning')))",
            POLICY_JS,
        )
    ) > 0


def test_only_errors_interrupt_a_screen_reader():
    """`alert` is assertive. Using it for a confirmation talks over whatever
    the user is already hearing; using `status` for a failure makes them wait
    their turn for news they need immediately."""
    roles = json.loads(
        run_node(
            "process.stdout.write(JSON.stringify(["
            "M0.roleFor('error'), M0.roleFor('success'), M0.roleFor('info')]))",
            POLICY_JS,
        )
    )
    assert roles == ["alert", "status", "status"]


# ---------------------------------------------------------------------------
# The dismissal clock: pause, resume, unmount.
# ---------------------------------------------------------------------------


TIMER_HARNESS = """
const timers = M0.createToastTimers()
const expired = []
const onExpire = (id) => expired.push(id)
const out = {}

// Expires on its own when nobody is reading it.
timers.arm(1, 30, onExpire)
out.runningBefore = timers.isRunning(1)

// Pausing keeps it alive past the point it would have gone.
out.pauseResult = timers.pause(1)
out.pausedAfter = timers.isPaused(1)
out.remainingWhenPaused = timers.remaining(1)
await new Promise((r) => setTimeout(r, 60))
out.expiredWhilePaused = expired.length

// Resuming brings back only the time it had left, so it is still gone after
// roughly the remainder rather than a fresh full term.
out.resumeResult = timers.resume(1, 5)
await new Promise((r) => setTimeout(r, 60))
out.expiredAfterResume = expired.length

// Unmount cancels what is left, so no timeout calls back into a dead tree.
timers.arm(2, 20, onExpire)
out.pendingBeforeDispose = timers.pending
timers.dispose()
out.pendingAfterDispose = timers.pending
await new Promise((r) => setTimeout(r, 50))
out.expiredAfterDispose = expired.length

process.stdout.write(JSON.stringify(out))
"""


def test_the_clock_pauses_resumes_and_disposes():
    result = json.loads(run_node(TIMER_HARNESS, TIMERS_JS))
    assert result["runningBefore"] is True
    assert result["pauseResult"] is True
    assert result["pausedAfter"] is True
    assert result["expiredWhilePaused"] == 0, "the toast expired while being read"
    assert result["resumeResult"] is True
    assert result["expiredAfterResume"] == 1, "a paused toast never came back"
    assert result["expiredAfterDispose"] == 1, "a timer fired after unmount"


def test_a_long_read_is_not_punished():
    """A user who hovers a toast until its clock is nearly spent must still be
    able to read it after they leave. `resume` takes the larger of the time
    left and a floor, so the floor is what decides here."""
    result = json.loads(
        run_node(
            """
const timers = M0.createToastTimers()
const expired = []
timers.arm(7, 40, (id) => expired.push(id))
// Let nearly all of it run down, then stop the clock.
await new Promise((r) => setTimeout(r, 35))
timers.pause(7)
const left = timers.remaining(7)
timers.resume(7, 50)
await new Promise((r) => setTimeout(r, 20))
const mid = expired.length
await new Promise((r) => setTimeout(r, 80))
process.stdout.write(JSON.stringify({ left, mid, end: expired.length }))
""",
            TIMERS_JS,
        )
    )
    assert result["left"] < 50, "the clock was not nearly spent, so this proves nothing"
    assert result["mid"] == 0, (
        f"only {result['left']}ms was left but it expired {20}ms after resuming — "
        "the floor was not applied"
    )
    assert result["end"] == 1, "the toast never expired at all"


def test_pause_is_honest_about_elapsed_time():
    """A toast paused halfway through must not restart with its full term —
    that is the bug a floor alone would hide."""
    result = json.loads(
        run_node(
            """
const timers = M0.createToastTimers()
timers.arm(1, 100, () => {})
await new Promise((r) => setTimeout(r, 70))
timers.pause(1)
process.stdout.write(JSON.stringify({ left: timers.remaining(1) }))
""",
            TIMERS_JS,
        )
    )
    assert result["left"] < 60, (
        f"70ms of a 100ms term had passed but {result['left']}ms was left"
    )


def test_operations_on_an_unknown_toast_are_harmless():
    """Hover and blur can both fire for a toast that already expired."""
    result = json.loads(
        run_node(
            """
const timers = M0.createToastTimers()
const out = {
  pause: timers.pause(999),
  resume: timers.resume(999),
  remaining: timers.remaining(999),
}
timers.arm(1, 5, () => {})
await new Promise((r) => setTimeout(r, 20))
out.pauseAfterExpiry = timers.pause(1)
out.resumeAfterExpiry = timers.resume(1)
process.stdout.write(JSON.stringify(out))
""",
            TIMERS_JS,
        )
    )
    assert result["pause"] is False
    assert result["resume"] is False
    assert result["remaining"] == 0
    assert result["pauseAfterExpiry"] is False
    assert result["resumeAfterExpiry"] is False


def test_re_arming_does_not_leak_the_previous_timer():
    """Two timers for one toast would remove it out from under a second
    notification that reused the id."""
    result = json.loads(
        run_node(
            """
const timers = M0.createToastTimers()
const expired = []
timers.arm(1, 10, (id) => expired.push(id))
timers.arm(1, 200, (id) => expired.push(id))
await new Promise((r) => setTimeout(r, 60))
process.stdout.write(JSON.stringify({ expired: expired.length }))
""",
            TIMERS_JS,
        )
    )
    assert result["expired"] == 0, "the superseded timer still fired"


# ---------------------------------------------------------------------------
# The component wiring.
# ---------------------------------------------------------------------------


def source() -> str:
    return CONTEXT_JSX.read_text(encoding="utf-8")


def test_the_stack_is_a_live_region():
    """Without this a screen reader announces nothing at all."""
    assert 'aria-live="polite"' in source()


def test_errors_are_assertive():
    assert "role={roleFor(t.type)}" in source()


def test_the_duration_is_no_long_than_a_hardcoded_four_seconds():
    """The single 4000 that caused the bug must not reappear."""
    assert "setTimeout(() => remove(id), 4000)" not in source()
    assert "4000)" not in source().replace("TOAST_DURATION", "")


def test_the_message_is_text_not_a_title_attribute():
    """A tooltip is not announced and vanishes on focus."""
    assert "{t.message}" in source()
    assert "title={t.message}" not in source()


def test_there_is_a_keyboard_reachable_dismiss_control():
    """The toast was a div with an onClick — unreachable by keyboard."""
    assert "<button" in source()
    assert "aria-label={`Dismiss: ${t.message}`}" in source()


def test_timers_are_cancelled_on_unmount():
    assert "return () => timers.dispose()" in source()


def test_the_policy_is_not_duplicated_in_the_component():
    """The durations live in one module; a second copy would drift."""
    assert "durationFor" in source()
    assert "TOAST_DURATION" not in source()


def test_every_import_in_the_component_resolves():
    """The behavioural tests above all passed while the component pointed at
    `../../lib/toastPolicy`, which does not exist — `src/context/` is a sibling
    of `src/lib/`, not a child. Only the bundler noticed, and only at build
    time. Every relative specifier is checked here instead."""
    import re

    specifiers = re.findall(r"from\s+'(\.[^']+)'", source())
    assert specifiers, "no relative imports found — the check is not looking at anything"
    for specifier in specifiers:
        target = (CONTEXT_JSX.parent / specifier).resolve()
        resolved = None
        for candidate in (
            target,
            target.with_suffix(".js"),
            target.with_suffix(".jsx"),
            target / "index.js",
            target / "index.jsx",
        ):
            if candidate.is_file():
                resolved = candidate
                break
        assert resolved is not None, f"{specifier} does not resolve to a file"
