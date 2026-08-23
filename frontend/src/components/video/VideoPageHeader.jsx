import { Link } from 'react-router-dom'
import VideoIcon from './VideoIcon.jsx'

// ---------------------------------------------------------------------------
// The heading every Video Studio page opens with.
//
// One component rather than a heading per page, so the title size, the gap
// under it and the position of the actions cannot drift between eight screens.
// `back` renders the same left-chevron the mockup shows on every sub-page.
//
// Wraps on a narrow screen: the actions drop under the title rather than
// squeezing it, which is what keeps a two-word button from becoming three
// lines on a phone.
// ---------------------------------------------------------------------------

export default function VideoPageHeader({ title, subtitle, back, backLabel, actions }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="flex min-w-0 items-start gap-3">
        {back && (
          <Link
            to={back}
            aria-label={backLabel || 'Back'}
            className="btn btn-ghost btn-sm mt-0.5 shrink-0 px-2"
          >
            <span aria-hidden="true">‹</span>
          </Link>
        )}
        <div className="min-w-0">
          <h1 className="truncate text-xl font-bold text-body sm:text-2xl">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
        </div>
      </div>

      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

/** An empty state that says what is missing and offers the one action that
 *  fixes it. Used by Projects and by the Overview's recent list. */
export function VideoEmptyState({ icon = 'film', title, description, action }) {
  return (
    <div className="card flex flex-col items-center gap-3 px-6 py-12 text-center">
      <span className="grid h-12 w-12 place-items-center rounded-full bg-inset text-muted">
        <VideoIcon name={icon} className="h-6 w-6" />
      </span>
      <div>
        <p className="font-semibold text-body">{title}</p>
        {description && (
          <p className="mx-auto mt-1 max-w-sm text-sm text-muted">{description}</p>
        )}
      </div>
      {action}
    </div>
  )
}
