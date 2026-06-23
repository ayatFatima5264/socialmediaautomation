// The backend stores/returns naive UTC timestamps (no timezone suffix).
// We parse them as UTC and render in the user's local timezone.

export function parseServerDate(s) {
  if (!s) return null
  const hasTz = /[zZ]|[+-]\d\d:?\d\d$/.test(s)
  return new Date(hasTz ? s : s + 'Z')
}

// Convert a local <input type="datetime-local"> value to a UTC ISO string.
export function localInputToISO(value) {
  if (!value) return null
  return new Date(value).toISOString()
}

export function formatDateTime(s) {
  const d = parseServerDate(s)
  if (!d) return '—'
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatRelative(s) {
  const d = parseServerDate(s)
  if (!d) return ''
  const diffMs = d.getTime() - Date.now()
  const mins = Math.round(diffMs / 60000)
  const abs = Math.abs(mins)
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
  if (abs < 60) return rtf.format(mins, 'minute')
  const hours = Math.round(mins / 60)
  if (Math.abs(hours) < 24) return rtf.format(hours, 'hour')
  return rtf.format(Math.round(hours / 24), 'day')
}
