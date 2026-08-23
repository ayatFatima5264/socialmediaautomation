// ---------------------------------------------------------------------------
// Display helpers shared across the module.
//
// Kept out of the components so the projects grid, the Overview's recent
// strip and the project page cannot disagree about what "2 minutes ago" or
// "0:07" looks like — three implementations of a duration formatter is three
// chances to be off by one.
// ---------------------------------------------------------------------------

/** Seconds as m:ss, or h:mm:ss past an hour. */
export function formatDuration(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60

  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

const RELATIVE_STEPS = [
  [60, 'second'],
  [60, 'minute'],
  [24, 'hour'],
  [7, 'day'],
  [4.348, 'week'],
  [12, 'month'],
]

/** "just now", "5 minutes ago", "3 days ago".
 *
 *  Uses Intl.RelativeTimeFormat so the wording follows the browser's locale
 *  rather than being hardcoded English — the app already has Urdu-speaking
 *  users and a hand-rolled "ago" would only ever be one language. */
export function relativeTime(value) {
  if (!value) return 'never'

  const then = new Date(value)
  if (Number.isNaN(then.getTime())) return 'never'

  let delta = (then.getTime() - Date.now()) / 1000
  if (Math.abs(delta) < 45) return 'just now'

  let unit = 'second'
  for (const [size, nextUnit] of RELATIVE_STEPS) {
    if (Math.abs(delta) < size) break
    delta /= size
    unit = nextUnit
  }

  try {
    return new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(
      Math.round(delta),
      unit,
    )
  } catch {
    return 'recently'
  }
}

/** Bytes as KB / MB / GB, one decimal past a megabyte. */
export function formatBytes(bytes) {
  const value = Number(bytes) || 0
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`
  if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`
  return `${(value / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

// A readable name for a platform key. The authoritative list comes from the
// server (`/api/video/capabilities`), and the UI renders whatever it is given
// — this is only the fallback for a card rendered before that request lands,
// and for a key the server added that this build has not seen.
const PLATFORM_LABELS = {
  youtube: 'YouTube',
  youtube_shorts: 'YouTube Shorts',
  tiktok: 'TikTok',
  instagram_reels: 'Instagram Reels',
  instagram_post: 'Instagram Post',
  facebook: 'Facebook',
  custom: 'Custom',
}

export function platformLabel(key) {
  if (PLATFORM_LABELS[key]) return PLATFORM_LABELS[key]
  // An unknown key becomes "Youtube Live" rather than "youtube_live", so a
  // platform added server-side still reads as a name.
  return String(key || '')
    .split('_')
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(' ')
}

// Project status, styled the way the rest of the app styles status (see
// STATUS_STYLES in lib/constants.js). The vocabulary matches
// PROJECT_STATUSES in app/models/video_project.py.
export const STATUS_STYLES = {
  draft: {
    label: 'Draft',
    className: 'border border-line bg-inset text-muted',
  },
  processing: {
    label: 'Rendering',
    className: 'border border-amber-300 bg-amber-50 text-amber-700',
  },
  completed: {
    label: 'Ready',
    className: 'badge-accent',
  },
  failed: {
    label: 'Failed',
    className: 'border border-rose-300 bg-rose-50 text-rose-700',
  },
}

/** The status filter's options, including "all". */
export const STATUS_FILTERS = [
  { value: '', label: 'All statuses' },
  { value: 'draft', label: 'Draft' },
  { value: 'processing', label: 'Rendering' },
  { value: 'completed', label: 'Ready' },
  { value: 'failed', label: 'Failed' },
]
