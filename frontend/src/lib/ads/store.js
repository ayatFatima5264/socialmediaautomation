import { api } from '../api'

// ---------------------------------------------------------------------------
// AI Ads Studio — the campaign storage layer.
//
// Campaigns are the user's data, so they live in the database behind
// /api/ads/campaigns, scoped to the signed-in account. This module is the one
// place that knows that: every screen awaits `campaignStore` and none of them
// builds a URL or knows a field is spelled differently on the wire.
//
// The provider seam (`setCampaignProvider`) is kept. It was what let the UI be
// built against localStorage before the table existed, and it is what would let
// a future offline mode or a test double slot in without touching a component.
//
// ---- Field naming ---------------------------------------------------------
// The API speaks snake_case like the rest of the app; the UI reads camelCase.
// The mapping happens HERE, once, in `fromApi`/`toApi` — not in each component,
// which is how half a codebase ends up checking both spellings.
// ---------------------------------------------------------------------------

/** API row → the shape the UI reads. */
function fromApi(row) {
  if (!row) return null
  return {
    id: row.id,
    name: row.name,
    objective: row.objective,
    platforms: row.platforms || [],
    status: row.status,
    brief: row.brief || '',
    creatives: row.creatives ?? 0,
    // Deliberately preserved as null rather than coerced to 0 — a campaign
    // that has not run has no CTR, and "0%" would claim it ran and failed.
    ctr: row.ctr ?? null,
    impressions: row.impressions ?? 0,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  }
}

/** UI patch → the API's field names. Undefined keys are dropped, so a PATCH */
/*  only ever sends what the caller actually changed. */
function toApi(patch = {}) {
  const out = {}
  if (patch.name !== undefined) out.name = patch.name
  if (patch.objective !== undefined) out.objective = patch.objective
  if (patch.platforms !== undefined) out.platforms = patch.platforms
  if (patch.status !== undefined) out.status = patch.status
  if (patch.brief !== undefined) out.brief = patch.brief
  if (patch.creatives !== undefined) out.creatives = patch.creatives
  return out
}

class ApiCampaignProvider {
  async list() {
    const rows = await api.listCampaigns()
    return (rows || []).map(fromApi)
  }

  async get(id) {
    return fromApi(await api.getCampaign(id))
  }

  async create(patch = {}) {
    return fromApi(
      await api.createCampaign({
        name: 'Untitled campaign',
        objective: 'Brand Awareness',
        platforms: [],
        status: 'draft',
        ...toApi(patch),
      }),
    )
  }

  async update(id, patch = {}) {
    return fromApi(await api.updateCampaign(id, toApi(patch)))
  }

  async remove(id) {
    await api.deleteCampaign(id)
  }
}

let provider = new ApiCampaignProvider()

/**
 * Replace the implementation backing campaigns.
 *
 * Every screen only ever awaited `campaignStore`, so a different provider —
 * an offline cache, a test double — needs no change above this file.
 */
export function setCampaignProvider(next) {
  if (!next || typeof next.list !== 'function') {
    throw new Error('A campaign provider must implement list()')
  }
  provider = next
}

export const campaignStore = {
  list: (...args) => provider.list(...args),
  get: (...args) => provider.get(...args),
  create: (...args) => provider.create(...args),
  update: (...args) => provider.update(...args),
  remove: (...args) => provider.remove(...args),
}

/**
 * The overview counts, derived from a campaign list.
 *
 * A pure function of rows the caller already holds, rather than a second
 * request: the widgets and the table must never disagree about how many
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
