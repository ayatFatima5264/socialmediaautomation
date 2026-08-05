// ---------------------------------------------------------------------------
// AI Ads Studio — the campaign storage layer.
//
// Phase 1 ships the Studio's foundation, and campaigns have no backend table
// yet. Rather than scatter mock arrays through the UI, everything goes through
// one async, promise-based interface shaped exactly like a REST client:
//
//   list() · get(id) · create(patch) · update(id, patch) · remove(id)
//
// The UI awaits those calls and renders loading / empty / error states around
// them. When the backend lands, `setCampaignProvider()` swaps this local
// implementation for one that talks to `lib/api.js` and not a single component
// changes — the same seam `setMediaProvider` gives the Media Library, and for
// the same reason: the storage decision should not be baked into the views.
//
// Until then records live in localStorage, so a campaign a user starts survives
// a refresh instead of vanishing mid-phase.
//
// ---- Sample data ----------------------------------------------------------
// The store seeds a few example campaigns on first use so the dashboard has
// something real to lay out. They are marked `isSample: true`, seeded exactly
// once (deleting them is remembered), and `clearSamples()` removes them — which
// is what makes the empty state a state the user can actually reach rather than
// dead code nobody ever sees.
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'as_ads_campaigns'
const SEEDED_KEY = 'as_ads_campaigns_seeded'

// ---------------------------------------------------------------------------
// Sample campaigns
// ---------------------------------------------------------------------------

// Timestamps are built relative to first run, so "Last updated" reads as
// "2 days ago" whenever the user first opens the Studio — not as a fixed date
// that drifts further into the past the longer the feature ships.
const daysAgo = (n) => new Date(Date.now() - n * 86_400_000).toISOString()

function sampleCampaigns() {
  return [
    {
      id: 'sample-spring-launch',
      name: 'Spring Product Launch',
      objective: 'Sales',
      platforms: ['instagram', 'facebook'],
      status: 'active',
      creatives: 12,
      updatedAt: daysAgo(1),
      createdAt: daysAgo(14),
      isSample: true,
    },
    {
      id: 'sample-b2b-demo',
      name: 'B2B Demo Requests — Q3',
      objective: 'Lead Generation',
      platforms: ['linkedin'],
      status: 'scheduled',
      creatives: 6,
      updatedAt: daysAgo(2),
      createdAt: daysAgo(9),
      isSample: true,
    },
    {
      id: 'sample-retargeting',
      name: 'Website Retargeting',
      objective: 'Traffic',
      platforms: ['facebook', 'instagram', 'twitter'],
      status: 'active',
      creatives: 9,
      updatedAt: daysAgo(3),
      createdAt: daysAgo(21),
      isSample: true,
    },
    {
      id: 'sample-holiday-teaser',
      name: 'Holiday Teaser Concepts',
      objective: 'Brand Awareness',
      platforms: ['instagram', 'pinterest'],
      status: 'draft',
      creatives: 4,
      updatedAt: daysAgo(5),
      createdAt: daysAgo(5),
      isSample: true,
    },
    {
      id: 'sample-webinar',
      name: 'Webinar Signups',
      objective: 'Lead Generation',
      platforms: ['linkedin', 'twitter'],
      status: 'completed',
      creatives: 8,
      updatedAt: daysAgo(12),
      createdAt: daysAgo(40),
      isSample: true,
    },
  ]
}

// ---------------------------------------------------------------------------
// Local provider — localStorage
// ---------------------------------------------------------------------------

function read() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const rows = raw ? JSON.parse(raw) : null
    return Array.isArray(rows) ? rows : null
  } catch {
    // Corrupt or unavailable storage behaves like an empty library rather than
    // taking the page down with it.
    return null
  }
}

function write(rows) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(rows))
  } catch {
    /* storage unavailable — campaigns just won't persist this session */
  }
}

/** Seeds the samples once. A user who deletes them does not get them back. */
function load() {
  const rows = read()
  if (rows) return rows

  let seeded = false
  try {
    seeded = localStorage.getItem(SEEDED_KEY) === '1'
  } catch {
    /* treat unreadable storage as "not yet seeded" */
  }
  if (seeded) return []

  const samples = sampleCampaigns()
  write(samples)
  try {
    localStorage.setItem(SEEDED_KEY, '1')
  } catch {
    /* without the flag the samples reappear after a wipe — harmless */
  }
  return samples
}

const uid = () =>
  `cmp_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`

class LocalCampaignProvider {
  async list() {
    // Newest activity first — the same ordering the real endpoint should use,
    // so swapping providers does not reshuffle the table.
    return load()
      .slice()
      .sort((a, b) => String(b.updatedAt || '').localeCompare(String(a.updatedAt || '')))
  }

  async get(id) {
    return load().find((c) => c.id === id) || null
  }

  async create(patch = {}) {
    const now = new Date().toISOString()
    const campaign = {
      id: uid(),
      name: 'Untitled campaign',
      objective: 'Brand Awareness',
      platforms: [],
      status: 'draft',
      creatives: 0,
      ...patch,
      createdAt: now,
      updatedAt: now,
      isSample: false,
    }
    write([campaign, ...load()])
    return campaign
  }

  async update(id, patch = {}) {
    const rows = load()
    const i = rows.findIndex((c) => c.id === id)
    if (i === -1) return null
    // `id` and `createdAt` are identity — an edit must not be able to rewrite
    // which record it is or when it started.
    const { id: _id, createdAt: _createdAt, ...safe } = patch
    const next = { ...rows[i], ...safe, updatedAt: new Date().toISOString() }
    rows[i] = next
    write(rows)
    return next
  }

  async remove(id) {
    write(load().filter((c) => c.id !== id))
  }
}

let provider = new LocalCampaignProvider()

/**
 * Replace the implementation backing campaigns.
 *
 * The migration path to the backend: write a provider whose five methods call
 * `api.*`, register it at startup, and every screen keeps working — they only
 * ever awaited `campaignStore`.
 */
export function setCampaignProvider(next) {
  if (!next || typeof next.list !== 'function') {
    throw new Error('A campaign provider must implement list()')
  }
  provider = next
}

// ---------------------------------------------------------------------------
// The facade every consumer uses
// ---------------------------------------------------------------------------

export const campaignStore = {
  list: (...args) => provider.list(...args),
  get: (...args) => provider.get(...args),
  create: (...args) => provider.create(...args),
  update: (...args) => provider.update(...args),
  remove: (...args) => provider.remove(...args),

  /** Drop the seeded examples, leaving anything the user made. */
  async clearSamples() {
    const rows = await provider.list()
    await Promise.all(rows.filter((c) => c.isSample).map((c) => provider.remove(c.id)))
  },
}

/**
 * The overview counts, derived from a campaign list.
 *
 * A pure function of rows the caller already holds, rather than a second trip
 * to storage: the widgets and the table must never disagree about how many
 * campaigns are active, and they cannot if both read the same array.
 */
export function campaignStats(campaigns = []) {
  const counts = { active: 0, draft: 0, scheduled: 0, paused: 0, completed: 0, creatives: 0 }
  campaigns.forEach((c) => {
    if (counts[c.status] !== undefined) counts[c.status] += 1
    counts.creatives += Number(c.creatives) || 0
  })
  return counts
}

export default campaignStore
