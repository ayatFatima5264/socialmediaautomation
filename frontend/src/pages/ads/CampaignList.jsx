import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import AdsEmptyState from '../../components/ads/AdsEmptyState.jsx'
import AdsPageHeader from '../../components/ads/AdsPageHeader.jsx'
import CampaignTable from '../../components/ads/CampaignTable.jsx'
import useCampaigns from '../../hooks/useCampaigns'
import { CAMPAIGN_FILTERS, CAMPAIGN_SORTS } from '../../lib/ads/constants'
import { CAMPAIGN_NEW_PATH } from '../../lib/ads/tools'

// ---------------------------------------------------------------------------
// Every campaign this account has — the module's management screen.
//
// The Studio home answers "where was I"; this answers "where is everything".
// They are different jobs, which is why the home keeps five rows and a way
// through to here rather than growing a search box and a filter bar it would
// only need once an account has more campaigns than fit on a screen.
//
// ---- State in the URL -----------------------------------------------------
// The filter, the search term and the sort all live in the query string, so a
// filtered view can be bookmarked, shared and survives a refresh — and the back
// button steps through them, which is what a user expects after narrowing a
// list three times.
//
// This is the SAME rule the tools follow with `?campaign=`: the URL carries a
// reference to state, never the state itself. The campaigns are rows in
// Postgres; the query string just says which of them to ask for.
//
// ---- Searching ------------------------------------------------------------
// Debounced, and filtered server-side. The input updates immediately so typing
// never feels laggy, and the request follows a beat later — one query per
// pause rather than one per keystroke.
// ---------------------------------------------------------------------------

const SEARCH_DEBOUNCE_MS = 300

export default function CampaignList() {
  const [params, setParams] = useSearchParams()

  const filterKey = params.get('filter') || 'all'
  const sort = params.get('sort') || 'updated'
  const query = params.get('q') || ''

  const filter = CAMPAIGN_FILTERS.find((f) => f.key === filterKey) || CAMPAIGN_FILTERS[0]

  // Typed text is local; the URL — and therefore the request — follows it after
  // a pause. Without this the address bar rewrites on every character.
  const [typed, setTyped] = useState(query)

  useEffect(() => {
    if (typed === query) return undefined
    const id = setTimeout(() => {
      const next = new URLSearchParams(params)
      if (typed.trim()) next.set('q', typed.trim())
      else next.delete('q')
      setParams(next, { replace: true })
    }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(id)
  }, [typed]) // eslint-disable-line react-hooks/exhaustive-deps

  // The browser's back button can change the URL underneath the input.
  useEffect(() => setTyped(query), [query])

  const {
    campaigns,
    loading,
    busy,
    error,
    rename,
    duplicate,
    setStatus,
    remove,
  } = useCampaigns({ status: filter.status, q: query, sort })

  function patch(key, value) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  const actions = { rename, duplicate, setStatus, remove, busy }
  const searching = Boolean(query)

  return (
    <div className="space-y-5 pb-4">
      <AdsPageHeader
        title="Campaigns"
        description="Every campaign on this account, with everything it has produced."
        backLabel="AI Ads Studio"
        actions={
          <Link to={CAMPAIGN_NEW_PATH} className="btn btn-primary">
            ✦ New Campaign
          </Link>
        }
      />

      {/* ---- Controls ---------------------------------------------------- */}
      <div className="card space-y-3 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="min-w-[200px] flex-1">
            <label htmlFor="cmp-search" className="sr-only">
              Search campaigns
            </label>
            <input
              id="cmp-search"
              type="search"
              className="input"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              placeholder="Search by name or brief…"
            />
          </div>

          <div className="flex items-center gap-2">
            <label htmlFor="cmp-sort" className="text-xs font-medium text-muted">
              Sort
            </label>
            <select
              id="cmp-sort"
              className="select w-auto"
              value={sort}
              onChange={(e) => patch('sort', e.target.value)}
            >
              {CAMPAIGN_SORTS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 border-t border-line pt-3">
          {CAMPAIGN_FILTERS.map((f) => {
            const on = f.key === filter.key
            return (
              <button
                key={f.key}
                type="button"
                onClick={() => patch('filter', f.key === 'all' ? '' : f.key)}
                aria-pressed={on}
                className={`rounded-full border px-3.5 py-1.5 text-sm font-medium transition ${
                  on
                    ? 'border-accent bg-accent-soft text-accent'
                    : 'border-line text-muted hover:border-accent'
                }`}
              >
                {f.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* ---- The list ---------------------------------------------------- */}
      <div className="card p-3">
        {loading ? (
          <div className="space-y-3 p-3">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="skeleton h-11 w-full" />
            ))}
          </div>
        ) : error ? (
          <p className="px-4 py-10 text-center text-sm text-rose-600">{error}</p>
        ) : campaigns.length ? (
          <>
            <div className="pt-2">
              <CampaignTable campaigns={campaigns} actions={actions} />
            </div>
            <p className="border-t border-line px-4 pb-1 pt-3 text-xs text-muted">
              {campaigns.length} {campaigns.length === 1 ? 'campaign' : 'campaigns'}
              {filter.status ? ` · ${filter.label.toLowerCase()}` : ''}
              {searching ? ` · matching “${query}”` : ''}
              {!filter.status && ' · archived campaigns are hidden'}
            </p>
          </>
        ) : searching || filter.status ? (
          // A filtered empty result is not the same as having no campaigns, and
          // offering "create your first campaign" to someone who has twelve of
          // them would be wrong.
          <p className="px-4 py-10 text-center text-sm leading-relaxed text-muted">
            No campaigns match {searching ? `“${query}”` : `the ${filter.label} filter`}.{' '}
            <button
              type="button"
              onClick={() => setParams(new URLSearchParams(), { replace: true })}
              className="link-accent"
            >
              Clear filters
            </button>
          </p>
        ) : (
          <AdsEmptyState
            title="No campaigns yet"
            description="A campaign is the project every ad tool works inside. Brief it once — what you're advertising, to whom, on which platforms — and the banner, copy, carousel and video tools all inherit it."
            actionLabel="Create Your First Campaign"
            actionTo={CAMPAIGN_NEW_PATH}
          />
        )}
      </div>
    </div>
  )
}
