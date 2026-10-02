"""Tests for BUG-10: generation timeout, cancel, progress and late-response safety.

The QA report found the results panel could sit on "Generating…" indefinitely —
one run went past 90s — with no progress, no timeout, and no way to cancel. The
cause was a chain of up to four third-party image hosts with retries, bounded
only per request (30s each), and a `fetch` with no timeout at all.

Fixed on both sides: an overall deadline in the provider chain server-side
(`image_generation_deadline`), and in the browser a deadline, a Cancel, a
progress clock, and a run identity so a late response cannot overwrite newer
state.

The frontend has no test runner, so the run logic lives in a pure ESM module
that pytest drives through Node, and the wiring is checked against the sources.
"""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_JS = REPO_ROOT / "frontend" / "src" / "lib" / "generationRun.js"
RETRY_JS = REPO_ROOT / "frontend" / "src" / "lib" / "imageRetry.js"
HOOK_JS = REPO_ROOT / "frontend" / "src" / "hooks" / "useAdGeneration.js"
BUTTON_JSX = REPO_ROOT / "frontend" / "src" / "components" / "ads" / "workspace" / "GenerateButton.jsx"
RESULTS_JSX = REPO_ROOT / "frontend" / "src" / "components" / "ads" / "workspace" / "CreativeResults.jsx"
API_JS = REPO_ROOT / "frontend" / "src" / "lib" / "api.js"
TOOL_DIR = REPO_ROOT / "frontend" / "src" / "pages" / "ads" / "tools"
GENERATION_TOOLS = [
    "BannerGenerator",
    "CarouselAds",
    "CtaGenerator",
    "HeadlineGenerator",
    "ProductAds",
    "ProductShowcaseVideo",
    "TextToVideo",
]

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="Node is needed to run the ESM frontend modules."
)


def run_node(body: str, *modules: Path) -> str:
    imports = "\n".join(
        f"import * as M{i} from {json.dumps(path.as_uri())};" for i, path in enumerate(modules)
    )
    result = subprocess.run(
        ["node", "--input-type=module", "-e", f"{imports}\n{body}"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


# ---------------------------------------------------------------------------
# The deadline.
# ---------------------------------------------------------------------------


def test_a_request_that_never_answers_is_given_up_on():
    """The QA observation: over 90s with nothing happening. `fetch` has no
    timeout of its own, so without this the wait is however long the user
    tolerates."""
    result = json.loads(
        run_node(
            """
const run = M0.createGenerationRun({ deadline: 30 })
const { id } = run.start()
const before = run.isCurrent(id)
await new Promise((r) => setTimeout(r, 60))
process.stdout.write(JSON.stringify({
  before,
  after: run.isCurrent(id),
  reason: run.reason(),
}))
""",
            RUN_JS,
        )
    )
    assert result["before"] is True
    assert result["after"] is False, "the run was still considered live past its deadline"
    assert result["reason"] == "timed_out"


def test_the_deadline_actually_aborts_the_request():
    """Aborting is the only thing that closes the socket. Without it the server
    keeps working on a request nobody is waiting for."""
    result = json.loads(
        run_node(
            """
const run = M0.createGenerationRun({ deadline: 20 })
const { signal } = run.start()
let aborted = null
signal.addEventListener('abort', () => { aborted = { reason: signal.reason } })
await new Promise((r) => setTimeout(r, 50))
process.stdout.write(JSON.stringify({ aborted, abortedFlag: signal.aborted }))
""",
            RUN_JS,
        )
    )
    assert result["abortedFlag"] is True
    assert result["aborted"] is not None, "no abort event was dispatched"
    assert result["aborted"]["reason"] == "timed_out"


def test_clearing_the_deadline_on_success():
    """A finished request must not leave a timer that fires later and reports a
    timeout for work that already succeeded."""
    result = json.loads(
        run_node(
            """
const run = M0.createGenerationRun({ deadline: 30 })
const { id } = run.start()
run.finish()
await new Promise((r) => setTimeout(r, 60))
process.stdout.write(JSON.stringify({ reason: run.reason(), running: run.running }))
""",
            RUN_JS,
        )
    )
    assert result["reason"] is None
    assert result["running"] is False


def test_the_default_deadline_is_long_enough_to_be_useful():
    """It has to outlast a legitimate slow generation, or it fixes the symptom
    by breaking the feature."""
    result = json.loads(
        run_node(
            "process.stdout.write(JSON.stringify(M0.GENERATION_DEADLINE))", RUN_JS
        )
    )
    assert 45_000 <= result <= 120_000, f"{result}ms is not a usable budget"


# ---------------------------------------------------------------------------
# Cancel, and not reporting a cancel as a failure.
# ---------------------------------------------------------------------------


def test_cancel_ends_the_run():
    result = json.loads(
        run_node(
            """
const run = M0.createGenerationRun({ deadline: 5000 })
const { id, signal } = run.start()
run.cancel()
process.stdout.write(JSON.stringify({
  current: run.isCurrent(id),
  reason: run.reason(),
  aborted: signal.aborted,
}))
""",
            RUN_JS,
        )
    )
    assert result["current"] is False
    assert result["reason"] == "cancelled"
    assert result["aborted"] is True


def test_cancel_is_distinguishable_from_a_timeout():
    """The two need different words: one is the user's doing, the other is a
    host being too slow."""
    reasons = json.loads(
        run_node(
            """
const a = M0.createGenerationRun({ deadline: 5000 })
a.start(); a.cancel()
const b = M0.createGenerationRun({ deadline: 10 })
b.start()
await new Promise((r) => setTimeout(r, 40))
process.stdout.write(JSON.stringify([a.reason(), b.reason()]))
""",
            RUN_JS,
        )
    )
    assert reasons == ["cancelled", "timed_out"]


def test_an_abort_error_is_recognised():
    """`fetch` rejects with a `DOMException` named `AbortError`; it must not be
    mistaken for a network fault worth a red toast."""
    result = json.loads(
        run_node(
            """
const err = new Error('aborted')
err.name = 'AbortError'
process.stdout.write(JSON.stringify([
  M0.isAbortError(err),
  M0.isAbortError(new Error('network down')),
  M0.isAbortError(null),
]))
""",
            RUN_JS,
        )
    )
    assert result == [True, False, False]


def test_cancelling_before_the_deadline_does_not_report_a_timeout():
    """Otherwise pressing Cancel produces the red "took longer than 90 seconds"
    message, blaming a host for the user's own decision."""
    result = json.loads(
        run_node(
            """
const run = M0.createGenerationRun({ deadline: 5000 })
run.start()
run.cancel()
await new Promise((r) => setTimeout(r, 60))
process.stdout.write(JSON.stringify(run.reason()))
""",
            RUN_JS,
        )
    )
    assert result == "cancelled"


# ---------------------------------------------------------------------------
# The late response.
# ---------------------------------------------------------------------------


def test_a_superseded_run_cannot_touch_state():
    """The recommendation from the report: an AbortController on unmount would
    stop late responses overwriting newer state. This is that guard.

    A user starts a generation, starts another, and the first answers last.
    Without an identity check the *older* result is what ends up on screen.
    """
    result = json.loads(
        run_node(
            """
const run = M0.createGenerationRun({ deadline: 5000 })
const first = run.start()
const second = run.start()
process.stdout.write(JSON.stringify({
  firstIsCurrent: run.isCurrent(first.id),
  secondIsCurrent: run.isCurrent(second.id),
  firstReason: (() => { run.finish(); return null })(),
}))
""",
            RUN_JS,
        )
    )
    assert result["firstIsCurrent"] is False, "the superseded run still claims to be live"
    assert result["secondIsCurrent"] is True


def test_starting_a_second_run_aborts_the_first():
    result = json.loads(
        run_node(
            """
const run = M0.createGenerationRun({ deadline: 5000 })
const first = run.start()
const second = run.start()
process.stdout.write(JSON.stringify({
  firstAborted: first.signal.aborted,
  secondAborted: second.signal.aborted,
  ids: [first.id, second.id],
}))
""",
            RUN_JS,
        )
    )
    assert result["ids"][0] != result["ids"][1]
    assert result["firstAborted"] is True
    assert result["secondAborted"] is False


def test_dispose_is_unmount_and_leaves_nothing_behind():
    result = json.loads(
        run_node(
            """
const run = M0.createGenerationRun({ deadline: 20 })
const { id, signal } = run.start()
run.dispose()
await new Promise((r) => setTimeout(r, 50))
process.stdout.write(JSON.stringify({
  current: run.isCurrent(id),
  running: run.running,
  aborted: signal.aborted,
  reason: run.reason(),
}))
""",
            RUN_JS,
        )
    )
    assert result["current"] is False
    assert result["running"] is False
    assert result["aborted"] is True
    # Nothing may fire after unmount: a timer that outlives the component calls
    # setState on a tree that is gone.
    assert result["reason"] is None


# ---------------------------------------------------------------------------
# Progress.
# ---------------------------------------------------------------------------


def test_elapsed_moves_so_the_panel_is_not_silent():
    result = json.loads(
        run_node(
            """
let t = 0
const run = M0.createGenerationRun({ deadline: 5000, now: () => t, schedule: () => 0 })
run.start()
const a = run.elapsed()
t = 1500
const b = run.elapsed()
process.stdout.write(JSON.stringify([a, b, M0.formatElapsed(b)]))
""",
            RUN_JS,
        )
    )
    assert result[0] == 0
    assert result[1] == 1500
    assert result[2] == "2s"


def test_elapsed_is_null_when_idle():
    result = json.loads(
        run_node(
            """
const run = M0.createGenerationRun({ deadline: 5000 })
process.stdout.write(JSON.stringify([run.elapsed(), M0.formatElapsed(run.elapsed())]))
""",
            RUN_JS,
        )
    )
    assert result == [None, ""]


def test_elapsed_formats_minutes():
    result = json.loads(
        run_node(
            "process.stdout.write(JSON.stringify(["
            "M0.formatElapsed(1000), M0.formatElapsed(64000), M0.formatElapsed(59999),"
            "M0.formatElapsed(0)]))",
            RUN_JS,
        )
    )
    assert result == ["1s", "1m 04s", "1m 00s", "0s"]


# ---------------------------------------------------------------------------
# The server's half of it.
# ---------------------------------------------------------------------------


def test_the_provider_chain_has_an_overall_deadline(monkeypatch):
    """Four hosts x 3 retries x 30s is minutes behind a spinner, and the QA run
    proved it. The per-request timeout alone does not bound the chain."""
    import asyncio
    import time

    from app.config import settings
    from app.services import image_service

    async def _never_answers(*_args, **_kwargs):
        await asyncio.sleep(30)
        return True, ""

    monkeypatch.setattr(image_service, "_try_ai_candidate", _never_answers)
    monkeypatch.setattr(settings, "image_generation_deadline", 0.5)

    started = time.monotonic()
    with pytest.raises(image_service.ImageError) as exc:
        asyncio.run(image_service.generate_with_fallback("a cat", verify=True))
    elapsed = time.monotonic() - started

    assert elapsed < 5, f"it waited {elapsed:.1f}s — the deadline did not apply"
    # The message has to explain itself, or the user goes looking at their
    # prompt instead of at a host that is too slow.
    assert "gave up" in str(exc.value)
    assert "slower" in str(exc.value) or "slowly" in str(exc.value)


def test_the_client_deadline_is_longer_than_the_servers(monkeypatch):
    """The server should give up first so the user gets a real reason rather
    than a silent client-side abort."""
    from app.config import settings

    server = settings.image_generation_deadline * 1000
    client = json.loads(
        run_node("process.stdout.write(JSON.stringify(M0.GENERATION_DEADLINE))", RUN_JS)
    )
    assert client > server, (
        f"the client gives up at {client}ms but the server at {server}ms, so the "
        "user sees an abort with no explanation"
    )


def test_a_fast_generation_is_untouched(monkeypatch):
    """The deadline must not fire on the happy path."""
    import asyncio

    from app.config import settings
    from app.services import image_service

    async def _immediate(*_args, **_kwargs):
        return True, ""

    monkeypatch.setattr(image_service, "_try_ai_candidate", _immediate)
    url, provider = asyncio.run(
        image_service.generate_with_fallback("a cat", verify=True)
    )
    assert provider
    assert url


# ---------------------------------------------------------------------------
# The wiring.
# ---------------------------------------------------------------------------


def hook_source() -> str:
    return HOOK_JS.read_text(encoding="utf-8")


def test_the_hook_aborts_on_unmount():
    assert "return () => started.dispose()" in hook_source()


def test_the_hook_guards_the_state_write():
    """Both writes are behind the identity check — the result and the reset of
    `loading`."""
    source = hook_source()
    assert source.count("started.isCurrent(id)") >= 2, (
        "a late response can still reach setData"
    )


def test_the_hook_passes_the_signal_down():
    assert "await call(payload, { signal })" in hook_source()


def test_the_request_layer_forwards_and_preserves_the_signal():
    """`request` has to pass the signal to fetch, and must not fold an abort
    into 'could not reach the API server' — the user pressed Cancel, or hit the
    deadline, and telling them to check their connection is wrong."""
    source = API_JS.read_text(encoding="utf-8")
    assert "if (signal) opts.signal = signal" in source
    assert "if (err?.name === 'AbortError') throw err" in source


def test_the_generation_endpoints_accept_options():
    """The hook passes `{ signal }` as a second argument; an endpoint that takes
    one parameter drops it and the abort never reaches fetch."""
    source = API_JS.read_text(encoding="utf-8")
    for endpoint in ("adCopy", "adHeadlines", "adCtas", "adCreative", "adVideoPlan"):
        line = next(
            (l for l in source.splitlines() if f"{endpoint}:" in l),
            None,
        )
        assert line, f"{endpoint} not found"
        assert "opts" in line, f"{endpoint} ignores the AbortSignal: {line.strip()}"


def test_every_generation_tool_can_cancel():
    """A tool with a Cancel button that cancels nothing is the same defect as
    the stub this release removed."""
    for tool in GENERATION_TOOLS:
        source = (TOOL_DIR / f"{tool}.jsx").read_text(encoding="utf-8")
        assert "cancel" in source.split("useAdGeneration(")[0].splitlines()[-1], (
            f"{tool} does not take `cancel` from the hook"
        )
        assert "onCancel={cancel}" in source, f"{tool} has no Cancel wired"
        assert "elapsed={elapsed}" in source, f"{tool} shows no progress"


def test_cancel_only_appears_when_it_can_be_honoured():
    source = BUTTON_JSX.read_text(encoding="utf-8")
    assert "loading && onCancel" in source, (
        "Cancel is not gated on the tool being able to honour it"
    )


def test_a_failed_tile_offers_a_retry():
    """The report: 'No retry affordance offered'."""
    source = RESULTS_JSX.read_text(encoding="utf-8")
    assert "Retry" in source
    # And it must actually retry rather than re-render the same thing.
    assert "withAttempt" in source


def test_retry_busts_the_cache():
    """A per-URL rate limit can serve the same cached error, so retrying the
    byte-identical URL can fail identically and the button would look broken."""
    result = json.loads(
        run_node(
            "process.stdout.write(JSON.stringify(["
            "M0.withAttempt('https://h.test/a.png', 0),"
            "M0.withAttempt('https://h.test/a.png', 2),"
            "M0.withAttempt('https://h.test/a.png', 3),"
            "M0.withAttempt('https://h.test/a.png?seed=1', 2),"
            "M0.withAttempt('https://h.test/a.png?seed=1&w=512', 1)]))",
            RETRY_JS,
        )
    )
    plain, first, second, with_query, two_params = result

    # Attempt 0 is the original URL — no marker, so the first load is untouched.
    assert plain == "https://h.test/a.png"
    # Each retry is a distinct request...
    assert first != second != plain
    assert first == "https://h.test/a.png?retry=2"
    # ...and an existing query string is extended rather than broken.
    assert with_query == "https://h.test/a.png?seed=1&retry=2"
    assert two_params == "https://h.test/a.png?seed=1&w=512&retry=1"


def test_the_tile_uses_the_shared_retry_helper():
    """One copy of the cache-busting rule, or a retry that quietly stops
    working when the other is changed."""
    source = RESULTS_JSX.read_text(encoding="utf-8")
    assert "from '../../../lib/imageRetry'" in source
    assert "function withAttempt" not in source, "a second copy of the retry rule"
