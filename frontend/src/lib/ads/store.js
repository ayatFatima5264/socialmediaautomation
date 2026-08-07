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
    // Defaulted rather than passed through: campaigns created before this
    // field existed have no value, and every tool reads it to decide what to
    // ask for. A missing type must open as the default, not as `undefined`.
    campaignType: row.campaign_type || 'Product Promotion',
    objective: row.objective,
    platforms: row.platforms || [],
    status: row.status,
    brief: row.brief || '',
    tone: row.tone || '',
    audience: row.audience || '',
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
  if (patch.campaignType !== undefined) out.campaign_type = patch.campaignType
  if (patch.objective !== undefined) out.objective = patch.objective
  if (patch.platforms !== undefined) out.platforms = patch.platforms
  if (patch.status !== undefined) out.status = patch.status
  if (patch.brief !== undefined) out.brief = patch.brief
  if (patch.tone !== undefined) out.tone = patch.tone
  if (patch.audience !== undefined) out.audience = patch.audience
  if (patch.creatives !== undefined) out.creatives = patch.creatives
  return out
}

class ApiCampaignProvider {
  async list(params) {
    const rows = await api.listCampaigns(params)
    return (rows || []).map(fromApi)
  }

  async get(id) {
    return fromApi(await api.getCampaign(id))
  }

  async create(patch = {}) {
    return fromApi(
      await api.createCampaign({
        name: 'Untitled campaign',
        campaign_type: 'Product Promotion',
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

  /** Copy a campaign, with its assets unless told otherwise. */
  async duplicate(id, withAssets = true) {
    return fromApi(await api.duplicateCampaign(id, withAssets))
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
  duplicate: (...args) => provider.duplicate(...args),
  remove: (...args) => provider.remove(...args),
}

// ---------------------------------------------------------------------------
// Creative library
// ---------------------------------------------------------------------------
// What the generators produced, attached to the campaign they were made in.
// Same rules as campaigns above: the wire is snake_case, the UI is camelCase,
// and the translation happens once — here.
//
// Saving is not something the user does. A tool calls `assetStore.save()` the
// moment a generation returns, so there is no "did I remember to keep that?"
// step and nothing is lost by pressing Back.

/** API row → the shape the library reads. */
function assetFromApi(row) {
  if (!row) return null
  return {
    id: row.id,
    campaignId: row.campaign_id,
    campaignName: row.campaign_name || '',
    kind: row.kind,
    title: row.title,
    url: row.url || '',
    body: row.body || '',
    tool: row.tool || '',
    meta: row.meta || {},
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  }
}

/** One asset the UI wants saved → the API's field names. */
function assetToApi(asset = {}) {
  return {
    kind: asset.kind,
    title: asset.title || 'Untitled',
    url: asset.url ?? null,
    body: asset.body ?? null,
    tool: asset.tool ?? null,
    meta: asset.meta || {},
  }
}

export const assetStore = {
  /** Every asset on a campaign, newest first. */
  async list(campaignId) {
    const rows = await api.listCampaignAssets(campaignId)
    return (rows || []).map(assetFromApi)
  },

  /**
   * Save what a generation produced — one asset or a whole set.
   *
   * One request per generation rather than one per image: a five-slide carousel
   * that half-saved because the fourth request failed would leave a broken
   * sequence in the library.
   */
  async save(campaignId, assets) {
    const list = (Array.isArray(assets) ? assets : [assets]).filter(Boolean)
    if (!list.length) return []
    const rows = await api.createCampaignAssets(campaignId, {
      assets: list.map(assetToApi),
    })
    return (rows || []).map(assetFromApi)
  },

  async update(campaignId, assetId, patch = {}) {
    const body = {}
    if (patch.title !== undefined) body.title = patch.title
    if (patch.url !== undefined) body.url = patch.url
    if (patch.body !== undefined) body.body = patch.body
    if (patch.meta !== undefined) body.meta = patch.meta
    return assetFromApi(await api.updateCampaignAsset(campaignId, assetId, body))
  },

  async duplicate(campaignId, assetId) {
    return assetFromApi(await api.duplicateCampaignAsset(campaignId, assetId))
  },

  async remove(campaignId, assetId) {
    await api.deleteCampaignAsset(campaignId, assetId)
  },

  /** The user's most recent assets across every campaign — the Studio home. */
  async recent(limit = 12) {
    const rows = await api.listRecentAssets(limit)
    return (rows || []).map(assetFromApi)
  },
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
