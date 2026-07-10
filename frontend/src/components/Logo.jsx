// Shared brand mark — the AutoSocial AI network icon: three connected nodes
// (top in mint) on an emerald rounded-square badge. Single source of truth used
// by the app sidebar, auth screen, marketing header/footer, and loader. Change
// the logo here and it updates everywhere. `size` is the square edge in px.
export default function Logo({ size = 36, className = '' }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 200 200"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="AutoSocial AI"
      className={className}
    >
      <title>AutoSocial AI</title>
      <rect width="200" height="200" rx="46" fill="#0E7A5A" />
      {/* Network recentred to the badge centre (100,100). */}
      <g transform="translate(-10 -5)">
        <line x1="110" y1="60" x2="64" y2="150" stroke="#EAFBF3" strokeWidth="8" strokeLinecap="round" />
        <line x1="110" y1="60" x2="156" y2="150" stroke="#EAFBF3" strokeWidth="8" strokeLinecap="round" />
        <line x1="64" y1="150" x2="156" y2="150" stroke="#EAFBF3" strokeWidth="8" strokeLinecap="round" />
        <circle cx="110" cy="60" r="18" fill="#6EE7B7" />
        <circle cx="64" cy="150" r="16" fill="#EAFBF3" />
        <circle cx="156" cy="150" r="16" fill="#EAFBF3" />
      </g>
    </svg>
  )
}
