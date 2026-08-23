import { useEffect, useRef, useState } from 'react'
import VideoIcon from '../VideoIcon.jsx'
import Waveform from './Waveform.jsx'
import { formatDuration } from '../../../lib/video/format.js'

// ---------------------------------------------------------------------------
// Play / pause, a real waveform, and the duration.
//
// Playback is a plain `<audio>` element, deliberately: it handles streaming,
// range requests, codecs and the OS media keys, none of which is worth
// reimplementing over the Web Audio API. The waveform reads the same file
// separately, purely to draw it.
//
// The displayed duration prefers the element's own `duration` over the one the
// server measured. They agree in practice — the server measures with ffmpeg —
// but if they ever disagree, the number next to a playhead should be the one
// that playhead is moving through.
// ---------------------------------------------------------------------------

export default function AudioPreview({ src, duration = 0, label }) {
  const audioRef = useRef(null)
  const [playing, setPlaying] = useState(false)
  const [position, setPosition] = useState(0)
  const [length, setLength] = useState(duration)
  const [failed, setFailed] = useState(false)

  // A new source resets everything: the old playhead means nothing against a
  // different file, and leaving `playing` true shows a pause button for audio
  // that is not playing.
  useEffect(() => {
    setPlaying(false)
    setPosition(0)
    setLength(duration)
    setFailed(false)
  }, [src, duration])

  function toggle() {
    const audio = audioRef.current
    if (!audio) return
    if (audio.paused) {
      // play() rejects when the browser blocks autoplay or the file will not
      // decode. Unhandled, that is an uncaught rejection and a button that
      // silently does nothing.
      audio.play().catch(() => setFailed(true))
    } else {
      audio.pause()
    }
  }

  function seekTo(fraction) {
    const audio = audioRef.current
    if (!audio || !Number.isFinite(audio.duration)) return
    audio.currentTime = fraction * audio.duration
    setPosition(fraction * audio.duration)
  }

  const progress = length > 0 ? position / length : 0

  return (
    <div className="flex flex-col gap-3">
      <Waveform src={src} progress={progress} onSeek={src ? seekTo : undefined} />

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={toggle}
          disabled={!src}
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

        <div className="min-w-0 flex-1">
          {label && <p className="truncate text-sm font-medium text-body">{label}</p>}
          <p className="text-xs tabular-nums text-muted">
            {formatDuration(position)} / {formatDuration(length)}
          </p>
        </div>
      </div>

      {failed && (
        <p className="text-xs text-rose-600">
          This browser could not play that audio. Downloading it should still work.
        </p>
      )}

      {src && (
        <audio
          ref={audioRef}
          src={src}
          preload="metadata"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => {
            setPlaying(false)
            setPosition(0)
          }}
          onTimeUpdate={(event) => setPosition(event.currentTarget.currentTime)}
          onLoadedMetadata={(event) => {
            const value = event.currentTarget.duration
            if (Number.isFinite(value) && value > 0) setLength(value)
          }}
          onError={() => setFailed(true)}
          className="hidden"
        />
      )}
    </div>
  )
}
