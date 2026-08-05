import AdsEmptyState from '../../components/ads/AdsEmptyState.jsx'
import AdsHero from '../../components/ads/AdsHero.jsx'
import AdToolSection from '../../components/ads/AdToolSection.jsx'
import CampaignStatTile from '../../components/ads/CampaignStatTile.jsx'
import CampaignTable from '../../components/ads/CampaignTable.jsx'
import useCampaigns from '../../hooks/useCampaigns'
import { CAMPAIGN_STAT_TILES } from '../../lib/ads/constants'
import { AD_CATEGORIES, CAMPAIGN_NEW_PATH, toolsInCategory } from '../../lib/ads/tools'

// ---------------------------------------------------------------------------
// AI Ads Studio — the module's home.
//
// The entry point for every advertising feature, and a separate workflow from
// the AI Generator: that page produces one organic post, this one produces ad
// creative and the campaigns it belongs to.
//
// ---- What this page leads with -------------------------------------------
// Creation, then the campaign state. A user opening the Studio is here to make
// an ad, not to read counters, so the hero and the four tool sections come
// first and the overview sits underneath in its compact form. It is still on
// the page — knowing three campaigns are live is worth one glance — but it no
// longer takes the space above the fold that the tools need.
//
// Tools are grouped by job (Create / Video / AI Tools / Assets) rather than
// listed flat: fifteen equal cards is a wall, four short sections is a choice.
//
// ---- What is real today ---------------------------------------------------
// Brand Kit links to the business profile, which ships. Every other card routes
// to its placeholder, and campaign data comes from a local store behind the
// same async interface the backend will implement (lib/ads/store.js) — so the
// layout, loading, empty and populated states are all genuine.
//
// ---- Scrolling ------------------------------------------------------------
// This page does NOT create a scroll container of its own. The app shell's
// <main> already scrolls, so a `.split-pane` here would nest a second scroll
// area inside it and the user gets two scrollbars.
//
// The `.split-shell` / `.split-pane` pattern in index.css is for TWO-COLUMN
// working pages (Generator, Create Post, Scheduler), where the point is that
// the controls and the results scroll independently of each other. This page is
// a single column, so there is no second thing to scroll and nothing to gain —
// only the nesting to lose.
// ---------------------------------------------------------------------------

const RECENT_LIMIT = 5

export default function AdsStudio() {
  const { campaigns, stats, loading, error, clearSamples, hasOnlySamples } = useCampaigns()

  const recent = campaigns.slice(0, RECENT_LIMIT)
  const hasCampaigns = campaigns.length > 0

  return (
    <div className="space-y-6 pb-2">
      <AdsHero />

      {/* ---- The tools, grouped by job --------------------------------- */}
      {AD_CATEGORIES.map((category) => (
        <AdToolSection
          key={category.key}
          category={category}
          tools={toolsInCategory(category.key)}
        />
      ))}

      {/* ---- Campaign Overview ----------------------------------------- *
       * Below the tools and deliberately quiet — see the note at the top of
       * this file. The counts and the table read the same array, so they can
       * never disagree about how many campaigns are active.               */}
      <section aria-labelledby="ads-campaigns" className="pb-1">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <h2 id="ads-campaigns" className="font-semibold text-body">
            Your Campaigns
          </h2>

          {/* Offered only while every campaign is a seeded example, so it can
              never read as "delete my real work". */}
          {hasOnlySamples && (
            <button onClick={clearSamples} className="text-xs text-muted hover:text-accent">
              Clear sample data
            </button>
          )}
        </div>

        <div className="card p-3">
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

          <div className="mt-3 border-t border-line pt-1">
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
                description="Campaigns group your creatives, copy and platforms into one thing you can schedule and measure. Start a tool above, or brief a whole campaign at once."
                actionLabel="Create Your First Campaign"
                actionTo={CAMPAIGN_NEW_PATH}
              />
            )}
          </div>
        </div>
      </section>
    </div>
  )
}
