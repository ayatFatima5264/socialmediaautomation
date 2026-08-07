import { Link } from 'react-router-dom'
import AdCreativeArt from './AdCreativeArt.jsx'
import {
  CAMPAIGN_NEW_PATH,
  HERO_CAPABILITIES,
  HERO_QUICK_ACTIONS,
} from '../../lib/ads/tools'

// ---------------------------------------------------------------------------
// The Studio's hero.
//
// Two halves: the promise on the left, an example of the output on the right.
// Showing a finished ad is the fastest way to say what this module makes —
// faster than the sentence next to it — and it is why the artwork is a mock
// creative rather than an icon.
//
// Built from the app's own tokens: the standard card border and radius, the
// accent-soft wash, the existing button classes. It reads as a section of this
// product, not a marketing block pasted into it.
// ---------------------------------------------------------------------------

const TINTS = {
  emerald: 'bg-emerald-500/12 text-emerald-600',
  amber: 'bg-amber-500/12 text-amber-600',
  rose: 'bg-rose-500/12 text-rose-600',
  violet: 'bg-violet-500/12 text-violet-600',
}

export default function AdsHero() {
  return (
    <section className="card overflow-hidden">
      <div className="grid gap-0 lg:grid-cols-[minmax(0,1fr)_minmax(0,42%)]">
        {/* ---- The promise -------------------------------------------- */}
        <div className="bg-accent-soft px-5 py-6 md:px-7 md:py-8">
          <h1 className="text-2xl font-black leading-tight tracking-tight text-body md:text-3xl">
            AI Ads Studio
          </h1>

          <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted">
            Start a campaign, brief it once, and every tool — creatives, banners, videos,
            carousels and copy — works from it. Nothing asks you the same question twice.
          </p>

          <ul className="mt-4 flex flex-wrap gap-x-4 gap-y-2">
            {HERO_CAPABILITIES.map((c) => (
              <li key={c} className="flex items-center gap-1.5 text-sm font-medium text-body">
                <span aria-hidden="true" className="text-accent">
                  ✓
                </span>
                {c}
              </li>
            ))}
          </ul>

          <div className="mt-6 flex flex-wrap items-center gap-2.5">
            <Link to={CAMPAIGN_NEW_PATH} className="btn btn-primary">
              ✦ Create New Campaign
            </Link>
          </div>
        </div>

        {/* ---- An example of the output -------------------------------- *
         * Hidden below `lg`: on a phone it would push the buttons off the
         * first screen, and the buttons are the point.                    */}
        <AdCreativeArt name="heroAd" className="hidden min-h-[220px] lg:block" />
      </div>

      {/* ---- Quick start -------------------------------------------------
          Four ways in, all of them campaigns. These used to jump straight into
          a generator, which is what made the same six questions get asked in
          every tool — a creative made outside a campaign has no brief, no brand
          and nowhere to be saved. Picking the type here means the new-campaign
          form opens already knowing what the campaign is for. */}
      <div className="border-t border-line p-3 md:p-4">
        <h2 className="mb-2.5 px-1 text-xs font-semibold uppercase tracking-wide text-muted">
          Start a Campaign
        </h2>

        <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-4">
          {HERO_QUICK_ACTIONS.map((action) => (
            <Link
              key={action.type}
              to={`${CAMPAIGN_NEW_PATH}?type=${encodeURIComponent(action.type)}`}
              className="panel flex items-center gap-3 p-3 transition-colors hover:border-accent-line hover:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-page"
            >
              <span
                aria-hidden="true"
                className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg text-sm ${
                  TINTS[action.tint] || TINTS.emerald
                }`}
              >
                {action.icon}
              </span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-semibold text-body">
                  {action.label}
                </span>
                <span className="block truncate text-xs text-muted">{action.hint}</span>
              </span>
            </Link>
          ))}
        </div>
      </div>
    </section>
  )
}
