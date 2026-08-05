import { Link } from 'react-router-dom'
import AdCreativeArt from './AdCreativeArt.jsx'
import { toolArt, toolHref } from '../../lib/ads/tools'

// ---------------------------------------------------------------------------
// A tool card on the Studio home.
//
// The artwork is roughly half the card and shows an example of what the tool
// produces, not a symbol for it — so the grid reads as a portfolio of outputs
// and a user can tell Banner Generator from Carousel Ads at a glance, without
// reading either label.
//
// The whole card is one <Link>, with "Open" drawn as a button rather than being
// one. A nested <button> inside a link is invalid and a worse target: two focus
// stops and two hit areas for one action. This way the entire card is
// clickable and keyboard users get a single tab stop that says where it goes.
//
// A card links wherever the registry points it — a tool the Studio owns goes to
// its own route, one that already exists elsewhere goes to the real page.
// Nothing here builds a path.
// ---------------------------------------------------------------------------

export default function AdToolCard({ tool }) {
  return (
    <Link
      to={toolHref(tool)}
      className="card group flex flex-col overflow-hidden transition-shadow duration-150 hover:shadow-[var(--shadow-pop)] focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-page"
    >
      <div className="relative">
        <AdCreativeArt name={toolArt(tool.slug)} className="h-36 w-full" />

        {tool.available && (
          <span className="badge badge-accent absolute right-2 top-2 bg-surface">Ready</span>
        )}

        {/* A tool blocked on something the user must obtain says so HERE,
            where they choose it — not after they have filled in a form and
            pressed the button. */}
        {tool.blocked && (
          <span className="badge absolute right-2 top-2 bg-surface text-amber-600 shadow-sm">
            Needs setup
          </span>
        )}
      </div>

      <div className="flex flex-1 flex-col p-4">
        <h3 className="text-sm font-bold leading-snug text-body">
          {tool.name}
          {tool.featured && (
            <span className="ml-1.5 text-amber-500" title="Most used" aria-label="Most used">
              ★
            </span>
          )}
        </h3>

        <p className="mt-1.5 flex-1 text-xs leading-relaxed text-muted">{tool.description}</p>

        <span className="btn btn-primary btn-sm mt-3.5 self-start">
          Open
          <span aria-hidden="true" className="transition-transform group-hover:translate-x-0.5">
            →
          </span>
        </span>
      </div>
    </Link>
  )
}
