// ---------------------------------------------------------------------------
// AI Ads Studio — the creative library's vocabulary.
//
// One kind per section on the campaign page, in the order they are shown.
// Declared here rather than in the page so the sections, the overview counts
// and the save calls inside each tool all name a kind the same way — the thing
// that silently breaks when a tool saves `"videos"` and the library looks for
// `"video"`.
//
// The keys match ASSET_KINDS in app/models/campaign_asset.py, which rejects
// anything else with a 422. That is deliberate: a typo fails at the request
// rather than becoming an asset no section ever renders.
// ---------------------------------------------------------------------------

export const ASSET_KINDS = [
  { key: 'image', label: 'Images', singular: 'Image', media: true },
  { key: 'banner', label: 'Banners', singular: 'Banner', media: true },
  { key: 'carousel', label: 'Carousel', singular: 'Slide', media: true },
  { key: 'video', label: 'Videos', singular: 'Video', media: true },
  { key: 'headline', label: 'Headlines', singular: 'Headline', media: false },
  { key: 'caption', label: 'Captions', singular: 'Caption', media: false },
  { key: 'cta', label: 'CTAs', singular: 'CTA', media: false },
]

export const ASSET_KIND_KEYS = ASSET_KINDS.map((k) => k.key)

/** A kind's display metadata, or a safe stand-in for one the app does not know. */
export function assetKind(key) {
  return (
    ASSET_KINDS.find((k) => k.key === key) || {
      key,
      label: key,
      singular: key,
      media: false,
    }
  )
}

/** Is this kind a picture or a video, rather than words? */
export function isMediaKind(key) {
  return assetKind(key).media
}

/**
 * The overview counts, derived from an asset list.
 *
 * A pure function of the array the page already holds, for the same reason
 * campaignStats is: the summary cards and the sections below them must never
 * disagree about how many banners exist, and they cannot if both read one array.
 *
 * `copy` is the three written kinds counted together — the summary says "AI
 * Copy", not "headlines, captions and CTAs".
 */
export function assetCounts(assets = []) {
  const counts = { total: assets.length, copy: 0 }
  ASSET_KIND_KEYS.forEach((key) => {
    counts[key] = 0
  })

  assets.forEach((a) => {
    if (counts[a.kind] !== undefined) counts[a.kind] += 1
    if (!isMediaKind(a.kind)) counts.copy += 1
  })

  return counts
}

/** Assets of one kind, newest first — the order the API already returns. */
export function assetsOfKind(assets = [], kind) {
  return assets.filter((a) => a.kind === kind)
}
