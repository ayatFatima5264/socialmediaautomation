import { PLATFORMS } from '../lib/constants'

// ---------------------------------------------------------------------------
// Platform marks.
//
// These were two-letter chips ("Ig", "Fb", "in") on a flat colour — legible,
// but they read as placeholders because that is exactly what they were (the
// old comment said as much).
//
// Depth comes from three cheap layers rather than raster art: a diagonal brand
// gradient, a top-light highlight, and an inset ring. That keeps them
// vector-crisp at any size, free of assets to load, and identical whether
// they render at 16px in a list or 40px in a toggle.
//
// Every gradient is the platform's own palette; nothing here invents a colour.
// ---------------------------------------------------------------------------

const MARKS = {
  instagram: {
    gradient: ['#FEDA75', '#D62976', '#4F5BD5'],
    // Outline glyph: rounded square, lens, flash dot.
    outline: {
      strokes: [
        'M8.6 3.9h6.8a4.7 4.7 0 0 1 4.7 4.7v6.8a4.7 4.7 0 0 1-4.7 4.7H8.6a4.7 4.7 0 0 1-4.7-4.7V8.6a4.7 4.7 0 0 1 4.7-4.7z',
        'M12 8.35a3.65 3.65 0 1 0 0 7.3 3.65 3.65 0 0 0 0-7.3z',
      ],
      dots: ['M16.75 6.3a1.05 1.05 0 1 0 0 2.1 1.05 1.05 0 0 0 0-2.1z'],
    },
  },
  facebook: {
    gradient: ['#4293FF', '#1877F2', '#0B5FCC'],
    glyph:
      'M13.5 20.5v-7.4h2.5l.37-2.9h-2.87V8.35c0-.84.23-1.41 1.44-1.41h1.53V4.35a20.6 20.6 0 0 0-2.23-.11c-2.21 0-3.72 1.35-3.72 3.83v2.13H8v2.9h2.52v7.4z',
  },
  twitter: {
    gradient: ['#4B5563', '#1F2937', '#000000'],
    glyph:
      'M16.6 4.9h2.42l-5.29 6.05 6.22 8.22h-4.87l-3.82-4.99-4.36 4.99H4.47l5.66-6.47L4.15 4.9h5l3.45 4.56zm-.85 12.83h1.34L8.6 6.23H7.16z',
  },
  linkedin: {
    gradient: ['#2D8FE0', '#0A66C2', '#04437F'],
    glyph:
      'M7.4 9.6H4.9v9.9h2.5zM6.15 5.1a1.45 1.45 0 1 0 0 2.9 1.45 1.45 0 0 0 0-2.9zM19.1 13.6c0-2.66-1.42-3.9-3.31-3.9-1.52 0-2.21.84-2.59 1.43V9.6h-2.47c.03.7 0 9.9 0 9.9h2.47v-5.53c0-.22.02-.44.08-.6.18-.44.58-.9 1.26-.9.89 0 1.25.68 1.25 1.67v5.36h2.47z',
  },
  threads: {
    gradient: ['#5B6472', '#374151', '#111827'],
    glyph:
      'M16.05 11.42a5.6 5.6 0 0 0-.24-.11c-.15-2.63-1.58-4.14-3.99-4.16h-.03c-1.44 0-2.64.62-3.38 1.74l1.33.91c.55-.84 1.41-1.01 2.05-1.01h.03c.79.01 1.39.24 1.78.68.28.33.47.79.57 1.37a10.4 10.4 0 0 0-2.29-.11c-2.3.13-3.78 1.47-3.68 3.34.05.94.52 1.75 1.33 2.29.68.44 1.56.66 2.48.61 1.21-.06 2.16-.52 2.82-1.37.5-.64.81-1.47.95-2.51.57.35.99.8 1.23 1.36.39.93.42 2.47-.83 3.72-1.1 1.09-2.42 1.57-4.4 1.58-2.2-.02-3.87-.72-4.95-2.1-1.02-1.29-1.54-3.11-1.56-5.81.02-2.7.54-4.52 1.56-5.81C7.91 5.13 9.58 4.43 11.78 4.41c2.22.02 3.92.73 5.05 2.12.56.68.98 1.54 1.26 2.55l1.56-.42c-.34-1.23-.87-2.29-1.59-3.16-1.45-1.78-3.58-2.7-6.28-2.72h-.01c-2.69.02-4.8.95-6.21 2.78-1.26 1.63-1.91 3.89-1.93 6.74v.01c.02 2.87.67 5.13 1.93 6.76 1.41 1.83 3.52 2.76 6.21 2.78h.01c2.39-.02 4.08-.64 5.47-2.03 1.81-1.82 1.76-4.1 1.16-5.5-.43-1-1.25-1.81-2.38-2.36zm-3.7 4.05c-1.02.06-2.08-.4-2.13-1.36-.04-.72.51-1.52 2.2-1.62l.41-.01c.62 0 1.19.06 1.72.17-.2 2.45-1.35 2.77-2.2 2.82z',
  },
  pinterest: {
    gradient: ['#F04A5E', '#E60023', '#A8001A'],
    glyph:
      'M12 4a8 8 0 0 0-2.92 15.45c-.07-.63-.13-1.6.03-2.28.14-.62.96-3.96.96-3.96s-.25-.49-.25-1.22c0-1.14.66-2 1.48-2 .7 0 1.04.53 1.04 1.16 0 .7-.45 1.75-.68 2.73-.19.82.41 1.48 1.22 1.48 1.46 0 2.58-1.54 2.58-3.77 0-1.97-1.42-3.35-3.45-3.35-2.35 0-3.73 1.76-3.73 3.58 0 .71.27 1.47.62 1.88.07.08.08.16.05.24l-.23.94c-.03.15-.12.18-.28.11-1.02-.48-1.66-1.97-1.66-3.18 0-2.59 1.88-4.96 5.42-4.96 2.84 0 5.05 2.02 5.05 4.73 0 2.83-1.78 5.1-4.25 5.1-.83 0-1.61-.43-1.88-.94l-.51 1.96c-.18.71-.68 1.6-1.02 2.14A8 8 0 1 0 12 4z',
  },
}

export default function PlatformIcon({ platform, size = 32, className = '' }) {
  const meta = PLATFORMS[platform] || { label: platform, color: '#6366f1', initial: '?' }
  const mark = MARKS[platform]

  // Unknown key falls back to the old chip, so adding a platform to PLATFORMS
  // without a mark here renders something rather than nothing.
  if (!mark) {
    return (
      <span
        title={meta.label}
        style={{ background: meta.color, width: size, height: size }}
        className={`inline-grid shrink-0 place-items-center rounded-lg text-xs font-bold text-white ${className}`}
      >
        {meta.initial}
      </span>
    )
  }

  // SVG ids are document-global, so several icons on one page would otherwise
  // share — and cross-wire — each other's gradients.
  const id = `pi-${platform}`
  const [from, mid, to] = mark.gradient

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      role="img"
      aria-label={meta.label}
      className={`shrink-0 ${className}`}
    >
      <title>{meta.label}</title>
      <defs>
        <linearGradient id={`${id}-g`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={from} />
          <stop offset="55%" stopColor={mid} />
          <stop offset="100%" stopColor={to} />
        </linearGradient>
        <linearGradient id={`${id}-hi`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#fff" stopOpacity="0.40" />
          <stop offset="55%" stopColor="#fff" stopOpacity="0.06" />
          <stop offset="100%" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
      </defs>

      <rect x="1" y="1" width="22" height="22" rx="6.5" fill={`url(#${id}-g)`} />
      <rect x="1" y="1" width="22" height="22" rx="6.5" fill={`url(#${id}-hi)`} />

      {mark.glyph ? (
        <path d={mark.glyph} fill="#fff" />
      ) : (
        <>
          {mark.outline.strokes.map((d) => (
            <path key={d} d={d} fill="none" stroke="#fff" strokeWidth="1.8" />
          ))}
          {mark.outline.dots.map((d) => (
            <path key={d} d={d} fill="#fff" />
          ))}
        </>
      )}

      {/* Inset ring — keeps the tile readable against any background. */}
      <rect
        x="1"
        y="1"
        width="22"
        height="22"
        rx="6.5"
        fill="none"
        stroke="#000"
        strokeOpacity="0.15"
      />
    </svg>
  )
}
