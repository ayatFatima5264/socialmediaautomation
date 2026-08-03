import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { CONSENT_DENIED, CONSENT_GRANTED, getConsent, setConsent } from '../../lib/consent'

// ---------------------------------------------------------------------------
// Cookie consent banner.
//
// Shown once, until the visitor chooses. Choosing "Accept" is what actually
// starts analytics and AdSense — see lib/analytics.js, which subscribes to the
// consent store rather than loading on page load.
//
// Deliberately offers a genuine reject option with equal visual weight. A
// banner where refusing is hidden or harder than accepting is not valid
// consent under GDPR/UK GDPR and is a common reason publishers run into
// trouble with Google's EU user consent policy.
// ---------------------------------------------------------------------------

export default function CookieConsent() {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    // Defer a tick so the banner never blocks first paint or LCP.
    const t = setTimeout(() => setVisible(getConsent() === null), 800)
    return () => clearTimeout(t)
  }, [])

  if (!visible) return null

  const decide = (value) => {
    setConsent(value)
    setVisible(false)
  }

  return (
    <div
      role="dialog"
      aria-live="polite"
      aria-label="Cookie consent"
      className="fixed inset-x-0 bottom-0 z-50 p-3 sm:p-4"
    >
      <div className="mx-auto flex max-w-4xl flex-col gap-4 rounded-2xl border border-line bg-surface p-5 shadow-lg sm:flex-row sm:items-center">
        <p className="flex-1 text-sm leading-relaxed text-muted">
          We use essential cookies to keep you signed in. With your permission we also use
          analytics and advertising cookies to understand how the site is used and to support
          the site.{' '}
          <Link to="/cookies" className="link-accent font-semibold">
            Read our Cookie Policy
          </Link>
          .
        </p>
        <div className="flex shrink-0 gap-2">
          <button
            onClick={() => decide(CONSENT_DENIED)}
            className="btn btn-secondary btn-sm flex-1 sm:flex-none"
          >
            Reject non-essential
          </button>
          <button
            onClick={() => decide(CONSENT_GRANTED)}
            className="btn btn-primary btn-sm flex-1 sm:flex-none"
          >
            Accept all
          </button>
        </div>
      </div>
    </div>
  )
}
