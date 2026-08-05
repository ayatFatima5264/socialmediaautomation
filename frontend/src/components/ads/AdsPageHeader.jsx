import { Link } from 'react-router-dom'
import { ADS_BASE_PATH } from '../../lib/ads/tools'

// ---------------------------------------------------------------------------
// The header every AI Ads Studio page opens with.
//
// Shared so the Studio home and each tool page keep one title scale, one
// description treatment and one place for the primary action — the thing that
// most often drifts once a module grows past its first screen.
//
// `backLabel` turns on the breadcrumb back to the Studio; the home page omits
// it, since it is the destination.
// ---------------------------------------------------------------------------

export default function AdsPageHeader({ title, description, backLabel, actions }) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0 max-w-2xl">
        {backLabel && (
          <Link
            to={ADS_BASE_PATH}
            className="mb-2 inline-flex items-center gap-1.5 text-sm text-muted transition-colors hover:text-accent"
          >
            <span aria-hidden="true">←</span>
            {backLabel}
          </Link>
        )}

        <h1 className="text-xl font-bold tracking-tight text-body md:text-2xl">{title}</h1>

        {description && (
          <p className="mt-2 text-sm leading-relaxed text-muted">{description}</p>
        )}
      </div>

      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  )
}
