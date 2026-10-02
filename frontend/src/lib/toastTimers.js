/**
 * The bookkeeping behind a toast's dismissal clock.
 *
 * A fixed timeout is wrong twice over: it keeps running while the user is
 * reading the message (so an error vanishes mid-sentence as they reach for
 * Retry), and it survives unmount (so it calls setState on a tree that is gone).
 *
 * `createToastTimers` owns both problems and nothing else — no React, no DOM —
 * so the behaviour can be tested in Node.
 *
 * `schedule`, `clear` and `clock` are injectable so tests can drive it with
 * short durations instead of waiting four real seconds.
 */
export function createToastTimers({
  schedule = setTimeout,
  clear: clearHandle = clearTimeout,
  clock = () => Date.now(),
} = {}) {
  /**
   * id -> { handle, startedAt, total, onExpire }
   *
   * `startedAt` is what makes pausing honest: a paused toast has to come back
   * with the time it actually had left, not the time it was originally given.
   * Without it, hovering an error for nine of its ten seconds would still cost
   * the user the last one.
   */
  const entries = new Map()

  function arm(id, total, onExpire) {
    const existing = entries.get(id)
    if (existing && existing.handle !== null) clearHandle(existing.handle)
    const handle = schedule(() => {
      entries.delete(id)
      onExpire(id)
    }, total)
    entries.set(id, { handle, startedAt: clock(), total, onExpire })
  }

  /**
   * Freeze `id`'s clock, banking the time it has left.
   * Returns false when there was nothing running — a toast already dismissed,
   * or a hover arriving after it expired.
   */
  function pause(id) {
    const entry = entries.get(id)
    if (!entry || entry.handle === null) return false
    clearHandle(entry.handle)
    const elapsed = Math.max(0, clock() - entry.startedAt)
    entries.set(id, {
      ...entry,
      handle: null,
      total: Math.max(0, entry.total - elapsed),
    })
    return true
  }

  /**
   * Restart a paused clock for whatever it had left, never less than `floor`
   * so a toast the user sat on for a minute does not vanish the instant the
   * pointer leaves it.
   */
  function resume(id, floor = 1000) {
    const entry = entries.get(id)
    if (!entry || entry.handle !== null) return false
    arm(id, Math.max(floor, entry.total), entry.onExpire)
    return true
  }

  function cancel(id) {
    const entry = entries.get(id)
    if (entry && entry.handle !== null) clearHandle(entry.handle)
    entries.delete(id)
  }

  /** Cancel everything. Called on unmount. */
  function dispose() {
    entries.forEach((entry) => {
      if (entry.handle !== null) clearHandle(entry.handle)
    })
    entries.clear()
  }

  return {
    arm,
    pause,
    resume,
    cancel,
    dispose,
    isRunning: (id) => {
      const entry = entries.get(id)
      return Boolean(entry && entry.handle !== null)
    },
    isPaused: (id) => {
      const entry = entries.get(id)
      return Boolean(entry && entry.handle === null)
    },
    /** Milliseconds still to run, for a paused entry. */
    remaining: (id) => {
      const entry = entries.get(id)
      if (!entry) return 0
      if (entry.handle === null) return entry.total
      return Math.max(0, entry.total - Math.max(0, clock() - entry.startedAt))
    },
    get pending() {
      return entries.size
    },
  }
}
