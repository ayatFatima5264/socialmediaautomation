// ---------------------------------------------------------------------------
// Content templates.
//
// Phase 1 templates arrange BRANDING (logo, name, contact). These arrange
// CONTENT — the headline, supporting line, and call to action that turn a
// generated background into a designed post rather than a stock picture with
// a caption underneath.
//
// Same contract as the brand templates: a template is a pure function
// (content, options) -> Layer[]. It draws nothing, so the SVG preview, the
// Canvas exporter, and a future editor all consume it unchanged.
//
// Two things a template declares beyond its layout:
//
//   slots       — the fields the AI must produce to fill it. This is what
//                 makes generation layout-aware: the model is asked for a
//                 headline of a given length rather than a caption, so the
//                 text fits the design instead of being truncated into it.
//   background  — how the underlying image should be shot for this layout
//                 (e.g. "leave the centre clear"), folded into the prompt.
//
// Nine layout builders serve thirteen templates: the platform templates differ
// mainly in proportion, and fractional geometry already handles that, so
// duplicating a near-identical layout per platform would add no value.
// ---------------------------------------------------------------------------

import { LAYER_TYPES, createLayer, paletteOf, readableOn } from './layers.js'
import { applyPlacement } from './smartLayout.js'
import { validateLayers } from './validateLayout.js'

// Content layers sit below brand layers (z 10-30 in the brand templates get
// merged on top) but above the background image.
const Z = { SCRIM: 1, CHIP: 4, TEXT: 5 }

// ---- Layout rules ----------------------------------------------------------
//
// Every template declares these. They are the contract three separate stages
// rely on, which is why they live on the template rather than inside its build
// function:
//
//   zone / band  -> the safe text area. Sent to the image pipeline so the
//                   artwork is composed with that region left empty, and used
//                   by the layout validator as the box text must stay inside.
//   altZones     -> where smart placement may move the text if the generated
//                   image turns out busy where the template expected calm.
//   margin       -> one number for every edge inset in the layout, so margins
//                   are consistent by construction instead of per-builder.
//   logo / cta   -> where those elements belong, so they stay aligned with the
//                   text block rather than floating independently.
//   maxChars     -> the per-slot budget the copy is written to. A template with
//                   a big centred headline can carry fewer characters than one
//                   with a three-line lower third; sending these to the copy
//                   writer is what stops text overflowing before it is drawn.
//
const LAYOUT_DEFAULTS = {
  zone: 'bottom',
  altZones: [],
  band: 0.5,
  margin: 0.07,
  align: 'left',
  logo: 'top-right',
  cta: 'bottom-left',
  maxChars: { headline: 70, subtext: 110, cta: 22, badge: 16, price: 12 },
}

const layoutOf = (overrides) => ({
  ...LAYOUT_DEFAULTS,
  ...overrides,
  maxChars: { ...LAYOUT_DEFAULTS.maxChars, ...(overrides?.maxChars || {}) },
})

const text = (id, value, props) =>
  value
    ? createLayer(LAYER_TYPES.TEXT, { id, text: value, z: Z.TEXT, fill: '#ffffff', ...props })
    : null

// The inner edge inset for a layout. One source for every offset in a builder,
// so headline, subtext, chip and CTA all line up on the same vertical rule.
const marginOf = (opts) => opts?.layout?.margin ?? LAYOUT_DEFAULTS.margin

// Wrap a headline onto at most `maxLines` lines of ~`perLine` characters.
// SVG has no text wrapping, so long headlines must be split into separate
// layers or they run off the frame.
//
// Copy is written to a character budget, so overflow should be rare — but when
// it happens the tail is marked with an ellipsis rather than silently deleted,
// because a headline that just stops mid-thought reads as a rendering bug.
function wrap(value, perLine, maxLines) {
  if (!value) return []
  const words = String(value).trim().split(/\s+/)
  const lines = []
  let line = ''
  let dropped = false
  for (const w of words) {
    const next = line ? `${line} ${w}` : w
    if (next.length <= perLine) line = next
    else {
      if (line) lines.push(line)
      line = w
      if (lines.length === maxLines) {
        dropped = true
        break
      }
    }
  }
  if (line && lines.length < maxLines) lines.push(line)
  else if (line) dropped = true
  if (dropped && lines.length) {
    const last = lines[lines.length - 1]
    lines[lines.length - 1] = `${last.replace(/[\s.,;:]+$/, '').slice(0, perLine - 1)}…`
  }
  return lines.slice(0, maxLines)
}

// A small pill — "50% OFF", "WE'RE HIRING", "NEW".
function chip(id, label, { anchor, offset, brandKit, size = 0.032 }) {
  if (!label) return []
  const { primary } = paletteOf(brandKit)
  const width = Math.min(0.14 + String(label).length * 0.019, 0.7)
  return [
    createLayer(LAYER_TYPES.RECT, {
      id: `${id}-bg`,
      anchor,
      offset,
      size: { w: width, h: size * 2 },
      fill: primary,
      radius: size,
      locked: true,
      z: Z.CHIP,
    }),
    createLayer(LAYER_TYPES.TEXT, {
      id,
      text: String(label).toUpperCase(),
      anchor,
      offset: { x: offset.x + 0.028, y: offset.y + size * 0.55 },
      size: { w: width, h: size },
      fill: readableOn(primary),
      weight: 800,
      tracking: 0.06,
      align: 'left',
      z: Z.TEXT,
    }),
  ]
}

// Gradient behind text so it reads on any generated background.
const scrim = (height, from = 'rgba(0,0,0,0)', to = 'rgba(0,0,0,0.82)') =>
  createLayer(LAYER_TYPES.RECT, {
    id: 'content-scrim',
    anchor: 'bottom-left',
    offset: { x: 0, y: 0 },
    size: { w: 1, h: height },
    gradient: { from, to },
    locked: true,
    z: Z.SCRIM,
  })

// ---- Layout builders -------------------------------------------------------

// Headline + subtext stacked at the bottom. The workhorse feed layout.
function lowerThird(content, opts) {
  const m = marginOf(opts)
  const lines = wrap(content.headline, 26, 3)
  const hasSub = Boolean(content.subtext)
  const layers = [scrim(hasSub ? 0.58 : 0.48)]

  const baseY = hasSub ? 0.17 : 0.09
  lines.forEach((line, i) =>
    layers.push(
      text(`headline-${i}`, line, {
        anchor: 'bottom-left',
        offset: { x: m, y: baseY + (lines.length - 1 - i) * 0.085 },
        size: { w: 1 - m * 2, h: 0.072 },
        weight: 800,
      }),
    ),
  )

  if (hasSub) {
    wrap(content.subtext, 46, 2).forEach((line, i) =>
      layers.push(
        text(`sub-${i}`, line, {
          anchor: 'bottom-left',
          offset: { x: m, y: 0.095 - i * 0.042 },
          size: { w: 1 - m * 2, h: 0.036 },
          opacity: 0.9,
          weight: 500,
        }),
      ),
    )
  }
  layers.push(...ctaLayers(content, opts, { anchor: 'bottom-left', y: 0.05 }))
  return layers
}

// Big centred statement. Quote and Announcement.
function centered(content, opts) {
  const m = marginOf(opts)
  // Three lines, not four: a centred statement is read in one glance, and a
  // four-line block plus the quote mark above it reaches far enough up the
  // frame to collide with a corner badge.
  const lines = wrap(content.headline, 22, 3)
  const { primary } = paletteOf(opts.brandKit)
  const layers = [
    createLayer(LAYER_TYPES.RECT, {
      id: 'content-scrim',
      anchor: 'center',
      offset: { x: 0, y: 0 },
      size: { w: 1, h: 1 },
      fill: 'rgba(0,0,0,0.5)',
      locked: true,
      z: Z.SCRIM,
    }),
  ]

  // Centre-anchored offsets are a displacement from the middle of the frame:
  // negative is up, positive is down.
  const LINE = 0.09
  const block = lines.length * LINE
  const top = -block / 2 // where the headline block starts

  if (opts.quoteMark) {
    layers.push(
      text('quote-mark', '“', {
        anchor: 'center',
        offset: { x: 0, y: top - 0.105 },
        size: { w: 0.2, h: 0.16 },
        fill: primary,
        weight: 800,
        align: 'center',
      }),
    )
  }

  lines.forEach((line, i) =>
    layers.push(
      text(`headline-${i}`, line, {
        anchor: 'center',
        offset: { x: 0, y: top + i * LINE },
        size: { w: 1 - m * 2, h: 0.078 },
        weight: 800,
        align: 'center',
      }),
    ),
  )

  if (content.subtext) {
    layers.push(
      text('sub-0', content.subtext, {
        anchor: 'center',
        offset: { x: 0, y: top + block + 0.04 },
        size: { w: 1 - m * 3, h: 0.034 },
        opacity: 0.85,
        weight: 500,
        align: 'center',
      }),
    )
  }
  return layers.filter(Boolean)
}

// Vertical: headline high, CTA low — Story/Reel safe zones keep the middle
// clear of UI chrome.
function story(content, opts) {
  const m = marginOf(opts)
  const lines = wrap(content.headline, 20, 4)
  const layers = [
    createLayer(LAYER_TYPES.RECT, {
      id: 'content-scrim-top',
      anchor: 'top-left',
      offset: { x: 0, y: 0 },
      size: { w: 1, h: 0.42 },
      gradient: { from: 'rgba(0,0,0,0.75)', to: 'rgba(0,0,0,0)' },
      locked: true,
      z: Z.SCRIM,
    }),
    scrim(0.3),
  ]

  layers.push(...chip('kicker', content.badge, { anchor: 'top-left', offset: { x: m, y: 0.1 }, brandKit: opts.brandKit }))

  lines.forEach((line, i) =>
    layers.push(
      text(`headline-${i}`, line, {
        anchor: 'top-left',
        offset: { x: m, y: (content.badge ? 0.2 : 0.14) + i * 0.07 },
        size: { w: 1 - m * 2, h: 0.06 },
        weight: 800,
      }),
    ),
  )

  layers.push(...ctaLayers(content, opts, { anchor: 'bottom-left', y: 0.09 }))
  return layers.filter(Boolean)
}

// Tall pin: dense headline block, strong CTA — Pinterest rewards clarity.
function pin(content, opts) {
  const m = marginOf(opts)
  const lines = wrap(content.headline, 20, 4)
  const layers = [scrim(0.55)]

  lines.forEach((line, i) =>
    layers.push(
      text(`headline-${i}`, line, {
        anchor: 'bottom-left',
        offset: { x: m, y: 0.2 + (lines.length - 1 - i) * 0.065 },
        size: { w: 1 - m * 2, h: 0.056 },
        weight: 800,
      }),
    ),
  )
  if (content.subtext) {
    layers.push(
      text('sub-0', content.subtext, {
        anchor: 'bottom-left',
        offset: { x: m, y: 0.15 },
        size: { w: 1 - m * 2, h: 0.03 },
        opacity: 0.88,
        weight: 500,
      }),
    )
  }
  layers.push(...ctaLayers(content, opts, { anchor: 'bottom-left', y: 0.07 }))
  return layers.filter(Boolean)
}

// Offer-led: badge, large offer text, CTA.
function offer(content, opts) {
  const m = marginOf(opts)
  const { primary } = paletteOf(opts.brandKit)
  const lines = wrap(content.headline, 18, 3)
  const HEAD = { base: 0.19, step: 0.088, size: 0.082 }
  // The badge sits above the headline block, so it has to clear whatever that
  // block turned out to be. Pinning it to a fixed height assumes a two-line
  // headline and puts it straight through a three-line one.
  const headTop = HEAD.base + (lines.length - 1) * HEAD.step + HEAD.size
  const badgeY = headTop + 0.022
  const layers = [scrim(Math.min(0.72, badgeY + 0.09))]

  layers.push(
    ...chip('offer-badge', content.badge, {
      anchor: 'bottom-left',
      offset: { x: m, y: badgeY },
      brandKit: opts.brandKit,
      size: 0.034,
    }),
  )

  lines.forEach((line, i) =>
    layers.push(
      text(`headline-${i}`, line, {
        anchor: 'bottom-left',
        offset: { x: m, y: HEAD.base + (lines.length - 1 - i) * HEAD.step },
        size: { w: 1 - m * 2, h: HEAD.size },
        weight: 800,
      }),
    ),
  )

  if (content.subtext) {
    layers.push(
      text('sub-0', content.subtext, {
        anchor: 'bottom-left',
        offset: { x: m, y: 0.135 },
        size: { w: 1 - m * 2, h: 0.032 },
        opacity: 0.9,
        weight: 500,
      }),
    )
  }
  layers.push(...ctaLayers(content, opts, { anchor: 'bottom-left', y: 0.05, solid: primary }))
  return layers.filter(Boolean)
}

// Product: name, price, CTA — bottom-weighted so the product stays visible.
function product(content, opts) {
  const m = marginOf(opts)
  const { primary } = paletteOf(opts.brandKit)
  const layers = [scrim(0.46)]

  // The price chip occupies the right edge, so the headline column stops
  // short of it rather than running underneath.
  const priceW = 0.28
  const headW = content.price ? 1 - m * 2 - priceW - 0.03 : 1 - m * 2

  wrap(content.headline, 24, 2).forEach((line, i) =>
    layers.push(
      text(`headline-${i}`, line, {
        anchor: 'bottom-left',
        offset: { x: m, y: 0.16 + (1 - i) * 0.07 },
        size: { w: headW, h: 0.062 },
        weight: 800,
      }),
    ),
  )

  if (content.price) {
    layers.push(
      createLayer(LAYER_TYPES.RECT, {
        id: 'price-bg',
        anchor: 'bottom-right',
        offset: { x: m, y: 0.15 },
        size: { w: priceW, h: 0.09 },
        fill: primary,
        radius: 0.02,
        locked: true,
        z: Z.CHIP,
      }),
      text('price', content.price, {
        anchor: 'bottom-right',
        offset: { x: m + 0.02, y: 0.175 },
        size: { w: priceW - 0.04, h: 0.048 },
        fill: readableOn(primary),
        weight: 800,
        align: 'center',
      }),
    )
  }

  if (content.subtext) {
    layers.push(
      text('sub-0', content.subtext, {
        anchor: 'bottom-left',
        offset: { x: m, y: 0.105 },
        size: { w: headW, h: 0.03 },
        opacity: 0.88,
        weight: 500,
      }),
    )
  }
  layers.push(...ctaLayers(content, opts, { anchor: 'bottom-left', y: 0.05 }))
  return layers.filter(Boolean)
}

// Event: date chip, title, venue.
function event(content, opts) {
  const m = marginOf(opts)
  const layers = [scrim(0.6)]
  layers.push(
    ...chip('event-date', content.badge, {
      anchor: 'bottom-left',
      offset: { x: m, y: 0.34 },
      brandKit: opts.brandKit,
      size: 0.032,
    }),
  )
  wrap(content.headline, 22, 3).forEach((line, i) =>
    layers.push(
      text(`headline-${i}`, line, {
        anchor: 'bottom-left',
        offset: { x: m, y: 0.18 + (2 - i) * 0.075 },
        size: { w: 1 - m * 2, h: 0.068 },
        weight: 800,
      }),
    ),
  )
  if (content.subtext) {
    layers.push(
      text('sub-0', content.subtext, {
        anchor: 'bottom-left',
        offset: { x: m, y: 0.125 },
        size: { w: 1 - m * 2, h: 0.034 },
        opacity: 0.9,
        weight: 500,
      }),
    )
  }
  layers.push(...ctaLayers(content, opts, { anchor: 'bottom-left', y: 0.05 }))
  return layers.filter(Boolean)
}

// Carousel slide: index marker + headline, cohesive across slides.
function carouselSlide(content, opts) {
  const m = marginOf(opts)
  const { primary } = paletteOf(opts.brandKit)
  const layers = [scrim(0.5)]

  if (opts.slideIndex != null) {
    layers.push(
      createLayer(LAYER_TYPES.RECT, {
        id: 'slide-no-bg',
        anchor: 'top-left',
        offset: { x: m, y: m },
        size: { w: 0.1, h: 0.1 },
        square: true,
        fill: primary,
        radius: 0.05,
        locked: true,
        z: Z.CHIP,
      }),
      text('slide-no', String(opts.slideIndex + 1), {
        anchor: 'top-left',
        offset: { x: m, y: m + 0.025 },
        size: { w: 0.1, h: 0.05 },
        fill: readableOn(primary),
        weight: 800,
        align: 'center',
      }),
    )
  }

  wrap(content.headline, 24, 3).forEach((line, i) =>
    layers.push(
      text(`headline-${i}`, line, {
        anchor: 'bottom-left',
        offset: { x: m, y: 0.11 + (2 - i) * 0.078 },
        size: { w: 1 - m * 2, h: 0.07 },
        weight: 800,
      }),
    ),
  )
  return layers.filter(Boolean)
}

// Shared CTA renderer — a solid pill or an underlined link, depending on
// whether the layout wants emphasis.
function ctaLayers(content, opts, { anchor, y, solid }) {
  if (!content.cta) return []
  const m = marginOf(opts)
  const { primary } = paletteOf(opts.brandKit)
  const fill = solid || primary
  // The pill hugs its label, but never wider than the safe area — a long CTA
  // must shrink to fit rather than run past the margin.
  const width = Math.min(0.16 + String(content.cta).length * 0.021, 1 - m * 2)
  return [
    createLayer(LAYER_TYPES.RECT, {
      id: 'cta-bg',
      anchor,
      offset: { x: m, y },
      size: { w: width, h: 0.072 },
      fill,
      radius: 0.036,
      locked: true,
      z: Z.CHIP,
    }),
    createLayer(LAYER_TYPES.TEXT, {
      id: 'cta',
      text: content.cta,
      anchor,
      offset: { x: m + width / 2, y: y + 0.022 },
      size: { w: width, h: 0.034 },
      fill: readableOn(fill),
      weight: 700,
      align: 'center',
      z: Z.TEXT,
    }),
  ]
}

// ---- Catalog ---------------------------------------------------------------

const SLOTS = {
  basic: ['headline', 'subtext'],
  cta: ['headline', 'subtext', 'cta'],
  offer: ['badge', 'headline', 'subtext', 'cta'],
  product: ['headline', 'price', 'subtext', 'cta'],
  event: ['badge', 'headline', 'subtext', 'cta'],
  quote: ['headline', 'subtext'],
}

export const TEMPLATE_CATEGORIES = ['Platform', 'Purpose']

// Shared layout rules. Most templates are one of three shapes — a lower-third
// text block, a full-frame centred statement, or a top-weighted vertical — so
// the rules are declared once and pointed at, rather than restated thirteen
// times where they could drift apart.
const LOWER_THIRD_LAYOUT = layoutOf({
  zone: 'bottom',
  altZones: ['top'], // safe to flip: the block is self-contained
  band: 0.58,
  logo: 'top-right',
  cta: 'bottom-left',
})
const CENTERED_LAYOUT = layoutOf({
  zone: 'center',
  band: 1,
  align: 'center',
  logo: 'top-right',
  cta: 'bottom-center',
  // A centred statement is read in one glance; long copy destroys that.
  maxChars: { headline: 60, subtext: 90 },
})
const STORY_LAYOUT = layoutOf({
  zone: 'top',
  band: 0.42,
  margin: 0.08, // stories lose their edges to platform UI
  logo: 'bottom-right',
  cta: 'bottom-left',
  maxChars: { headline: 60 },
})

export const CONTENT_TEMPLATES = [
  // --- Platform-shaped -------------------------------------------------
  {
    id: 'ig-post', label: 'Instagram Post', category: 'Platform',
    defaultSize: 'ig-square', build: lowerThird, slots: SLOTS.cta,
    background: 'clean composition with uncluttered space in the lower half',
    layout: LOWER_THIRD_LAYOUT,
  },
  {
    id: 'ig-story', label: 'Instagram Story', category: 'Platform',
    defaultSize: 'story', build: story, slots: SLOTS.offer,
    background: 'vertical composition, subject centred, clear space top and bottom',
    layout: STORY_LAYOUT,
  },
  {
    id: 'fb-post', label: 'Facebook Post', category: 'Platform',
    defaultSize: 'facebook', build: lowerThird, slots: SLOTS.cta,
    background: 'warm approachable scene with clear space in the lower half',
    layout: LOWER_THIRD_LAYOUT,
  },
  {
    id: 'li-post', label: 'LinkedIn Post', category: 'Platform',
    defaultSize: 'linkedin', build: lowerThird, slots: SLOTS.cta,
    background: 'professional business setting, restrained palette, clear lower third',
    // Landscape: less height for text, so the copy budget is tighter.
    layout: layoutOf({ ...LOWER_THIRD_LAYOUT, maxChars: { headline: 60, subtext: 90 } }),
  },
  {
    id: 'x-post', label: 'Twitter / X Post', category: 'Platform',
    defaultSize: 'twitter', build: lowerThird, slots: SLOTS.basic,
    background: 'bold high-contrast composition, clear space in the lower third',
    layout: layoutOf({ ...LOWER_THIRD_LAYOUT, maxChars: { headline: 60, subtext: 90 } }),
  },
  {
    id: 'pin', label: 'Pinterest Pin', category: 'Platform',
    defaultSize: 'pinterest', build: pin, slots: SLOTS.cta,
    background: 'tall vertical composition, bright and aspirational, clear lower half',
    layout: layoutOf({ zone: 'bottom', altZones: ['top'], band: 0.55, logo: 'top-right' }),
  },
  {
    id: 'carousel', label: 'Carousel', category: 'Platform',
    defaultSize: 'ig-square', build: carouselSlide, slots: SLOTS.basic,
    background: 'cohesive series style, consistent palette, clear lower third',
    isCarousel: true,
    // No altZones: the slide number sits top-left, and slides must stay
    // consistent with each other — flipping one would break the set.
    layout: layoutOf({ zone: 'bottom', band: 0.5, logo: 'top-right', maxChars: { headline: 65 } }),
  },
  // --- Purpose-shaped ---------------------------------------------------
  {
    id: 'promotional', label: 'Promotional', category: 'Purpose',
    defaultSize: 'ig-square', build: offer, slots: SLOTS.offer,
    background: 'energetic promotional scene, vibrant, clear space in the lower half',
    layout: layoutOf({ zone: 'bottom', altZones: ['top'], band: 0.62, maxChars: { headline: 50 } }),
  },
  {
    id: 'product', label: 'Product Showcase', category: 'Purpose',
    defaultSize: 'ig-square', build: product, slots: SLOTS.product,
    background: 'clean product photography on a seamless background, product in the upper two thirds',
    // The product must stay visible, so the text never moves off the bottom.
    layout: layoutOf({ zone: 'bottom', band: 0.46, maxChars: { headline: 48, subtext: 70 } }),
  },
  {
    id: 'quote', label: 'Quote', category: 'Purpose',
    defaultSize: 'ig-square', build: centered, slots: SLOTS.quote,
    background: 'simple textured backdrop, minimal detail, nothing competing with centred text',
    options: { quoteMark: true },
    layout: CENTERED_LAYOUT,
  },
  {
    id: 'event', label: 'Event', category: 'Purpose',
    defaultSize: 'ig-portrait', build: event, slots: SLOTS.event,
    background: 'atmospheric venue or gathering scene, clear space in the lower half',
    layout: layoutOf({ zone: 'bottom', altZones: ['top'], band: 0.6, maxChars: { headline: 60 } }),
  },
  {
    id: 'hiring', label: 'Hiring', category: 'Purpose',
    defaultSize: 'ig-square', build: offer, slots: SLOTS.offer,
    background: 'welcoming workplace scene with real people, clear space in the lower half',
    layout: layoutOf({ zone: 'bottom', altZones: ['top'], band: 0.62, maxChars: { headline: 50 } }),
  },
  {
    id: 'announcement', label: 'Announcement', category: 'Purpose',
    defaultSize: 'ig-square', build: centered, slots: SLOTS.basic,
    background: 'striking simple backdrop, low detail, nothing competing with centred text',
    layout: CENTERED_LAYOUT,
  },
]

export const DEFAULT_TEMPLATE_ID = 'ig-post'

export function getContentTemplate(id) {
  return (
    CONTENT_TEMPLATES.find((t) => t.id === id) ||
    CONTENT_TEMPLATES.find((t) => t.id === DEFAULT_TEMPLATE_ID)
  )
}

/** The layout rules a template declares (safe zone, margins, budgets, …). */
export function getLayout(templateId) {
  return getContentTemplate(templateId).layout || LAYOUT_DEFAULTS
}

/**
 * Where this template's text lives — "bottom", "center", "top".
 * Sent to the image pipeline so the artwork is composed around it.
 */
export function safeZoneFor(templateId) {
  return getLayout(templateId).zone
}

/** Per-slot character budgets for this layout, for the copy writer. */
export function maxCharsFor(templateId) {
  return getLayout(templateId).maxChars
}

/**
 * Build the content layers for a template.
 *
 * @param {string} templateId
 * @param {object} content   AI-generated slot values { headline, subtext, cta, badge, price }
 * @param {object} options   { brandKit, slideIndex, placement, aspect }
 *
 * `placement` is the result of reading the generated image (see smartLayout.js)
 * — which zone actually came out calm, how busy it is, how bright. Omitted,
 * the template's declared zone is used, which is the behaviour without any
 * image analysis.
 */
export function buildContentLayers(templateId, content, options = {}) {
  if (!content) return []
  // Layouts open with a scrim to guarantee text contrast. With no text there
  // is nothing to make readable, so the scrim would just darken the image for
  // no reason — return nothing and let the artwork stand on its own.
  const hasCopy = ['headline', 'subtext', 'cta', 'badge', 'price'].some((k) =>
    String(content[k] || '').trim(),
  )
  if (!hasCopy) return []
  const template = getContentTemplate(templateId)
  const layout = getLayout(templateId)
  const opts = { ...template.options, layout, ...options }
  try {
    const built = template.build(content, opts).filter(Boolean)
    const placed = applyPlacement(built, layout, options.placement)
    // Last gate before anything is drawn: nothing outside the canvas, nothing
    // outside the safe margins, nothing overlapping.
    return validateLayers(placed, { aspect: options.aspect ?? 1, layout })
  } catch {
    // A broken layout must never take the whole image down.
    return []
  }
}

/** Prompt guidance so the background suits the layout rather than fighting it. */
export function backgroundHintFor(templateId) {
  return getContentTemplate(templateId).background || null
}
