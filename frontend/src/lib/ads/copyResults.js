// ---------------------------------------------------------------------------
// What one round of per-platform ad copy actually produced.
//
// Ad Copy fans out one request per platform, so a round is a
// Promise.allSettled. BUG-04 was in how that array was read afterwards: only
// the fulfilled results were kept, and when none survived the tool said "The
// model returned no usable copy. Try again." — which is a statement about the
// user's brief, delivered because the provider chain was down. Every rejection
// reason, including the server's 502 detail, was thrown away on the way.
//
// Split out as a pure function so the distinction is testable without a
// browser, and so the page has one place that decides between "the model
// failed" and "the model had nothing".
// ---------------------------------------------------------------------------

/**
 * @param {string[]} platforms - the platforms requested, in request order.
 * @param {PromiseSettledResult<{variants?: any[]}>[]} settled
 * @param {(platform: string) => string} [labelFor] - display name per platform.
 * @returns {{
 *   variants: Record<string, any[]>,
 *   failures: {platform: string, message: string|null}[],
 *   empty: boolean,
 *   error: string|null,   // what to show when nothing was written at all
 *   info: string|null,    // what to show when some were
 * }}
 */
export function collectCopyResults(settled, platforms, labelFor = (p) => p) {
  const variants = {}
  const failures = []

  settled.forEach((outcome, i) => {
    const platform = platforms[i]
    if (outcome.status === 'rejected') {
      failures.push({ platform, message: outcome.reason?.message || null })
      return
    }
    const list = outcome.value?.variants
    if (Array.isArray(list) && list.length) variants[platform] = list
  })

  const written = Object.keys(variants).length

  if (!written) {
    // A rejection is a real answer and gets reported as one. The generic copy
    // is kept for the only case it was written for: the provider answered and
    // the answer was empty.
    return {
      variants,
      failures,
      empty: true,
      error: failures.length
        ? failures[0].message ||
          `Copy failed for ${labelFor(failures[0].platform)}. Try again.`
        : 'The model returned no usable copy. Try again.',
      info: null,
    }
  }

  const missed = platforms.length - written
  return {
    variants,
    failures,
    empty: false,
    error: null,
    // Partial success reports the count; each failure reports itself, so an
    // outage on one platform is not hidden inside a tally.
    info: missed > 0 ? `Copy written for ${written} of ${platforms.length} platforms.` : null,
  }
}
