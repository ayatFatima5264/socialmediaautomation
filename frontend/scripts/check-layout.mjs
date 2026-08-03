// ---------------------------------------------------------------------------
// Layout invariants, checked across every combination the product can produce.
//
//   13 content templates x 5 aspect ratios x short/long copy x 4 brand
//   templates = 520 designs, each asserted to have nothing off the canvas and
//   nothing overlapping.
//
// This exists because layout bugs are invisible in code review and obvious to
// a user: a template's geometry is correct for the copy length and frame shape
// it was written against, and quietly wrong two aspect ratios away. The
// combinations are too many to check by eye and too cheap to skip.
//
// Run with:  node scripts/check-layout.mjs   (or: npm run check:layout)
// The brandKit modules are plain ESM with no React or DOM dependency, so Node
// runs them directly — no test framework, no build step.
// ---------------------------------------------------------------------------

import {
  CONTENT_TEMPLATES,
  buildContentLayers,
  getLayout,
} from '../src/lib/brandKit/contentTemplates.js'
import { buildBrandLayers, TEMPLATES } from '../src/lib/brandKit/templates.js'
import { findLayoutIssues, validateLayers } from '../src/lib/brandKit/validateLayout.js'
import { resolveLayer } from '../src/lib/brandKit/layers.js'
import { applyPlacement, choosePlacement } from '../src/lib/brandKit/smartLayout.js'

const ASPECTS = { '1:1': 1, '4:5': 0.8, '9:16': 0.5625, '16:9': 1.7778, '2:3': 0.6667 }

const BRAND = {
  business_name: 'Croyten Digital Solutions',
  logo_url: 'data:image/png;base64,iVBORw0KGgo=',
  brand_colors: ['#1f8a5b', '#0b3d2e'],
  website: 'www.croyten.com',
  phone: '+92 300 1234567',
  email: 'hello@croyten.com',
}

const COPY = {
  short: { headline: 'Fresh bread daily', subtext: 'Baked at 5am', cta: 'Order', badge: 'NEW', price: '£4' },
  long: {
    headline: 'Our brand new artisan sourdough range is finally here for everyone',
    subtext:
      'Slow fermented for thirty six hours using stoneground organic flour milled a few miles down the road from us',
    cta: 'Reserve your loaf today',
    badge: 'LIMITED TIME OFFER',
    price: 'From £12.50',
  },
}

let failures = 0
const fail = (msg) => {
  failures++
  console.log('  FAIL ' + msg)
}

// Measurements standing in for a generated image: the declared zone calm, and
// the declared zone busy enough that placement should look elsewhere.
const READINGS = {
  calm: { top: { busy: 0.3, light: 0.5 }, center: { busy: 0.4, light: 0.5 }, bottom: { busy: 0.15, light: 0.3 } },
  busy: { top: { busy: 0.1, light: 0.7 }, center: { busy: 0.9, light: 0.5 }, bottom: { busy: 0.85, light: 0.6 } },
}

console.log('== overflow / margins / overlap ==')
let combos = 0
for (const t of CONTENT_TEMPLATES) {
  for (const [name, aspect] of Object.entries(ASPECTS)) {
    for (const [kind, content] of Object.entries(COPY)) {
      for (const brandTemplate of TEMPLATES) {
        for (const [reading, zones] of Object.entries({ none: null, ...READINGS })) {
          const layout = getLayout(t.id)
          const placement = zones ? choosePlacement(layout, zones) : undefined
          const layers = validateLayers(
            [
              ...buildContentLayers(t.id, content, {
                brandKit: BRAND,
                aspect,
                placement,
                slideIndex: t.isCarousel ? 0 : undefined,
              }),
              ...buildBrandLayers(BRAND, {
                template: brandTemplate.id,
                logoPosition: 'top-right',
                includeContact: brandTemplate.usesContact,
              }),
            ],
            { aspect, layout },
          )
          combos++
          const where = `${t.id}/${name}/${kind}/${brandTemplate.id}/${reading}`
          const issues = findLayoutIssues(layers, { aspect, layout })
          const outside = issues.filter((i) => i.type === 'outside-canvas')
          if (outside.length) fail(`${where}: ${JSON.stringify(outside)}`)
          const overlaps = issues.filter((i) => i.type === 'overlap')
          if (overlaps.length) fail(`${where} overlaps: ${JSON.stringify(overlaps.slice(0, 3))}`)
        }
      }
    }
  }
}
console.log(failures ? `  ${failures} failure(s) of ${combos}` : `  ok (${combos} designs)`)

console.log('== centred headline lines get distinct baselines ==')
const centred = buildContentLayers('quote', COPY.long, { brandKit: BRAND, aspect: 1 })
const ys = centred.filter((l) => l.id?.startsWith('headline-')).map((l) => Math.round(resolveLayer(l, { width: 1000, height: 1000 }).y))
console.log('  baselines:', ys)
if (new Set(ys).size !== ys.length) fail('centred headline lines share a baseline')
if (ys.length > 1 && !ys.every((y, i) => i === 0 || y > ys[i - 1])) fail('centred lines are out of order')

console.log('== placement flip preserves reading order ==')
const built = buildContentLayers('ig-post', COPY.short, { brandKit: BRAND, aspect: 1 })
const layout = getLayout('ig-post')
const flipped = applyPlacement(built, layout, { zone: 'top', moved: true, scrim: 1 })
const order = (list) =>
  list
    .filter((l) => l.type === 'text')
    .map((l) => ({ id: l.id, y: resolveLayer(l, { width: 1000, height: 1000 }).y }))
    .sort((a, b) => a.y - b.y)
    .map((l) => l.id)
console.log('  bottom:', order(built).join(' > '))
console.log('  top   :', order(flipped).join(' > '))
if (order(built).join() !== order(flipped).join()) fail('flip changed reading order')
const topBoxes = flipped.filter((l) => l.type === 'text').map((l) => resolveLayer(l, { width: 1000, height: 1000 }))
if (!topBoxes.every((b) => b.y < 600)) fail('flipped layers did not move to the top band')

console.log('== busy zone triggers a move, calm one does not ==')
const calm = choosePlacement(layout, { top: { busy: 0.1, light: 0.4 }, center: { busy: 0.5, light: 0.4 }, bottom: { busy: 0.12, light: 0.3 } })
const busy = choosePlacement(layout, { top: { busy: 0.1, light: 0.4 }, center: { busy: 0.5, light: 0.4 }, bottom: { busy: 0.8, light: 0.3 } })
console.log('  calm ->', calm.zone, 'scrim', calm.scrim.toFixed(2), '| busy ->', busy.zone, 'scrim', busy.scrim.toFixed(2))
if (calm.moved) fail('moved despite a calm declared zone')
if (!busy.moved || busy.zone !== 'top') fail('did not move away from a busy zone')
if (!(busy.scrim > calm.scrim)) fail('busy zone did not get a stronger scrim')

console.log('== validation is idempotent ==')
const once = validateLayers(built, { aspect: 1, layout })
const twice = validateLayers(once, { aspect: 1, layout })
if (JSON.stringify(once) !== JSON.stringify(twice)) fail('validateLayers is not idempotent')

console.log(failures ? `\nFAILURES: ${failures}` : '\nALL OK')
process.exit(failures ? 1 : 0)
