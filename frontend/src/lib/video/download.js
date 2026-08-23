// ---------------------------------------------------------------------------
// Saving a Blob to the user's disk.
//
// The download endpoints need the bearer token, so a plain `<a href>` cannot
// reach them — the browser would send an unauthenticated request and get a 401.
// The file is fetched with the token, turned into an object URL, and clicked.
//
// The object URL is revoked afterwards. Without that, every download pins its
// whole file in memory for the life of the page, which for a handful of WAVs is
// tens of megabytes the tab never gives back.
// ---------------------------------------------------------------------------

export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  // Must be in the document for the click to be honoured in Firefox.
  document.body.appendChild(link)
  link.click()
  link.remove()
  // Deferred: revoking synchronously can cancel the download in Safari, which
  // has not finished reading the URL when click() returns.
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

/** A filesystem-safe filename stem from a title. Never empty. */
export function safeFilename(title, fallback = 'voiceover') {
  const cleaned = String(title || '')
    .replace(/[^\w\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
    .slice(0, 60)
  return cleaned || fallback
}
