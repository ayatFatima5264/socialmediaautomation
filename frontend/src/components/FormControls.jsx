import { useEffect, useRef, useState } from 'react'

// Shared compact form controls used by the AI Generator and Create Post forms.

// ---------------------------------------------------------------------------
// Icon + label dropdown — a single control that replaces a wide grid of pills.
// Uses the app's .select trigger (border + chevron) and .menu popover list.
// ---------------------------------------------------------------------------
export function SourceDropdown({ options, value, onChange, ariaLabel }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const current = options.find((o) => o.id === value) || options[0]

  useEffect(() => {
    function onDoc(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        className="select flex items-center text-left"
      >
        <span className="flex items-center gap-2">
          <span className="w-5 text-center">{current.icon}</span>
          {current.label}
        </span>
      </button>
      {open && (
        <div
          role="listbox"
          className="menu absolute left-0 right-0 z-30 mt-1 max-h-64 overflow-auto"
        >
          {options.map((o) => (
            <button
              type="button"
              key={o.id}
              role="option"
              aria-selected={o.id === value}
              onClick={() => {
                onChange(o.id)
                setOpen(false)
              }}
              className={`menu-item ${o.id === value ? 'bg-accent-soft text-accent' : ''}`}
            >
              <span className="w-5 shrink-0 text-center">{o.icon}</span>
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Collapsible section — 0.5px top divider, header with chevron (▸/▾), and a
// smooth 200ms height transition. Collapsed content takes no layout space.
// ---------------------------------------------------------------------------
export function Accordion({ title, open, onToggle, children }) {
  return (
    <div className="pt-3" style={{ borderTop: '0.5px solid var(--line)' }}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center justify-between text-sm font-semibold"
      >
        <span>{title}</span>
        <span className="text-muted">{open ? '▾' : '▸'}</span>
      </button>
      <div
        className="grid transition-[grid-template-rows] duration-200 ease-in-out"
        style={{ gridTemplateRows: open ? '1fr' : '0fr' }}
      >
        <div className="overflow-hidden">
          <div className="pt-3">{children}</div>
        </div>
      </div>
    </div>
  )
}
