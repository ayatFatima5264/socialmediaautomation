import { useCallback, useEffect, useState } from 'react'
import { campaignStats, campaignStore } from '../lib/ads/store'

// ---------------------------------------------------------------------------
// Loads the user's ad campaigns and the counts derived from them.
//
// The store is async and provider-backed (see lib/ads/store.js), so this hook
// is written for a network round trip it does not make yet: it tracks loading
// and error state and exposes `refresh()`. When the backend provider is
// registered, nothing here changes.
//
// Stats are derived from the same array the table renders, never fetched
// separately — that is what stops the widgets and the table disagreeing.
// ---------------------------------------------------------------------------

export default function useCampaigns() {
  const [campaigns, setCampaigns] = useState(null)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    try {
      setError(null)
      setCampaigns(await campaignStore.list())
    } catch (e) {
      setError(e?.message || 'Could not load your campaigns')
      setCampaigns([])
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    campaignStore
      .list()
      .then((rows) => {
        if (!cancelled) setCampaigns(rows)
      })
      .catch((e) => {
        if (cancelled) return
        setError(e?.message || 'Could not load your campaigns')
        setCampaigns([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  const clearSamples = useCallback(async () => {
    await campaignStore.clearSamples()
    await refresh()
  }, [refresh])

  const rows = campaigns || []

  return {
    campaigns: rows,
    stats: campaignStats(rows),
    loading: campaigns === null,
    error,
    refresh,
    clearSamples,
    // Drives the "Clear sample data" affordance: offering it once the user has
    // real campaigns of their own would risk reading as "delete everything".
    hasOnlySamples: rows.length > 0 && rows.every((c) => c.isSample),
  }
}
