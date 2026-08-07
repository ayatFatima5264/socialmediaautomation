import { useEffect, useState } from 'react'
import { assetStore } from '../lib/ads/store'

// ---------------------------------------------------------------------------
// The user's most recent creatives, across every campaign.
//
// This is the Studio home's answer to "what was I last working on" — a
// deliberately cross-campaign view, which is why it does not reuse
// useCampaignAssets. It is also read-only: renaming or deleting happens inside
// the campaign that owns the asset, where the rest of the set is visible.
//
// A failure resolves to an empty list rather than an error banner. The strip is
// a convenience on a page whose real content is the campaign list; a red
// message about assets would overstate the problem.
// ---------------------------------------------------------------------------

export default function useRecentAssets(limit = 8) {
  const [assets, setAssets] = useState(null)

  useEffect(() => {
    let cancelled = false
    assetStore
      .recent(limit)
      .then((rows) => !cancelled && setAssets(rows))
      .catch(() => !cancelled && setAssets([]))
    return () => {
      cancelled = true
    }
  }, [limit])

  return { assets: assets || [], loading: assets === null }
}
