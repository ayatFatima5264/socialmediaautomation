import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useToast } from '../context/ToastContext.jsx'
import { assetStore, campaignStore } from '../lib/ads/store'
import { campaignPath, ADS_BASE_PATH } from '../lib/ads/tools'

// ---------------------------------------------------------------------------
// Campaign memory — the one thing that makes every ad tool stop asking.
//
// A tool opened from a campaign carries `?campaign=<id>` in its URL. This hook
// turns that into the campaign itself, so the workspace can preload the name,
// type, objective, platforms, tone, audience and brief instead of putting the
// same six questions in front of the user for the sixth time.
//
// ---- Why the URL rather than a React context -----------------------------
// The campaign has to survive a refresh, a bookmark and a link pasted to a
// colleague. A provider at the top of the tree survives none of those, and a
// tool opened from a bookmarked URL would silently fall back to asking for
// everything again — which is exactly the behaviour being removed.
//
// ---- Why the cache --------------------------------------------------------
// Moving between four tools in one campaign is four mounts of this hook. Each
// re-fetching the same row would be four identical requests and four visible
// loading flashes on data that has not changed. The cache is invalidated by
// `forget()` whenever the campaign is edited.
// ---------------------------------------------------------------------------

let cache = { id: null, campaign: null }

/** Drop the cached campaign — call after an edit so tools reload it. */
export function forgetCampaign(id) {
  if (id == null || String(cache.id) === String(id)) {
    cache = { id: null, campaign: null }
  }
}

export default function useCampaignContext() {
  const [params] = useSearchParams()
  const toast = useToast()

  const campaignId = params.get('campaign')
  // `?asset=` puts the tool in EDIT mode: it is re-doing one existing asset
  // rather than making another. See the note on `saveAssets` below.
  const editingAssetId = params.get('asset')
  const cached = campaignId && String(cache.id) === String(campaignId) ? cache.campaign : null

  const [campaign, setCampaign] = useState(cached)
  const [loading, setLoading] = useState(Boolean(campaignId) && !cached)
  const [editingAsset, setEditingAsset] = useState(null)

  useEffect(() => {
    if (!campaignId) {
      setCampaign(null)
      setLoading(false)
      return undefined
    }
    if (String(cache.id) === String(campaignId) && cache.campaign) {
      setCampaign(cache.campaign)
      setLoading(false)
      return undefined
    }

    let cancelled = false
    setLoading(true)
    campaignStore
      .get(campaignId)
      .then((row) => {
        cache = { id: campaignId, campaign: row }
        if (!cancelled) setCampaign(row)
      })
      .catch(() => {
        // A campaign that cannot be loaded leaves the tool usable standalone
        // rather than dead. The context bar simply does not appear.
        if (!cancelled) setCampaign(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [campaignId])

  // The asset being edited, when the URL names one. Loaded separately from the
  // campaign because it is a different lifetime: the campaign is cached across
  // every tool visit, an edit target belongs to this visit only.
  useEffect(() => {
    if (!campaignId || !editingAssetId) {
      setEditingAsset(null)
      return undefined
    }
    let cancelled = false
    assetStore
      .list(campaignId)
      .then((rows) => {
        if (cancelled) return
        setEditingAsset(rows.find((a) => String(a.id) === String(editingAssetId)) || null)
      })
      .catch(() => !cancelled && setEditingAsset(null))
    return () => {
      cancelled = true
    }
  }, [campaignId, editingAssetId])

  /**
   * Put what a generation produced into the campaign's library.
   *
   * There is no Save button anywhere in the Studio: a tool calls this the
   * moment a result comes back, so nothing is lost by navigating away. Outside
   * a campaign it is a no-op — the tool still works, the output just has
   * nowhere to live.
   *
   * ---- Editing vs creating ------------------------------------------------
   * In EDIT mode (`?asset=` in the URL) the first result REPLACES that asset in
   * place — same id, same position in the library, same title unless the tool
   * changed it. Re-doing a banner you did not like must not leave the one you
   * rejected sitting next to it; that is how a library fills with near-
   * duplicates nobody dares delete.
   *
   * `saveAsNew` opts out, which is the other real intention: keeping the
   * original and branching a variant from it.
   *
   * A tool in edit mode is expected to produce exactly one result. If it
   * produces more, the first updates the asset and the rest are added — losing
   * generated work to a rule about counts would be worse than a slightly
   * fuller library.
   */
  const saveAssets = useCallback(
    async (assets, { saveAsNew = false } = {}) => {
      const list = (Array.isArray(assets) ? assets : [assets]).filter(Boolean)
      if (!campaign || !list.length) return []

      const editing = editingAsset && !saveAsNew

      try {
        let saved = []

        if (editing) {
          const [replacement, ...extra] = list
          const updated = await assetStore.update(campaign.id, editingAsset.id, {
            // The user's own name for the asset survives a re-generation —
            // renaming it and then re-rolling the image should not undo the
            // rename. A tool only overrides the title if it means to.
            title: replacement.title ?? editingAsset.title,
            url: replacement.url ?? null,
            body: replacement.body ?? null,
            meta: replacement.meta || {},
          })
          setEditingAsset(updated)
          saved = [updated, ...(extra.length ? await assetStore.save(campaign.id, extra) : [])]
        } else {
          saved = await assetStore.save(campaign.id, list)
        }

        // The count on the campaign may have moved, so the cached copy is stale.
        forgetCampaign(campaign.id)

        toast.success(
          editing
            ? `Updated “${saved[0]?.title}” in ${campaign.name}.`
            : saved.length === 1
              ? `Saved to ${campaign.name}.`
              : `${saved.length} assets saved to ${campaign.name}.`,
        )
        return saved
      } catch (err) {
        toast.error(err?.message || 'Could not save to the campaign.')
        return []
      }
    },
    [campaign, editingAsset, toast],
  )

  return {
    campaign,
    campaignId,
    loading,
    /** The asset this tool was opened to re-do, or null when making a new one. */
    editingAsset,
    /** Where Back goes: the campaign if there is one, the Studio otherwise. */
    backTo: campaign ? campaignPath(campaign.id) : ADS_BASE_PATH,
    backLabel: campaign ? campaign.name : 'AI Ads Studio',
    saveAssets,
  }
}
