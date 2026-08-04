import { useEffect, useRef, useState } from 'react'
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
// Covering changes what this IS, not just how it looks: an overlay over the
// workspace is a modal dialog, and is marked and behaves like one. Docked it
// is a region beside the canvas, and marking that as a dialog would announce a
// modal that never was one.
//
// Picking is immediate. The modal used elsewhere stages a choice behind a
// confirm button because it is answering "which image for this post?"; here the
// answer lands on the canvas where it can be moved, undone, or deleted, so a
// confirmation step would only add a click.
// ---------------------------------------------------------------------------

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'

/** Tailwind's `lg`, which is where the drawer stops covering and docks. */
function useDocked() {
  const query = '(min-width: 1024px)'
  const [docked, setDocked] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const mq = window.matchMedia(query)
    const onChange = (e) => setDocked(e.matches)
    setDocked(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])
  return docked
}

/** Keep Tab inside `root`, wrapping at both ends. */
function trapTab(e, root) {
  if (!root) return
  const items = [...root.querySelectorAll(FOCUSABLE)].filter((el) => el.offsetParent !== null)
  if (!items.length) return
  const first = items[0]
  const last = items[items.length - 1]
  const active = document.activeElement
  if (!root.contains(active)) {
    e.preventDefault()
    first.focus()
  } else if (e.shiftKey && active === first) {
    e.preventDefault()
    last.focus()
  } else if (!e.shiftKey && active === last) {
    e.preventDefault()
    first.focus()
  }
}

export default function MediaLibraryDrawer({ open, mode = 'add', onClose, onPick }) {
  const ref = useRef(null)
  const docked = useDocked()

  useEffect(() => {
    if (!open) return
    const onKey = (e) => {
      if (e.key === 'Escape') {
        // The editor also closes on Escape, from its own listener on window.
        // Both would answer this one keypress — dismissing the drawer would
        // take the editor and every unsaved edit down with it — and this
        // listener is on document, so it runs first and can stop that.
        e.stopPropagation()
        onClose()
        return
      }
      // While covering, everything behind this is hidden but still in the tab
      // order, so Tab would walk onto a canvas and toolbar the user cannot see.
      if (e.key === 'Tab' && !docked) trapTab(e, ref.current)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose, docked])

  // Opening a dialog should put the caret in it; docked, focus belongs to
  // whatever the user was doing on the canvas.
  useEffect(() => {
    if (open && !docked) ref.current?.focus()
  }, [open, docked])

  if (!open) return null

  return (
    <aside
      ref={ref}
      className="absolute inset-0 z-20 flex flex-col border-r border-line bg-surface lg:relative lg:inset-auto lg:z-auto lg:w-96 lg:shrink-0"
      aria-label="Media library"
      role={docked ? undefined : 'dialog'}
      aria-modal={docked ? undefined : true}
      tabIndex={docked ? undefined : -1}
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
