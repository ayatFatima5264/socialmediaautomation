// ---------------------------------------------------------------------------
// Browser-side video rendering.
//
// Image to Video and Slideshow Video do not need a generative video model —
// they need compositing. Animating a still and cutting between several images
// is camera work, not generation, so both are rendered here with two APIs
// every current browser ships: a <canvas> to draw the frames and
// MediaRecorder to capture that canvas into a real file.
//
// That makes these two tools genuinely free and genuinely offline: nothing
// reaches the network, no key, no quota, no per-render cost, and the file the
// user downloads is a real video rather than a placeholder.
//
// ---- What this deliberately does NOT do -----------------------------------
// It invents no imagery. It moves, crops, fades and captions pictures the user
// already has. Text to Video and Product Showcase are absent from this module
// for exactly that reason — inventing a shot is a model's job.
//
// ---- Constraints worth knowing --------------------------------------------
// * Recording is REAL TIME. MediaRecorder captures the canvas as it plays, so
//   a 15-second video takes 15 seconds to produce. The caller is given
//   progress so the UI can say so rather than appearing hung.
// * There is no audio track. A music bed needs audio the app does not have,
//   and a silent video is more honest than one with a stock loop nobody chose.
// * The container depends on what the browser can encode. MP4 is preferred
//   because it plays everywhere including the ad platforms; WebM is the
//   fallback. `render()` reports which one came back.
// ---------------------------------------------------------------------------

const FPS = 30

// Ordered by how widely the result can be uploaded, not by quality: an ad
// platform that rejects WebM makes a better-compressed WebM worthless.
const MIME_CANDIDATES = [
  'video/mp4;codecs=avc1.42E01E',
  'video/mp4',
  'video/webm;codecs=vp9',
  'video/webm;codecs=vp8',
  'video/webm',
]

/** The best container this browser can actually encode, or null if none. */
export function pickMimeType() {
  if (typeof MediaRecorder === 'undefined') return null
  return MIME_CANDIDATES.find((t) => MediaRecorder.isTypeSupported(t)) || null
}

/** Is rendering possible at all here? Checked before a button is offered. */
export function canRender() {
  return (
    typeof MediaRecorder !== 'undefined' &&
    typeof HTMLCanvasElement !== 'undefined' &&
    typeof HTMLCanvasElement.prototype.captureStream === 'function' &&
    !!pickMimeType()
  )
}

export const ASPECT_SIZES = {
  '1:1': [1080, 1080],
  '4:5': [1080, 1350],
  '9:16': [1080, 1920],
  '16:9': [1920, 1080],
  '2:3': [1080, 1620],
}

/** Load a File or URL into a decoded image. */
function loadImage(source) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    // Canvas is read back through captureStream, so a cross-origin image
    // without permissive CORS would taint it and kill the recording.
    img.crossOrigin = 'anonymous'
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('That image could not be loaded.'))
    img.src = source instanceof Blob ? URL.createObjectURL(source) : source
  })
}

const easeInOut = (t) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2)

/**
 * Draw `img` to fill the canvas at a given zoom and pan, cropping the overflow.
 *
 * Always cover, never letterbox: a bar down the side of a vertical ad reads as
 * a mistake, and the crop is what makes the movement visible.
 */
function drawCovered(ctx, img, w, h, zoom, panX, panY) {
  const scale = Math.max(w / img.width, h / img.height) * zoom
  const dw = img.width * scale
  const dh = img.height * scale
  // Pan is a fraction of the overflow, so an image with little overflow moves
  // little rather than tearing away from the frame edge.
  const dx = (w - dw) / 2 + panX * (dw - w) * 0.5
  const dy = (h - dh) / 2 + panY * (dh - h) * 0.5
  ctx.drawImage(img, dx, dy, dw, dh)
}

/** Camera moves, as start/end (zoom, panX, panY) triples. */
const MOTIONS = {
  'Slow zoom in': { from: [1.0, 0, 0], to: [1.18, 0, 0] },
  'Zoom out': { from: [1.18, 0, 0], to: [1.0, 0, 0] },
  'Pan left': { from: [1.12, 0.6, 0], to: [1.12, -0.6, 0] },
  'Pan right': { from: [1.12, -0.6, 0], to: [1.12, 0.6, 0] },
  Orbit: { from: [1.14, -0.4, -0.3], to: [1.14, 0.4, 0.3] },
  Static: { from: [1.0, 0, 0], to: [1.0, 0, 0] },
}

function drawCaption(ctx, text, w, h, alpha) {
  if (!text || alpha <= 0) return
  const pad = Math.round(w * 0.06)
  const size = Math.round(w * 0.055)

  ctx.save()
  ctx.globalAlpha = alpha

  // A scrim under the text, because a caption over a bright photo is a caption
  // nobody can read.
  const bandH = size * 2.6
  const grad = ctx.createLinearGradient(0, h - bandH * 1.6, 0, h)
  grad.addColorStop(0, 'rgba(0,0,0,0)')
  grad.addColorStop(1, 'rgba(0,0,0,0.62)')
  ctx.fillStyle = grad
  ctx.fillRect(0, h - bandH * 1.6, w, bandH * 1.6)

  ctx.fillStyle = '#ffffff'
  ctx.font = `700 ${size}px Inter, system-ui, sans-serif`
  ctx.textBaseline = 'bottom'

  // Wrap by measured width — a fixed character count breaks on long words and
  // on any language that is not English.
  const maxW = w - pad * 2
  const words = String(text).split(/\s+/)
  const lines = []
  let line = ''
  words.forEach((word) => {
    const next = line ? `${line} ${word}` : word
    if (ctx.measureText(next).width > maxW && line) {
      lines.push(line)
      line = word
    } else {
      line = next
    }
  })
  if (line) lines.push(line)

  lines.slice(-3).forEach((l, i, arr) => {
    ctx.fillText(l, pad, h - pad - (arr.length - 1 - i) * size * 1.25)
  })
  ctx.restore()
}

/**
 * Render a video and resolve with { blob, mimeType, extension }.
 *
 * @param {object}   opts
 * @param {Array}    opts.slides       [{ source, seconds, caption }]
 * @param {string}   opts.aspect       key of ASPECT_SIZES
 * @param {string}   opts.motion       key of MOTIONS (single-image mode)
 * @param {string}   opts.transition   'Cut' | 'Crossfade' | 'Slide' | 'Zoom blur'
 * @param {function} opts.onProgress   0..1
 * @param {AbortSignal} opts.signal
 */
export async function renderVideo({
  slides,
  aspect = '9:16',
  motion = 'Slow zoom in',
  transition = 'Crossfade',
  onProgress,
  signal,
}) {
  const mimeType = pickMimeType()
  if (!mimeType) {
    throw new Error('This browser cannot record video. Try Chrome, Edge or Firefox.')
  }
  if (!slides?.length) throw new Error('Add at least one image first.')

  const [w, h] = ASPECT_SIZES[aspect] || ASPECT_SIZES['9:16']

  const images = await Promise.all(slides.map((s) => loadImage(s.source)))
  const durations = slides.map((s) => Math.max(0.5, Number(s.seconds) || 3))
  const totalMs = durations.reduce((a, b) => a + b, 0) * 1000

  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d')
  ctx.imageSmoothingQuality = 'high'

  const stream = canvas.captureStream(FPS)
  const recorder = new MediaRecorder(stream, {
    mimeType,
    // Enough for 1080p motion without producing a file too large to upload.
    videoBitsPerSecond: 6_000_000,
  })

  const chunks = []
  recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data)

  const finished = new Promise((resolve, reject) => {
    recorder.onstop = () => resolve()
    recorder.onerror = (e) => reject(e.error || new Error('Recording failed.'))
  })

  const fadeMs = transition === 'Cut' ? 0 : 420
  const move = MOTIONS[motion] || MOTIONS['Slow zoom in']

  // Which slide is on screen at `t`, and how far through it we are.
  function locate(tMs) {
    let acc = 0
    for (let i = 0; i < durations.length; i += 1) {
      const ms = durations[i] * 1000
      if (tMs < acc + ms) return { index: i, local: (tMs - acc) / ms, slideMs: ms }
      acc += ms
    }
    const last = durations.length - 1
    return { index: last, local: 1, slideMs: durations[last] * 1000 }
  }

  recorder.start()
  const startedAt = performance.now()

  await new Promise((resolve) => {
    function frame() {
      if (signal?.aborted) {
        resolve()
        return
      }
      const elapsed = performance.now() - startedAt
      const t = Math.min(elapsed, totalMs)
      const { index, local, slideMs } = locate(t)

      ctx.fillStyle = '#000'
      ctx.fillRect(0, 0, w, h)

      // Single image: one continuous camera move across the whole clip.
      // Several images: a gentle push per slide, so the cut is not the only
      // thing moving.
      const single = images.length === 1
      const p = easeInOut(single ? t / totalMs : local)
      const [z0, x0, y0] = move.from
      const [z1, x1, y1] = move.to
      const zoom = single ? z0 + (z1 - z0) * p : 1.0 + 0.08 * p
      const panX = single ? x0 + (x1 - x0) * p : 0
      const panY = single ? y0 + (y1 - y0) * p : 0

      drawCovered(ctx, images[index], w, h, zoom, panX, panY)

      // Crossfade the incoming slide over the tail of the outgoing one.
      const remaining = slideMs * (1 - local)
      if (fadeMs && remaining < fadeMs && index + 1 < images.length) {
        const a = 1 - remaining / fadeMs
        ctx.save()
        ctx.globalAlpha = a
        drawCovered(ctx, images[index + 1], w, h, 1.0, 0, 0)
        ctx.restore()
      }

      // Captions fade in at the start of their slide and hold.
      const caption = slides[index]?.caption
      if (caption) {
        const inMs = 300
        drawCaption(ctx, caption, w, h, Math.min(1, (local * slideMs) / inMs))
      }

      onProgress?.(Math.min(1, t / totalMs))

      if (elapsed >= totalMs) {
        resolve()
        return
      }
      requestAnimationFrame(frame)
    }
    requestAnimationFrame(frame)
  })

  // A short tail so the encoder flushes the final frames rather than clipping
  // the last few — MediaRecorder stops on a chunk boundary, not on demand.
  await new Promise((r) => setTimeout(r, 220))
  recorder.stop()
  await finished
  stream.getTracks().forEach((t) => t.stop())

  const blob = new Blob(chunks, { type: mimeType })
  if (!blob.size) throw new Error('The recording came back empty. Try a shorter clip.')

  return {
    blob,
    mimeType,
    extension: mimeType.startsWith('video/mp4') ? 'mp4' : 'webm',
  }
}

/** Save a rendered blob under a sensible filename. */
export function downloadVideo(blob, extension, stem = 'ad') {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${stem}.${extension}`
  document.body.appendChild(a)
  a.click()
  a.remove()
  // Revoked on the next tick — revoking immediately cancels the download in
  // some browsers.
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
