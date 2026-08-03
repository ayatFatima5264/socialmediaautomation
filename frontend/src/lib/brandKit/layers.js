// ---------------------------------------------------------------------------
// Brand Kit layer model.
//
// A branded image is a base image plus an ordered list of layers. Layers are
// pure data — they carry no rendering logic — so the same list can be handed to
// three different consumers:
//
//   • BrandOverlay.jsx  -> SVG, for live display (stays sharp at any zoom)
//   • rasterize.js      -> Canvas, to flatten for publishing
//   • (future) an editor -> drag/resize by mutating offset + size
//
// GEOMETRY: every position and size is expressed as a FRACTION of the frame
// (0..1), never in pixels. A layer therefore describes the same visual result
// on a 1080x1080 Instagram square and a 240px preview thumbnail, which is what
// makes the system resolution-independent rather than hardcoded to one size.
// `resolveLayer` converts fractions to pixels for a given frame.
//
// ANCHORING: a layer's offset is measured from its anchor corner, not from the
// origin. A logo anchored bottom-right with offset {x: .04, y: .04} sits 4% in
// from the bottom-right regardless of the frame's aspect ratio — so switching
// a post from square to portrait does not require repositioning anything.
// ---------------------------------------------------------------------------

export const LAYER_TYPES = {
  IMAGE: 'image', // logo, photo, replaced background art
  TEXT: 'text', // company name, website, phone, email, headlines
  RECT: 'rect', // colour bar, badge background, scrim, rectangle shape
  // ---- Editor shapes (Phase 3) ----------------------------------------
  ELLIPSE: 'ellipse',
  LINE: 'line',
  ARROW: 'arrow',
  // A full-bleed fill sitting under everything. Kept distinct from RECT so
  // the editor can guarantee exactly one, and never let it be reordered
  // above the artwork.
  BACKGROUND: 'background',
}

// Fonts offered in the editor. Restricted to families that are either already
// loaded (Inter) or universally available, because a font that fails to load
// renders at a different width and silently breaks the layout it was sized for.
export const FONT_FAMILIES = [
  { value: 'Inter, system-ui, sans-serif', label: 'Inter' },
  { value: 'Georgia, serif', label: 'Georgia' },
  { value: '"Times New Roman", Times, serif', label: 'Times' },
  { value: '"Courier New", monospace', label: 'Courier' },
  { value: 'Verdana, Geneva, sans-serif', label: 'Verdana' },
  { value: '"Trebuchet MS", sans-serif', label: 'Trebuchet' },
  { value: 'Impact, sans-serif', label: 'Impact' },
]

export const TEXT_ALIGNMENTS = ['left', 'center', 'right']

// [xFactor, yFactor] — where in the frame the anchor point sits.
export const ANCHORS = {
  'top-left': [0, 0],
  'top-center': [0.5, 0],
  'top-right': [1, 0],
  'center-left': [0, 0.5],
  center: [0.5, 0.5],
  'center-right': [1, 0.5],
  'bottom-left': [0, 1],
  'bottom-center': [0.5, 1],
  'bottom-right': [1, 1],
}

// The four corners offered for logo placement in the UI.
export const LOGO_POSITIONS = [
  { value: 'top-left', label: 'Top left' },
  { value: 'top-right', label: 'Top right' },
  { value: 'bottom-left', label: 'Bottom left' },
  { value: 'bottom-right', label: 'Bottom right' },
]

let seq = 0
const nextId = (prefix) => `${prefix}-${(seq += 1)}`

/**
 * Create a layer. Callers supply fractional geometry; defaults keep every
 * layer valid even when a template only sets the fields it cares about.
 */
export function createLayer(type, props = {}) {
  return {
    id: props.id || nextId(type),
    type,
    anchor: 'bottom-right',
    // Distance from the anchor, as a fraction of frame width/height.
    offset: { x: 0.04, y: 0.04 },
    // Fraction of frame width/height. Text uses `size.h` as its font size.
    size: { w: 0.2, h: 0.2 },
    opacity: 1,
    z: 0,
    // Marks layers a future editor may move/resize. Scrims are locked because
    // they exist to guarantee contrast, not to be repositioned.
    locked: false,
    ...props,
  }
}

/**
 * Convert a layer's fractional geometry into pixels for a concrete frame.
 *
 * @param {object} layer
 * @param {{width:number,height:number}} frame
 * @returns {{x:number,y:number,w:number,h:number}} top-left origin box
 */
export function resolveLayer(layer, frame) {
  const { width: W, height: H } = frame
  const [ax, ay] = ANCHORS[layer.anchor] || ANCHORS['bottom-right']

  // `square` layers size off the SHORTER edge, so a logo occupies the same
  // visual weight on a 1:1, a 4:5, and a 16:9 frame. Sizing off width alone
  // would make it square but oversized on landscape (16% of a 1920px width is
  // 28% of a 1080px height); sizing each axis independently would make it a
  // non-square rectangle. The shorter edge is the only stable reference.
  const short = Math.min(W, H)
  const w = layer.square ? (layer.size?.w ?? 0) * short : (layer.size?.w ?? 0) * W
  const h = layer.square ? w : (layer.size?.h ?? 0) * H
  const ox = (layer.offset?.x ?? 0) * W
  const oy = (layer.offset?.y ?? 0) * H

  // Offsets always push the layer INWARD from its anchor, so the same offset
  // reads as "4% margin" at every corner instead of flipping sign per corner.
  //
  // A mid anchor (centre, top-centre, centre-left…) has no inward direction on
  // that axis, so its offset is a plain displacement: positive is right and
  // down, matching the direction the editor drags. Treating it as zero — which
  // is what "no inward direction" used to mean here — quietly collapsed every
  // line of a centred headline onto the same baseline, and made centred layers
  // impossible to drag in the editor.
  let x = ax * W - ax * w
  let y = ay * H - ay * h
  x += ax === 1 ? -ox : ox
  y += ay === 1 ? -oy : oy

  return { x, y, w, h }
}

// Text alignment follows the anchor unless the layer overrides it, so a
// bottom-right block reads right-aligned without templates restating it.
export function textAlignFor(layer) {
  if (layer.align) return layer.align
  const [ax] = ANCHORS[layer.anchor] || [0]
  return ax === 1 ? 'right' : ax === 0.5 ? 'center' : 'left'
}

// Painter's order. Stable within equal z so template order is preserved.
export function sortLayers(layers) {
  return [...layers].sort((a, b) => (a.z ?? 0) - (b.z ?? 0))
}

// ---- Colour helpers --------------------------------------------------------

const HEX = /^#([0-9a-f]{6})$/i

export function isHex(value) {
  return HEX.test(String(value || '').trim())
}

/**
 * Relative luminance (WCAG). Used to decide whether text on a brand colour
 * should be white or near-black — hardcoding white breaks the moment someone
 * picks a pale brand colour.
 */
export function luminance(hex) {
  const m = HEX.exec(String(hex || '').trim())
  if (!m) return 0
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16) / 255)
  const lin = (c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
}

export function readableOn(background) {
  return luminance(background) > 0.45 ? '#111827' : '#ffffff'
}

/** Primary/secondary brand colours with sensible fallbacks. */
export function paletteOf(brandKit) {
  const colors = (brandKit?.brand_colors || []).filter(isHex)
  return {
    primary: colors[0] || '#1f8a5b',
    secondary: colors[1] || colors[0] || '#0b3d2e',
    all: colors,
  }
}

/** True when there is anything worth overlaying. */
export function hasBrandAssets(brandKit) {
  if (!brandKit) return false
  return Boolean(
    brandKit.logo_url ||
      brandKit.business_name ||
      brandKit.website ||
      brandKit.phone ||
      brandKit.email ||
      (brandKit.brand_colors || []).length,
  )
}
