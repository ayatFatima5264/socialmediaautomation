// ---------------------------------------------------------------------------
// Generated blog cover art.
//
// Every article gets a distinct header image without shipping a single binary:
// each cover is an inline SVG built from a per-post palette (20 unique ones)
// and one of five geometric pattern families. That keeps the whole blog's
// artwork at roughly zero kilobytes, keeps it crisp at any size, and keeps it
// visually part of the brand rather than borrowed stock photography.
//
// NOTE: gradient/clip ids are namespaced with the post slug. Without that, the
// eight covers on the blog index would all resolve to the first card's
// gradient — SVG ids are document-global.
// ---------------------------------------------------------------------------

// Twenty palettes: [deep, mid, glow]. Hue walks the wheel while saturation and
// lightness stay put, so the set reads as one family instead of a paint box.
export const PALETTES = [
  ['#0b3d2e', '#1f8a5b', '#6ee7b7'], // emerald (brand)
  ['#0c3b44', '#127d8e', '#67e8f9'], // teal
  ['#10314f', '#1d6fa5', '#7dd3fc'], // ocean
  ['#1a2c5b', '#3b56b8', '#a5b4fc'], // indigo
  ['#2b1f5c', '#5b45bd', '#c4b5fd'], // violet
  ['#3d1c4f', '#7c3aad', '#e9d5ff'], // plum
  ['#4a1338', '#a8317a', '#f9a8d4'], // magenta
  ['#4d1226', '#b02a4d', '#fda4af'], // rose
  ['#4f1a15', '#b8452c', '#fca5a5'], // ember
  ['#4a2a10', '#b06a1c', '#fcd34d'], // amber
  ['#3f3510', '#8f8218', '#fde68a'], // gold
  ['#26401a', '#4e8c26', '#bef264'], // lime
  ['#12401f', '#1f8f43', '#86efac'], // forest
  ['#0d4038', '#12907c', '#5eead4'], // jade
  ['#123647', '#1a7fa0', '#a5f3fc'], // lagoon
  ['#152a4d', '#2c62b5', '#bfdbfe'], // azure
  ['#241d47', '#4b3fa8', '#ddd6fe'], // periwinkle
  ['#38204a', '#6d3fa0', '#e9d5ff'], // orchid
  ['#432036', '#94356f', '#fbcfe8'], // mulberry
  ['#1c3b30', '#2f7f62', '#a7f3d0'], // sage
]

// ---- Pattern families -----------------------------------------------------
// Each returns SVG children drawn over the gradient, in the palette's glow
// colour at low opacity. Pure geometry — no randomness, so a given post's
// cover is byte-identical on every render.

function Rings({ glow }) {
  return (
    <g stroke={glow} fill="none" opacity="0.28">
      {[90, 170, 250, 330, 410].map((r, i) => (
        <circle key={r} cx="985" cy="150" r={r} strokeWidth={i % 2 ? 1.5 : 3} />
      ))}
    </g>
  )
}

function Grid({ glow }) {
  return (
    <g fill={glow} opacity="0.3">
      {Array.from({ length: 11 }, (_, row) =>
        Array.from({ length: 20 }, (_, col) => {
          const cx = 60 + col * 60
          const cy = 40 + row * 58
          // Dots fade out toward the lower-left so the title stays readable.
          const r = 2 + ((row + col) % 4) * 1.1
          return <circle key={`${row}-${col}`} cx={cx} cy={cy} r={r} opacity={0.25 + (col / 20) * 0.75} />
        }),
      )}
    </g>
  )
}

function Waves({ glow }) {
  return (
    <g stroke={glow} fill="none" opacity="0.32">
      {[0, 1, 2, 3, 4, 5].map((i) => {
        const y = 120 + i * 92
        return (
          <path
            key={i}
            d={`M-40 ${y} C 200 ${y - 70}, 420 ${y + 70}, 660 ${y} S 1080 ${y - 70}, 1260 ${y}`}
            strokeWidth={i % 2 ? 2 : 3.5}
          />
        )
      })}
    </g>
  )
}

function Shards({ glow }) {
  return (
    <g fill={glow} opacity="0.26">
      <path d="M1200 0 L1200 300 L900 0 Z" />
      <path d="M1200 200 L1200 470 L960 470 Z" opacity="0.7" />
      <path d="M760 0 L980 0 L760 240 Z" opacity="0.5" />
      <path d="M1080 630 L1200 630 L1200 430 Z" opacity="0.6" />
      <path d="M880 630 L1020 630 L1020 500 Z" opacity="0.35" />
    </g>
  )
}

function Bars({ glow }) {
  return (
    <g fill={glow} opacity="0.3">
      {[
        [820, 380, 250],
        [880, 300, 330],
        [940, 190, 440],
        [1000, 260, 370],
        [1060, 120, 510],
        [1120, 330, 300],
      ].map(([x, y, h]) => (
        <rect key={x} x={x} y={y} width="34" height={h} rx="17" />
      ))}
      <circle cx="837" cy="330" r="14" opacity="0.9" />
      <circle cx="957" cy="140" r="14" opacity="0.9" />
      <circle cx="1077" cy="70" r="14" opacity="0.9" />
    </g>
  )
}

const PATTERNS = [Rings, Grid, Waves, Shards, Bars]

/**
 * @param {string} slug     unique per post — namespaces the SVG ids
 * @param {number} palette  index into PALETTES
 * @param {number} pattern  index into PATTERNS
 * @param {string} icon     large watermark glyph
 * @param {string} label    short kicker printed on the art (usually the category)
 */
export default function BlogCover({
  slug = 'post',
  palette = 0,
  pattern = 0,
  icon = '✦',
  label,
  className = '',
  rounded = 'rounded-2xl',
}) {
  const [deep, mid, glow] = PALETTES[palette % PALETTES.length]
  const Pattern = PATTERNS[pattern % PATTERNS.length]
  const gid = `cvg-${slug}`
  const fid = `cvf-${slug}`

  return (
    <svg
      viewBox="0 0 1200 630"
      className={`${className} ${rounded} block h-full w-full`}
      role="img"
      aria-label={label ? `${label} article cover` : 'Article cover'}
      preserveAspectRatio="xMidYMid slice"
    >
      <defs>
        <linearGradient id={gid} x1="0" y1="1" x2="1" y2="0">
          <stop offset="0%" stopColor={deep} />
          <stop offset="62%" stopColor={mid} />
          <stop offset="100%" stopColor={glow} stopOpacity="0.75" />
        </linearGradient>
        {/* Softens the pattern where the kicker text sits. */}
        <linearGradient id={fid} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor={deep} stopOpacity="0.92" />
          <stop offset="55%" stopColor={deep} stopOpacity="0.15" />
          <stop offset="100%" stopColor={deep} stopOpacity="0" />
        </linearGradient>
      </defs>

      <rect width="1200" height="630" fill={`url(#${gid})`} />
      <Pattern glow={glow} />
      <rect width="1200" height="630" fill={`url(#${fid})`} />

      {/* Oversized watermark glyph, bottom-left. */}
      <text
        x="72"
        y="560"
        fontSize="300"
        fill={glow}
        opacity="0.22"
        fontFamily="Inter, system-ui, sans-serif"
      >
        {icon}
      </text>

      {label && (
        <text
          x="76"
          y="112"
          fontSize="34"
          fill={glow}
          opacity="0.95"
          letterSpacing="6"
          fontWeight="700"
          fontFamily="Inter, system-ui, sans-serif"
        >
          {label.toUpperCase()}
        </text>
      )}
    </svg>
  )
}
