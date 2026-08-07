import { Link } from 'react-router-dom'
import AdsEmptyState from '../../components/ads/AdsEmptyState.jsx'
import AdsHero from '../../components/ads/AdsHero.jsx'
import CampaignStatTile from '../../components/ads/CampaignStatTile.jsx'
import CampaignTable from '../../components/ads/CampaignTable.jsx'
import RecentAssetStrip from '../../components/ads/RecentAssetStrip.jsx'
import useCampaigns from '../../hooks/useCampaigns'
import useRecentAssets from '../../hooks/useRecentAssets'
import { CAMPAIGN_STAT_TILES } from '../../lib/ads/constants'
import {
  ADS_BASE_PATH,
  CAMPAIGN_LIST_PATH,
  CAMPAIGN_NEW_PATH,
  campaignPath,
} from '../../lib/ads/tools'
import { formatRelative } from '../../lib/datetime'

// ---------------------------------------------------------------------------
// AI Ads Studio — the module's home.
//
// ---- What changed and why -------------------------------------------------
// This page used to lead with fifteen tool cards. That made the tools the entry
// point, and a tool entered directly has no campaign behind it: no brief, no
// brand, no platforms, and nowhere to save what it makes. The result was every
// generator re-asking the same six questions and every creative evaporating on
// navigation.
//
// So the tools are no longer here. The campaign is the entry point, and the
// tools live inside a campaign — where they inherit its brief and save into its
// library. This page answers three questions and nothing else:
//
//   Where do I start?      → the hero, and Create New Campaign
//   Where was I?           → recent campaigns, recent assets, recent activity
//   How is it going?       → quick stats
//
// ---- Scrolling ------------------------------------------------------------
// This page does NOT create a scroll container of its own. The app shell's
// <main> already scrolls, so a `.split-pane` here would nest a second scroll
// area inside it and the user gets two scrollbars.
// ---------------------------------------------------------------------------

const RECENT_LIMIT = 5
const ACTIVITY_LIMIT = 6

/**
 * One timeline out of two sources.
 *
 * Campaigns and assets are separate records with separate endpoints, but "what
 * has been happening" is one question. Merging them here — rather than showing
 * two lists side by side and leaving the user to interleave them mentally — is
 * the whole point of the section.
 */
function buildActivity(campaigns, assets) {
  const entries = [
    ...campaigns.map((c) => ({
      id: `campaign-${c.id}`,
      at: c.updatedAt,
      to: campaignPath(c.id),
      text: `${c.name} — ${c.campaignType}`,
      kind: 'Campaign updated',
    })),
    ...assets.map((a) => ({
      id: `asset-${a.id}`,
      at: a.createdAt,
      to: campaignPath(a.campaignId),
      text: `${a.title}${a.campaignName ? ` — ${a.campaignName}` : ''}`,
      kind: a.tool ? `Made with ${a.tool}` : 'Asset created',
    })),
  ]

  return entries
    .filter((e) => e.at)
    .sort((a, b) => new Date(b.at) - new Date(a.at))
    .slice(0, ACTIVITY_LIMIT)
}

export default function AdsStudio() {
  const { campaigns, stats, loading, error } = useCampaigns()
  const { assets, loading: assetsLoading } = useRecentAssets(8)

  const total = campaigns.length
  const recent = campaigns.slice(0, RECENT_LIMIT)
  const hasCampaigns = total > 0
  const activity = buildActivity(campaigns, assets)

  return (
    <div className="space-y-6 pb-2">
      <AdsHero />

      {/* ---- Quick stats ------------------------------------------------- */}
      <section aria-labelledby="ads-stats">
        <h2 id="ads-stats" className="mb-3 font-semibold text-body">
          Quick Stats
        </h2>
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
          {CAMPAIGN_STAT_TILES.map((tile) => (
            <CampaignStatTile
              key={tile.key}
              compact
              label={tile.label}
              accent={tile.accent}
              value={stats[tile.key] ?? 0}
              loading={loading}
            />
          ))}
        </div>
      </section>

      {/* ---- Recent campaigns -------------------------------------------- *
       * The main content of the page. A campaign is where all the work
       * happens, so this is the list that matters and it is not buried under
       * anything.                                                            */}
      <section aria-labelledby="ads-campaigns">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <h2 id="ads-campaigns" className="font-semibold text-body">
            Recent Campaigns
          </h2>
          {hasCampaigns && (
            <div className="flex items-center gap-2">
              {/* The home page shows the five most recent. Everything else —
                  search, filters, archive, the management actions — lives on
                  the list page rather than growing a control bar here for a
                  table that is only ever five rows long. */}
              <Link to={CAMPAIGN_LIST_PATH} className="btn btn-secondary btn-sm">
                View All
                {total > RECENT_LIMIT ? ` (${total})` : ''}
              </Link>
              <Link to={CAMPAIGN_NEW_PATH} className="btn btn-primary btn-sm">
                ✦ New Campaign
              </Link>
            </div>
          )}
        </div>

        <div className="card p-3">
          {loading ? (
            <div className="space-y-3 p-3">
              {[0, 1, 2].map((i) => (
                <div key={i} className="skeleton h-11 w-full" />
              ))}
            </div>
          ) : error ? (
            <p className="px-4 py-10 text-center text-sm text-rose-600">{error}</p>
          ) : hasCampaigns ? (
            <div className="pt-2">
              <CampaignTable campaigns={recent} />
            </div>
          ) : (
            <AdsEmptyState
              title="No campaigns yet"
              description="A campaign is the project every ad tool works inside. Brief it once — what you're advertising, to whom, on which platforms — and the banner, copy, carousel and video tools all inherit it. Nothing gets asked twice."
              actionLabel="Create Your First Campaign"
              actionTo={CAMPAIGN_NEW_PATH}
            />
          )}
        </div>
      </section>

      {/* ---- Recent assets ----------------------------------------------- */}
      {(assetsLoading || assets.length > 0) && (
        <section aria-labelledby="ads-assets">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <h2 id="ads-assets" className="font-semibold text-body">
              Recent Assets
            </h2>
            <p className="text-xs text-muted">
              Open the campaign to rename, reuse or download them.
            </p>
          </div>
          <RecentAssetStrip assets={assets} loading={assetsLoading} />
        </section>
      )}

      {/* ---- Templates ---------------------------------------------------- */}
      <section aria-labelledby="ads-templates">
        <h2 id="ads-templates" className="mb-3 font-semibold text-body">
          Templates
        </h2>
        <Link
          to={`${ADS_BASE_PATH}/templates`}
          className="card block p-4 transition-shadow hover:shadow-[var(--shadow-pop)] focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-page"
        >
          <span className="text-sm font-semibold text-body">Browse starting layouts</span>
          <span className="mt-1 block text-xs leading-relaxed text-muted">
            A layout per ad type and placement, already sized and wired to your Brand Kit.
            Picking one starts a campaign with the template recorded on it.
          </span>
        </Link>
      </section>

      {/* ---- Recent activity ---------------------------------------------- */}
      {activity.length > 0 && (
        <section aria-labelledby="ads-activity" className="pb-1">
          <h2 id="ads-activity" className="mb-3 font-semibold text-body">
            Recent Activity
          </h2>
          <ul className="card divide-y divide-line p-0">
            {activity.map((entry) => (
              <li key={entry.id}>
                <Link
                  to={entry.to}
                  className="flex items-baseline justify-between gap-3 px-4 py-2.5 transition-colors hover:bg-inset"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium text-body">
                      {entry.text}
                    </span>
                    <span className="block text-xs text-muted">{entry.kind}</span>
                  </span>
                  <span className="shrink-0 text-xs text-muted">
                    {formatRelative(entry.at)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
