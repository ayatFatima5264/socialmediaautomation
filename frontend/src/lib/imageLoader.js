// Queued image loader with fallback.
//
// Free image hosts (e.g. Pollinations) rate-limit concurrent requests with
// HTTP 429, so loading many images at once leaves some blank. This module:
//   1. Limits how many images preload at the same time (avoids the 429), and
//   2. Tries each candidate URL in order until one actually loads, so a
//      rate-limited or failed source falls back to the next.

const MAX_CONCURRENT = 2

let active = 0
const queue = []

function acquire() {
  if (active < MAX_CONCURRENT) {
    active += 1
    return Promise.resolve()
  }
  return new Promise((resolve) => queue.push(resolve))
}

function release() {
  active -= 1
  const next = queue.shift()
  if (next) {
    active += 1
    next()
  }
}

// Preload a single URL; resolves true if it loads, false on error/timeout.
function preload(url, timeoutMs = 45000) {
  return new Promise((resolve) => {
    const img = new Image()
    let done = false
    const finish = (ok) => {
      if (done) return
      done = true
      img.onload = null
      img.onerror = null
      resolve(ok)
    }
    const timer = setTimeout(() => finish(false), timeoutMs)
    img.onload = () => {
      clearTimeout(timer)
      finish(true)
    }
    img.onerror = () => {
      clearTimeout(timer)
      finish(false)
    }
    img.src = url
  })
}

const delay = (ms) => new Promise((r) => setTimeout(r, ms))

async function tryLoad(url) {
  await acquire()
  try {
    return await preload(url)
  } finally {
    release()
  }
}

// Try candidates in order (each through the concurrency gate). Returns the
// first URL that loads, or null if all fail. The primary AI source gets one
// retry after a short backoff, since its failures are usually a transient 429.
export async function loadFirstAvailable(candidates) {
  for (let i = 0; i < candidates.length; i++) {
    const url = candidates[i]
    if (!url) continue
    const attempts = i === 0 ? 2 : 1
    for (let a = 0; a < attempts; a++) {
      if (await tryLoad(url)) return url
      if (a + 1 < attempts) await delay(1500) // back off before retrying primary
    }
  }
  return null
}
