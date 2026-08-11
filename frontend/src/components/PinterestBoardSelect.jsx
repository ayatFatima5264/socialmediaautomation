import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../lib/api'

// Board picker for Pinterest. Every Pin must be saved to a board, so this is
// shown wherever a Pinterest post is composed, scheduled or configured.
//
// Boards are fetched live from Pinterest each time (the backend does no
// caching), so "Refresh" is simply loading again — a board created seconds ago
// shows up. Errors are shown inline in the app's own style; the backend already
// turns Pinterest's 401/403/429/5xx into user-safe sentences, so they're
// rendered as-is.
export default function PinterestBoardSelect({
  value,
  onChange,
  label = 'Pinterest board',
  // Extra hint under the control (e.g. "Used when a post doesn't pick one").
  help = null,
  disabled = false,
  // Called with the loaded boards, so a parent can pre-select a default.
  onLoaded = null,
}) {
  const [boards, setBoards] = useState(null) // null = loading
  const [defaultBoardId, setDefaultBoardId] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const data = await api.pinterestBoards()
      setBoards(data.boards || [])
      setDefaultBoardId(data.default_board_id || null)
      onLoaded?.(data)
    } catch (err) {
      setBoards([])
      setError(
        err instanceof ApiError
          ? err.message
          : 'Could not load your Pinterest boards.',
      )
    } finally {
      setBusy(false)
    }
    // onLoaded is intentionally excluded — a parent's inline callback would
    // otherwise re-run this on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const loading = boards === null
  const empty = !loading && boards.length === 0 && !error

  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <label className="label mb-0" htmlFor="pinterest-board">
          {label}
        </label>
        <button
          type="button"
          onClick={load}
          disabled={busy}
          className="text-xs text-muted underline-offset-2 hover:underline disabled:opacity-50"
        >
          {busy ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      <select
        id="pinterest-board"
        className="select"
        value={value || ''}
        disabled={disabled || loading || empty || !!error}
        onChange={(e) => onChange(e.target.value || null)}
      >
        <option value="">
          {loading ? 'Loading boards…' : 'Select a board…'}
        </option>
        {(boards || []).map((b) => (
          <option key={b.id} value={b.id}>
            {b.name}
            {b.privacy && b.privacy !== 'PUBLIC' ? ` (${b.privacy.toLowerCase()})` : ''}
            {b.id === defaultBoardId ? ' — default' : ''}
          </option>
        ))}
      </select>

      {error && <p className="mt-1.5 text-xs text-rose-600">{error}</p>}
      {empty && (
        <p className="mt-1.5 text-xs text-muted">
          No boards yet. Create one on Pinterest, then hit Refresh — every Pin
          must be saved to a board.
        </p>
      )}
      {help && !error && !empty && (
        <p className="mt-1.5 text-xs text-muted">{help}</p>
      )}
    </div>
  )
}
