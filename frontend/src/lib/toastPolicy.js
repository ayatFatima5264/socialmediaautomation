/**
 * How long a notification stays on screen, and what a screen reader is told
 * about it.
 *
 * This is split out of ToastContext so it can be tested without a renderer —
 * the project has no frontend test runner, and pure ESM is what pytest can
 * reach through Node.
 */

/**
 * Milliseconds before each kind of notification expires.
 *
 * Every toast used to live for the same 4s, which is a reasonable read of
 * "Saved" and not long enough to read a provider error, find the reason, and
 * decide what to do about it. An error is the one message the user has to act
 * on, so it gets the longest life on screen.
 */
export const TOAST_DURATION = {
  success: 4000,
  info: 5000,
  error: 10000,
}

export const DEFAULT_DURATION = TOAST_DURATION.info

export function durationFor(type) {
  return TOAST_DURATION[type] ?? DEFAULT_DURATION
}

/**
 * The ARIA role for a notification.
 *
 * `alert` is assertive: it interrupts whatever the screen reader is saying.
 * That is correct for a failure and rude for a confirmation, so only errors
 * interrupt — everything else is `status`, which waits its turn.
 */
export function roleFor(type) {
  return type === 'error' ? 'alert' : 'status'
}

/** Errors are the ones worth pausing the clock for. */
export function isDismissable(type) {
  return Boolean(TOAST_DURATION[type])
}
