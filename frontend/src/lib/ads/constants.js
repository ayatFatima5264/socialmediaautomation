// ---------------------------------------------------------------------------
// AI Ads Studio — display metadata for campaigns.
//
// Separate from lib/constants.js on purpose: that module describes organic
// posts (statuses like `published` / `failed`, per-platform caption limits) and
// is imported by the Generator, Scheduler and History. A campaign is a
// different object with a different lifecycle, so it gets its own vocabulary
// rather than overloading the post statuses and forcing every existing consumer
// to reason about values that can never appear there.
//
// The shape mirrors ACCOUNT_STATUS in lib/constants.js — label, badge classes,
// dot colour — so CampaignStatusBadge and AccountStatusBadge stay visually
// identical without sharing code they would otherwise have to be coupled by.
// ---------------------------------------------------------------------------

export const CAMPAIGN_STATUS = {
  draft: {
    label: 'Draft',
    badge: 'bg-slate-500/15 text-slate-500',
    dot: 'bg-slate-400',
  },
  scheduled: {
    label: 'Scheduled',
    badge: 'bg-amber-500/15 text-amber-600',
    dot: 'bg-amber-400',
  },
  active: {
    label: 'Active',
    badge: 'bg-emerald-500/15 text-emerald-600',
    dot: 'bg-emerald-400',
  },
  paused: {
    label: 'Paused',
    badge: 'bg-sky-500/15 text-sky-600',
    dot: 'bg-sky-400',
  },
  completed: {
    label: 'Completed',
    badge: 'bg-violet-500/15 text-violet-600',
    dot: 'bg-violet-400',
  },
  // Put away rather than deleted. An archived campaign keeps every asset it
  // made and can be restored, but it is excluded from the default list and from
  // the Studio's counts — otherwise archiving would be a label that changes
  // nothing and last year's work would sit at the top of the page forever.
  archived: {
    label: 'Archived',
    badge: 'bg-zinc-500/15 text-zinc-500',
    dot: 'bg-zinc-400',
  },
}

export const CAMPAIGN_STATUS_KEYS = Object.keys(CAMPAIGN_STATUS)

// ---------------------------------------------------------------------------
// Campaign list controls
// ---------------------------------------------------------------------------
// What the list page can filter and sort by. `status: null` means "no filter",
// which the API reads as "everything except archived" — see list_campaigns in
// app/routes/ads.py for why that is the default rather than a special case.

export const CAMPAIGN_FILTERS = [
  { key: 'all', label: 'All', status: null },
  { key: 'draft', label: 'Draft', status: 'draft' },
  { key: 'active', label: 'Active', status: 'active' },
  { key: 'scheduled', label: 'Scheduled', status: 'scheduled' },
  { key: 'completed', label: 'Completed', status: 'completed' },
  { key: 'archived', label: 'Archived', status: 'archived' },
]

// Values must match _CAMPAIGN_SORTS in app/routes/ads.py, which whitelists them.
export const CAMPAIGN_SORTS = [
  { value: 'updated', label: 'Last edited' },
  { value: 'created', label: 'Created date' },
  { value: 'name', label: 'Name (A–Z)' },
]

/**
 * The three counts the overview widgets track, plus the creative total.
 *
 * Declared rather than hardcoded in the dashboard so a new status becomes a
 * widget by adding a line here — and so the tile order is one decision in one
 * place. `accent` matches the bar colours the Dashboard's stat cards already
 * use, keeping the two pages visually consistent.
 */
export const CAMPAIGN_STAT_TILES = [
  { key: 'active', label: 'Active Campaigns', accent: 'bg-emerald-400' },
  { key: 'draft', label: 'Draft Campaigns', accent: 'bg-slate-400' },
  { key: 'scheduled', label: 'Scheduled Campaigns', accent: 'bg-amber-400' },
  { key: 'creatives', label: 'Total Creatives Generated', accent: 'bg-accent' },
]

// What a campaign is trying to achieve. Mirrors BUSINESS_GOALS in
// lib/constants.js where they overlap, so a user who set goals during
// onboarding sees familiar language here.
export const CAMPAIGN_OBJECTIVES = [
  'Brand Awareness',
  'Traffic',
  'Engagement',
  'Lead Generation',
  'Sales',
  'App Installs',
]

// Platforms that accept paid placements. A subset of PLATFORM_KEYS — Threads
// has no ads product, so offering it would be a dead end. Keys match
// lib/constants.js PLATFORMS so <PlatformIcon /> renders these unchanged.
export const AD_PLATFORM_KEYS = ['facebook', 'instagram', 'linkedin', 'twitter', 'pinterest']

// ---------------------------------------------------------------------------
// Workspace options
// ---------------------------------------------------------------------------
// The choices each tool's control panel offers. Declared here rather than
// inline in the pages so the six workspaces stay layout-only, and so a value
// the backend will eventually validate has exactly one spelling in the app.
//
// Aspect ratios reuse ASPECT_RATIOS from lib/constants.js where they overlap —
// an ad and an organic post are cropped by the same platforms.

export const BANNER_SIZES = [
  { value: '1200x628', label: 'Facebook Feed', hint: '1200 × 628' },
  { value: '1080x1080', label: 'Square', hint: '1080 × 1080' },
  { value: '1080x1920', label: 'Story / Reel', hint: '1080 × 1920' },
  { value: '728x90', label: 'Leaderboard', hint: '728 × 90' },
  { value: '300x250', label: 'Medium Rectangle', hint: '300 × 250' },
  { value: '160x600', label: 'Wide Skyscraper', hint: '160 × 600' },
]

// The sizes the right rail offers to export a finished banner into.
export const BANNER_EXPORT_SETS = [
  { network: 'Facebook', sizes: ['1200 × 628', '1080 × 1080', '1080 × 1920'] },
  { network: 'Google Ads', sizes: ['728 × 90', '300 × 250', '160 × 600'] },
  { network: 'LinkedIn', sizes: ['1200 × 627', '1080 × 1080'] },
  { network: 'Pinterest', sizes: ['1000 × 1500'] },
]

export const VIDEO_DURATIONS = [
  { value: 6, label: '6 seconds' },
  { value: 10, label: '10 seconds' },
  { value: 15, label: '15 seconds' },
  { value: 30, label: '30 seconds' },
]

export const CAMERA_MOTIONS = ['Slow zoom in', 'Zoom out', 'Pan left', 'Pan right', 'Orbit', 'Static']

export const ANIMATION_STYLES = ['Smooth', 'Cinematic', 'Snappy', 'Parallax']

export const VIDEO_STYLES = ['Modern & Clean', 'Warm & Natural', 'Bold & Punchy', 'Luxury', 'Playful']

export const CAROUSEL_SLIDE_COUNTS = [3, 4, 5, 6, 7, 8, 10]

export const COPY_TONES = [
  'Professional',
  'Friendly',
  'Bold',
  'Playful',
  'Luxury',
  'Urgent',
]

export const CTA_OPTIONS = [
  'Shop Now',
  'Learn More',
  'Sign Up',
  'Get Offer',
  'Book Now',
  'Download',
]

// Backdrop presets for Product Ads. Names describe the SET, not a colour, so a
// user picks the photograph they want rather than a swatch.
export const BACKGROUND_PRESETS = [
  'Studio white',
  'Soft beige',
  'Marble surface',
  'Natural greenery',
  'Gradient glow',
  'Dark luxury',
]
