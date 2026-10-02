/**
 * One run of a generation: a deadline, a cancel, and a way to tell a late
 * answer from the current one.
 *
 * BUG-10 was that the results panel could sit on "Generating…" indefinitely —
 * the QA run went past 90s — with no progress, no timeout, and no way to stop.
 * There was nothing to wait *for*: the browser's `fetch` has no timeout by
 * default, so a request that never resolves waits forever.
 *
 * Three things go wrong in the absence of all of this, and each is handled here:
 *
 *   1. A request that never answers. `deadline` aborts it and says so.
 *   2. A user who changed their mind. `cancel()` aborts it, and is not
 *      reported as a failure — they did it on purpose.
 *   3. A response that arrives after the user has moved on. Navigating away or
 *      starting again unmounts or supersedes the run, and without an identity
 *      check the stale answer still lands in `setData` and overwrites what the
 *      user is now looking at. `isCurrent(id)` is that check.
 *
 * No React and no DOM beyond `AbortController`, so the behaviour is testable in
 * Node. `schedule`, `clearTimer`, `now` and `createController` are injectable
 * for the same reason.
 */

/**
 * How long a generation may run before it is given up on.
 *
 * The server's own budget is lower (see `image_generation_deadline`) — it walks
 * up to four image hosts with retries — so this is the backstop for the case the
 * server cannot enforce: a connection that is simply never closed. Long enough
 * that a legitimately slow generation is not killed, short enough that a stuck
 * one does not outlive the user's patience.
 */
export const GENERATION_DEADLINE = 90_000

/** Reasons a run can end, so the caller can say the right thing about it. */
export const RUN_ENDED = {
  COMPLETED: 'completed',
  CANCELLED: 'cancelled',
  TIMED_OUT: 'timed_out',
  SUPERSEDED: 'superseded',
}

/**
 * An abort that is the user's or the clock's doing, not a failure to report.
 *
 * `fetch` rejects with a `DOMException` named `AbortError`; this carries the
 * reason so the caller does not have to guess, and so a genuine network error
 * stays distinguishable from a cancellation.
 */
export class GenerationStopped extends Error {
  constructor(reason) {
    super(`Generation ${reason.replace('_', ' ')}.`)
    this.name = 'GenerationStopped'
    this.reason = reason
  }
}

/** Is this the `AbortError` that `fetch` throws, however it reached us? */
export function isAbortError(err) {
  if (!err) return false
  return err.name === 'AbortError' || err.name === 'GenerationStopped'
}

export function createGenerationRun({
  deadline = GENERATION_DEADLINE,
  schedule = setTimeout,
  clearTimer = clearTimeout,
  now = () => Date.now(),
  createController = () => new AbortController(),
} = {}) {
  let runId = 0
  let active = null
  let stopped = null

  function stop(reason) {
    if (!active) return
    stopped = reason
    if (active.timer !== null) {
      clearTimer(active.timer)
      active.timer = null
    }
    // Aborting is what actually closes the socket; without it the request
    // keeps running server-side and the response is discarded on arrival.
    active.controller.abort(reason)
  }

  return {
    /**
     * Begin a run, superseding any in flight. Returns its identity; pass it back
     * to `isCurrent` before writing anything to state.
     */
    start() {
      stop(RUN_ENDED.SUPERSEDED)
      const id = ++runId
      // The reason belongs to the run that was just stopped. Left in place, the
      // new run would look stopped too: `isCurrent` would refuse it and
      // `reason()` would report it as superseded, so its results would be
      // discarded and its errors silenced — the newest generation, invisible.
      stopped = null
      active = {
        id,
        controller: createController(),
        startedAt: now(),
        timer: null,
      }
      if (deadline > 0) {
        active.timer = schedule(() => stop(RUN_ENDED.TIMED_OUT), deadline)
      }
      return { id, signal: active.controller.signal }
    },

    /** True while `id` is the newest run and has not been stopped. */
    isCurrent(id) {
      return active !== null && active.id === id && stopped === null
    },

    /** The reason this run ended, or null while it is healthy. */
    reason() {
      return stopped
    },

    signal() {
      return active ? active.controller.signal : undefined
    },

    /** ms since the run began, for the progress line. Null when idle. */
    elapsed() {
      return active ? Math.max(0, now() - active.startedAt) : null
    },

    remaining() {
      if (!active || deadline <= 0) return null
      return Math.max(0, deadline - Math.max(0, now() - active.startedAt))
    },

    cancel() {
      stop(RUN_ENDED.CANCELLED)
    },

    /** Clear the deadline once the request has answered either way. */
    finish() {
      if (!active) return
      if (active.timer !== null) {
        clearTimer(active.timer)
        active.timer = null
      }
      active = null
      stopped = null
    },

    /** Unmount: abort, and leave nothing behind to fire. */
    dispose() {
      stop(RUN_ENDED.CANCELLED)
      active = null
      stopped = null
    },

    get running() {
      return active !== null
    },
  }
}

/** "12s", "1m 04s" — enough to show that something is happening. */
export function formatElapsed(ms) {
  if (ms === null || ms === undefined) return ''
  const total = Math.max(0, Math.round(ms / 1000))
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  return minutes ? `${minutes}m ${String(seconds).padStart(2, '0')}s` : `${seconds}s`
}
