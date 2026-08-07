import { useCallback, useEffect, useState } from 'react'
import { useToast } from '../context/ToastContext.jsx'
import { assetStore } from '../lib/ads/store'
import { assetCounts } from '../lib/ads/assets'
import { forgetCampaign } from './useCampaignContext'

// ---------------------------------------------------------------------------
// A campaign's creative library, and the four things you can do to a card.
//
// Rename, duplicate and delete update the local array as well as the server so
// the library responds immediately rather than after a full reload — but each
// one awaits the request first. Optimism here would mean a card disappearing
// and then reappearing when the delete turned out to fail, which reads as a bug.
//
// Counts come from `assetCounts` over the same array the sections render, so
// the summary at the top of the campaign can never disagree with what is
// underneath it.
// ---------------------------------------------------------------------------

export default function useCampaignAssets(campaignId) {
  const [assets, setAssets] = useState(null)
  const [error, setError] = useState(null)
  const toast = useToast()

  // The only fetch. Every mutation below folds the server's answer into the
  // array rather than re-reading the list, so there is nothing else to reload
  // and no second copy of this to drift out of step with it.
  useEffect(() => {
    let cancelled = false
    if (!campaignId) {
      setAssets([])
      return undefined
    }
    setError(null)
    assetStore
      .list(campaignId)
      .then((rows) => !cancelled && setAssets(rows))
      .catch((e) => {
        if (cancelled) return
        setError(e?.message || 'Could not load this campaign’s assets')
        setAssets([])
      })
    return () => {
      cancelled = true
    }
  }, [campaignId])

  const rename = useCallback(
    async (asset, title) => {
      const next = title.trim()
      if (!next || next === asset.title) return
      try {
        const updated = await assetStore.update(campaignId, asset.id, { title: next })
        setAssets((rows) => rows.map((a) => (a.id === asset.id ? updated : a)))
      } catch (e) {
        toast.error(e?.message || 'Could not rename that asset.')
      }
    },
    [campaignId, toast],
  )

  /**
   * Rewrite a copy asset's words in place.
   *
   * An edit to a headline updates THAT headline — it does not add a second one
   * beside it. Duplicate is the separate, explicit action for when a variant is
   * what was wanted.
   */
  const editBody = useCallback(
    async (asset, body) => {
      if (body === asset.body) return
      try {
        const updated = await assetStore.update(campaignId, asset.id, { body })
        setAssets((rows) => rows.map((a) => (a.id === asset.id ? updated : a)))
        toast.success('Updated.')
      } catch (e) {
        toast.error(e?.message || 'Could not save that edit.')
      }
    },
    [campaignId, toast],
  )

  // Duplicate and delete move the campaign's creative count, which the server
  // recounts. The cached campaign row still holds the old number, so it is
  // dropped here — otherwise a tool opened straight after deleting an asset
  // would show the count from before the delete in its context bar.
  const duplicate = useCallback(
    async (asset) => {
      try {
        const copy = await assetStore.duplicate(campaignId, asset.id)
        setAssets((rows) => [copy, ...rows])
        forgetCampaign(campaignId)
        toast.success('Duplicated.')
      } catch (e) {
        toast.error(e?.message || 'Could not duplicate that asset.')
      }
    },
    [campaignId, toast],
  )

  const remove = useCallback(
    async (asset) => {
      try {
        await assetStore.remove(campaignId, asset.id)
        setAssets((rows) => rows.filter((a) => a.id !== asset.id))
        forgetCampaign(campaignId)
        toast.success('Deleted.')
      } catch (e) {
        toast.error(e?.message || 'Could not delete that asset.')
      }
    },
    [campaignId, toast],
  )

  const rows = assets || []

  return {
    assets: rows,
    counts: assetCounts(rows),
    loading: assets === null,
    error,
    rename,
    editBody,
    duplicate,
    remove,
  }
}
