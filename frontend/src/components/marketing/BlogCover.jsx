// ---------------------------------------------------------------------------
// Generated blog cover art.
//
// Every article gets a distinct header image without shipping a single binary:
// each cover is an inline SVG built from a per-post palette (20 unique ones)
// and one of five geometric pattern families. That keeps the whole blog's
// artwork at roughly zero kilobytes, keeps it crisp at any size, and keeps it
// visually part of the brand rather than borrowed stock photography.
//
// SAFE AREA — the reason the layout constants below look fussy:
// the same 1200x630 artwork is rendered into three different container
// shapes (16/9 cards, 16/10 featured, and a wide article header), all with
// `preserveAspectRatio="slice"`, which crops rather than letterboxes. The
// tightest crops are:
//
//   article header  1200x430  -> vertical crop, leaves y 100..530
//   featured card   16/10     -> horizontal crop, leaves x  96..1104
//
// Anything outside the intersection of those gets cut off. SAFE below is that
// intersection with a margin, and every piece of text or iconography is
// positioned inside it. Decorative patterns may bleed past — that is the point
// of them.
//
// NOTE: gradient/clip ids are namespaced with the post slug. Without that, the
// eight covers on the blog index would all resolve to the first card's
// gradient — SVG ids are document-global.
// ---------------------------------------------------------------------------

const SAFE = { left: 140, right: 1060, top: 130, bottom: 500 }

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
// Drawn behind the content in the palette's glow colour at low opacity, and
// weighted toward the right so the left-hand text block stays legible. These
// are allowed to bleed outside the safe area.

function Rings({ glow }) {
  return (
    <g stroke={glow} fill="none" opacity="0.22">
      {[70, 140, 210, 280, 350].map((r, i) => (
        <circle key={r} cx="1010" cy="315" r={r} strokeWidth={i % 2 ? 1.5 : 3} />
      ))}
    </g>
  )
}

function Grid({ glow }) {
  return (
    <g fill={glow} opacity="0.26">
      {Array.from({ length: 11 }, (_, row) =>
        Array.from({ length: 20 }, (_, col) => {
          const cx = 60 + col * 60
          const cy = 40 + row * 58
          const r = 2 + ((row + col) % 4) * 1.1
          // Fade toward the left so the headline sits on clean colour.
          return <circle key={`${row}-${col}`} cx={cx} cy={cy} r={r} opacity={0.1 + (col / 20) * 0.9} />
        }),
      )}
    </g>
  )
}

function Waves({ glow }) {
  return (
    <g stroke={glow} fill="none" opacity="0.26">
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
    <g fill={glow} opacity="0.22">
      <path d="M1200 0 L1200 300 L900 0 Z" />
      <path d="M1200 200 L1200 470 L960 470 Z" opacity="0.7" />
      <path d="M1080 630 L1200 630 L1200 430 Z" opacity="0.6" />
      <path d="M880 630 L1020 630 L1020 500 Z" opacity="0.35" />
    </g>
  )
}

function Bars({ glow }) {
  return (
    <g fill={glow} opacity="0.24">
      {[
        [900, 330, 190],
        [955, 270, 250],
        [1010, 200, 320],
        [1065, 250, 270],
        [1120, 150, 380],
      ].map(([x, y, h]) => (
        <rect key={x} x={x} y={y} width="30" height={h} rx="15" />
      ))}
    </g>
  )
}

const PATTERNS = [Rings, Grid, Waves, Shards, Bars]

// ---- Headline wrapping ----------------------------------------------------
// SVG has no text wrapping, so lines are measured here. At 60px in Inter Black
// the average glyph is roughly 0.52em wide, and the headline column is
// SAFE.left..820 (the icon badge occupies the right). Three lines maximum —
// a fourth would collide with the kicker above or the crop below.
function wrapTitle(text, maxChars = 23, maxLines = 3) {
  const words = String(text).split(/\s+/)
  const lines = []
  let line = ''

  for (const word of words) {
    const candidate = line ? `${line} ${word}` : word
    if (candidate.length <= maxChars) {
      line = candidate
    } else {
      if (line) lines.push(line)
      line = word
      if (lines.length === maxLines) break
    }
  }
  if (line && lines.length < maxLines) lines.push(line)

  // If the title overflowed, trim the last line and mark the truncation.
  if (lines.length === maxLines) {
    const consumed = lines.join(' ').split(/\s+/).length
    if (consumed < words.length) {
      lines[maxLines - 1] = `${lines[maxLines - 1].replace(/[,:;]$/, '')}…`
    }
  }
  return lines
}

/**
 * @param {string} slug     unique per post — namespaces the SVG ids
 * @param {number} palette  index into PALETTES
 * @param {number} pattern  index into PATTERNS
 * @param {string} icon     glyph shown in the badge
 * @param {string} label    short kicker (the article's category)
 * @param {string} title    when supplied, the headline is drawn on the art.
 *                          Used for the article header, where the cover is
 *                          large; omitted on cards, where the real title sits
 *                          directly beneath the image and repeating it reads
 *                          as a mistake.
 */
export default function BlogCover({
  slug = 'post',
  palette = 0,
  pattern = 0,
  icon = '✦',
  label,
  title,
  className = '',
  rounded = 'rounded-2xl',
}) {
  const [deep, mid, glow] = PALETTES[palette % PALETTES.length]
  const Pattern = PATTERNS[pattern % PATTERNS.length]
  const gid = `cvg-${slug}`
  const sid = `cvs-${slug}`

  const lines = title ? wrapTitle(title) : []
  // Vertically centre the text block within the safe band.
  const blockHeight = (label ? 52 : 0) + lines.length * 72
  const startY = (SAFE.top + SAFE.bottom) / 2 - blockHeight / 2 + 34

  return (
    <svg
      viewBox="0 0 1200 630"
      className={`${className} ${rounded} block h-full w-full`}
      role="img"
      aria-label={title ? `Cover image for “${title}”` : `${label || 'Article'} cover image`}
      preserveAspectRatio="xMidYMid slice"
    >
      <defs>
        <linearGradient id={gid} x1="0" y1="1" x2="1" y2="0">
          <stop offset="0%" stopColor={deep} />
          <stop offset="62%" stopColor={mid} />
          <stop offset="100%" stopColor={glow} stopOpacity="0.75" />
        </linearGradient>
        {/* Darkens the left third so the headline always clears contrast,
            whatever the pattern is doing behind it. */}
        <linearGradient id={sid} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor={deep} stopOpacity="0.85" />
          <stop offset="60%" stopColor={deep} stopOpacity="0.2" />
          <stop offset="100%" stopColor={deep} stopOpacity="0" />
        </linearGradient>
      </defs>

      <rect width="1200" height="630" fill={`url(#${gid})`} />
      <Pattern glow={glow} />
      <rect width="1200" height="630" fill={`url(#${sid})`} />

      {/* Icon badge, right of the headline and inside the horizontal crop. */}
      <g opacity="0.9">
        <circle cx="925" cy="315" r="96" fill={glow} opacity="0.14" />
        <circle cx="925" cy="315" r="96" fill="none" stroke={glow} strokeWidth="2.5" opacity="0.45" />
        <text
          x="925"
          y="315"
          fontSize="96"
          fill={glow}
          textAnchor="middle"
          dominantBaseline="central"
          fontFamily="Inter, system-ui, sans-serif"
        >
          {icon}
        </text>
      </g>

      {label && (
        <text
          x={SAFE.left}
          y={startY - 34}
          fontSize="26"
          fill={glow}
          letterSpacing="5"
          fontWeight="700"
          fontFamily="Inter, system-ui, sans-serif"
        >
          {label.toUpperCase()}
        </text>
      )}

      {lines.map((line, i) => (
        <text
          key={i}
          x={SAFE.left}
          y={startY + 42 + i * 72}
          fontSize="60"
          fill="#ffffff"
          fontWeight="800"
          fontFamily="Inter, system-ui, sans-serif"
        >
          {line}
        </text>
      ))}
    </svg>
  )
}
