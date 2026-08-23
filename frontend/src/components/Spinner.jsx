// Tiny inline spinner for buttons and inline status text. It borrows the
// current text colour so it works on every button variant and in both themes.
export default function Spinner({ className = '' }) {
  return (
    <span
      className={`inline-block h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent ${className}`}
      aria-hidden="true"
    />
  )
}
