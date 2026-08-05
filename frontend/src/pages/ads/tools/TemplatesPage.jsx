import { Link } from 'react-router-dom'
import AdsPageHeader from '../../../components/ads/AdsPageHeader.jsx'
import AdCreativeArt from '../../../components/ads/AdCreativeArt.jsx'
import { TEMPLATES } from '../../../lib/brandKit/templates'
import { AD_CATEGORIES, toolHref, toolsInCategory } from '../../../lib/ads/tools'

// ---------------------------------------------------------------------------
// Templates.
//
// Two kinds of template, kept visibly apart because only one of them exists:
//
//   Brand overlays — REAL. These ship today, drive the branded image output in
//   the Generator and Content Planner, and are read straight from
//   lib/brandKit/templates.js. Listing them from that module rather than
//   re-describing them here means adding an overlay shows up on this page.
//
//   Ad layouts — phase 2. Sized, typeset starting points per ad type. Stated as
//   coming rather than mocked up as a grid of fake thumbnails, because a
//   template gallery that cannot be opened is worse than a sentence.
//
// The tool links at the bottom are the honest answer to "so where do I start" —
// each of those workspaces exists now.
// ---------------------------------------------------------------------------

const ART_FOR_CATEGORY = { create: 'productAd', video: 'imageVideo' }

export default function TemplatesPage() {
  const startHere = AD_CATEGORIES.filter((c) => c.key === 'create' || c.key === 'video')

  return (
    <div className="space-y-6 pb-2">
      <AdsPageHeader
        title="Templates"
        description="Starting points rather than a blank artboard — the brand overlays you have now, and the ad layouts arriving next."
        backLabel="AI Ads Studio"
      />

      {/* ---- Real: brand overlay templates ----------------------------- */}
      <section aria-labelledby="tpl-brand">
        <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h2 id="tpl-brand" className="font-semibold text-body">
            Brand overlays
          </h2>
          <span className="badge badge-accent">Available now</span>
        </div>

        <p className="mb-3 max-w-2xl text-xs leading-relaxed text-muted">
          Applied to generated images across the app. Edit the logo, colours and contact
          details behind them in your{' '}
          <Link to="/business-profile" className="link-accent">
            Brand Kit
          </Link>
          .
        </p>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
          {TEMPLATES.map((tpl) => (
            <div key={tpl.id} className="card p-4">
              <h3 className="text-sm font-bold text-body">{tpl.label}</h3>
              <p className="mt-1.5 text-xs leading-relaxed text-muted">{tpl.description}</p>
              {tpl.usesContact && (
                <span className="mt-2.5 inline-block text-[11px] font-medium text-muted">
                  Includes contact details
                </span>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* ---- Coming: ad layout templates ------------------------------- */}
      <section aria-labelledby="tpl-layouts">
        <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h2 id="tpl-layouts" className="font-semibold text-body">
            Ad layouts
          </h2>
          <span className="badge badge-accent">Phase 2</span>
        </div>

        <div className="card p-5">
          <p className="max-w-2xl text-sm leading-relaxed text-muted">
            Layouts per ad type and placement — already sized, typeset and wired to your
            Brand Kit, so a campaign starts from a design rather than an empty frame. Until
            they land, every tool below starts you from its own defaults, which is one step
            rather than none.
          </p>

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {startHere.map((category) => (
              <div key={category.key} className="panel overflow-hidden">
                <AdCreativeArt
                  name={ART_FOR_CATEGORY[category.key]}
                  className="h-20 w-full opacity-50"
                />
                <div className="p-3">
                  <div className="text-sm font-semibold text-body">{category.label}</div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {toolsInCategory(category.key).map((tool) => (
                      <Link
                        key={tool.slug}
                        to={toolHref(tool)}
                        className="btn btn-secondary btn-sm"
                      >
                        {tool.name}
                      </Link>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  )
}
