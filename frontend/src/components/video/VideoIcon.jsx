// ---------------------------------------------------------------------------
// The module's icon set.
//
// Inline SVG rather than an icon font or a package: the app ships no icon
// dependency today (the sidebar uses text glyphs), and adding one for nine
// shapes would be a bundle for a rounding error. Every path is stroked with
// `currentColor` so an icon takes the colour of whatever it sits in — a tinted
// tile, a button, a muted label — with no per-context variant.
//
// 24x24 viewBox, 1.75 stroke, round caps. Matching those three across the set
// is what makes the icons read as one family rather than as clip art.
// ---------------------------------------------------------------------------

const PATHS = {
  sparkle: 'M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM18.5 15.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z',
  grid: 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
  square: 'M4 5.5A1.5 1.5 0 015.5 4h13A1.5 1.5 0 0120 5.5v13a1.5 1.5 0 01-1.5 1.5h-13A1.5 1.5 0 014 18.5z',
  document: 'M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8zM14 3v5h5M9 13h6M9 17h4',
  film: 'M3 6a2 2 0 012-2h14a2 2 0 012 2v12a2 2 0 01-2 2H5a2 2 0 01-2-2zM3 9h4M3 15h4M17 9h4M17 15h4M8 4v16M16 4v16',
  music: 'M9 18V6l10-2v12M9 18a2.5 2.5 0 11-5 0 2.5 2.5 0 015 0zM19 16a2.5 2.5 0 11-5 0 2.5 2.5 0 015 0z',
  mic: 'M12 3a3 3 0 00-3 3v6a3 3 0 006 0V6a3 3 0 00-3-3zM5 11a7 7 0 0014 0M12 18v3M9 21h6',
  captions: 'M3 5.5A1.5 1.5 0 014.5 4h15A1.5 1.5 0 0121 5.5v10a1.5 1.5 0 01-1.5 1.5h-11L4 21v-4h-.5A1.5 1.5 0 013 15.5zM7 9.5h4M7 12.5h6M14 9.5h3M16 12.5h1',
  timeline: 'M3 6h18M3 12h18M3 18h18M7 4v4M14 10v4M10 16v4',
  layout: 'M3 5.5A1.5 1.5 0 014.5 4h15A1.5 1.5 0 0121 5.5v13a1.5 1.5 0 01-1.5 1.5h-15A1.5 1.5 0 013 18.5zM3 9h18M9 9v11',
  image: 'M3 5.5A1.5 1.5 0 014.5 4h15A1.5 1.5 0 0121 5.5v13a1.5 1.5 0 01-1.5 1.5h-15A1.5 1.5 0 013 18.5zM3 16l5-5 4 4 3-3 6 6M15.5 8.5h.01',
  scissors: 'M6.5 8.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5zM6.5 20.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5zM8.6 9.9L20 19M8.6 14.1L20 5',
  play: 'M8 5.5v13l11-6.5z',
  search: 'M11 18a7 7 0 100-14 7 7 0 000 14zM20 20l-4-4',
  plus: 'M12 5v14M5 12h14',
  trash: 'M4 7h16M9 7V5a1 1 0 011-1h4a1 1 0 011 1v2M6 7l1 13a1 1 0 001 1h8a1 1 0 001-1l1-13M10 11v6M14 11v6',
  copy: 'M9 9V5a1 1 0 011-1h9a1 1 0 011 1v9a1 1 0 01-1 1h-4M4 10a1 1 0 011-1h9a1 1 0 011 1v9a1 1 0 01-1 1H5a1 1 0 01-1-1z',
  pencil: 'M4 20h4l10.5-10.5a2.1 2.1 0 00-3-3L5 17v3zM14.5 6.5l3 3',
  dots: 'M12 6.5h.01M12 12h.01M12 17.5h.01',
  clock: 'M12 21a9 9 0 100-18 9 9 0 000 18zM12 7v5l3.5 2',
  check: 'M5 12.5l4.5 4.5L19 7.5',
  alert: 'M12 8v5M12 16.5h.01M10.3 3.9L2.4 17.5A1.9 1.9 0 004 20.4h16a1.9 1.9 0 001.6-2.9L13.7 3.9a1.9 1.9 0 00-3.4 0z',
}

export default function VideoIcon({ name, className = 'h-5 w-5', strokeWidth = 1.75 }) {
  const d = PATHS[name] || PATHS.square
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d={d} />
    </svg>
  )
}

// Tints for the icon tile on a tool card. Each is a soft background and a
// readable foreground drawn from Tailwind's palette — deliberately quiet, so
// the mint accent stays the module's primary and these only differentiate.
export const TINTS = {
  emerald: 'bg-emerald-50 text-emerald-700',
  teal: 'bg-teal-50 text-teal-700',
  sky: 'bg-sky-50 text-sky-700',
  indigo: 'bg-indigo-50 text-indigo-700',
  violet: 'bg-violet-50 text-violet-700',
  amber: 'bg-amber-50 text-amber-700',
  rose: 'bg-rose-50 text-rose-700',
  orange: 'bg-orange-50 text-orange-700',
  slate: 'bg-slate-100 text-slate-700',
}

export function tintClass(tint) {
  return TINTS[tint] || TINTS.slate
}
