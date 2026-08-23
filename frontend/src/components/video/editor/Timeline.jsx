import { useCallback, useEffect, useRef, useState } from 'react'
import VideoIcon from '../VideoIcon.jsx'
import { formatDuration } from '../../../lib/video/format.js'

// ---------------------------------------------------------------------------
// The timeline.
//
// Three lanes, one per track, sharing one horizontal scale. A clip is a
// positioned div; a drag moves it, the handles at its edges trim it, and the
// playhead decides where a split happens.
//
// **Dragging is local; committing is not.** While the pointer is down the clip
// follows it using local state, so the interaction is at screen refresh rate.
// On release the *operation* is posted and the server's document replaces
// local state wholesale. The editor never keeps a document it computed itself
// — see the note in useTimelineEditor.js. If the server refuses the edit (an
// overlap, a clip trimmed to nothing) the drag simply disappears, because the
// document it is drawn from never changed.
//
// **Snapping is to clip edges and the playhead**, not to a grid. A grid at
// this zoom is arbitrary; what people actually want is a cut that lands
// exactly where the last one ended, with no one-frame gap of black.
// ---------------------------------------------------------------------------

// Pixels per second at zoom 1. Chosen so a 60-second project fits a laptop
// screen without scrolling, which is the length most of these videos are.
const BASE_SCALE = 18
const ZOOM_LEVELS = [0.5, 0.75, 1, 1.5, 2, 3, 4]

// How close, in pixels, an edge has to be to snap.
const SNAP_PIXELS = 8

const TRACK_META = {
  video: { label: 'Video', icon: 'film', tint: 'bg-indigo-500/15 border-indigo-400/50' },
  audio: { label: 'Audio', icon: 'music', tint: 'bg-violet-500/15 border-violet-400/50' },
  text: { label: 'Text', icon: 'captions', tint: 'bg-sky-500/15 border-sky-400/50' },
}

/** The nearest interesting time to `value`, or `value` itself. */
function snap(value, candidates, secondsPerPixel) {
  const tolerance = SNAP_PIXELS * secondsPerPixel
  let best = value
  let distance = tolerance
  for (const candidate of candidates) {
    const gap = Math.abs(candidate - value)
    if (gap < distance) {
      distance = gap
      best = candidate
    }
  }
  return Math.max(0, best)
}

export default function Timeline({
  tracks,
  assets,
  duration,
  time,
  selectedId,
  onSelect,
  onSeek,
  onMove,
  onTrim,
  onSplit,
  onDelete,
  busy,
}) {
  const [zoom, setZoom] = useState(1)
  const [drag, setDrag] = useState(null)
  const laneRef = useRef(null)

  const scale = BASE_SCALE * zoom
  const secondsPerPixel = 1 / scale
  // Always leave room past the end so a clip can be dragged beyond the last
  // one; a timeline that stops exactly at the content cannot be extended.
  const span = Math.max(duration + 10, 30)

  const byId = new Map(assets.map((asset) => [asset.id, asset]))

  // Splitting needs the playhead strictly inside the selected clip — the server
  // refuses anything closer than MIN_CLIP_SECONDS to either edge, because a
  // split there would leave a sliver too short to be a clip. Mirror that rule
  // so the button is not offered for an operation that is going to be refused.
  const MIN_CLIP = 0.05
  const selectedClip = selectedId
    ? tracks.flatMap((track) => track.clips).find((clip) => clip.id === selectedId)
    : null
  const canSplit = Boolean(
    selectedClip &&
      time - selectedClip.start >= MIN_CLIP &&
      time - selectedClip.start <= selectedClip.duration - MIN_CLIP,
  )

  // ---- Dragging ----------------------------------------------------------

  const onPointerDown = useCallback(
    (event, clip, mode) => {
      event.preventDefault()
      event.stopPropagation()
      onSelect(clip.id)
      if (clip.locked) return

      setDrag({
        mode,
        clipId: clip.id,
        trackId: clip.track,
        pointerStart: event.clientX,
        origin: { start: clip.start, duration: clip.duration },
        preview: { start: clip.start, duration: clip.duration },
      })
      event.currentTarget.setPointerCapture?.(event.pointerId)
    },
    [onSelect],
  )

  useEffect(() => {
    if (!drag) return undefined

    // Edges worth snapping to: every other clip's boundaries, the playhead,
    // and zero.
    const edges = [0, time]
    for (const track of tracks) {
      for (const clip of track.clips) {
        if (clip.id === drag.clipId) continue
        edges.push(clip.start, clip.start + clip.duration)
      }
    }

    function onMoveEvent(event) {
      const delta = (event.clientX - drag.pointerStart) * secondsPerPixel
      setDrag((current) => {
        if (!current) return current
        const { origin, mode } = current

        if (mode === 'move') {
          const start = snap(origin.start + delta, edges, secondsPerPixel)
          return { ...current, preview: { start, duration: origin.duration } }
        }
        if (mode === 'trim-end') {
          const end = snap(
            origin.start + origin.duration + delta, edges, secondsPerPixel,
          )
          return {
            ...current,
            preview: {
              start: origin.start,
              duration: Math.max(0.05, end - origin.start),
            },
          }
        }
        // trim-start
        const start = snap(origin.start + delta, edges, secondsPerPixel)
        const end = origin.start + origin.duration
        return {
          ...current,
          preview: { start: Math.min(start, end - 0.05), duration: Math.max(0.05, end - start) },
        }
      })
    }

    async function onUp() {
      const current = drag
      setDrag(null)
      if (!current) return

      const { mode, origin, preview, clipId } = current
      const moved =
        Math.abs(preview.start - origin.start) > 0.01 ||
        Math.abs(preview.duration - origin.duration) > 0.01
      if (!moved) return

      // Commit as an operation. The server decides whether it is allowed.
      if (mode === 'move') {
        await onMove(clipId, Number(preview.start.toFixed(3)))
      } else if (mode === 'trim-end') {
        await onTrim(clipId, 'end', Number((preview.start + preview.duration).toFixed(3)))
      } else {
        await onTrim(clipId, 'start', Number(preview.start.toFixed(3)))
      }
    }

    window.addEventListener('pointermove', onMoveEvent)
    window.addEventListener('pointerup', onUp)
    return () => {
      window.removeEventListener('pointermove', onMoveEvent)
      window.removeEventListener('pointerup', onUp)
    }
  }, [drag, secondsPerPixel, tracks, time, onMove, onTrim])

  // ---- Scrubbing ---------------------------------------------------------

  function seekFromEvent(event) {
    const lane = laneRef.current
    if (!lane) return
    const box = lane.getBoundingClientRect()
    const at = (event.clientX - box.left + lane.scrollLeft) * secondsPerPixel
    onSeek(Math.max(0, Math.min(at, duration)))
  }

  // ---- Keyboard ----------------------------------------------------------
  // The shortcuts an editor is unusable without. Bound on the window rather
  // than the lane so they work while the inspector has focus, and skipped
  // while a field is focused so typing a title does not delete a clip.

  useEffect(() => {
    function onKey(event) {
      const tag = event.target?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return

      if (event.key === 'Delete' || event.key === 'Backspace') {
        if (selectedId) {
          event.preventDefault()
          onDelete(selectedId)
        }
      } else if (event.key.toLowerCase() === 's' && !event.metaKey && !event.ctrlKey) {
        if (canSplit) {
          event.preventDefault()
          onSplit(selectedId, time)
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selectedId, canSplit, time, onDelete, onSplit])

  // ---- Ruler -------------------------------------------------------------
  // A tick every second, labelled every five — enough to read a position
  // without the labels colliding at any zoom this offers.

  const ticks = []
  for (let second = 0; second <= span; second += 1) {
    ticks.push(second)
  }

  return (
    <div className="card flex flex-col">
      {/* ---- Toolbar ---- */}
      <div className="flex flex-wrap items-center gap-2 border-b border-line p-3">
        <button
          className="btn btn-secondary btn-sm"
          onClick={() => canSplit && onSplit(selectedId, time)}
          disabled={!canSplit || busy}
          title={
            selectedId && !canSplit
              ? 'Move the playhead further into the clip to split it'
              : 'Split the selected clip at the playhead (S)'
          }
        >
          <VideoIcon name="scissors" className="h-4 w-4" />
          Split
        </button>
        <button
          className="btn btn-secondary btn-sm"
          onClick={() => selectedId && onDelete(selectedId)}
          disabled={!selectedId || busy}
          title="Delete the selected clip (Del)"
        >
          <VideoIcon name="trash" className="h-4 w-4" />
          Delete
        </button>

        <span className="ml-auto flex items-center gap-1.5 text-xs text-muted">
          <span className="tabular-nums">{formatDuration(time)}</span>
          <span aria-hidden="true">/</span>
          <span className="tabular-nums">{formatDuration(duration)}</span>
        </span>

        <div className="flex items-center gap-1">
          <button
            className="btn btn-ghost btn-sm px-2"
            onClick={() =>
              setZoom((z) => ZOOM_LEVELS[Math.max(0, ZOOM_LEVELS.indexOf(z) - 1)])
            }
            disabled={zoom === ZOOM_LEVELS[0]}
            aria-label="Zoom out"
          >
            −
          </button>
          <button
            className="btn btn-ghost btn-sm px-2"
            onClick={() =>
              setZoom((z) =>
                ZOOM_LEVELS[Math.min(ZOOM_LEVELS.length - 1, ZOOM_LEVELS.indexOf(z) + 1)],
              )
            }
            disabled={zoom === ZOOM_LEVELS[ZOOM_LEVELS.length - 1]}
            aria-label="Zoom in"
          >
            +
          </button>
        </div>
      </div>

      {/* ---- Lanes ---- */}
      <div className="flex">
        {/* Fixed track labels, outside the scroll area so they stay put. */}
        <div className="w-24 shrink-0 border-r border-line">
          <div className="h-7 border-b border-line" />
          {tracks.map((track) => (
            <div
              key={track.id}
              className="flex h-16 items-center gap-2 border-b border-line px-3 text-xs font-medium text-muted"
            >
              <VideoIcon name={TRACK_META[track.id]?.icon || 'film'} className="h-4 w-4" />
              {TRACK_META[track.id]?.label || track.label}
            </div>
          ))}
        </div>

        <div ref={laneRef} className="relative min-w-0 flex-1 overflow-x-auto">
          <div style={{ width: span * scale }}>
            {/* Ruler */}
            <div
              className="relative h-7 cursor-pointer border-b border-line bg-inset"
              onPointerDown={seekFromEvent}
            >
              {ticks.map((second) => (
                <span
                  key={second}
                  className="absolute top-0 h-full border-l border-line/70"
                  style={{ left: second * scale }}
                >
                  {second % 5 === 0 && (
                    <span className="absolute left-1 top-1 text-[10px] tabular-nums text-muted">
                      {formatDuration(second)}
                    </span>
                  )}
                </span>
              ))}
            </div>

            {tracks.map((track) => (
              <div
                key={track.id}
                className="relative h-16 border-b border-line"
                onPointerDown={(event) => {
                  if (event.target === event.currentTarget) {
                    onSelect(null)
                    seekFromEvent(event)
                  }
                }}
              >
                {track.clips.map((clip) => {
                  const dragging = drag?.clipId === clip.id
                  const start = dragging ? drag.preview.start : clip.start
                  const length = dragging ? drag.preview.duration : clip.duration
                  const asset = byId.get(clip.asset_id)
                  const missing = clip.asset_id && !asset

                  return (
                    <div
                      key={clip.id}
                      role="button"
                      tabIndex={0}
                      onPointerDown={(event) => onPointerDown(event, clip, 'move')}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          onSelect(clip.id)
                        }
                      }}
                      className={[
                        'absolute top-2 flex h-12 items-center overflow-hidden rounded-md border text-xs',
                        missing
                          ? 'border-rose-400/70 bg-rose-500/15'
                          : TRACK_META[track.id]?.tint || 'border-line bg-inset',
                        selectedId === clip.id
                          ? 'ring-2 ring-accent'
                          : 'hover:border-accent-line',
                        clip.locked ? 'cursor-not-allowed' : 'cursor-grab',
                        dragging ? 'opacity-80' : '',
                      ].join(' ')}
                      style={{
                        left: start * scale,
                        width: Math.max(8, length * scale),
                      }}
                      title={
                        missing
                          ? 'The file this clip uses is no longer in your library.'
                          : clip.label || asset?.title || clip.text || 'Clip'
                      }
                    >
                      {/* Trim handles. Wide enough to hit, narrow enough not
                          to swallow the body of a short clip. */}
                      <span
                        onPointerDown={(event) => onPointerDown(event, clip, 'trim-start')}
                        className="absolute left-0 top-0 h-full w-2 cursor-ew-resize bg-black/20 hover:bg-black/40"
                        aria-label="Trim the start"
                      />
                      <span className="pointer-events-none truncate px-3 font-medium text-body">
                        {missing && '⚠ '}
                        {clip.kind === 'text'
                          ? clip.text || 'Text'
                          : clip.label || asset?.title || clip.kind}
                      </span>
                      <span
                        onPointerDown={(event) => onPointerDown(event, clip, 'trim-end')}
                        className="absolute right-0 top-0 h-full w-2 cursor-ew-resize bg-black/20 hover:bg-black/40"
                        aria-label="Trim the end"
                      />
                    </div>
                  )
                })}
              </div>
            ))}

            {/* Playhead, over every lane. */}
            <div
              className="pointer-events-none absolute top-0 z-10 w-px bg-accent"
              style={{ left: time * scale, height: 28 + tracks.length * 64 }}
            >
              <span className="absolute -left-1 top-0 h-2 w-2 rounded-full bg-accent" />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
