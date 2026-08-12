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
  // One-line variant for the account card, where a full-size labelled control
  // would make that card taller than the others sharing its grid row.
  compact = false,
  // Called with the loaded boards, so a parent can pre-select a default.
  onLoaded = null,
}) {
  const [boards, setBoards] = useState(null) // null = loading
  const [defaultBoardId, setDefaultBoardId] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  // Creating a board in-app is not a convenience: boards don't cross Pinterest
  // environments, so a Sandbox connection starts with none and Pinterest's own
  // website can't make one there.
  const [newName, setNewName] = useState(null) // null = form closed
  const [creating, setCreating] = useState(false)

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

  async function createBoard() {
    const name = (newName || '').trim()
    if (!name || creating) return
    setCreating(true)
    setError(null)
    try {
      const board = await api.createPinterestBoard(name)
      setBoards((list) => [...(list || []), board])
      setNewName(null)
      onChange(board.id) // a board made right now is the one they meant
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Could not create the board.',
      )
    } finally {
      setCreating(false)
    }
  }

  const loading = boards === null
  const empty = !loading && boards.length === 0 && !error

  // The inline "new board" form, shared by both layouts.
  const createForm = newName !== null && (
    <div className="mt-1.5 flex items-center gap-1.5">
      <input
        autoFocus
        className="input py-1 text-xs"
        value={newName}
        maxLength={180}
        placeholder="Board name"
        disabled={creating}
        onChange={(e) => setNewName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            createBoard()
          }
          if (e.key === 'Escape') setNewName(null)
        }}
      />
      <button
        type="button"
        onClick={createBoard}
        disabled={creating || !newName.trim()}
        className="btn btn-primary btn-sm shrink-0 disabled:opacity-50"
      >
        {creating ? 'Creating…' : 'Create'}
      </button>
      <button
        type="button"
        onClick={() => setNewName(null)}
        disabled={creating}
        className="btn btn-ghost btn-sm shrink-0"
      >
        Cancel
      </button>
    </div>
  )

  const newBoardButton = newName === null && !loading && !error && (
    <button
      type="button"
      onClick={() => setNewName('')}
      className="shrink-0 text-xs text-accent underline-offset-2 hover:underline"
    >
      + New board
    </button>
  )

  const options = (
    <>
      <option value="">{loading ? 'Loading boards…' : 'Select a board…'}</option>
      {(boards || []).map((b) => (
        <option key={b.id} value={b.id}>
          {b.name}
          {b.privacy && b.privacy !== 'PUBLIC' ? ` (${b.privacy.toLowerCase()})` : ''}
          {/* Marking the default is only useful where a post picks a board.
              On the account card this control *is* the default, so the suffix
              would be redundant — and it truncates the name it follows. */}
          {!compact && b.id === defaultBoardId ? ' — default' : ''}
        </option>
      ))}
    </>
  )
  const isDisabled = disabled || loading || empty || !!error
  const onSelect = (e) => onChange(e.target.value || null)
  const emptyHint = 'No boards yet — create one to publish Pins.'

  // Compact: one row that matches the surrounding detail lines, so adding this
  // control doesn't make its card taller than the others in the grid row.
  if (compact) {
    return (
      <div className="space-y-1">
        <div className="flex items-center justify-between gap-2">
          <span className="shrink-0 text-xs text-muted">{label}</span>
          <div className="flex min-w-0 flex-1 items-center justify-end gap-1">
            <select
              aria-label={label}
              className="select max-w-[190px] truncate py-1 text-xs"
              value={value || ''}
              disabled={isDisabled}
              onChange={onSelect}
            >
              {options}
            </select>
            <button
              type="button"
              onClick={load}
              disabled={busy}
              title="Refresh boards"
              aria-label="Refresh boards"
              className="shrink-0 rounded-md px-1.5 py-1 text-xs text-muted hover:bg-inset disabled:opacity-50"
            >
              {busy ? '…' : '↻'}
            </button>
          </div>
        </div>
        {error && <p className="text-right text-xs text-rose-600">{error}</p>}
        {empty && newName === null && (
          <p className="text-right text-xs text-muted">{emptyHint}</p>
        )}
        {createForm}
        {newName === null && !loading && (
          <div className="flex justify-end">{newBoardButton}</div>
        )}
      </div>
    )
  }

  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <label className="label mb-0" htmlFor="pinterest-board">
          {label}
        </label>
        <div className="flex items-center gap-3">
          {newBoardButton}
          <button
            type="button"
            onClick={load}
            disabled={busy}
            className="text-xs text-muted underline-offset-2 hover:underline disabled:opacity-50"
          >
            {busy ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      <select
        id="pinterest-board"
        className="select"
        value={value || ''}
        disabled={isDisabled}
        onChange={onSelect}
      >
        {options}
      </select>

      {createForm}

      {error && <p className="mt-1.5 text-xs text-rose-600">{error}</p>}
      {empty && newName === null && (
        <p className="mt-1.5 text-xs text-muted">
          No boards yet — every Pin must be saved to one. Use “+ New board”
          above to make your first.
        </p>
      )}
      {help && !error && !empty && (
        <p className="mt-1.5 text-xs text-muted">{help}</p>
      )}
    </div>
  )
}
