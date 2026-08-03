// ---------------------------------------------------------------------------
// Brand Kit templates.
//
// A template is a pure function: (brandKit, options) -> Layer[]. It decides
// WHICH brand elements appear and HOW they are arranged; it never draws
// anything. That separation is what lets the same template feed the SVG
// preview, the Canvas rasteriser, and a future drag-to-edit surface.
//
// Adding a template means adding one entry to TEMPLATES — no renderer changes,
// no UI changes. Phase 2 template editing can generate these objects at
// runtime instead of importing them from here.
//
// All geometry is fractional (see layers.js), so every template is responsive
// across square, portrait, and landscape frames by construction.
// ---------------------------------------------------------------------------

import {
  LAYER_TYPES,
  createLayer,
  paletteOf,
  readableOn,
} from './layers.js'

// Contact lines, in the order they should appear when present.
function contactLines(brandKit, { includeContact }) {
  if (!includeContact) return []
  return [brandKit.website, brandKit.phone, brandKit.email].filter(Boolean)
}

// Vertical rhythm for a bottom-anchored contact block.
//
// Offsets measure from the frame's bottom edge to an element's own bottom, so
// a block is built by stacking UPWARD from a bottom padding: the last line
// sits at the padding, each earlier line one step above it. Laying it out the
// other way — first line highest, subtract a step per line — silently walks
// the last line off the bottom of the frame as soon as there are three of
// them, which is exactly one website, one phone number and one email.
const CONTACT = { pad: 0.04, step: 0.032, lineH: 0.028, nameH: 0.048 }

function contactBlock(lines) {
  const { pad, step, nameH } = CONTACT
  // Offset for line `i`, counting from the top of the block.
  const lineY = (i) => pad + (lines.length - 1 - i) * step
  const top = pad + lines.length * step // where the block ends
  const nameY = lines.length ? top + 0.008 : pad
  return { lineY, nameY, height: nameY + nameH + pad }
}

// A logo layer in one of the four corners. Square-ish box; the renderer
// preserves the logo's own aspect ratio inside it.
function logoLayer(brandKit, { logoPosition = 'bottom-right', scale = 0.16 } = {}) {
  if (!brandKit.logo_url) return null
  return createLayer(LAYER_TYPES.IMAGE, {
    id: 'brand-logo',
    src: brandKit.logo_url,
    anchor: logoPosition,
    offset: { x: 0.045, y: 0.045 },
    size: { w: scale, h: scale },
    // Square box regardless of frame aspect — see resolveLayer.
    square: true,
    keepAspect: true,
    z: 30,
  })
}

// ---- Templates -------------------------------------------------------------

// Logo alone. The lightest possible branding — nothing competes with the art.
function cornerLogo(brandKit, opts) {
  return [logoLayer(brandKit, opts)].filter(Boolean)
}

// Solid brand bar across the bottom carrying the name and contact details.
// The bar guarantees contrast, so text is always readable whatever the image.
function footerBar(brandKit, opts) {
  const { primary } = paletteOf(brandKit)
  const ink = readableOn(primary)
  const lines = contactLines(brandKit, opts)
  // A bar with nothing in it is just a coloured stripe over the artwork.
  if (!brandKit.business_name && !brandKit.logo_url && !lines.length) return []
  // The bar is sized by what it holds, not by a fixed guess — three contact
  // lines need more room than none, and a bar too short for its contents puts
  // the last line on the artwork below it.
  const { lineY, nameY, height } = contactBlock(lines)
  const barH = Math.min(0.34, height)

  const layers = [
    createLayer(LAYER_TYPES.RECT, {
      id: 'brand-bar',
      anchor: 'bottom-left',
      offset: { x: 0, y: 0 },
      size: { w: 1, h: barH },
      fill: primary,
      opacity: 0.95,
      locked: true, // exists for contrast, not composition
      z: 10,
    }),
  ]

  if (brandKit.business_name) {
    layers.push(
      createLayer(LAYER_TYPES.TEXT, {
        id: 'brand-name',
        text: brandKit.business_name,
        anchor: 'bottom-left',
        offset: { x: 0.05, y: nameY },
        size: { w: 0.6, h: CONTACT.nameH },
        fill: ink,
        weight: 800,
        z: 20,
      }),
    )
  }

  lines.forEach((line, i) => {
    layers.push(
      createLayer(LAYER_TYPES.TEXT, {
        id: `brand-contact-${i}`,
        text: line,
        anchor: 'bottom-left',
        offset: { x: 0.05, y: lineY(i) },
        size: { w: 0.7, h: CONTACT.lineH },
        fill: ink,
        opacity: 0.92,
        weight: 500,
        z: 20,
      }),
    )
  })

  const logo = logoLayer(brandKit, { ...opts, logoPosition: 'bottom-right', scale: 0.1 })
  if (logo) {
    // Sit the logo inside the bar rather than over the artwork, centred on the
    // bar's own height whatever that turned out to be.
    logo.offset = { x: 0.05, y: Math.max(0.02, barH / 2 - 0.05) }
    layers.push(logo)
  }
  return layers
}

// Rounded badge holding the logo and name. Sits over the art, so it carries a
// translucent backing to stay legible on busy images.
function badge(brandKit, opts) {
  const { primary } = paletteOf(brandKit)
  const ink = readableOn(primary)
  // An empty badge is a coloured rectangle with nothing to say.
  if (!brandKit.business_name && !brandKit.logo_url) return []
  const position = opts.logoPosition || 'bottom-left'
  const hasName = Boolean(brandKit.business_name)
  const w = hasName ? 0.46 : 0.16

  const layers = [
    createLayer(LAYER_TYPES.RECT, {
      id: 'brand-badge',
      anchor: position,
      offset: { x: 0.045, y: 0.045 },
      size: { w, h: 0.13 },
      fill: primary,
      opacity: 0.92,
      radius: 0.028,
      locked: true,
      z: 10,
    }),
  ]

  if (brandKit.logo_url) {
    layers.push(
      createLayer(LAYER_TYPES.IMAGE, {
        id: 'brand-logo',
        src: brandKit.logo_url,
        anchor: position,
        offset: { x: 0.07, y: 0.065 },
        size: { w: 0.09, h: 0.09 },
        keepAspect: true,
        z: 30,
      }),
    )
  }

  if (hasName) {
    layers.push(
      createLayer(LAYER_TYPES.TEXT, {
        id: 'brand-name',
        text: brandKit.business_name,
        anchor: position,
        offset: { x: brandKit.logo_url ? 0.19 : 0.075, y: 0.088 },
        size: { w: 0.3, h: 0.042 },
        fill: ink,
        weight: 700,
        align: 'left',
        z: 30,
      }),
    )
  }
  return layers
}

// Gradient scrim + text, no solid bar. The most editorial look; the scrim is a
// soft fade so the underlying image still reads through it.
function editorial(brandKit, opts) {
  const { primary } = paletteOf(brandKit)
  const lines = contactLines(brandKit, opts)
  // The scrim exists to make text readable; with no text it is just a shadow.
  if (!brandKit.business_name && !brandKit.logo_url && !lines.length) return []

  // Same upward-stacking rhythm as the footer bar — see contactBlock.
  const { lineY, nameY, height } = contactBlock(lines)

  const layers = [
    createLayer(LAYER_TYPES.RECT, {
      id: 'brand-scrim',
      anchor: 'bottom-left',
      offset: { x: 0, y: 0 },
      // The fade has to cover everything it is making readable, plus room to
      // fall off above it, or the top line sits on bare artwork.
      size: { w: 1, h: Math.min(0.6, height + 0.16) },
      gradient: { from: 'rgba(0,0,0,0)', to: 'rgba(0,0,0,0.78)' },
      locked: true,
      z: 10,
    }),
  ]

  if (brandKit.business_name) {
    layers.push(
      createLayer(LAYER_TYPES.TEXT, {
        id: 'brand-name',
        text: brandKit.business_name,
        anchor: 'bottom-left',
        offset: { x: 0.06, y: lines.length ? nameY + 0.026 : nameY },
        size: { w: 0.7, h: 0.062 },
        fill: '#ffffff',
        weight: 800,
        z: 20,
      }),
    )
  }

  if (lines.length) {
    layers.push(
      createLayer(LAYER_TYPES.RECT, {
        id: 'brand-rule',
        anchor: 'bottom-left',
        offset: { x: 0.06, y: nameY + 0.008 },
        size: { w: 0.1, h: 0.006 },
        fill: primary,
        radius: 0.003,
        locked: true,
        z: 20,
      }),
    )
    lines.forEach((line, i) => {
      layers.push(
        createLayer(LAYER_TYPES.TEXT, {
          id: `brand-contact-${i}`,
          text: line,
          anchor: 'bottom-left',
          offset: { x: 0.06, y: lineY(i) },
          size: { w: 0.8, h: 0.03 },
          fill: '#ffffff',
          opacity: 0.85,
          weight: 500,
          z: 20,
        }),
      )
    })
  }

  const logo = logoLayer(brandKit, { ...opts, logoPosition: opts.logoPosition || 'top-right', scale: 0.13 })
  if (logo) layers.push(logo)
  return layers
}

export const TEMPLATES = [
  {
    id: 'corner-logo',
    label: 'Logo only',
    description: 'Just your logo in a corner. Least intrusive.',
    build: cornerLogo,
    usesContact: false,
  },
  {
    id: 'badge',
    label: 'Badge',
    description: 'Logo and name in a rounded brand-colour badge.',
    build: badge,
    usesContact: false,
  },
  {
    id: 'footer-bar',
    label: 'Footer bar',
    description: 'Solid brand bar with your name and contact details.',
    build: footerBar,
    usesContact: true,
  },
  {
    id: 'editorial',
    label: 'Editorial',
    description: 'Soft gradient with large name — most magazine-like.',
    build: editorial,
    usesContact: true,
  },
]

export const DEFAULT_TEMPLATE = 'badge'

export function getTemplate(id) {
  return TEMPLATES.find((t) => t.id === id) || TEMPLATES.find((t) => t.id === DEFAULT_TEMPLATE)
}

/**
 * Build the layer list for a brand kit.
 *
 * @param {object} brandKit  business profile fields (logo_url, brand_colors, …)
 * @param {object} options   { template, logoPosition, includeContact }
 * @returns {Array} layers, or [] when branding is off or there is nothing to show
 */
export function buildBrandLayers(brandKit, options = {}) {
  if (!brandKit) return []
  const template = getTemplate(options.template)
  const opts = {
    logoPosition: options.logoPosition || 'bottom-right',
    includeContact: options.includeContact ?? template.usesContact,
    ...options,
  }
  try {
    return template.build(brandKit, opts).filter(Boolean)
  } catch {
    // A malformed template must never take the image with it.
    return []
  }
}
