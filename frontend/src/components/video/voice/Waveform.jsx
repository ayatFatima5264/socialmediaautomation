import { useEffect, useRef, useState } from 'react'

// ---------------------------------------------------------------------------
// A waveform drawn from the actual audio.
//
// The peaks come from decoding the file with the Web Audio API and reducing the
// samples — they are the real shape of the recording, so silence looks like
// silence and a loud passage looks loud. This matters more than it sounds: a
// decorative waveform made from random numbers is the single most common way an
// audio UI lies, and here it would be lying about the one thing the user is
// checking.
//
// While decoding, the component says "Reading audio" rather than showing bars
// that mean nothing. If decoding fails — an unusual codec, a browser without
// AudioContext — it says so and the player still works, because playback is
// the <audio> element's job and does not depend on this at all.
//
// Drawn on a canvas rather than as a few hundred DOM nodes: this repaints on
// every animation frame during playback to move the playhead.
// ---------------------------------------------------------------------------

const BAR_WIDTH = 3
const BAR_GAP = 2

/** Reduce decoded samples to one peak per bar. */
function peaksFrom(buffer, bars) {
  // Mono mix: a voice-over is centred, and averaging the channels avoids a
  // waveform that changes shape depending on which channel is louder.
  const channels = []
  for (let c = 0; c < buffer.numberOfChannels; c += 1) {
    channels.push(buffer.getChannelData(c))
  }

  const total = channels[0].length
  const block = Math.max(1, Math.floor(total / bars))
  const peaks = new Float32Array(bars)

  for (let i = 0; i < bars; i += 1) {
    const start = i * block
    const end = Math.min(total, start + block)
    let peak = 0
    for (let j = start; j < end; j += 1) {
      let sum = 0
      for (let c = 0; c < channels.length; c += 1) sum += channels[c][j]
      const value = Math.abs(sum / channels.length)
      if (value > peak) peak = value
    }
    peaks[i] = peak
  }

  // Normalise to the loudest peak so a quietly-recorded voice still fills the
  // box. Guarded: an all-silence buffer would divide by zero.
  const loudest = peaks.reduce((max, value) => (value > max ? value : max), 0)
  if (loudest > 0) {
    for (let i = 0; i < bars; i += 1) peaks[i] /= loudest
  }
  return peaks
}

export default function Waveform({ src, progress = 0, height = 72, onSeek }) {
  const canvasRef = useRef(null)
  const [peaks, setPeaks] = useState(null)
  const [state, setState] = useState('idle') // idle | decoding | ready | failed

  // ---- decode ------------------------------------------------------------
  useEffect(() => {
    if (!src) {
      setPeaks(null)
      setState('idle')
      return undefined
    }

    let cancelled = false
    let context = null
    setState('decoding')

    async function decode() {
      try {
        const Ctx = window.AudioContext || window.webkitAudioContext
        if (!Ctx) throw new Error('no AudioContext')

        const response = await fetch(src)
        const bytes = await response.arrayBuffer()
        if (cancelled) return

        context = new Ctx()
        const buffer = await context.decodeAudioData(bytes)
        if (cancelled) return

        const width = canvasRef.current?.clientWidth || 600
        setPeaks(peaksFrom(buffer, Math.floor(width / (BAR_WIDTH + BAR_GAP))))
        setState('ready')
      } catch {
        // Playback does not depend on this, so a decode failure is a missing
        // picture, not a broken player.
        if (!cancelled) setState('failed')
      } finally {
        // Browsers cap concurrent AudioContexts; leaking one per take would
        // stop decoding entirely after a handful of generations.
        context?.close?.()
      }
    }

    decode()
    return () => {
      cancelled = true
    }
  }, [src])

  // ---- draw --------------------------------------------------------------
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !peaks) return

    const dpr = window.devicePixelRatio || 1
    const width = canvas.clientWidth
    canvas.width = width * dpr
    canvas.height = height * dpr

    const ctx = canvas.getContext('2d')
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, width, height)

    // Read the palette off the page rather than hardcoding hex, so the
    // waveform follows the app's tokens like everything else does.
    const styles = getComputedStyle(document.documentElement)
    const accent = styles.getPropertyValue('--accent').trim() || '#1f8a5b'
    const muted = styles.getPropertyValue('--line').trim() || '#d0e9dc'

    const played = Math.round(peaks.length * Math.min(1, Math.max(0, progress)))
    const middle = height / 2

    for (let i = 0; i < peaks.length; i += 1) {
      // A floor of 2px: a silent passage should read as a quiet line, not as a
      // gap in the waveform that looks like missing audio.
      const barHeight = Math.max(2, peaks[i] * (height - 6))
      ctx.fillStyle = i < played ? accent : muted
      ctx.fillRect(
        i * (BAR_WIDTH + BAR_GAP),
        middle - barHeight / 2,
        BAR_WIDTH,
        barHeight,
      )
    }
  }, [peaks, progress, height])

  function seek(event) {
    if (!onSeek || state !== 'ready') return
    const box = event.currentTarget.getBoundingClientRect()
    onSeek(Math.min(1, Math.max(0, (event.clientX - box.left) / box.width)))
  }

  return (
    <div
      className="panel relative flex items-center justify-center overflow-hidden px-2"
      style={{ height }}
      onClick={seek}
      role={onSeek && state === 'ready' ? 'slider' : undefined}
      aria-label={onSeek && state === 'ready' ? 'Seek' : undefined}
      aria-valuenow={onSeek && state === 'ready' ? Math.round(progress * 100) : undefined}
      aria-valuemin={onSeek && state === 'ready' ? 0 : undefined}
      aria-valuemax={onSeek && state === 'ready' ? 100 : undefined}
    >
      {state === 'ready' && (
        <canvas
          ref={canvasRef}
          className={`h-full w-full ${onSeek ? 'cursor-pointer' : ''}`}
          style={{ height }}
        />
      )}

      {/* The canvas needs to exist to be measured, so it is rendered
          zero-height while decoding rather than not at all. */}
      {state !== 'ready' && <canvas ref={canvasRef} className="h-0 w-full" />}

      {state === 'idle' && (
        <p className="text-xs text-muted">Generate a voice-over to see its waveform.</p>
      )}
      {state === 'decoding' && (
        <p className="text-xs text-muted">Reading audio…</p>
      )}
      {state === 'failed' && (
        <p className="text-xs text-muted">
          Could not draw the waveform for this file — playback still works.
        </p>
      )}
    </div>
  )
}
