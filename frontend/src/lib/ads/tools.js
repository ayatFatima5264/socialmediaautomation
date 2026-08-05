// ---------------------------------------------------------------------------
// AI Ads Studio — the module's feature registry.
//
// One list drives everything: the cards on the Studio home and how they are
// grouped, the module's routes in App.jsx, each placeholder page's copy, and
// the private route/title entries in seo/pages.data.js. Adding a feature in a
// later phase means adding an entry here and pointing its route at a real page
// — the section it appears in, its card, its artwork, its tab title and its
// robots.txt Disallow all follow.
//
// This module is deliberately dependency-free and free of Vite-specific syntax
// (no import.meta, no JSX, no ?raw globs) for the same reason posts.data.js is:
// seo/pages.data.js imports it, and that module is loaded by the Node-side
// build plugin. Artwork is referenced by KEY, not by component, so the drawings
// can live in a .jsx file without dragging JSX into a Node import.
// ---------------------------------------------------------------------------

export const ADS_BASE_PATH = '/ads'

// ---------------------------------------------------------------------------
// Sections
// ---------------------------------------------------------------------------
// The home page groups cards by category rather than listing them flat: with
// fifteen tools, an ungrouped grid gives the user no answer to "what do I do
// first". Order here is the order on the page — creation first, because that is
// what the Studio is for.

export const AD_CATEGORIES = [
  {
    key: 'create',
    label: 'Create Ads',
    description: 'Turn a product or an idea into finished ad creative.',
  },
  {
    key: 'video',
    label: 'Video Ads',
    description: 'Motion creative for Reels, Stories and in-feed placements.',
  },
  {
    key: 'tools',
    label: 'AI Tools',
    description: 'Write, vary and test the words around the creative.',
  },
  {
    key: 'assets',
    label: 'Assets',
    description: 'The brand, imagery and layouts every ad is built from.',
  },
]

// ---------------------------------------------------------------------------
// Tools
// ---------------------------------------------------------------------------
// `preview` is what the card draws. Two panels reading before → after says what
// a tool DOES far faster than an icon does; `single` is for tools that are a
// place rather than a transformation.
//
// `tint` gives each card its own identity while staying inside the palette the
// app already uses (see CONTENT_TYPE_STYLES / STATUS_STYLES in lib/constants.js).
// The mint accent stays the module's primary — these colour the artwork only.
//
// `to` points a card at an EXISTING page instead of a module placeholder. Brand
// Kit is the case today: it is the business profile, already built, and sending
// users to a "coming soon" screen for something that ships would be a lie.

export const AD_TOOLS = [
  // ---- Create Ads ---------------------------------------------------------
  {
    slug: 'product-ads',
    name: 'Product Ads',
    description: 'Drop in a product photo and get a finished, on-brand ad set.',
    category: 'create',
    tint: 'emerald',
    featured: true,
    phase: 2,
    preview: { before: 'photo', after: 'ad' },
    longDescription:
      'Upload a product shot and AI Ads Studio will build a complete ad set around it — background, offer framing, headline, and a call to action sized for each platform placement.',
    capabilities: [
      'Background replacement and product clean-up',
      'Offer, headline and CTA generated from your Brand Kit',
      'One creative per placement, exported at the right ratio',
    ],
  },
  {
    slug: 'banner-generator',
    name: 'Banner Generator',
    description: 'One layout, re-flowed into every standard display size.',
    category: 'create',
    tint: 'violet',
    phase: 2,
    preview: { before: 'blank', after: 'banners' },
    longDescription:
      'Produce a full set of display banners from one layout. The studio re-flows your headline, logo and CTA into every standard size instead of cropping a single design.',
    capabilities: [
      'All IAB standard sizes from one source layout',
      'Brand Kit logo, colours and fonts applied automatically',
      'Re-flowed per size — never a stretched crop',
    ],
  },
  {
    slug: 'carousel-ads',
    name: 'Carousel Ads',
    description: 'Multi-card ads that tell one story across the swipe.',
    category: 'create',
    tint: 'amber',
    phase: 2,
    preview: { before: 'still', after: 'slides' },
    longDescription:
      'Plan a carousel as a sequence rather than a pile of images: a hook card, the middle cards that carry the argument, and a closing card that asks for the click.',
    capabilities: [
      'Hook → body → CTA card structure',
      'Consistent layout and typography across slides',
      'Per-card copy tuned to its position in the sequence',
    ],
  },

  // ---- Video Ads ----------------------------------------------------------
  {
    slug: 'image-to-video',
    name: 'Image to Video',
    description: 'Animate a still creative into a scroll-stopping video ad.',
    category: 'video',
    tint: 'sky',
    phase: 2,
    preview: { before: 'still', after: 'frames' },
    longDescription:
      'Take any still creative — a product shot, a banner, a generated image — and turn it into a short motion ad with camera movement, text reveals, and a soundtrack.',
    capabilities: [
      'Camera pans, zooms and parallax from a single image',
      'Animated headline and CTA reveals',
      'Exports sized for Reels, Stories and in-feed video',
    ],
  },
  {
    slug: 'text-to-video',
    name: 'Text to Video',
    description: 'Describe the ad you want and get a finished video concept.',
    category: 'video',
    tint: 'indigo',
    phase: 3,
    preview: { before: 'prompt', after: 'video' },
    longDescription:
      'Write a prompt or paste your offer, and the studio scripts, storyboards and assembles a short video ad — scenes, on-screen copy, voiceover and pacing included.',
    capabilities: [
      'Script and storyboard generated from a single prompt',
      'Scene-by-scene editing before render',
      'Voiceover and captions in your brand voice',
    ],
  },
  {
    slug: 'product-showcase-video',
    name: 'Product Showcase Video',
    description: 'Rotate, light and present a product in short-form video.',
    category: 'video',
    tint: 'cyan',
    phase: 3,
    preview: { before: 'photo', after: 'video' },
    longDescription:
      'Turn a handful of product photos into a showcase video — controlled camera moves, studio lighting, and feature callouts timed to the reveal.',
    capabilities: [
      'Turntable and dolly moves from stills',
      'Feature callouts timed to the shot',
      'Studio lighting presets per product type',
    ],
  },
  {
    slug: 'slideshow-video',
    name: 'Slideshow Video',
    description: 'Several images into one paced, captioned video.',
    category: 'video',
    tint: 'teal',
    phase: 3,
    preview: { before: 'photos', after: 'video' },
    longDescription:
      'The fastest route from a folder of images to a running ad: pick the shots, and the studio handles order, pacing, transitions and captions.',
    capabilities: [
      'Automatic pacing and transitions',
      'Captions generated per slide',
      'Music bed matched to the cut',
    ],
  },

  // ---- AI Tools -----------------------------------------------------------
  {
    slug: 'ad-copy',
    name: 'AI Ad Copy',
    description: 'Headlines, primary text and CTAs tuned to each platform.',
    category: 'tools',
    tint: 'rose',
    phase: 2,
    preview: { before: 'text', after: 'copyset' },
    longDescription:
      'Generate ad copy that respects each platform’s character limits and conventions, with several angles per campaign so you have something real to test against.',
    capabilities: [
      'Multiple angles per campaign, not one safe option',
      'Headline, primary text, description and CTA variants',
      'Platform character limits enforced as you edit',
    ],
  },
  {
    slug: 'headline-generator',
    name: 'Headline Generator',
    description: 'Ranked headline options for one offer.',
    category: 'tools',
    tint: 'orange',
    phase: 2,
    preview: { before: 'text', after: 'headlines' },
    longDescription:
      'Produce a spread of headlines for a single offer — different angles, lengths and levels of directness — ranked so you know which to test first.',
    capabilities: [
      'Curiosity, benefit, objection and proof angles',
      'Length variants for every placement',
      'Ranked, with the reasoning shown',
    ],
  },
  {
    slug: 'cta-generator',
    name: 'CTA Generator',
    description: 'Calls to action matched to the offer and the platform.',
    category: 'tools',
    tint: 'pink',
    phase: 2,
    preview: { before: 'text', after: 'cta' },
    longDescription:
      'The last two words of an ad decide whether the click happens. Generate calls to action matched to the offer, the funnel stage and each platform’s button set.',
    capabilities: [
      'Matched to funnel stage, not generic',
      'Mapped to each platform’s native CTA buttons',
      'Microcopy for the surrounding line as well',
    ],
  },
  {
    slug: 'variations',
    name: 'Multiple Variations',
    description: 'Spin one winning creative into a testable set.',
    category: 'tools',
    tint: 'fuchsia',
    phase: 3,
    preview: { before: 'ad', after: 'variants' },
    longDescription:
      'Take a creative that works and generate a set around it — changing one variable at a time so the results are readable rather than a pile of unrelated ads.',
    capabilities: [
      'One variable changed per variant',
      'Copy, colour, layout and imagery axes',
      'Batch export to every placement',
    ],
  },
  {
    slug: 'ab-testing',
    name: 'A/B Testing',
    description: 'Run creatives against each other and read the result.',
    category: 'tools',
    tint: 'slate',
    phase: 4,
    preview: { before: 'variants', after: 'abtest' },
    longDescription:
      'Set two or more creatives against each other with a split that holds, and get a readout that says which won and whether the gap is real yet.',
    capabilities: [
      'Even splits that survive platform delivery',
      'Significance shown, not just totals',
      'Winner promoted to the campaign in a click',
    ],
  },

  // ---- Assets -------------------------------------------------------------
  {
    slug: 'brand-kit',
    name: 'Brand Kit',
    description: 'Your logo, colours, fonts and voice — applied to every ad.',
    category: 'assets',
    tint: 'emerald',
    // Already built: the Brand Kit is the business profile. The card links
    // there rather than to a placeholder for something that ships today.
    to: '/business-profile',
    available: true,
  },
  {
    slug: 'media-library',
    name: 'Media Library',
    description: 'Stock imagery and your own uploads, ready to drop into an ad.',
    category: 'assets',
    tint: 'sky',
    phase: 2,
    longDescription:
      'The Media Library already ships as a picker inside the editor — it opens wherever an image is needed. This is where browsing and managing it from the Studio will live.',
    capabilities: [
      'Curated stock set plus your own uploads',
      'Search by category, industry, colour and orientation',
      'Opens directly inside every ad tool',
    ],
  },
  {
    slug: 'templates',
    name: 'Templates',
    description: 'Starting layouts for each ad type and placement.',
    category: 'assets',
    tint: 'violet',
    phase: 2,
    longDescription:
      'Layouts to start from rather than a blank artboard — each one already sized, typeset and wired to your Brand Kit.',
    capabilities: [
      'A starting layout per ad type and placement',
      'Brand Kit applied on selection',
      'Save your own layouts as reusable templates',
    ],
  },
]

/** Tools in a category, in registry order. */
export function toolsInCategory(key) {
  return AD_TOOLS.filter((t) => t.category === key)
}

/** Route for a tool's own page inside the module. */
export function adToolPath(slug) {
  return `${ADS_BASE_PATH}/${slug}`
}

/**
 * Where a card links.
 *
 * A tool that already exists elsewhere in the app points at the real page; a
 * tool the Studio owns points at its own route. Cards never build this string
 * themselves, so moving a feature is one edit in the registry.
 */
export function toolHref(tool) {
  return tool.to || adToolPath(tool.slug)
}

/** A tool by slug, or null — an unknown slug must render a not-found, not crash. */
export function getAdTool(slug) {
  return AD_TOOLS.find((t) => t.slug === slug) || null
}

// ---- Hero quick actions ---------------------------------------------------
// The shortcuts under the hero's primary buttons. Each is a real starting point
// that lands inside a tool, so the hero offers a way in rather than one button
// and a wall of cards.

export const HERO_QUICK_ACTIONS = [
  { label: 'Upload Product', hint: 'Add your product image', slug: 'product-ads', icon: '⬆', tint: 'emerald' },
  { label: 'Generate Copy', hint: 'AI headlines & text', slug: 'ad-copy', icon: '✍', tint: 'amber' },
  { label: 'Generate Banner', hint: 'Multiple sizes', slug: 'banner-generator', icon: '▭', tint: 'rose' },
  { label: 'Make a Video', hint: 'From image or text', slug: 'image-to-video', icon: '▶', tint: 'violet' },
]

// ---- Card artwork ---------------------------------------------------------
// Which scene in AdCreativeArt a tool's card shows. Kept as a slug → scene map
// rather than a field on each entry so the registry above stays about the
// product and this stays about presentation — and so several tools can share
// one scene without that looking like a copy-paste mistake.
const TOOL_ART = {
  'product-ads': 'productAd',
  'banner-generator': 'bannerAd',
  'carousel-ads': 'carouselAd',
  'image-to-video': 'imageVideo',
  'text-to-video': 'textVideo',
  'product-showcase-video': 'showcase',
  'slideshow-video': 'imageVideo',
  'ad-copy': 'adCopy',
  'headline-generator': 'adCopy',
  'cta-generator': 'adCopy',
  variations: 'productAd',
  'ab-testing': 'bannerAd',
  'brand-kit': 'productAd',
  'media-library': 'carouselAd',
  templates: 'bannerAd',
}

/** The creative scene a tool's card shows. */
export function toolArt(slug) {
  return TOOL_ART[slug] || 'productAd'
}

// What the Studio can do, said plainly at the top of the page.
export const HERO_CAPABILITIES = [
  'Product Photos',
  'Video Ads',
  'Carousel Ads',
  'AI Copy',
  'Banners',
]

// ---- Campaign routes ------------------------------------------------------
// The campaign editor is a later phase, but the Studio home already needs
// somewhere for "New campaign" and each row's Edit button to go. Naming the
// paths here means the placeholder now and the real editor later share one
// definition instead of hardcoded strings scattered through the UI.
export const CAMPAIGN_NEW_PATH = `${ADS_BASE_PATH}/campaigns/new`

export function campaignPath(id) {
  return `${ADS_BASE_PATH}/campaigns/${id}`
}

// ---- SEO registry support -------------------------------------------------
// seo/pages.data.js needs two answers about any path: is it private (so it is
// disallowed in robots.txt and forced noindex), and what should the browser tab
// say. Both are answered here rather than by a hand-kept list over there —
// campaign paths carry an id and could never be enumerated, and a list of tool
// paths would silently fall behind the moment a tool is added.

/** Does this path belong to AI Ads Studio? */
export function isAdsPath(path) {
  return path === ADS_BASE_PATH || String(path).startsWith(`${ADS_BASE_PATH}/`)
}

/**
 * The browser-tab title for a path in this module, or null if it is not one.
 *
 * Private routes are served the noindex 404 shell by design, so without a title
 * here a perfectly working Studio page would sit under a "Page Not Found" tab.
 */
export function adsRouteTitle(path) {
  if (!isAdsPath(path)) return null
  if (path === ADS_BASE_PATH) return 'AI Ads Studio'
  if (path === CAMPAIGN_NEW_PATH) return 'New Campaign'
  if (path.startsWith(`${ADS_BASE_PATH}/campaigns/`)) return 'Campaign'

  const tool = getAdTool(path.slice(ADS_BASE_PATH.length + 1))
  return tool ? tool.name : 'AI Ads Studio'
}
