import { useCallback, useEffect, useRef } from 'react'
import BrandOverlay from '../brand/BrandOverlay.jsx'
import { resolveLayer, sortLayers, LAYER_TYPES } from '../../lib/brandKit/layers'
import { boxRatio, measureImage } from '../../lib/brandKit/editor/imageBox'

// ---------------------------------------------------------------------------
// The interactive editing surface.
//
// Rendering reuses BrandOverlay unchanged — the same component that draws the
// preview elsewhere — with a second, transparent SVG layered on top carrying
// hit targets and handles. Keeping interaction out of the renderer means what
// you edit is literally what gets exported; there is no "editor version" of
// the drawing code to drift.
//
// Pointer maths works in FRACTIONS of the frame, matching the layer model, so
// dragging behaves identically whether the canvas is displayed at 400px or
// 900px wide. Nothing here deals in screen pixels beyond converting the
// initial event coordinates.
// ---------------------------------------------------------------------------

const HANDLE = 9 // px, screen-space — handles shouldn't scale with the canvas

export default function EditorCanvas({
  document: doc,
  selectedId,
  onSelect,
  onDrag,
  onGestureStart,
  onGestureEnd,
}) {
  const ref = useRef(null)
  const gesture = useRef(null)

  const aspect = doc.size.width / doc.size.height
  const frame = { width: 1000, height: 1000 / aspect }

  // Every image's real proportions, keyed by source.
  //
  // A ref rather than state because nothing rendered depends on it: the only
  // reader is the resize gesture below, which runs imperatively. And measured
  // here rather than stored on the layer because it is a property of the
  // bytes, not of the document — writing it in would push a measurement onto
  // the undo stack and mark a freshly opened document dirty.
  const naturals = useRef(new Map())
  useEffect(() => {
    for (const layer of doc.layers) {
      if (layer.type !== LAYER_TYPES.IMAGE || !layer.src) continue
      if (naturals.current.has(layer.src)) continue
      naturals.current.set(layer.src, null) // claim it, so it is measured once
      measureImage(layer.src)
        .then((n) => naturals.current.set(layer.src, n))
        .catch(() => {}) // stays null; the gesture falls back to the box
    }
  }, [doc.layers])

  // Screen pixels -> frame fractions.
  const toFraction = useCallback((e) => {
    const rect = ref.current?.getBoundingClientRect()
    if (!rect) return { x: 0, y: 0 }
    return { x: (e.clientX - rect.left) / rect.width, y: (e.clientY - rect.top) / rect.height }
  }, [])

  const startGesture = (e, layer, mode) => {
    e.stopPropagation()
    e.preventDefault()
    onSelect(layer.id)
    if (layer.locked) return
    gesture.current = { layer, mode, origin: toFraction(e), start: { ...layer } }
    onGestureStart?.()
    e.currentTarget.setPointerCapture?.(e.pointerId)
  }

  const onPointerMove = (e) => {
    const g = gesture.current
    if (!g) return
    const now = toFraction(e)
    const dx = now.x - g.origin.x
    const dy = now.y - g.origin.y
    const { layer, start, mode } = g

    if (mode === 'move') {
      // Offsets are measured inward from the anchor, so a drag toward a
      // right/bottom anchor DECREASES its offset. Without this the layer would
      // move opposite the pointer for two of the four corners.
      const [ax, ay] = anchorFactors(layer.anchor)
      onDrag(layer.id, {
        offset: {
          x: clamp01((start.offset?.x ?? 0) + (ax === 1 ? -dx : dx)),
          y: clamp01((start.offset?.y ?? 0) + (ay === 1 ? -dy : dy)),
        },
      })
      return
    }

    if (mode === 'resize') {
      const min = 0.02
      const startW = start.size?.w ?? 0.2
      let w = Math.max(min, startW + dx)
      let h
      if (layer.type === LAYER_TYPES.TEXT) {
        // Text uses size.h as its font size, so resizing it should change the
        // type size rather than stretch a box that has no visual extent.
        h = Math.max(0.012, (start.size?.h ?? 0.05) + dy * 0.5)
      } else if (layer.type === LAYER_TYPES.IMAGE && layer.keepAspect !== false && !layer.square) {
        // A picture is letterboxed inside its box, so moving width and height
        // independently reintroduces the empty bands the box was sized to
        // avoid — dragging a corner to fill the frame only widened the gap.
        // Holding the PICTURE's ratio keeps it filling the box at every size.
        //
        // Reading the ratio off the box instead would only preserve whatever
        // shape it already has, so a box that does not match its image — one
        // from a template, or from before boxes were derived from pictures —
        // could never be dragged out of letterboxing. That is the one case
        // this handle exists for.
        const natural = naturals.current.get(layer.src)
        const ratio = natural ? boxRatio(natural, frame) : (start.size?.h ?? 0.2) / startW
        // Height follows width, so a mostly-vertical drag on the corner would
        // otherwise do nothing at all and read as a broken handle. Whichever
        // axis the pointer moved further along drives the size.
        const byHeight = dy / ratio
        w = Math.max(min, startW + (Math.abs(byHeight) > Math.abs(dx) ? byHeight : dx))
        h = Math.max(min, w * ratio)
      } else {
        h = Math.max(min, (start.size?.h ?? 0.2) + dy)
      }
      onDrag(layer.id, { size: { w, h } })
    }
  }

  const endGesture = () => {
    if (!gesture.current) return
    gesture.current = null
    onGestureEnd?.()
  }

  const selected = doc.layers.find((l) => l.id === selectedId)
  const selBox = selected ? resolveLayer(selected, frame) : null

  return (
    <div
      ref={ref}
      className="relative h-full w-full select-none overflow-hidden rounded-xl border border-line bg-inset shadow-sm"
      style={{ aspectRatio: `${doc.size.width} / ${doc.size.height}` }}
      onPointerMove={onPointerMove}
      onPointerUp={endGesture}
      onPointerLeave={endGesture}
      onPointerDown={() => onSelect(null)}
    >
      {/* Rendered output — identical to what export produces. */}
      <BrandOverlay layers={doc.layers} aspect={aspect} idPrefix="editor" />

      {/* Interaction layer: hit targets + selection handles. */}
      <svg
        viewBox={`0 0 ${frame.width} ${frame.height}`}
        preserveAspectRatio="none"
        className="absolute inset-0 h-full w-full"
      >
        {sortLayers(doc.layers)
          .filter((l) => l.type !== LAYER_TYPES.BACKGROUND)
          .map((layer) => {
            const box = resolveLayer(layer, frame)
            // Text has no filled area to click, so give it a usable band.
            const h = layer.type === LAYER_TYPES.TEXT ? box.h * 1.4 : box.h
            return (
              <rect
                key={layer.id}
                x={box.x}
                y={box.y}
                width={Math.max(box.w, 8)}
                height={Math.max(h, 8)}
                fill="transparent"
                style={{ cursor: layer.locked ? 'not-allowed' : 'move' }}
                onPointerDown={(e) => startGesture(e, layer, 'move')}
              />
            )
          })}

        {selBox && selected && (
          <g pointerEvents="none">
            <rect
              x={selBox.x}
              y={selBox.y}
              width={Math.max(selBox.w, 8)}
              height={Math.max(selected.type === LAYER_TYPES.TEXT ? selBox.h * 1.4 : selBox.h, 8)}
              fill="none"
              stroke="var(--accent)"
              strokeWidth="2.5"
              strokeDasharray="7 5"
              vectorEffect="non-scaling-stroke"
            />
            {!selected.locked && (
              <rect
                x={selBox.x + Math.max(selBox.w, 8) - HANDLE}
                y={selBox.y + Math.max(selBox.h, 8) - HANDLE}
                width={HANDLE * 2}
                height={HANDLE * 2}
                rx="3"
                fill="var(--accent)"
                stroke="#fff"
                strokeWidth="2"
                pointerEvents="all"
                style={{ cursor: 'nwse-resize' }}
                onPointerDown={(e) => startGesture(e, selected, 'resize')}
              />
            )}
          </g>
        )}
      </svg>
    </div>
  )
}

function anchorFactors(anchor) {
  const map = {
    'top-left': [0, 0], 'top-center': [0.5, 0], 'top-right': [1, 0],
    'center-left': [0, 0.5], center: [0.5, 0.5], 'center-right': [1, 0.5],
    'bottom-left': [0, 1], 'bottom-center': [0.5, 1], 'bottom-right': [1, 1],
  }
  return map[anchor] || [1, 1]
}

const clamp01 = (v) => Math.min(1, Math.max(-0.5, v))
