import { useEffect } from 'react'
import MediaBrowser from './MediaBrowser.jsx'

// ---------------------------------------------------------------------------
// The Media Library as an editor tool.
//
// A docked drawer, not a covering modal, and that is the whole point: the
// canvas has to stay visible for an image to be dragged onto it. On a wide
// screen this is a column in the editor's workspace row, so opening it shrinks
// the canvas rather than hiding it — the stage measures itself with a
// ResizeObserver, so the artwork reflows on its own. Below `lg` there is not
// enough width for both, so it covers instead; dragging is not a phone gesture
// anyway, and tapping a tile does the same job.
//
// Picking is immediate. The modal used elsewhere stages a choice behind a
// confirm button because it is answering "which image for this post?"; here the
// answer lands on the canvas where it can be moved, undone, or deleted, so a
// confirmation step would only add a click.
// ---------------------------------------------------------------------------

export default function MediaLibraryDrawer({ open, mode = 'add', onClose, onPick }) {
  useEffect(() => {
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <aside
      className="absolute inset-0 z-20 flex flex-col border-r border-line bg-surface lg:relative lg:inset-auto lg:z-auto lg:w-96 lg:shrink-0"
      aria-label="Media library"
    >
      <div className="flex shrink-0 items-center gap-2 border-b border-line px-3 py-2">
        <span className="text-sm font-bold">
          {mode === 'replace' ? 'Replace with…' : 'Media Library'}
        </span>
        <span className="hidden text-[11px] text-muted lg:inline">
          {mode === 'replace' ? 'Pick a replacement' : 'Click or drag onto the canvas'}
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close media library"
          className="btn btn-ghost btn-sm ml-auto shrink-0"
        >
          ✕
        </button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col p-3">
        <MediaBrowser
          manage
          draggableTiles={mode !== 'replace'}
          onSelect={onPick}
        />
      </div>
    </aside>
  )
}
