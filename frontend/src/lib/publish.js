// Interpret a Post (PostRead) returned by the publish endpoint.
//
// The backend returns the post object even when publishing did NOT really
// succeed on the platform:
//   * status === 'failed' → the platform rejected it; `error` explains why.
//   * external_id like 'sim_<platform>_...' → no real adapter/connected account,
//     so it was published by the SimulatedPublisher (not on the real network).
// Anything else is a genuine, real publish.

export function isSimulated(post) {
  return (
    typeof post?.external_id === 'string' && post.external_id.startsWith('sim_')
  )
}

// Returns { ok, simulated, message } describing what actually happened, so the
// UI can stop claiming "(simulated)" unconditionally.
export function publishOutcome(post, platformLabel = 'the platform') {
  if (!post || post.status === 'failed') {
    return {
      ok: false,
      simulated: false,
      message: post?.error || `Publish to ${platformLabel} failed`,
    }
  }
  if (isSimulated(post)) {
    return {
      ok: true,
      simulated: true,
      message: `Published to ${platformLabel} (simulated — connect a real ${platformLabel} account to post for real)`,
    }
  }
  return { ok: true, simulated: false, message: `Published to ${platformLabel}` }
}
