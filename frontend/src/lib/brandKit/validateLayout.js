// ---------------------------------------------------------------------------
// Layout validation.
//
// The last gate before a layer list is drawn. Templates position text with
// fractional geometry that is correct for typical copy at typical aspect
// ratios — but copy is written by a model and the frame can be anything from a
// 16:9 banner to a 9:16 story, so "typical" is not a guarantee. Three things
// go wrong in practice, and this fixes all three:
//
//   overflow  — a headline wider than the frame, or a CTA label longer than
//               its pill. Fixed by shrinking the type, then truncating only if
//               shrinking alone is not enough.
//   margins   — an element drifting into the outer edge, which is what makes
//               an otherwise fine design look unfinished. Fixed by pushing it
//               back inside the safe rect.
//   overlap   — a logo landing on a headline, or a CTA under a brand bar.
//               Fixed by moving the free element, never the anchored one.
//
// Every function here is pure and idempotent: running it on already-valid
// layers returns them unchanged, which is what makes it safe to apply at both
// the template level and again after brand layers merge in.
// ---------------------------------------------------------------------------

import { ANCHORS, LAYER_TYPES, resolveLayer, textAlignFor } from './layers.js'

// Type may shrink this far to fit before the text is truncated instead. Below
// roughly two thirds the hierarchy the template designed collapses — a
// "headline" at 60% of its size no longer reads as one.
const MIN_TYPE_SCALE = 0.68

// Breathing room between two stacked elements, as a fraction of frame height.
//
// Two values, because one cannot serve both jobs. MIN_GAP is the hard floor —
// the least separation that still reads as two elements rather than one, and
// the most a tight template (a long headline plus a subtitle plus a CTA in a
// half-frame band) can afford. PREFERRED_GAP is what the same stack should get
// when there is room for it: at 1.4% a 78px headline sits 15px off the line
// below it, which is legible at full size but reads as touching in a feed
// thumbnail or a card preview.
//
// The pipeline tries PREFERRED_GAP and keeps it only if the result still
// validates, so roomy layouts breathe and cramped ones behave exactly as
// before.
const MIN_GAP = 0.014
const PREFERRED_GAP = 0.032

// Layers that exist to cover the frame. They are meant to touch the edges, so
// margin and overlap rules do not apply to them.
const isFullBleed = (layer) =>
  layer.type === LAYER_TYPES.BACKGROUND ||
  (layer.size?.w ?? 0) >= 0.99 ||
  String(layer.id || '').includes('scrim')

// Elements the template composed as one thing must move as one thing: a CTA
// label and its pill, the successive lines of a wrapped headline. Stripping a
// `-bg` suffix or a line number yields the group they belong to.
const groupKey = (layer) =>
  String(layer.id || '')
    .replace(/-bg$/, '')
    .replace(/-\d+$/, '')

// A text layer and its own backing pill overlap by design.
const isOwnBacking = (a, b) => groupKey(a) === groupKey(b)

const isBrandLayer = (layer) => String(layer.id || '').startsWith('brand-')

let measureCtx = null
function measurer() {
  if (measureCtx !== null) return measureCtx
  try {
    measureCtx = document.createElement('canvas').getContext('2d')
  } catch {
    measureCtx = false // no canvas — fall back to estimation
  }
  return measureCtx
}

/**
 * Rendered width of a text layer, in frame pixels.
 *
 * Measured with the same font string the Canvas exporter uses, so what fits
 * here is what fits there. Falls back to a per-weight average glyph width when
 * canvas is unavailable (tests, SSR) — less exact, but it keeps the validator
 * working rather than silently passing everything.
 */
export function textWidth(layer, frame) {
  const value = String(layer.text ?? '')
  if (!value) return 0
  const fontSize = (layer.size?.h ?? 0.04) * frame.height
  const tracking = (layer.tracking || 0) * fontSize * value.length
  const ctx = measurer()
  if (ctx) {
    const style = layer.italic ? 'italic ' : ''
    const family = layer.fontFamily || 'Inter, system-ui, sans-serif'
    ctx.font = `${style}${layer.weight || 600} ${fontSize}px ${family}`
    return ctx.measureText(value).width + tracking
  }
  // Heavier weights are wider; 0.52em is a good average for Inter at 800.
  const perChar = (layer.weight || 600) >= 700 ? 0.54 : 0.5
  return value.length * fontSize * perChar + tracking
}

/** The box a layer actually paints, which for text is its measured width. */
function paintedBox(layer, frame) {
  const box = resolveLayer(layer, frame)
  if (layer.type !== LAYER_TYPES.TEXT) return box
  const w = Math.min(textWidth(layer, frame), box.w)
  const align = textAlignFor(layer)
  const x = align === 'right' ? box.x + box.w - w : align === 'center' ? box.x + (box.w - w) / 2 : box.x
  // Text is drawn from a baseline; the glyph band is roughly the font size.
  const h = (layer.size?.h ?? 0.04) * frame.height
  return { x, y: box.y, w, h }
}

/** Shift a layer by a pixel delta, respecting which corner it is anchored to. */
function translate(layer, dx, dy, frame) {
  const [ax, ay] = ANCHORS[layer.anchor] || ANCHORS['bottom-right']
  // Offsets push inward from the anchor, so the sign flips on the far edges.
  // A centred anchor has no inward direction — its offset is a true position.
  const sx = ax === 1 ? -1 : 1
  const sy = ay === 1 ? -1 : 1
  if (!dx && !dy) return layer
  return {
    ...layer,
    offset: {
      x: (layer.offset?.x ?? 0) + (sx * dx) / frame.width,
      y: (layer.offset?.y ?? 0) + (sy * dy) / frame.height,
    },
  }
}

// ---- Pass 1: overflow ------------------------------------------------------

function fitText(layers, frame, margin) {
  const safeRight = frame.width * (1 - margin)
  const safeLeft = frame.width * margin

  return layers.map((layer) => {
    if (layer.type !== LAYER_TYPES.TEXT || !layer.text) return layer

    const box = resolveLayer(layer, frame)
    const align = textAlignFor(layer)
    // How much room this line really has: its declared box, but never past the
    // safe edge it grows towards.
    const room =
      align === 'right'
        ? Math.min(box.w, box.x + box.w - safeLeft)
        : align === 'center'
          ? Math.min(box.w, (Math.min(box.x + box.w, safeRight) - Math.max(box.x, safeLeft)))
          : Math.min(box.w, safeRight - box.x)
    if (room <= 0) return layer

    const width = textWidth(layer, frame)
    if (width <= room) return layer

    const scale = Math.max(MIN_TYPE_SCALE, room / width)
    let next = { ...layer, size: { ...layer.size, h: (layer.size?.h ?? 0.04) * scale } }

    // Shrunk as far as the hierarchy allows and still too wide — trim the
    // tail. An ellipsis reads as an edit; a clipped glyph reads as a bug.
    if (textWidth(next, frame) > room) {
      const perChar = textWidth(next, frame) / String(next.text).length
      const keep = Math.max(1, Math.floor(room / perChar) - 1)
      if (keep < String(next.text).length) {
        next = { ...next, text: `${String(next.text).slice(0, keep).trimEnd()}…` }
      }
    }
    return next
  })
}

// ---- Pass 2: overlap -------------------------------------------------------

const overlaps = (a, b) =>
  a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h

const LOGO_CORNERS = ['top-right', 'top-left', 'bottom-right', 'bottom-left']

// Flipping a badge left to right does not work: its logo and name are laid out
// left-to-right inside it with offsets measured from one edge, so mirroring the
// anchor would send the logo to the far side of its own container. Top to
// bottom is safe — every element is inset from the same horizontal edge.
const VERTICAL_FLIP = {
  'top-left': 'bottom-left',
  'bottom-left': 'top-left',
  'top-right': 'bottom-right',
  'bottom-right': 'top-right',
}

/**
 * Move the corner branding out from under the content.
 *
 * A badge moves as a unit and only vertically; a standalone logo can take any
 * free corner. Branding attached to a full-width bar does not move at all —
 * the bar is the frame's furniture, and the content was already lifted clear
 * of it by `liftAboveBrandBlock`.
 */
function relocateBrandCorner(layers, frame) {
  if (layers.some((l) => l.id === 'brand-bar')) return layers

  const badge = layers.find((l) => l.id === 'brand-badge')
  const groupIds = badge
    ? new Set(['brand-badge', 'brand-logo', 'brand-name'])
    : new Set(['brand-logo'])
  const members = layers.filter((l) => groupIds.has(l.id))
  if (!members.length) return layers

  const anchor = members[0].anchor
  const obstacles = layers
    .filter((l) => !groupIds.has(l.id) && !isFullBleed(l))
    .map((l) => paintedBox(l, frame))

  // How much of the content this corner would cover, in square pixels.
  const costAt = (candidate) =>
    members.reduce((total, l) => {
      const box = paintedBox({ ...l, anchor: candidate }, frame)
      return (
        total +
        obstacles.reduce((sum, b) => {
          if (!overlaps(box, b)) return sum
          const w = Math.min(box.x + box.w, b.x + b.w) - Math.max(box.x, b.x)
          const h = Math.min(box.y + box.h, b.y + b.h) - Math.max(box.y, b.y)
          return sum + w * h
        }, 0)
      )
    }, 0)

  const current = costAt(anchor)
  if (current === 0) return layers

  // Prefer the corner the template asked for, then the rest in a fixed order,
  // so the same design always resolves to the same corner. When every corner
  // is occupied — a full-frame layout with a standalone logo — take the least
  // covered one: a logo clipping a corner of the text beats one across it.
  const options = badge
    ? [VERTICAL_FLIP[anchor]].filter(Boolean)
    : LOGO_CORNERS.filter((c) => c !== anchor)
  let best = anchor
  let bestCost = current
  for (const candidate of options) {
    const cost = costAt(candidate)
    if (cost < bestCost) {
      best = candidate
      bestCost = cost
    }
    if (bestCost === 0) break
  }
  if (best === anchor) return layers
  return layers.map((l) => (groupIds.has(l.id) ? { ...l, anchor: best } : l))
}

/**
 * Enforce vertical breathing room between stacked elements.
 *
 * Only elements that share a horizontal span can collide visually, and only
 * the one nearer the frame's edge is moved — pushing the anchored element
 * would drag the whole block off its baseline.
 */
/** Uniformly shrink every text layer, preserving the type hierarchy. */
function scaleType(layers, factor) {
  return layers.map((l) =>
    l.type === LAYER_TYPES.TEXT && l.size?.h
      ? { ...l, size: { ...l.size, h: l.size.h * factor } }
      : l,
  )
}

function spaceStack(layers, frame, gapFraction = MIN_GAP) {
  const gap = gapFraction * frame.height

  // Text inside a brand bar or badge is spaced by that container, not by this
  // pass — its neighbours are the container's, not the layout's.
  const contained = layers.some((l) => l.id === 'brand-bar' || l.id === 'brand-badge')

  // One entry per composed element, not per layer, so a headline and its
  // second line keep the spacing the template gave them.
  const groups = new Map()
  layers.forEach((layer, i) => {
    if (isFullBleed(layer)) return
    if (contained && isBrandLayer(layer)) return
    const key = groupKey(layer) || `anon-${i}`
    const box = paintedBox(layer, frame)
    const group = groups.get(key)
    if (!group) {
      groups.set(key, { key, members: [i], box: { ...box } })
      return
    }
    const right = Math.max(group.box.x + group.box.w, box.x + box.w)
    const bottom = Math.max(group.box.y + group.box.h, box.y + box.h)
    group.box.x = Math.min(group.box.x, box.x)
    group.box.y = Math.min(group.box.y, box.y)
    group.box.w = right - group.box.x
    group.box.h = bottom - group.box.y
    group.members.push(i)
  })

  const ordered = [...groups.values()].sort((a, b) => a.box.y - b.box.y)
  const moved = new Map()

  // Walk upward from the bottom: the element nearest the edge holds its
  // position and everything above it is pushed clear, which preserves the
  // baseline the layout was designed around.
  for (let k = ordered.length - 1; k > 0; k--) {
    const lower = ordered[k]
    const upper = ordered[k - 1]
    // No horizontal overlap means no visual collision, whatever the rows say.
    const shareColumn =
      upper.box.x < lower.box.x + lower.box.w && lower.box.x < upper.box.x + upper.box.w
    if (!shareColumn) continue

    const encroach = upper.box.y + upper.box.h + gap - lower.box.y
    if (encroach <= 0) continue
    // Never push a group off the top of the frame to solve a collision below.
    const shift = Math.min(encroach, Math.max(0, upper.box.y))
    if (shift <= 0) continue

    for (const i of upper.members) {
      const current = moved.get(i) || layers[i]
      moved.set(i, translate(current, 0, -shift, frame))
    }
    upper.box.y -= shift
  }

  return moved.size ? layers.map((l, i) => moved.get(i) || l) : layers
}

/**
 * Keep content clear of the brand block along the bottom edge.
 *
 * The content template and the brand template are chosen independently and
 * neither can see the other, yet both want the lower part of the frame — so a
 * footer bar lands on the CTA, and editorial contact lines land on the
 * subtext. Branding is the fixed furniture here: it carries the business's
 * real details and its position is a deliberate setting, so the content is
 * what moves.
 */
function liftAboveBrandBlock(layers, frame) {
  const gap = MIN_GAP * frame.height

  // The highest point anything branded reaches along the bottom edge.
  let brandTop = Infinity
  for (const layer of layers) {
    if (!isBrandLayer(layer)) continue
    if (layer.id === 'brand-scrim') continue // a fade, not an occupied area
    const box = layer.id === 'brand-bar' ? resolveLayer(layer, frame) : paintedBox(layer, frame)
    // Only the bottom-anchored block competes for the same space.
    if (box.y + box.h < frame.height * 0.5) continue
    brandTop = Math.min(brandTop, box.y)
  }
  if (!Number.isFinite(brandTop)) return layers

  // The bottom-weighted part of the content moves as one, by the single
  // largest encroachment. Shifting each element by its own overlap would
  // compress the spacing the template designed — a CTA deep inside the bar
  // travels much further than the headline above it, and lands on top of it.
  //
  // Content in the top half is left alone: a Story puts its headline up there
  // and its CTA down here, and dragging the headline along would empty the top
  // of the frame to solve a problem it has no part in.
  const half = frame.height * 0.5
  const members = []
  let worst = 0
  layers.forEach((layer, i) => {
    if (isBrandLayer(layer) || isFullBleed(layer)) return
    const box = paintedBox(layer, frame)
    if (box.y + box.h <= half) return
    members.push(i)
    worst = Math.max(worst, box.y + box.h + gap - brandTop)
  })
  if (worst <= 0 || !members.length) return layers

  const moving = new Set(members)
  return layers.map((l, i) => (moving.has(i) ? translate(l, 0, -worst, frame) : l))
}

// ---- Pass 3: margins -------------------------------------------------------

function clampToSafeArea(layers, frame, margin) {
  const left = frame.width * margin
  const right = frame.width * (1 - margin)
  // The layout's own margin, vertically as well as horizontally.
  //
  // This used to be a flat 3.5% floor on the reasoning that templates police
  // their own bottom padding. They do not: ig-post puts its CTA pill at 95%,
  // which cleared a 96.5% floor and so was never corrected — the button hung
  // off the bottom of every square post. A declared margin that only applies
  // to two of four edges is not a margin.
  const inset = frame.height * margin
  const top = inset
  const bottom = frame.height - inset

  // A brand bar or badge is a container the brand text is positioned inside.
  // Nudging that text against the frame's margins would slide it out of its
  // own container, so only its horizontal placement is policed here.
  const contained = layers.some((l) => l.id === 'brand-bar' || l.id === 'brand-badge')

  // Move composed elements as one, so a CTA label never drifts off its pill.
  const groups = new Map()
  layers.forEach((layer, i) => {
    if (isFullBleed(layer) || layer.type === LAYER_TYPES.BACKGROUND) return
    const key = groupKey(layer) || `anon-${i}`
    const box = paintedBox(layer, frame)
    const g = groups.get(key)
    if (!g) {
      groups.set(key, { members: [i], box: { ...box }, brand: isBrandLayer(layer) })
      return
    }
    const r = Math.max(g.box.x + g.box.w, box.x + box.w)
    const b = Math.max(g.box.y + g.box.h, box.y + box.h)
    g.box.x = Math.min(g.box.x, box.x)
    g.box.y = Math.min(g.box.y, box.y)
    g.box.w = r - g.box.x
    g.box.h = b - g.box.y
    g.members.push(i)
  })

  const deltas = new Map()
  for (const { members, box, brand } of groups.values()) {
    let dx = 0
    let dy = 0
    if (box.x < left) dx = left - box.x
    else if (box.x + box.w > right) dx = right - (box.x + box.w)
    if (box.y < top) dy = top - box.y
    else if (box.y + box.h > bottom) dy = bottom - (box.y + box.h)
    // An element wider or taller than the safe area cannot be satisfied by
    // moving it; pass 1 already shrank what it could, so leave it where the
    // template put it rather than jamming it against one edge.
    if (box.w > right - left) dx = 0
    if (box.h > bottom - top || (brand && contained)) dy = 0
    if (dx || dy) members.forEach((i) => deltas.set(i, { dx, dy }))
  }

  if (!deltas.size) return layers
  return layers.map((l, i) => {
    const d = deltas.get(i)
    return d ? translate(l, d.dx, d.dy, frame) : l
  })
}

/**
 * Validate and repair a layer list.
 *
 * @param {Array}  layers
 * @param {object} options { aspect, layout }
 * @returns {Array} layers guaranteed to fit inside the canvas and its margins
 */
export function validateLayers(layers, { aspect = 1, layout } = {}) {
  if (!layers?.length) return layers || []
  const margin = layout?.margin ?? 0.07
  // Same 1000-unit frame the SVG renderer uses, so measurements here describe
  // exactly what gets drawn there.
  const frame = { width: 1000, height: 1000 / (aspect || 1) }

  try {
    const base = liftAboveBrandBlock(fitText(layers, frame, margin), frame)

    // Space the stack, then clamp, then place the logo.
    const settle = (input, gapFraction) => {
      const spaced = clampToSafeArea(spaceStack(input, frame, gapFraction), frame, margin)
      // Last, once the content has settled: picking the logo's corner against
      // positions that are about to change would just move it into the way.
      return relocateBrandCorner(spaced, frame)
    }
    const clean = (out) => !findLayoutIssues(out, { aspect, layout }).length

    // 1. Generous spacing, offered rather than imposed. Pushing elements apart
    //    moves them upward, which in a tight template drives them into the
    //    safe-area clamp and back down onto their neighbours — so it is kept
    //    only when the result validates.
    const roomy = settle(base, PREFERRED_GAP)
    if (clean(roomy)) return roomy

    // 2. The minimum, which is what this function did before.
    let out = settle(base, MIN_GAP)
    if (clean(out)) return out

    // 3. Still colliding means the stack is taller than the band it has to live
    //    in — a long headline in a landscape frame, say. Spacing cannot fix
    //    that, so give up height instead: shrink the type a step at a time and
    //    stop as soon as it fits.
    //
    //    Keep the BEST attempt, not the last one. Shrinking does not always
    //    converge — on the product layout the price chip pins the headline
    //    column, so eight rounds of shrinking left illegible 17-unit text that
    //    still overlapped, and returning that last attempt was worse than
    //    returning the first. Ties go to the larger type, so a layout that
    //    cannot be fixed is at least returned readable.
    const score = (out) => findLayoutIssues(out, { aspect, layout }).length
    let best = out
    let bestScore = score(out)
    let shrunk = base
    for (let i = 0; i < 6 && bestScore > 0; i++) {
      shrunk = scaleType(shrunk, 0.88)
      const attempt = settle(shrunk, MIN_GAP)
      const s = score(attempt)
      if (s === 0) return attempt
      if (s < bestScore) {
        best = attempt
        bestScore = s
      }
    }
    return best
  } catch {
    // Validation is a safety net, not a dependency — a failure here must not
    // cost the user their design.
    return layers
  }
}

/**
 * Report what is still wrong with a layer list, without changing it.
 * Used by tests and available for diagnostics; the pipeline uses
 * `validateLayers`, which fixes rather than reports.
 */
export function findLayoutIssues(layers, { aspect = 1, layout } = {}) {
  const margin = layout?.margin ?? 0.07
  const frame = { width: 1000, height: 1000 / (aspect || 1) }
  const issues = []
  const boxes = []

  for (const layer of layers || []) {
    if (isFullBleed(layer)) continue
    const box = paintedBox(layer, frame)
    if (box.x < -0.5 || box.y < -0.5 || box.x + box.w > frame.width + 0.5 || box.y + box.h > frame.height + 0.5) {
      issues.push({ type: 'outside-canvas', id: layer.id })
    } else if (
      box.x < frame.width * margin - 0.5 ||
      box.x + box.w > frame.width * (1 - margin) + 0.5 ||
      // Vertical too — checking only the sides is what let a CTA sit 20 units
      // below the bottom margin across 1560 "passing" designs.
      //
      // Brand layers are exempt: a logo in the corner and a contact strip
      // along the bottom edge are placed there deliberately by the brand
      // template, the same reason clampToSafeArea only polices them
      // horizontally. Content has no such licence.
      (!isBrandLayer(layer) &&
        (box.y < frame.height * margin - 0.5 ||
          box.y + box.h > frame.height * (1 - margin) + 0.5))
    ) {
      issues.push({ type: 'outside-margin', id: layer.id })
    }
    boxes.push({ layer, box })
  }

  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      if (isOwnBacking(boxes[i].layer, boxes[j].layer)) continue
      if (boxes[i].layer.locked || boxes[j].layer.locked) continue
      if (overlaps(boxes[i].box, boxes[j].box)) {
        issues.push({ type: 'overlap', id: boxes[i].layer.id, with: boxes[j].layer.id })
      }
    }
  }
  return issues
}
