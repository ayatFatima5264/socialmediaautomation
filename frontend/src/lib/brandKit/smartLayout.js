// ---------------------------------------------------------------------------
// Smart text placement.
//
// A template declares where its text *should* go. A diffusion model does not
// always cooperate — ask for a clear lower third and you sometimes get a face
// there anyway. This module closes that loop: it reads the image that actually
// came back and decides where the text really goes.
//
// Two steps, deliberately separate:
//
//   analyzeZones()   — pure measurement. Downscales the image and reports, per
//                      candidate band, how busy it is and how bright.
//   choosePlacement()— pure decision. Given those measurements and the
//                      template's rules, picks a zone, a scrim strength, and
//                      an ink colour.
//   applyPlacement() — pure transform. Rewrites a built layer list to match.
//
// Everything degrades to the template's own layout: analysis returns null on a
// cross-origin image, a load failure, or a browser without canvas, and every
// consumer treats null as "use the template as declared". Nothing here is ever
// required for an image to render.
// ---------------------------------------------------------------------------

import { LAYER_TYPES } from './layers.js'

// Sampling resolution. 96px on the long edge is enough to tell a calm sky from
// a crowd — the measurement is about regions, not pixels — and keeps the whole
// pass to a fraction of a millisecond.
const SAMPLE = 96

// Candidate bands as [yStart, yEnd] fractions of frame height. They overlap
// slightly because a headline block does not respect a hard boundary.
const BANDS = {
  top: [0, 0.4],
  center: [0.28, 0.72],
  bottom: [0.6, 1],
}

/** Perceptual luminance, 0..1. */
const lum = (r, g, b) => (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    if (!String(src).startsWith('data:')) img.crossOrigin = 'anonymous'
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('image load failed'))
    img.src = src
  })
}

/**
 * Measure each candidate band of an image.
 *
 * "Busyness" is mean local contrast: the average absolute luminance step
 * between neighbouring samples. It is what actually matters for legibility —
 * text survives a dark area or a bright area, but not a detailed one — and it
 * is cheap, unlike edge detection or saliency.
 *
 * @returns {Promise<{top:object, center:object, bottom:object}|null>}
 *          per band { busy: 0..1, light: 0..1 }, or null if unmeasurable.
 */
export async function analyzeZones(src) {
  if (!src || typeof document === 'undefined') return null
  let img
  try {
    img = await loadImage(src)
  } catch {
    return null
  }

  const w = img.naturalWidth || img.width
  const h = img.naturalHeight || img.height
  if (!w || !h) return null

  const scale = SAMPLE / Math.max(w, h)
  const sw = Math.max(8, Math.round(w * scale))
  const sh = Math.max(8, Math.round(h * scale))

  let data
  try {
    const canvas = document.createElement('canvas')
    canvas.width = sw
    canvas.height = sh
    const ctx = canvas.getContext('2d', { willReadFrequently: true })
    if (!ctx) return null
    ctx.drawImage(img, 0, 0, sw, sh)
    // Throws a SecurityError if the host sent no CORS headers. That is a
    // normal outcome for some providers, not an error worth surfacing.
    data = ctx.getImageData(0, 0, sw, sh).data
  } catch {
    return null
  }

  // Luminance grid, then one pass per band over it.
  const grid = new Float32Array(sw * sh)
  for (let i = 0; i < sw * sh; i++) {
    grid[i] = lum(data[i * 4], data[i * 4 + 1], data[i * 4 + 2])
  }

  const measure = ([y0, y1]) => {
    const rowStart = Math.floor(y0 * sh)
    const rowEnd = Math.min(sh, Math.max(rowStart + 1, Math.ceil(y1 * sh)))
    let sum = 0
    let contrast = 0
    let n = 0
    let steps = 0
    for (let y = rowStart; y < rowEnd; y++) {
      for (let x = 0; x < sw; x++) {
        const v = grid[y * sw + x]
        sum += v
        n++
        if (x + 1 < sw) {
          contrast += Math.abs(v - grid[y * sw + x + 1])
          steps++
        }
        if (y + 1 < rowEnd) {
          contrast += Math.abs(v - grid[(y + 1) * sw + x])
          steps++
        }
      }
    }
    if (!n) return { busy: 0.5, light: 0.5 }
    // A mean step of ~0.12 already reads as visually noisy, so that is the
    // top of the scale rather than the theoretical maximum of 1.
    return {
      light: sum / n,
      busy: Math.min(1, steps ? contrast / steps / 0.12 : 0),
    }
  }

  return {
    top: measure(BANDS.top),
    center: measure(BANDS.center),
    bottom: measure(BANDS.bottom),
  }
}

/**
 * Decide where the text goes and how it should be treated.
 *
 * @param {object} layout    the template's layout rules
 * @param {object|null} zones  analyzeZones() output
 * @returns {{zone:string, busy:number, light:number, scrim:number, moved:boolean}}
 */
export function choosePlacement(layout, zones) {
  const declared = layout?.zone || 'bottom'
  const fallback = { zone: declared, busy: 0.5, light: 0.35, scrim: 1, moved: false }
  if (!zones) return fallback

  const here = zones[declared] || fallback
  const alternatives = (layout?.altZones || []).filter((z) => zones[z])

  let zone = declared
  let best = here
  for (const alt of alternatives) {
    // Only move for a clear win. Flipping a layout is a visible change, and
    // doing it over measurement noise makes the output feel unstable across
    // regenerations of the same post.
    if (zones[alt].busy < best.busy - 0.15) {
      zone = alt
      best = zones[alt]
    }
  }

  return {
    zone,
    busy: best.busy,
    light: best.light,
    // Busier or brighter areas need a stronger scrim for the text to hold;
    // a calm dark area needs barely any, and a heavy one there just looks
    // muddy. 0.6..1.35 keeps both ends usable.
    scrim: Math.max(0.6, Math.min(1.35, 0.72 + best.busy * 0.45 + best.light * 0.3)),
    moved: zone !== declared,
  }
}

/** Convenience: measure an image and decide, in one call. */
export async function planPlacement(src, layout) {
  return choosePlacement(layout, await analyzeZones(src))
}

// ---- Applying a placement --------------------------------------------------

const FLIP = {
  'bottom-left': 'top-left',
  'bottom-center': 'top-center',
  'bottom-right': 'top-right',
  'top-left': 'bottom-left',
  'top-center': 'bottom-center',
  'top-right': 'bottom-right',
}

/**
 * Move a layer from one edge band to the opposite one, preserving the stack's
 * internal reading order.
 *
 * A bottom-anchored layer's top edge sits at `1 - h - offset.y`. Within a band
 * of height B starting at `1 - B`, its position inside the band is therefore
 * `B - h - offset.y`. Anchoring to the top with that as the offset lands it at
 * the same position within the band at the other end of the frame — so a
 * headline above a subtitle stays above it, instead of being mirrored into
 * reverse order.
 */
function moveToBand(layer, band) {
  const anchor = FLIP[layer.anchor]
  if (!anchor) return layer
  const h = layer.square ? 0 : layer.size?.h ?? 0
  const y = band - h - (layer.offset?.y ?? 0)
  // Past the band the arithmetic stops meaning anything; leave it put and let
  // the validator clamp it rather than throwing it off the canvas.
  if (y < 0) return layer
  return { ...layer, anchor, offset: { ...layer.offset, y } }
}

// Scale an rgba colour's alpha, leaving anything else (hex, named) untouched.
const scaleAlpha = (color, factor, cap = 0.92) =>
  String(color).replace(
    /rgba?\(([^)]+?),\s*([\d.]+)\)/,
    (_, rgb, a) => `rgba(${rgb}, ${Math.min(cap, Number(a) * factor).toFixed(2)})`,
  )

/**
 * Restrengthen the wash behind the text, and — only when the text has actually
 * moved — flip which edge it fades from.
 *
 * The anchor is left alone otherwise. A Story carries two scrims, one at each
 * end, and both match the same id prefix: repositioning by the layout's zone
 * rather than by an actual move would drag its bottom scrim to the top.
 */
function restyleScrim(layer, zone, strength, moved) {
  if (!layer.gradient) {
    // A flat wash (the centred layouts). Darkening its fill is the only lever
    // — raising layer opacity cannot take it past the alpha already baked in.
    return { ...layer, fill: scaleAlpha(layer.fill || 'rgba(0,0,0,0.5)', strength, 0.72) }
  }
  const from = layer.gradient.from || 'rgba(0,0,0,0)'
  const to = scaleAlpha(layer.gradient.to || 'rgba(0,0,0,0.82)', strength)
  if (!moved) return { ...layer, gradient: { from, to } }
  return {
    ...layer,
    anchor: zone === 'top' ? 'top-left' : 'bottom-left',
    // The dense end of the fade belongs against the edge the text sits on.
    gradient: zone === 'top' ? { from: to, to: from } : { from, to },
  }
}

/**
 * Rewrite a built layer list for a chosen placement.
 *
 * Called with no placement, or one that matches the template, this returns the
 * layers untouched — so every existing surface behaves exactly as before until
 * an analysis says otherwise.
 */
export function applyPlacement(layers, layout, placement) {
  if (!placement || !layers?.length) return layers
  const strength = placement.scrim ?? 1

  return layers.map((layer) => {
    if (String(layer.id || '').startsWith('content-scrim')) {
      return restyleScrim(layer, placement.zone, strength, placement.moved)
    }
    if (!placement.moved) return layer
    // Full-bleed and centred elements have no band to move within.
    if (layer.type === LAYER_TYPES.BACKGROUND || layer.anchor === 'center') return layer
    return moveToBand(layer, layout.band ?? 0.5)
  })
}
