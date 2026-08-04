import { useState } from 'react'

// ---------------------------------------------------------------------------
// A "?" beside a page heading that holds the explanatory copy which would
// otherwise cost a paragraph of vertical space above the fold.
//
// Tap-to-toggle rather than hover-only: touch devices have no hover, so a
// hover-only tip is simply unreachable on a phone. Hover still opens it on a
// pointer device. The panel is width-clamped because it hangs off an icon that
// already sits some way in from the left edge of a narrow screen.
// ---------------------------------------------------------------------------
export default function HelpTip({ label = 'About this page', children }) {
  const [open, setOpen] = useState(false)

  return (
    <span className="group relative inline-flex align-middle">
      <button
        type="button"
        aria-label={label}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="grid h-5 w-5 place-items-center rounded-full border border-line text-[11px] font-bold leading-none text-muted transition hover:border-accent-line hover:text-accent"
      >
        ?
      </button>
      <span
        role="tooltip"
        className={`absolute left-0 top-full z-30 mt-1.5 w-64 max-w-[calc(100vw-6rem)] rounded-lg border border-line bg-surface p-2.5 text-xs leading-relaxed text-muted shadow-lg transition-opacity ${
          open
            ? 'opacity-100'
            : 'pointer-events-none opacity-0 group-hover:pointer-events-auto group-hover:opacity-100'
        }`}
      >
        {children}
      </span>
    </span>
  )
}
