// ---------------------------------------------------------------------------
// Executes the structured operations returned by /api/image-edit.
//
// The AI decides WHAT to change; this decides HOW, deterministically. Keeping
// execution client-side and rule-based means an edit either applies exactly as
// described or is skipped — the model never gets to invent geometry, so it
// cannot produce a layout that looks plausible in JSON and broken on screen.
//
// Every function here is pure and returns a new document, so an AI edit lands
// as a single undo step exactly like a manual one.
// ---------------------------------------------------------------------------

import { LAYER_TYPES, paletteOf, readableOn } from '../layers.js'
import { addLayer, newTextLayer, removeLayer, updateLayer, Z_BANDS } from './document.js'
import { createLayer } from '../layers.js'

// ---- Target resolution -----------------------------------------------------
// Maps a target word onto the layers it means. Ids are matched first so the
// model can address one specific layer when it needs to.

function resolveTargets(doc, target) {
  const layers = doc.layers
  if (!target || target === 'all') return layers.filter((l) => !l.structural)

  const byId = layers.filter((l) => l.id === target)
  if (byId.length) return byId

  switch (target) {
    case 'logo':
      return layers.filter((l) => /logo/i.test(l.id) || /logo/i.test(l.name || ''))
    case 'text':
      return layers.filter((l) => l.type === LAYER_TYPES.TEXT)
    case 'headline':
      return layers.filter((l) => l.type === LAYER_TYPES.TEXT && /headline|brand-name/i.test(l.id))
    case 'subtext':
      return layers.filter((l) => l.type === LAYER_TYPES.TEXT && /^sub|contact/i.test(l.id))
    case 'cta':
      return layers.filter((l) => /^cta/i.test(l.id))
    case 'background':
      return layers.filter((l) => l.type === LAYER_TYPES.BACKGROUND)
    case 'shapes':
      return layers.filter((l) =>
        [LAYER_TYPES.RECT, LAYER_TYPES.ELLIPSE, LAYER_TYPES.LINE, LAYER_TYPES.ARROW].includes(
          l.type,
        ),
      )
    case 'image':
      return layers.filter((l) => l.type === LAYER_TYPES.IMAGE && !/logo/i.test(l.id))
    default:
      return []
  }
}

const VALID_ANCHORS = new Set([
  'top-left', 'top-right', 'bottom-left', 'bottom-right', 'center',
])

const isHex = (v) => /^#[0-9a-f]{6}$/i.test(String(v || '').trim())

// ---- Operations ------------------------------------------------------------

const OPS = {
  move(doc, op) {
    if (!VALID_ANCHORS.has(op.anchor)) return doc
    return resolveTargets(doc, op.target).reduce(
      (d, l) =>
        l.structural
          ? d
          : updateLayer(d, l.id, {
              anchor: op.anchor,
              // Reset to a standard inset. Carrying the old offset over would
              // place a layer moved from a corner to the centre far off-frame,
              // because offsets are measured inward from the anchor.
              offset: op.anchor === 'center' ? { x: 0, y: 0 } : { x: 0.05, y: 0.05 },
            }),
      doc,
    )
  },

  recolor(doc, op, ctx) {
    const { primary, secondary } = paletteOf(ctx.brandKit)
    const useBrand = op.palette === 'brand' || !isHex(op.color)
    const color = isHex(op.color) ? op.color : primary

    return resolveTargets(doc, op.target).reduce((d, l) => {
      if (l.type === LAYER_TYPES.BACKGROUND) {
        return updateLayer(d, l.id, {
          gradient: useBrand ? { from: primary, to: secondary, angle: 180 } : null,
          fill: color,
        })
      }
      if (l.type === LAYER_TYPES.TEXT) {
        // Text sitting on a brand-coloured panel must stay legible, so pick
        // ink from the panel rather than painting text the brand colour and
        // leaving it invisible against its own background.
        return updateLayer(d, l.id, { fill: /cta|brand-name/i.test(l.id) ? readableOn(color) : color })
      }
      if (l.type === LAYER_TYPES.LINE || l.type === LAYER_TYPES.ARROW) {
        return updateLayer(d, l.id, { stroke: color })
      }
      return updateLayer(d, l.id, { fill: color })
    }, doc)
  },

  resize(doc, op) {
    const scale = Number(op.scale)
    if (!Number.isFinite(scale) || scale <= 0) return doc
    const clamped = Math.min(4, Math.max(0.25, scale))
    return resolveTargets(doc, op.target).reduce(
      (d, l) =>
        l.structural
          ? d
          : updateLayer(d, l.id, {
              size: {
                w: Math.min(1, (l.size?.w ?? 0.2) * clamped),
                h: Math.min(1, (l.size?.h ?? 0.2) * clamped),
              },
            }),
      doc,
    )
  },

  spacing(doc, op) {
    const delta = Number(op.delta)
    if (!Number.isFinite(delta)) return doc
    const d = Math.min(0.12, Math.max(-0.06, delta))
    // Offsets are measured inward, so adding to both axes increases the margin
    // at every anchor without needing to know which corner a layer sits in.
    return doc.layers.reduce(
      (acc, l) =>
        l.structural || l.type === LAYER_TYPES.BACKGROUND
          ? acc
          : updateLayer(acc, l.id, {
              offset: {
                x: Math.max(0, (l.offset?.x ?? 0) + d),
                y: Math.max(0, (l.offset?.y ?? 0) + d),
              },
            }),
      doc,
    )
  },

  theme(doc, op, ctx) {
    const dark = op.mode !== 'light'
    const { primary } = paletteOf(ctx.brandKit)
    return doc.layers.reduce((d, l) => {
      if (l.type === LAYER_TYPES.BACKGROUND) {
        return updateLayer(d, l.id, {
          fill: dark ? '#0d1512' : '#ffffff',
          gradient: dark ? { from: '#132019', to: '#050a08', angle: 180 } : null,
        })
      }
      // Scrims carry the contrast for text over artwork; a light theme needs
      // a pale scrim or the text it protects becomes unreadable.
      if (l.gradient && /scrim/i.test(l.id)) {
        return updateLayer(d, l.id, {
          gradient: dark
            ? { from: 'rgba(0,0,0,0)', to: 'rgba(0,0,0,0.82)' }
            : { from: 'rgba(255,255,255,0)', to: 'rgba(255,255,255,0.88)' },
        })
      }
      if (l.type === LAYER_TYPES.TEXT && !/cta/i.test(l.id)) {
        return updateLayer(d, l.id, { fill: dark ? '#ffffff' : '#111827' })
      }
      if (l.id === 'brand-bar' || /badge/i.test(l.id)) {
        return updateLayer(d, l.id, { fill: primary })
      }
      return d
    }, doc)
  },

  add_text(doc, op) {
    const layer = newTextLayer(String(op.text || 'Your text').slice(0, 120))
    if (VALID_ANCHORS.has(op.anchor)) {
      layer.anchor = op.anchor
      layer.offset = op.anchor === 'center' ? { x: 0, y: 0 } : { x: 0.06, y: 0.06 }
    }
    return addLayer(doc, layer)
  },

  add_cta(doc, op, ctx) {
    const label = String(op.text || 'Learn more').slice(0, 24)
    const { primary } = paletteOf(ctx.brandKit)
    const width = Math.min(0.16 + label.length * 0.021, 0.72)
    const stamp = Date.now().toString(36)

    return addLayer(
      addLayer(
        doc,
        createLayer(LAYER_TYPES.RECT, {
          id: `cta-bg-${stamp}`,
          name: 'CTA button',
          anchor: 'bottom-left',
          offset: { x: 0.07, y: 0.06 },
          size: { w: width, h: 0.072 },
          fill: primary,
          radius: 0.036,
          z: Z_BANDS.USER,
        }),
      ),
      createLayer(LAYER_TYPES.TEXT, {
        id: `cta-${stamp}`,
        name: 'CTA label',
        text: label,
        anchor: 'bottom-left',
        offset: { x: 0.07 + width / 2, y: 0.082 },
        size: { w: width, h: 0.034 },
        fill: readableOn(primary),
        weight: 700,
        align: 'center',
        z: Z_BANDS.USER + 1,
      }),
    )
  },

  remove(doc, op) {
    return resolveTargets(doc, op.target).reduce(
      (d, l) => (l.structural ? d : removeLayer(d, l.id)),
      doc,
    )
  },

  // Handled by the caller: these need new artwork, not a layer change.
  restyle: (doc) => doc,
  regenerate: (doc) => doc,
}

/**
 * Apply a list of operations to a document.
 *
 * @returns {{document, applied: string[], skipped: string[], regeneration: object|null}}
 */
export function applyOperations(doc, operations = [], ctx = {}) {
  let next = doc
  const applied = []
  const skipped = []
  let regeneration = null

  for (const op of operations) {
    const fn = OPS[op.op]
    if (!fn) {
      skipped.push(op.op)
      continue
    }
    if (op.op === 'restyle' || op.op === 'regenerate') {
      // Last one wins — two conflicting regenerations would race.
      regeneration = { style: op.style || null, prompt: op.prompt || null }
      applied.push(op.op)
      continue
    }
    const before = next
    next = fn(next, op, ctx)
    // An op that matched no layers is reported rather than silently ignored,
    // so "move the logo" on an image with no logo says so.
    ;(next === before ? skipped : applied).push(op.op)
  }

  return { document: next, applied, skipped, regeneration }
}

/** Compact layer summary for the API — ids and types are all the model needs. */
export function summarizeLayers(doc) {
  return doc.layers
    .filter((l) => !l.structural)
    .slice(0, 20)
    .map((l) => ({
      id: l.id,
      type: l.type,
      text: l.type === LAYER_TYPES.TEXT ? String(l.text || '').slice(0, 40) : null,
    }))
}
