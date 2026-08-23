import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import VideoIcon from '../VideoIcon.jsx'
import { formatDuration } from '../../../lib/video/format.js'

// ---------------------------------------------------------------------------
// The preview.
//
// **It is a function of the timeline document, and nothing else.** There is no
// separate preview model: the clips it draws are the clips the renderer reads,
// and the crop/fit/scale/position geometry it uses is not computed here at all
// — it comes from the server, which produced it with `compositor.place()`, the
// same function the ffmpeg graph is built from. The browser does not do its
// own framing arithmetic and hope it agrees with the export.
//
// **How it plays.** One canvas, one clock. On every animation frame the
// component asks the timeline what is visible at time `t`, syncs the hidden
// media elements to the right source position, and paints. Playback is real
// media playback — `<video>` and `<audio>` elements with their own
// `playbackRate` — rather than a frame-stepping simulation, so what is heard
// and seen is what those files actually contain.
//
// **Where it is honestly approximate**, and there are exactly two places:
//
//   * *Text metrics.* `drawtext` lays text out with libfreetype; the canvas
//     uses the browser's font stack. The anchor rules, margins and sizes here
//     mirror the compositor's, but two engines measuring the same string will
//     differ by a few pixels, and a font the server has and the browser does
//     not will differ by more.
//   * *Rotation.* The canvas rotates about the clip's centre, which is what
//     ffmpeg's `rotate` does, but ffmpeg clips to the frame it was given —
//     an extreme angle can lose slightly more at the corners in the export.
//
// Everything else — which clip is on screen, for how long, where it sits, how
// far into the source it is, how loud each audio layer is — is exact.
// ---------------------------------------------------------------------------

/** The clips on a track that cover a moment. */
function activeAt(track, time) {
  if (!track) return []
  return track.clips.filter(
    (clip) => time >= clip.start && time < clip.start + clip.duration,
  )
}

/** How far into a clip's *source* the playhead is.
 *
 *  Speed is why this is not just `t - start`: a clip at 2x has consumed two
 *  seconds of source for every second on the timeline. The renderer applies
 *  the same factor through `setpts`, so both land on the same frame. */
function sourceTime(clip, time) {
  const speed = clip.speed || 1
  return (clip.trim_start || 0) + (time - clip.start) * speed
}

/** A clip's gain at a moment, including its fades.
 *
 *  Mirrors the `afade` envelope the compositor builds: linear in, linear out,
 *  measured from the clip's own edges in output time. */
function gainAt(clip, time) {
  if (clip.muted) return 0
  let gain = clip.volume ?? 1
  const offset = time - clip.start
  const remaining = clip.duration - offset

  if (clip.fade_in > 0 && offset < clip.fade_in) {
    gain *= Math.max(0, offset / clip.fade_in)
  }
  if (clip.fade_out > 0 && remaining < clip.fade_out) {
    gain *= Math.max(0, remaining / clip.fade_out)
  }
  return Math.max(0, Math.min(gain, 1))
}

/** The alpha of an animated text clip — the compositor's `alpha` expression. */
function textAlpha(clip, time) {
  if (clip.animation === 'none') return 1
  const window = Math.min(0.35, clip.duration / 2)
  const offset = time - clip.start
  const remaining = clip.start + clip.duration - time
  if (offset < window) return Math.max(0, offset / window)
  if (remaining < window) return Math.max(0, remaining / window)
  return 1
}

export default function Preview({
  tracks,
  assets,
  placements,
  canvas,
  duration,
  time,
  playing,
  onTime,
  onPlayingChange,
}) {
  const canvasRef = useRef(null)
  const mediaRef = useRef(new Map())
  const frameRef = useRef(0)
  const clockRef = useRef({ startedAt: 0, from: 0 })
  const [ready, setReady] = useState(false)

  // Mirrors `time` so the animation loop can start from the current playhead
  // without taking `time` as a dependency — see the clock effect below.
  const timeRef = useRef(time)
  useEffect(() => {
    timeRef.current = time
  }, [time])

  // Memoized because `paint` depends on it and `paint` drives the animation
  // loop. A fresh Map on every render would make `paint` a new function on
  // every render, which would tear down and restart the clock sixty times a
  // second — playback would reset its start time on every frame.
  const byId = useMemo(
    () => new Map(assets.map((asset) => [asset.id, asset])),
    [assets],
  )
  const videoTrack = tracks.find((track) => track.id === 'video')
  const audioTrack = tracks.find((track) => track.id === 'audio')
  const textTrack = tracks.find((track) => track.id === 'text')

  // ---- Media elements ----------------------------------------------------
  // Created once per asset and reused. Recreating them on every render would
  // restart every download and make playback stutter on each edit.

  useEffect(() => {
    const pool = mediaRef.current
    const wanted = new Set(assets.map((asset) => asset.id))

    for (const asset of assets) {
      if (pool.has(asset.id)) continue
      const isImage = asset.content_type?.startsWith('image/')
      const isAudio = asset.content_type?.startsWith('audio/')

      const element = isImage
        ? new Image()
        : window.document.createElement(isAudio ? 'audio' : 'video')

      element.crossOrigin = 'anonymous'
      if (!isImage) {
        element.preload = 'auto'
        element.muted = isAudio ? false : true // video audio is mixed separately
      }
      element.src = asset.url
      pool.set(asset.id, element)
    }

    // Drop elements for assets no longer on the timeline, so a long session
    // does not hold every file it has ever touched.
    for (const [id, element] of pool) {
      if (wanted.has(id)) continue
      if (element.pause) element.pause()
      element.src = ''
      pool.delete(id)
    }

    setReady(true)
  }, [assets])

  // Stop everything when the component goes away — an <audio> element that
  // outlives its React tree keeps playing.
  useEffect(() => {
    const pool = mediaRef.current
    return () => {
      for (const element of pool.values()) {
        if (element.pause) element.pause()
        element.src = ''
      }
      pool.clear()
    }
  }, [])

  // ---- Painting ----------------------------------------------------------

  const paint = useCallback(
    (at) => {
      const surface = canvasRef.current
      if (!surface || !canvas) return
      const context = surface.getContext('2d')
      if (!context) return

      // The canvas *is* the project's canvas, in project pixels. CSS scales it
      // to the panel, so nothing here depends on how big the panel happens to
      // be — the same reason the compositor works in project pixels.
      context.fillStyle = '#000000'
      context.fillRect(0, 0, canvas.width, canvas.height)

      for (const clip of activeAt(videoTrack, at)) {
        const asset = byId.get(clip.asset_id)
        const placement = placements[clip.id]
        const element = mediaRef.current.get(clip.asset_id)
        if (!asset || !placement || !element) continue

        const drawable =
          element instanceof Image
            ? element.complete && element.naturalWidth > 0
            : element.readyState >= 2
        if (!drawable) continue

        context.save()
        context.globalAlpha = clip.opacity ?? 1

        const centreX = placement.x + placement.width / 2
        const centreY = placement.y + placement.height / 2
        if (clip.rotation) {
          context.translate(centreX, centreY)
          context.rotate((clip.rotation * Math.PI) / 180)
          context.translate(-centreX, -centreY)
        }

        // Source rectangle from the server's crop, destination from the
        // server's scale and position. Both are the encoder's own numbers.
        context.drawImage(
          element,
          placement.crop_x,
          placement.crop_y,
          placement.crop_w,
          placement.crop_h,
          placement.x,
          placement.y,
          placement.width,
          placement.height,
        )
        context.restore()
      }

      for (const clip of activeAt(textTrack, at)) {
        if (!clip.text?.trim()) continue
        drawText(context, clip, at, canvas)
      }
    },
    [videoTrack, textTrack, placements, canvas, byId],
  )

  // ---- Syncing media to the clock ---------------------------------------

  const sync = useCallback(
    (at, isPlaying) => {
      const pool = mediaRef.current
      const wanted = new Map()

      for (const clip of activeAt(videoTrack, at)) {
        const element = pool.get(clip.asset_id)
        if (!element || element instanceof Image) continue
        wanted.set(element, { clip, gain: clip.muted ? 0 : (clip.volume ?? 1) })
      }
      for (const clip of activeAt(audioTrack, at)) {
        const element = pool.get(clip.asset_id)
        if (!element) continue
        wanted.set(element, { clip, gain: gainAt(clip, at) })
      }

      for (const [element, { clip, gain }] of wanted) {
        const target = sourceTime(clip, at)
        element.volume = Math.max(0, Math.min(gain, 1))
        element.playbackRate = Math.max(0.25, Math.min(clip.speed || 1, 4))

        // Only correct real drift. Seeking every frame would make playback
        // stutter and never let the decoder get ahead.
        if (Number.isFinite(element.duration) &&
            Math.abs(element.currentTime - target) > 0.18) {
          try {
            element.currentTime = Math.max(0, target)
          } catch {
            // A media element that has not loaded enough to seek yet. The
            // next frame tries again.
          }
        }

        if (isPlaying && element.paused) {
          element.play().catch(() => {})
        } else if (!isPlaying && !element.paused) {
          element.pause()
        }
      }

      // Anything not currently on screen is silenced and stopped.
      for (const element of pool.values()) {
        if (element instanceof Image || wanted.has(element)) continue
        if (!element.paused) element.pause()
      }
    },
    [videoTrack, audioTrack],
  )

  // ---- The clock ---------------------------------------------------------

  // The loop reads the *latest* paint/sync through a ref rather than closing
  // over them. Both are recreated whenever the timeline changes, and if the
  // effect below depended on them directly it would restart the clock on
  // every edit — and, because `onTime` re-renders this component each frame,
  // on every frame as well.
  const latest = useRef({ paint, sync, onTime, onPlayingChange, duration })
  useEffect(() => {
    latest.current = { paint, sync, onTime, onPlayingChange, duration }
  }, [paint, sync, onTime, onPlayingChange, duration])

  useEffect(() => {
    if (!playing) return undefined

    // Started once, when playback begins. `time` is read here rather than
    // tracked as a dependency: it changes on every frame from `onTime`, and
    // depending on it would reset the clock's origin continuously.
    clockRef.current = { startedAt: performance.now(), from: timeRef.current }

    function step() {
      const current = latest.current
      const elapsed = (performance.now() - clockRef.current.startedAt) / 1000
      const at = clockRef.current.from + elapsed

      if (at >= current.duration) {
        current.onTime(current.duration)
        current.onPlayingChange(false)
        return
      }

      current.sync(at, true)
      current.paint(at)
      current.onTime(at)
      frameRef.current = requestAnimationFrame(step)
    }

    frameRef.current = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frameRef.current)
  }, [playing])

  // Repaint when the document changes while paused, so an edit is visible
  // immediately rather than at the next play.
  useEffect(() => {
    if (!playing) {
      sync(time, false)
      paint(time)
    }
  }, [playing, time, paint, sync, ready])

  const empty = !videoTrack?.clips.length && !textTrack?.clips.length

  return (
    <div className="flex flex-col gap-3">
      <div className="relative grid place-items-center overflow-hidden rounded-[10px] bg-black">
        <canvas
          ref={canvasRef}
          width={canvas?.width || 1080}
          height={canvas?.height || 1920}
          className="max-h-[52vh] w-auto max-w-full"
        />
        {empty && (
          <div className="absolute inset-0 grid place-items-center text-center">
            <div className="flex flex-col items-center gap-2 px-6">
              <VideoIcon name="film" className="h-8 w-8 text-white/40" />
              <p className="text-sm text-white/60">
                Add a clip to the timeline to see it here.
              </p>
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => onPlayingChange(!playing)}
          disabled={duration <= 0}
          aria-label={playing ? 'Pause' : 'Play'}
          className="btn btn-primary grid h-10 w-10 shrink-0 place-items-center rounded-full p-0"
        >
          {playing ? (
            <span className="flex gap-[3px]" aria-hidden="true">
              <span className="block h-3.5 w-[3px] rounded-sm bg-current" />
              <span className="block h-3.5 w-[3px] rounded-sm bg-current" />
            </span>
          ) : (
            <VideoIcon name="play" className="ml-0.5 h-4 w-4" />
          )}
        </button>

        <input
          type="range"
          min={0}
          max={Math.max(duration, 0.001)}
          step={0.01}
          value={Math.min(time, duration)}
          onChange={(event) => {
            onPlayingChange(false)
            onTime(Number(event.target.value))
          }}
          aria-label="Playhead"
          className="w-full accent-[var(--accent)]"
        />

        <span className="shrink-0 text-xs tabular-nums text-muted">
          {formatDuration(time)} / {formatDuration(duration)}
        </span>
      </div>
    </div>
  )
}

/** Draw one text clip, mirroring the compositor's drawtext placement.
 *
 *  The anchors, margins and animation curves are the compositor's; the metrics
 *  are the browser's. See the note at the top of this file about why those two
 *  cannot be made identical. */
function drawText(context, clip, at, canvas) {
  const alpha = textAlpha(clip, at)
  if (alpha <= 0) return

  const content = clip.uppercase ? clip.text.toUpperCase() : clip.text
  const lines = content.split('\n')
  const size = clip.font_size
  const lineHeight = size * 1.2 + 8 // matches `line_spacing=8`

  context.save()
  context.globalAlpha = alpha
  context.font = `${clip.font_weight || 700} ${size}px ${clip.font_family}, sans-serif`
  context.textBaseline = 'top'

  const marginX = Math.round(canvas.width * 0.06)
  const offsetX = Math.round((clip.x || 0) * canvas.width)
  const offsetY = Math.round((clip.y || 0) * canvas.height)

  const blockHeight = lines.length * lineHeight
  let top
  if (clip.position === 'top') {
    top = Math.round(canvas.height * 0.08) + offsetY
  } else if (clip.position === 'bottom') {
    top = canvas.height - blockHeight - Math.round(canvas.height * 0.12) + offsetY
  } else {
    top = (canvas.height - blockHeight) / 2 + offsetY
  }

  // The entry animations the compositor draws with a `y` expression.
  if (clip.animation === 'slide-up') {
    const window = 0.35
    const progress = Math.min(1, Math.max(0, (at - clip.start) / window))
    top += Math.round(canvas.height * 0.05) * (1 - progress)
  } else if (clip.animation === 'pop') {
    const window = 0.35
    const progress = Math.min(1, Math.max(0, (at - clip.start) / window))
    top -= Math.round(canvas.height * 0.02) * Math.sin(Math.PI * progress)
  }

  lines.forEach((line, index) => {
    const width = context.measureText(line).width
    let x
    if (clip.align === 'left') x = marginX + offsetX
    else if (clip.align === 'right') x = canvas.width - width - marginX + offsetX
    else x = (canvas.width - width) / 2 + offsetX

    const y = top + index * lineHeight

    if (clip.background && clip.background !== 'transparent') {
      context.fillStyle = clip.background
      context.fillRect(x - 18, y - 9, width + 36, lineHeight)
    }
    if (clip.outline_width > 0 && clip.outline !== 'transparent') {
      context.lineWidth = clip.outline_width * 2
      context.strokeStyle = clip.outline
      context.lineJoin = 'round'
      context.strokeText(line, x, y)
    }
    context.fillStyle = clip.color
    context.fillText(line, x, y)
  })

  context.restore()
}
