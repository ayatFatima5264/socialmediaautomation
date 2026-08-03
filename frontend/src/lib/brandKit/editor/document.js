// ---------------------------------------------------------------------------
// Editor document.
//
// A document is `{ size, layers }` and nothing else. Every operation below is
// PURE — it takes a document and returns a new one — which is what makes undo
// and redo a matter of keeping previous documents rather than writing an
// inverse for each of the twenty-odd edit operations.
//
// The layer model is the same one the Brand Kit and content templates already
// use, so a generated image opens in the editor with its existing layers
// intact and directly editable. Nothing is converted or flattened on the way
// in, which is why the preview and the editor cannot disagree about geometry.
// ---------------------------------------------------------------------------

import { LAYER_TYPES, createLayer, sortLayers } from '../layers.js'

// Z bands. Editor-added layers stack above generated content so a new text box
// is visible immediately rather than appearing behind the artwork it annotates.
export const Z_BANDS = {
  BACKGROUND: -1000,
  BASE_IMAGE: -500,
  CONTENT: 5,
  BRAND: 30,
  USER: 100,
}

export function createDocument({ size, layers = [] }) {
  return { size: { ...size }, layers: [...layers] }
}

/**
 * Seed a document from a generated image plus its existing overlay layers.
 * The image becomes a real layer so it can be replaced, cropped, or rotated
 * like anything else.
 */
export function documentFromImage({ imageUrl, size, overlayLayers = [] }) {
  const layers = []

  layers.push(
    createLayer(LAYER_TYPES.BACKGROUND, {
      id: 'background',
      fill: '#ffffff',
      anchor: 'top-left',
      offset: { x: 0, y: 0 },
      size: { w: 1, h: 1 },
      z: Z_BANDS.BACKGROUND,
      locked: true, // position is meaningless for a full-bleed fill
      structural: true,
    }),
  )

  if (imageUrl) {
    layers.push(
      createLayer(LAYER_TYPES.IMAGE, {
        id: 'base-image',
        src: imageUrl,
        anchor: 'top-left',
        offset: { x: 0, y: 0 },
        size: { w: 1, h: 1 },
        keepAspect: false, // fills the frame like object-fit: cover
        z: Z_BANDS.BASE_IMAGE,
        name: 'Background image',
        // Reorderable layers must never go behind the artwork — below it is
        // only the flat background fill, so 'send backward' past it would
        // make a layer vanish with no indication why.
        structural: true,
      }),
    )
  }

  return createDocument({ size, layers: [...layers, ...overlayLayers] })
}

// ---- Layer operations (all pure) ------------------------------------------

export function addLayer(doc, layer) {
  return { ...doc, layers: [...doc.layers, layer] }
}

export function updateLayer(doc, id, patch) {
  return {
    ...doc,
    layers: doc.layers.map((l) =>
      l.id === id ? { ...l, ...(typeof patch === 'function' ? patch(l) : patch) } : l,
    ),
  }
}

export function removeLayer(doc, id) {
  const layer = doc.layers.find((l) => l.id === id)
  // The background and base image are structural — deleting them leaves an
  // empty canvas with no way back short of undo.
  if (!layer || layer.type === LAYER_TYPES.BACKGROUND) return doc
  return { ...doc, layers: doc.layers.filter((l) => l.id !== id) }
}

export function duplicateLayer(doc, id) {
  const layer = doc.layers.find((l) => l.id === id)
  if (!layer) return doc
  const copy = {
    ...layer,
    id: `${layer.type}-${Math.round(performance.now())}-${doc.layers.length}`,
    // Nudge so the copy is visibly distinct rather than exactly on top.
    offset: { x: (layer.offset?.x ?? 0) + 0.03, y: (layer.offset?.y ?? 0) + 0.03 },
    z: Math.max(...doc.layers.map((l) => l.z ?? 0)) + 1,
  }
  return addLayer(doc, copy)
}

// ---- Z-ordering -----------------------------------------------------------
// Implemented as a swap with the adjacent layer in painter's order rather than
// by incrementing z. Incrementing produces no visible change when two layers
// already share a z value, which reads as the button being broken.

function reorder(doc, id, direction) {
  const movable = sortLayers(doc.layers.filter((l) => !l.structural))
  const index = movable.findIndex((l) => l.id === id)
  const target = index + direction
  if (index === -1 || target < 0 || target >= movable.length) return doc

  // Swap positions in the ordered array, then RENUMBER z sequentially.
  //
  // Swapping the two layers' z values instead looks equivalent but is not:
  // editor-added layers all start at the same z, and nudging both by ±1 moves
  // the layer past every sibling sharing that z rather than past exactly one.
  // Renumbering makes "one step" mean one step regardless of how the z values
  // arrived, and keeps forward/backward exact inverses of each other.
  const next = [...movable]
  ;[next[index], next[target]] = [next[target], next[index]]

  // Start above the structural band so renumbering never lifts a layer
  // beneath the artwork.
  const z = new Map(next.map((l, i) => [l.id, i + 1]))
  return {
    ...doc,
    layers: doc.layers.map((l) => (z.has(l.id) ? { ...l, z: z.get(l.id) } : l)),
  }
}

export const bringForward = (doc, id) => reorder(doc, id, 1)
export const sendBackward = (doc, id) => reorder(doc, id, -1)

// ---- Factories for the toolbar --------------------------------------------

let counter = 0
const uid = (prefix) => `${prefix}-${Date.now().toString(36)}-${(counter += 1)}`

// New layers land centred so they are immediately visible whatever the frame.
const centred = (w, h) => ({
  anchor: 'center',
  offset: { x: 0, y: 0 },
  size: { w, h },
})

export function newTextLayer(text = 'Your text') {
  return createLayer(LAYER_TYPES.TEXT, {
    id: uid('text'),
    name: 'Text',
    text,
    ...centred(0.7, 0.06),
    fill: '#ffffff',
    weight: 700,
    italic: false,
    align: 'center',
    fontFamily: 'Inter, system-ui, sans-serif',
    z: Z_BANDS.USER,
  })
}

export function newShapeLayer(kind) {
  const common = { id: uid(kind), name: kind[0].toUpperCase() + kind.slice(1), z: Z_BANDS.USER }

  if (kind === 'rectangle') {
    return createLayer(LAYER_TYPES.RECT, {
      ...common, ...centred(0.4, 0.25), fill: '#1f8a5b', radius: 0.01,
    })
  }
  if (kind === 'circle') {
    return createLayer(LAYER_TYPES.ELLIPSE, {
      ...common, ...centred(0.3, 0.3), square: true, fill: '#1f8a5b',
    })
  }
  if (kind === 'line') {
    return createLayer(LAYER_TYPES.LINE, {
      ...common, ...centred(0.5, 0.01), stroke: '#ffffff', strokeWidth: 0.006,
    })
  }
  return createLayer(LAYER_TYPES.ARROW, {
    ...common, ...centred(0.5, 0.06), stroke: '#ffffff', strokeWidth: 0.008,
  })
}

export function newImageLayer(src, { keepAspect = true } = {}) {
  return createLayer(LAYER_TYPES.IMAGE, {
    id: uid('image'),
    name: 'Image',
    src,
    ...centred(0.4, 0.4),
    keepAspect,
    z: Z_BANDS.USER,
  })
}

export function newLogoLayer(src) {
  return createLayer(LAYER_TYPES.IMAGE, {
    id: uid('logo'),
    name: 'Logo',
    src,
    anchor: 'bottom-right',
    offset: { x: 0.05, y: 0.05 },
    size: { w: 0.16, h: 0.16 },
    square: true,
    keepAspect: true,
    z: Z_BANDS.USER + 10,
  })
}

/** Human label for the layers list. */
export function layerLabel(layer) {
  if (layer.name) return layer.name
  if (layer.type === LAYER_TYPES.TEXT) return layer.text?.slice(0, 24) || 'Text'
  if (layer.type === LAYER_TYPES.BACKGROUND) return 'Background'
  return layer.type[0].toUpperCase() + layer.type.slice(1)
}
