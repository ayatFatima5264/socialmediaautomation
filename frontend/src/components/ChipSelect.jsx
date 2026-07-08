// Reusable pill selector. Single-select (value is a string) or multi-select
// (value is an array) via the `multi` prop. Used by the onboarding wizard and
// the Business Profile settings form so selection UX stays consistent.
export default function ChipSelect({ options, value, onChange, multi = false }) {
  const isOn = (opt) => (multi ? (value || []).includes(opt) : value === opt)

  function toggle(opt) {
    if (multi) {
      const set = new Set(value || [])
      set.has(opt) ? set.delete(opt) : set.add(opt)
      onChange([...set])
    } else {
      onChange(value === opt ? '' : opt)
    }
  }

  return (
    <div className="flex flex-wrap gap-2">
      {options.map((opt) => (
        <button
          key={opt}
          type="button"
          onClick={() => toggle(opt)}
          className={`rounded-full border px-3.5 py-1.5 text-sm font-medium transition ${
            isOn(opt)
              ? 'border-accent bg-accent-soft text-accent'
              : 'border-line text-muted hover:border-accent'
          }`}
        >
          {isOn(opt) && <span className="mr-1">✓</span>}
          {opt}
        </button>
      ))}
    </div>
  )
}
