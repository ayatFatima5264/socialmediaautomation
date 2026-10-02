/**
 * Re-fetching an image that failed to load.
 *
 * A creative tile whose image did not load used to say "the image host may be
 * rate-limiting, generate again" and offer nothing to click. The advice was
 * right and the affordance was missing (BUG-10), so the only route back was a
 * whole new generation — and paying for every other version again.
 *
 * Retrying re-fetches *this* URL rather than asking the model for a new image.
 * That is the honest reading of the message: the URL is good and the host was
 * busy, so what needs to pass is a second or two, not a new generation. It also
 * keeps the user's selection stable, which re-generating would not.
 */

/**
 * `url` with a cache-busting marker.
 *
 * Rate limits are commonly counted per URL, and an edge cache will happily
 * serve the same error response again — so retrying the byte-identical URL can
 * fail identically, and the button would look broken. The marker makes each
 * attempt a distinct request.
 */
export function withAttempt(url, attempt) {
  if (!attempt) return url
  const separator = url.includes('?') ? '&' : '?'
  return `${url}${separator}retry=${attempt}`
}
