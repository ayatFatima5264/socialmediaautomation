// ---------------------------------------------------------------------------
// Compact control primitives for the editor panel.
//
// The panel is a fixed ~19rem column that must hold every property without the
// page scrolling, so controls are laid out as a two-column grid — a small muted
// label on the left, the control on the right — rather than the stacked
// label-above-input pattern used elsewhere in the app. That halves the vertical
// space each property costs.
//
// Extracted into their own module because both LayerProperties and the panel
// sections use them, and because keeping the compact styling in one place stops
// it drifting control by control.
// ---------------------------------------------------------------------------

// label | control, aligned on a shared grid so every row lines up.
export function Field({ label, children, stack }) {
  if (stack) {
    return (
      <div className="py-1">
        <div className="mb-1 text-[11px] font-medium text-muted">{label}</div>
        {children}
      </div>
    )
  }
  return (
    <div className="grid grid-cols-[4.25rem_minmax(0,1fr)] items-center gap-2 py-1">
      <div className="text-[11px] font-medium text-muted">{label}</div>
      <div className="min-w-0">{children}</div>
    </div>
  )
}

export function CompactSelect({ value, onChange, options, style }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      style={style}
      className="w-full rounded-md border border-field-border bg-field px-2 py-1 text-xs text-body outline-none focus:border-accent"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value} style={o.style}>
          {o.label}
        </option>
      ))}
    </select>
  )
}

export function CompactSlider({ value, onChange, min, max, step, format }) {
  return (
    <div className="flex items-center gap-2">
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-1 min-w-0 flex-1 cursor-pointer accent-[var(--accent)]"
      />
      {format && (
        <span className="w-9 shrink-0 text-right font-mono text-[10px] text-muted">
          {format(value)}
        </span>
      )}
    </div>
  )
}

// Swatch + hex in one row — the two things people change together.
export function CompactColor({ value, onChange, fallback = '#ffffff' }) {
  return (
    <div className="flex items-center gap-1.5 rounded-md border border-field-border bg-field px-1.5 py-1">
      <input
        type="color"
        value={/^#[0-9a-f]{6}$/i.test(value || '') ? value : fallback}
        onChange={(e) => onChange(e.target.value)}
        className="h-5 w-5 shrink-0 cursor-pointer rounded border-0 bg-transparent p-0"
        aria-label="Colour"
      />
      <input
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder={fallback}
        maxLength={7}
        className="w-full min-w-0 bg-transparent font-mono text-[11px] uppercase text-body outline-none"
      />
    </div>
  )
}

// Segmented control. `wide` keeps text labels readable; icon sets stay square.
export function Segmented({ options, value, onChange, wide }) {
  return (
    <div className="flex gap-1">
      {options.map((o) => {
        const active = value === o.value
        return (
          <button
            key={o.value}
            type="button"
            title={o.title || o.label}
            onClick={() => onChange(o.value)}
            className={`${wide ? 'flex-1' : 'w-8'} rounded-md border py-1 text-[11px] font-semibold leading-5 transition ${
              active
                ? 'border-accent bg-accent-soft text-accent'
                : 'border-line text-muted hover:border-accent-line hover:text-accent'
            } ${o.className || ''}`}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

// Small icon-first action, used for add-buttons and layer actions.
export function MiniButton({ onClick, children, title, disabled, tone }) {
  const toneCls =
    tone === 'danger'
      ? 'border-rose-400/40 text-rose-600 hover:bg-rose-500/10'
      : 'border-line text-body hover:border-accent-line hover:text-accent'
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      disabled={disabled}
      className={`inline-flex items-center justify-center gap-1.5 rounded-md border px-2 py-1.5 text-[11px] font-semibold transition disabled:cursor-not-allowed disabled:opacity-40 ${toneCls}`}
    >
      {children}
    </button>
  )
}
