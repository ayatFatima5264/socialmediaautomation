// ---------------------------------------------------------------------------
// AI Ads Studio — what a campaign is ADVERTISING, and everything that follows
// from it.
//
// `objective` says what a campaign should achieve; this says what it is about.
// The two are independent and both are needed: "Traffic" does not tell a banner
// whether to show a bottle on marble or a browser window, and asking someone
// promoting a blog to upload a product photo is the bug this module exists to
// fix.
//
// ---- Why the behaviour lives here rather than in each tool ----------------
// Six workspaces need the same four answers — what to call the subject, which
// visual styles to offer, how to structure a carousel, which video concepts
// make sense. Written inline, those lists drift the moment a seventh type is
// added and one page is missed. Declared here, adding a campaign type is one
// entry and every tool follows.
//
// A campaign stores the LABEL (`campaign_type` is a string on the wire), not
// the key, so the database stays readable and an unrecognised value degrades to
// the default rather than crashing a page.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Visual style sets
// ---------------------------------------------------------------------------
// Each style carries the phrase the image model actually reads. The label is
// what the user picks; `prompt` is what gets sent. Keeping them together is why
// a style can be renamed without quietly changing what it generates.

const PRODUCT_STYLES = [
  { label: 'Surface', prompt: 'standing on a clean studio surface, soft even lighting' },
  { label: 'Shadow', prompt: 'on a plain backdrop with a long directional drop shadow' },
  { label: 'Reflection', prompt: 'on a glossy reflective surface with a mirrored reflection beneath' },
  { label: 'Scene', prompt: 'styled in a considered scene with props and depth of field' },
  { label: 'Lifestyle', prompt: 'in use in a real home setting, natural window light' },
  { label: 'Gradient glow', prompt: 'floating against a soft gradient backdrop with a glow behind it' },
]

const WEBSITE_STYLES = [
  { label: 'Website Screenshot', prompt: 'a clean modern website page shown flat and straight on, crisp UI, generous white space' },
  { label: 'Illustration', prompt: 'a flat vector illustration of the idea, simple shapes, limited palette' },
  { label: 'Laptop Mockup', prompt: 'an open laptop on a desk showing a website, shallow depth of field' },
  { label: 'Browser Window', prompt: 'a browser window mockup floating on a soft gradient background, subtle shadow' },
  { label: 'Gradient Background', prompt: 'a smooth colour gradient background with plenty of empty space for text' },
  { label: 'Blog Thumbnail', prompt: 'an editorial blog thumbnail image, photographic, uncluttered, room for a headline' },
]

const SERVICE_STYLES = [
  { label: 'At work', prompt: 'a professional delivering the service, candid, natural light' },
  { label: 'Client meeting', prompt: 'two people talking across a table in a bright modern office' },
  { label: 'Before and after', prompt: 'a clean split composition contrasting two states of the same space' },
  { label: 'Team portrait', prompt: 'a small confident team, environmental portrait, warm tone' },
  { label: 'Icon panel', prompt: 'a minimal composition of simple service icons on a flat background' },
  { label: 'Gradient Background', prompt: 'a smooth colour gradient background with plenty of empty space for text' },
]

const BRAND_STYLES = [
  { label: 'Brand pattern', prompt: 'an abstract geometric pattern in a tight brand palette' },
  { label: 'Lifestyle', prompt: 'an aspirational lifestyle photograph, natural light, unposed' },
  { label: 'Editorial', prompt: 'a bold editorial composition with strong negative space' },
  { label: 'Texture', prompt: 'a close macro texture, tactile, single dominant colour' },
  { label: 'Portrait', prompt: 'a striking human portrait, soft studio lighting, direct gaze' },
  { label: 'Gradient Background', prompt: 'a smooth colour gradient background with plenty of empty space for text' },
]

const EVENT_STYLES = [
  { label: 'Venue', prompt: 'a filled venue before an event starts, atmospheric lighting' },
  { label: 'Crowd energy', prompt: 'an engaged audience mid-event, motion, warm stage light' },
  { label: 'Speaker stage', prompt: 'a speaker on a lit stage seen from the audience' },
  { label: 'Ticket graphic', prompt: 'a bold graphic poster composition with large empty areas for date and title' },
  { label: 'Countdown', prompt: 'a dramatic minimal background suited to a large countdown number' },
  { label: 'Gradient Background', prompt: 'a smooth colour gradient background with plenty of empty space for text' },
]

const APP_STYLES = [
  { label: 'Phone Mockup', prompt: 'a modern smartphone held in one hand showing a clean app screen' },
  { label: 'Screen Showcase', prompt: 'three floating phone screens overlapping at an angle on a soft background' },
  { label: 'In use', prompt: 'someone using a phone app in a real setting, over-the-shoulder framing' },
  { label: 'Feature Graphic', prompt: 'a bold app store style feature graphic, flat background, room for a title' },
  { label: 'Illustration', prompt: 'a flat vector illustration of the app idea, simple shapes, limited palette' },
  { label: 'Gradient Background', prompt: 'a smooth colour gradient background with plenty of empty space for text' },
]

const LEAD_STYLES = [
  { label: 'Offer graphic', prompt: 'a clean graphic panel built around one offer, large empty area for the headline' },
  { label: 'Guide cover', prompt: 'a downloadable guide or ebook cover shown at a slight angle' },
  { label: 'Form mockup', prompt: 'a simple sign-up form mockup floating on a soft background' },
  { label: 'Consultation', prompt: 'a friendly one-to-one consultation photographed candidly' },
  { label: 'Illustration', prompt: 'a flat vector illustration of the idea, simple shapes, limited palette' },
  { label: 'Gradient Background', prompt: 'a smooth colour gradient background with plenty of empty space for text' },
]

const GENERIC_STYLES = [
  { label: 'Photographic', prompt: 'a clean photographic composition, natural light, uncluttered' },
  { label: 'Illustration', prompt: 'a flat vector illustration of the idea, simple shapes, limited palette' },
  { label: 'Editorial', prompt: 'a bold editorial composition with strong negative space' },
  { label: 'Minimal', prompt: 'an extremely minimal composition, one subject, lots of empty space' },
  { label: 'Gradient Background', prompt: 'a smooth colour gradient background with plenty of empty space for text' },
]

// ---------------------------------------------------------------------------
// Carousel structure
// ---------------------------------------------------------------------------
// A carousel is a sequence: the first card earns the stop, the last asks for
// the click, and the middle carries the argument. Each family lists the middle
// cards in the order they should be used, and `closer` is always last however
// many slides are chosen — so a 5-slide and a 10-slide carousel both end with
// the ask rather than trailing off.

const CAROUSEL_STORIES = {
  product: {
    middle: ['Feature', 'Benefit', 'Close-up', 'Comparison', 'Proof', 'How it works', 'In use', 'Offer', 'Reviews'],
    closer: 'CTA — ask for the click',
  },
  website: {
    middle: ['Problem', 'Solution', 'Tips', 'Features', 'Example', 'Data point', 'Quote', 'Common mistake', 'What to read next'],
    closer: 'Visit the website',
  },
  service: {
    middle: ['The problem', 'How it works', 'What you get', 'Timeline', 'Pricing', 'Proof', 'Who it suits', 'FAQ', 'Guarantee'],
    closer: 'Book a call',
  },
  brand: {
    middle: ['Who we are', 'What we believe', 'How we make it', 'The people', 'The proof', 'Behind the scenes', 'Where to find us', 'What is next', 'In the wild'],
    closer: 'Follow along',
  },
  event: {
    middle: ['The event', 'Who is speaking', 'What you will learn', 'Where and when', 'The line-up', 'Last year', 'Who attends', 'Pricing', 'Getting there'],
    closer: 'Get your ticket',
  },
  app: {
    middle: ['The problem', 'The app', 'Key feature', 'Second feature', 'How it works', 'Reviews', 'Free tier', 'Privacy', 'Platforms'],
    closer: 'Download the app',
  },
  lead: {
    middle: ['The problem', 'What you get', 'Inside the guide', 'Who it is for', 'Proof', 'How long it takes', 'What happens next', 'Common questions', 'No spam promise'],
    closer: 'Get it free',
  },
  custom: {
    middle: ['The hook', 'The point', 'The detail', 'The proof', 'The objection', 'The example', 'The comparison', 'The offer', 'The recap'],
    closer: 'CTA — ask for the click',
  },
}

// ---------------------------------------------------------------------------
// Video concepts
// ---------------------------------------------------------------------------
// The shot the video tools plan or render. `prompt` is the concept handed to
// the planner, so picking one is a complete brief rather than a label the user
// then has to describe in their own words.

const VIDEO_CONCEPTS = {
  product: [
    { label: 'Product Rotation', prompt: 'a slow 360° turntable of the product on a lit studio surface' },
    { label: 'Lifestyle Ad', prompt: 'the product being used in a real home, warm natural light, unhurried cuts' },
    { label: 'Product Showcase', prompt: 'a controlled showcase film: push in, hold, feature callouts timed to the reveal' },
    { label: 'Unboxing Style', prompt: 'a first-person unboxing: the box, the lift, the reveal, the first use' },
    { label: 'Offer Video', prompt: 'a punchy offer spot: the product, the price, the deadline, the call to action' },
  ],
  website: [
    { label: 'Website Promo', prompt: 'a short promo for a website: the problem, the site as the answer, the URL' },
    { label: 'Animated Browser', prompt: 'a browser window animating in, tabs and page loading, UI details in focus' },
    { label: 'Scrolling Website', prompt: 'a smooth scroll down a long web page, pausing on each key section' },
    { label: 'Feature Highlight', prompt: 'one feature at a time, zoomed into the interface, labelled as it appears' },
    { label: 'Typing Animation', prompt: 'a headline typed out character by character over a clean background' },
    { label: 'Blog Intro', prompt: 'an editorial intro card for an article: title, subtitle, byline, gentle motion' },
  ],
  service: [
    { label: 'Service Explainer', prompt: 'a plain explainer: the problem, the service, the result' },
    { label: 'Before and After', prompt: 'a split reveal moving from the before state to the after state' },
    { label: 'Client Story', prompt: 'a short testimonial-shaped film built around one client outcome' },
    { label: 'Process Walkthrough', prompt: 'the service delivered step by step, numbered on screen' },
    { label: 'Offer Video', prompt: 'a punchy offer spot: the service, the price, the deadline, the call to action' },
  ],
  brand: [
    { label: 'Brand Film', prompt: 'a short brand film: who we are, what we believe, what we make' },
    { label: 'Manifesto', prompt: 'a manifesto cut: bold typography over texture and light, one line at a time' },
    { label: 'Behind the Scenes', prompt: 'hands making the work, close and tactile, no voiceover' },
    { label: 'Founder Story', prompt: 'the founder talking to camera about why the company exists' },
    { label: 'Montage', prompt: 'a fast montage of the brand in the world, cut to a beat' },
  ],
  event: [
    { label: 'Event Trailer', prompt: 'a trailer for an event: energy, line-up, date, venue, ticket call to action' },
    { label: 'Countdown', prompt: 'a countdown film building to the event date, large numbers on screen' },
    { label: 'Speaker Reel', prompt: 'each speaker introduced in turn with name and topic on screen' },
    { label: 'Last Year Recap', prompt: 'highlights of the previous edition, crowd energy, quick cuts' },
    { label: 'Venue Tour', prompt: 'a walk through the venue, wide to detail, atmospheric' },
  ],
  app: [
    { label: 'App Demo', prompt: 'a screen recording style demo of the app, one task completed end to end' },
    { label: 'Feature Highlight', prompt: 'one feature at a time, zoomed into the interface, labelled as it appears' },
    { label: 'Phone in Hand', prompt: 'the app used on a phone held in one hand, over-the-shoulder framing' },
    { label: 'Onboarding Story', prompt: 'download, first open, first win — the shortest path to value' },
    { label: 'Install Ad', prompt: 'a direct install spot: the problem, the app, the store badge' },
  ],
  lead: [
    { label: 'Offer Video', prompt: 'a punchy offer spot: what they get, why it helps, how to claim it' },
    { label: 'Guide Preview', prompt: 'pages of a guide turning, key lines pulled out on screen' },
    { label: 'Problem to Answer', prompt: 'the problem stated plainly, then the free answer being offered' },
    { label: 'Talking Head', prompt: 'one person to camera making a single clear promise' },
    { label: 'Typing Animation', prompt: 'a headline typed out character by character over a clean background' },
  ],
  custom: [
    { label: 'Explainer', prompt: 'a plain explainer: the problem, the answer, the next step' },
    { label: 'Montage', prompt: 'a fast montage cut to a beat' },
    { label: 'Typing Animation', prompt: 'a headline typed out character by character over a clean background' },
    { label: 'Talking Head', prompt: 'one person to camera making a single clear promise' },
    { label: 'Offer Video', prompt: 'a punchy offer spot: the offer, the reason, the call to action' },
  ],
}

// ---------------------------------------------------------------------------
// The types
// ---------------------------------------------------------------------------
// `subject` is what the tools CALL the thing being advertised — the label on
// the field, the word in the placeholder. It is why a Website campaign never
// says "Product" anywhere.
//
// `creativeTool` names the one creative type that is specific to this family.
// Product campaigns get Product Ads; Website campaigns get Website Promotion
// instead. Everything else gets neither, rather than being shown a tool that
// would ask them for something they do not have.

export const CAMPAIGN_TYPES = [
  {
    key: 'product',
    label: 'Product Promotion',
    description: 'Sell a physical or digital product.',
    subject: 'Product',
    subjectPlaceholder: 'Amber glass skincare serum',
    creativeTool: 'product-ads',
    styles: PRODUCT_STYLES,
    // Product creative starts from a real photograph of a real object, so the
    // upload and the cut-out belong here and nowhere else.
    productControls: true,
  },
  {
    key: 'service',
    label: 'Service Promotion',
    description: 'Promote something you do rather than something you ship.',
    subject: 'Service',
    subjectPlaceholder: 'Same-week boiler servicing across Manchester',
    creativeTool: null,
    styles: SERVICE_STYLES,
  },
  {
    key: 'website',
    label: 'Website / Blog Promotion',
    description: 'Drive readers and visitors to a site, blog or article.',
    subject: 'Website or blog',
    subjectPlaceholder: 'An AI marketing blog for small business owners',
    creativeTool: 'website-promotion',
    styles: WEBSITE_STYLES,
  },
  {
    key: 'brand',
    label: 'Brand Awareness',
    description: 'Build recognition rather than push one offer.',
    subject: 'Brand',
    subjectPlaceholder: 'A small-batch coffee roaster with a slow-roast philosophy',
    creativeTool: null,
    styles: BRAND_STYLES,
  },
  {
    key: 'event',
    label: 'Event Promotion',
    description: 'Fill seats for something happening on a date.',
    subject: 'Event',
    subjectPlaceholder: 'A one-day AI marketing summit in Casablanca, 14 March',
    creativeTool: null,
    styles: EVENT_STYLES,
  },
  {
    key: 'app',
    label: 'Mobile App Promotion',
    description: 'Drive installs and first-session use.',
    subject: 'App',
    subjectPlaceholder: 'A habit tracker that works offline',
    creativeTool: null,
    styles: APP_STYLES,
  },
  {
    key: 'lead',
    label: 'Lead Generation',
    description: 'Collect enquiries, sign-ups or downloads.',
    subject: 'Offer',
    subjectPlaceholder: 'A free 12-page guide to ad copy that converts',
    creativeTool: null,
    styles: LEAD_STYLES,
  },
  {
    key: 'custom',
    label: 'Custom Campaign',
    description: 'Anything that does not fit the list above.',
    subject: 'Subject',
    subjectPlaceholder: 'What this campaign is about',
    creativeTool: null,
    styles: GENERIC_STYLES,
  },
]

export const DEFAULT_CAMPAIGN_TYPE = CAMPAIGN_TYPES[0]

/** The labels, in registry order — what the form offers and the DB stores. */
export const CAMPAIGN_TYPE_LABELS = CAMPAIGN_TYPES.map((t) => t.label)

/**
 * A type by its stored label, falling back to the default.
 *
 * Never returns null: a campaign written before this field existed, or by a
 * later version of the app, must still open — with product defaults — rather
 * than blanking every tool that reads it.
 */
export function campaignType(label) {
  return CAMPAIGN_TYPES.find((t) => t.label === label) || DEFAULT_CAMPAIGN_TYPE
}

/** A type by key. Used where the family is known rather than the stored label. */
export function campaignTypeByKey(key) {
  return CAMPAIGN_TYPES.find((t) => t.key === key) || DEFAULT_CAMPAIGN_TYPE
}

/** The visual style options a campaign's tools should offer. */
export function stylesFor(label) {
  return campaignType(label).styles
}

/** The phrase the image model reads for a chosen style label. */
export function stylePrompt(typeLabel, styleLabel) {
  const found = stylesFor(typeLabel).find((s) => s.label === styleLabel)
  return found ? found.prompt : ''
}

/**
 * The role of each slide in a carousel of `count` slides.
 *
 * The closer is always last, so lengthening a carousel adds argument in the
 * middle rather than pushing the ask off the end.
 */
export function carouselRoles(typeLabel, count) {
  const story = CAROUSEL_STORIES[campaignType(typeLabel).key] || CAROUSEL_STORIES.custom
  const middle = Array.from(
    { length: Math.max(0, count - 1) },
    (_, i) => story.middle[i] || `Slide ${i + 1}`,
  )
  return [...middle, story.closer]
}

/** The video concepts that make sense for this campaign. */
export function videoConcepts(typeLabel) {
  return VIDEO_CONCEPTS[campaignType(typeLabel).key] || VIDEO_CONCEPTS.custom
}

/** The concept phrase behind a chosen video concept label. */
export function videoConceptPrompt(typeLabel, conceptLabel) {
  const found = videoConcepts(typeLabel).find((c) => c.label === conceptLabel)
  return found ? found.prompt : conceptLabel || ''
}

/**
 * Is this creative tool relevant to this campaign?
 *
 * Product Ads and Website Promotion are each tied to one family — a Website
 * campaign must not be offered a tool that opens by asking for a product photo.
 * Every other tool works for every campaign.
 *
 * With NO campaign there is nothing to filter against, so everything applies.
 * Falling through to the default type instead would quietly hide Website
 * Promotion from anyone browsing the tools outside a campaign.
 */
export function toolAppliesTo(slug, typeLabel) {
  if (!typeLabel) return true
  const owners = CAMPAIGN_TYPES.filter((t) => t.creativeTool === slug)
  if (!owners.length) return true
  return owners.some((t) => t.label === campaignType(typeLabel).label)
}

/**
 * The subject line handed to a generator, built from campaign memory.
 *
 * This is the sentence that means no tool has to ask what the campaign is
 * about: the brief carries it, the audience narrows it, and the type frames it.
 */
export function campaignSubject(campaign) {
  if (!campaign) return ''
  const type = campaignType(campaign.campaignType)
  return [
    campaign.brief?.trim(),
    campaign.audience?.trim() ? `Audience: ${campaign.audience.trim()}.` : '',
    `Campaign: ${campaign.name} — ${type.label}, objective ${campaign.objective}.`,
  ]
    .filter(Boolean)
    .join(' ')
}
