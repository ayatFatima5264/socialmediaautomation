import { useState } from 'react'

// ---------------------------------------------------------------------------
// A "?" beside a page heading that holds the explanatory copy which would
// otherwise cost a paragraph of vertical space above the fold.
//
// Tap-to-toggle rather than hover-only: touch devices have no hover, so a
// hover-only tip is simply unreachable on a phone. Hover still opens it on a
// pointer device.
//
// Below `sm` the panel is a fixed strip across the bottom of the screen rather
// than a box hanging off the icon. Clamping its width was not enough: the "?"
// sits after a heading, so on a 390px screen it starts around x=220 and a 256px
// panel ran to x=478 — the tip was half off the screen whatever its width, and
// which half depended on how long the heading was. Anchored to the viewport
// instead, it always fits and is a comfortable tap target. From `sm` up there
// is room for the anchored panel, which keeps it tied to the icon it explains.
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
        className={`fixed inset-x-3 bottom-3 z-30 rounded-lg border border-line bg-surface p-3 text-xs leading-relaxed text-muted shadow-lg transition-opacity sm:absolute sm:inset-x-auto sm:bottom-auto sm:left-0 sm:top-full sm:mt-1.5 sm:w-64 sm:max-w-[calc(100vw-6rem)] sm:p-2.5 ${
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
