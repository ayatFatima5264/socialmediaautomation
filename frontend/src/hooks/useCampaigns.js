import { useCallback, useEffect, useRef, useState } from 'react'
import { useToast } from '../context/ToastContext.jsx'
import { campaignStats, campaignStore } from '../lib/ads/store'
import { forgetCampaign } from './useCampaignContext'

// ---------------------------------------------------------------------------
// Loads the user's ad campaigns, and the four things you can do to one.
//
// ---- Query, not filter ----------------------------------------------------
// `params` ({ status, q, sort }) goes to the API, which filters in SQL. The
// alternative — download everything and filter in the browser — reads the same
// on a test account and falls over on a real one, and it would also have to
// re-implement the "hide archived by default" rule the server already owns.
//
// A changed query refetches. `keepPrevious` holds the last rows on screen while
// it does, so typing in the search box does not blink the table to a skeleton on
// every keystroke.
//
// ---- Actions --------------------------------------------------------------
// Rename, duplicate, archive and delete all await the server, then refetch.
// Optimistic updates are wrong here: archiving changes which rows the current
// filter should contain, and guessing that locally means the list disagrees
// with what a refresh would show.
// ---------------------------------------------------------------------------

export default function useCampaigns(params = {}) {
  const { status = null, q = '', sort = 'updated' } = params

  const [campaigns, setCampaigns] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const toast = useToast()

  // Serialised so the effect below compares by value — a fresh object literal
  // from the caller on every render would otherwise refetch forever.
  const key = JSON.stringify({ status, q, sort })
  const latest = useRef(0)

  const load = useCallback(async () => {
    const ticket = ++latest.current
    try {
      const rows = await campaignStore.list({ status, q, sort })
      // A slow earlier request must not overwrite a faster later one — without
      // this, deleting the search box faster than the network responds leaves
      // stale results on screen.
      if (ticket === latest.current) {
        setError(null)
        setCampaigns(rows)
      }
    } catch (e) {
      if (ticket === latest.current) {
        setError(e?.message || 'Could not load your campaigns')
        setCampaigns([])
      }
    }
  }, [status, q, sort])

  useEffect(() => {
    load()
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps

  /** Run a mutation, report it, and resync the list. */
  const act = useCallback(
    async (fn, done, failed) => {
      setBusy(true)
      try {
        const result = await fn()
        await load()
        if (done) toast.success(done)
        return result
      } catch (e) {
        toast.error(e?.message || failed || 'That did not work.')
        return null
      } finally {
        setBusy(false)
      }
    },
    [load, toast],
  )

  const rename = useCallback(
    (campaign, name) => {
      const next = name.trim()
      if (!next || next === campaign.name) return Promise.resolve(null)
      return act(
        async () => {
          const row = await campaignStore.update(campaign.id, { name: next })
          // Tools cache the campaign; the name is on every context bar.
          forgetCampaign(campaign.id)
          return row
        },
        'Campaign renamed.',
        'Could not rename the campaign.',
      )
    },
    [act],
  )

  const duplicate = useCallback(
    (campaign) =>
      act(
        () => campaignStore.duplicate(campaign.id),
        'Campaign duplicated, with its assets, as a draft.',
        'Could not duplicate the campaign.',
      ),
    [act],
  )

  const setStatus = useCallback(
    (campaign, nextStatus) =>
      act(
        async () => {
          const row = await campaignStore.update(campaign.id, { status: nextStatus })
          forgetCampaign(campaign.id)
          return row
        },
        nextStatus === 'archived' ? 'Campaign archived.' : 'Campaign restored.',
        'Could not change the campaign status.',
      ),
    [act],
  )

  const remove = useCallback(
    (campaign) =>
      act(
        async () => {
          await campaignStore.remove(campaign.id)
          forgetCampaign(campaign.id)
        },
        'Campaign deleted.',
        'Could not delete the campaign.',
      ),
    [act],
  )

  const rows = campaigns || []

  return {
    campaigns: rows,
    stats: campaignStats(rows),
    loading: campaigns === null,
    busy,
    error,
    refresh: load,
    rename,
    duplicate,
    setStatus,
    remove,
  }
}
