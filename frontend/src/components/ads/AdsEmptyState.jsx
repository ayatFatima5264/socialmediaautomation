import { Link } from 'react-router-dom'

// ---------------------------------------------------------------------------
// The Studio's empty state.
//
// Generic on purpose: the campaign list is the first surface to need one, but
// every tool page in later phases has the same "nothing here yet" moment, and
// they should all look identical. Title, body and a single primary action —
// no illustration competing with the Quick Action cards above it.
// ---------------------------------------------------------------------------

export default function AdsEmptyState({ title, description, actionLabel, actionTo, icon = '◈' }) {
  return (
    <div className="flex flex-col items-center px-6 py-14 text-center">
      <div
        className="mb-5 grid h-14 w-14 place-items-center rounded-full bg-accent-soft text-xl text-accent"
        aria-hidden="true"
      >
        {icon}
      </div>

      <h3 className="text-base font-bold text-body">{title}</h3>
      <p className="mt-2 max-w-md text-sm leading-relaxed text-muted">{description}</p>

      {actionLabel && actionTo && (
        <Link to={actionTo} className="btn btn-primary mt-6">
          ✦ {actionLabel}
        </Link>
      )}
    </div>
  )
}
