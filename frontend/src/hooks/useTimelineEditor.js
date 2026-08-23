import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api.js'
import { useToast } from '../context/ToastContext.jsx'

// ---------------------------------------------------------------------------
// The editor's state.
//
// **The server owns the document.** Every edit is posted as an operation and
// the response replaces local state wholesale. This hook never computes the
// result of a trim or a split — the rules live in one place
// (app/services/video/timeline.py), and that is the same place the renderer
// reads, which is the entire reason the preview and the export cannot drift.
//
// The cost is a round trip per committed edit. It is paid deliberately, and it
// is not what the user feels: dragging is local and only the *release* posts.
// What never happens is a locally-computed document being kept.
//
// **Undo is a stack of documents, not a stack of inverse operations.**
// Reversing a split, a ripple delete and a reorder correctly would be three
// more rule implementations to keep in step with the server's. Swapping in a
// previous document is one PUT, and it cannot drift. The cost is memory, which
// for a JSON document of a few dozen clips is nothing.
//
// **Autosave only fires for things operations do not already save.** Every
// operation is persisted by the endpoint that applied it, so the timer here
// exists for the one case that is not an operation: an undo or redo, which is
// a document swap.
// ---------------------------------------------------------------------------

// How many steps back the user can go. Deep enough to cover a work session,
// shallow enough that the stack cannot grow without bound on a long edit.
const HISTORY_LIMIT = 50

// Long enough that a burst of undos collapses into one save, short enough that
// closing the tab straight after an undo does not lose it.
const AUTOSAVE_DELAY = 1200

export default function useTimelineEditor(projectId) {
  const toast = useToast()

  const [document, setDocument] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [selectedId, setSelectedId] = useState(null)
  const [saving, setSaving] = useState(false)
  const [savedAt, setSavedAt] = useState(null)

  // Undo/redo. `past` and `future` hold whole timeline documents.
  const [past, setPast] = useState([])
  const [future, setFuture] = useState([])

  // Set when an undo/redo has produced a document the server has not been told
  // about yet. Operations do their own saving, so this is the only thing the
  // autosave timer is for.
  const pendingRef = useRef(null)
  const revisionRef = useRef(null)

  const absorb = useCallback((data) => {
    setDocument(data)
    revisionRef.current = data.revision
    return data
  }, [])

  // ---- Load --------------------------------------------------------------

  const load = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    setError(null)
    try {
      absorb(await api.getTimeline(projectId))
      setPast([])
      setFuture([])
    } catch (err) {
      setError(err?.message || 'Could not open this project.')
    } finally {
      setLoading(false)
    }
  }, [projectId, absorb])

  useEffect(() => {
    load()
  }, [load])

  // ---- Operations --------------------------------------------------------

  /** Post one edit and take the server's document as the truth.
   *
   *  A refusal (an overlap, a split at the very edge, a locked clip) is
   *  reported and the local document is left exactly as it was — the server
   *  did not change anything either. */
  const apply = useCallback(
    async (operation, { quiet = false } = {}) => {
      if (!projectId || !document) return null

      const snapshot = document.timeline
      setBusy(true)
      try {
        const next = await api.timelineOp(projectId, {
          ...operation,
          expected_revision: revisionRef.current,
        })

        // Only push history once the server has accepted the edit, so a
        // refused operation does not leave an undo step that does nothing.
        setPast((stack) => [...stack, snapshot].slice(-HISTORY_LIMIT))
        setFuture([])
        pendingRef.current = null
        absorb(next)
        setSavedAt(new Date())

        if (next.affected_clip_ids?.length) {
          setSelectedId(next.affected_clip_ids[0])
        }
        return next
      } catch (err) {
        if (err?.status === 409) {
          toast.error('This project changed in another tab. Reloading it.')
          await load()
        } else if (!quiet) {
          toast.error(err?.message || 'That edit could not be applied.')
        }
        return null
      } finally {
        setBusy(false)
      }
    },
    [projectId, document, absorb, toast, load],
  )

  const addClip = useCallback(
    (trackId, clip, at) => apply({ op: 'add', track_id: trackId, clip, at }),
    [apply],
  )
  const moveClip = useCallback(
    (clipId, start) => apply({ op: 'move', clip_id: clipId, start }),
    [apply],
  )
  const trimClip = useCallback(
    (clipId, edge, to) => apply({ op: 'trim', clip_id: clipId, edge, to }),
    [apply],
  )
  const splitClip = useCallback(
    (clipId, at) => apply({ op: 'split', clip_id: clipId, at }),
    [apply],
  )
  const deleteClip = useCallback(
    (clipId, ripple = false) => apply({ op: 'delete', clip_id: clipId, ripple }),
    [apply],
  )
  const reorderTrack = useCallback(
    (trackId, clipIds) => apply({ op: 'reorder', track_id: trackId, clip_ids: clipIds }),
    [apply],
  )
  const updateClip = useCallback(
    (clipId, patch) => apply({ op: 'update', clip_id: clipId, patch }),
    [apply],
  )

  // ---- Undo / redo -------------------------------------------------------

  const swap = useCallback(
    (timeline) => {
      // Applied locally at once so the canvas responds immediately, then
      // written by the autosave timer. The server normalizes whatever it is
      // given, so an undo to a document written by an older build still lands
      // as something renderable.
      setDocument((current) => (current ? { ...current, timeline } : current))
      pendingRef.current = timeline
    },
    [],
  )

  const undo = useCallback(() => {
    setPast((stack) => {
      if (!stack.length) return stack
      const previous = stack[stack.length - 1]
      setFuture((forward) => [document.timeline, ...forward].slice(0, HISTORY_LIMIT))
      swap(previous)
      return stack.slice(0, -1)
    })
  }, [document, swap])

  const redo = useCallback(() => {
    setFuture((stack) => {
      if (!stack.length) return stack
      const [next, ...rest] = stack
      setPast((backward) => [...backward, document.timeline].slice(-HISTORY_LIMIT))
      swap(next)
      return rest
    })
  }, [document, swap])

  // ---- Autosave ----------------------------------------------------------

  const flush = useCallback(async () => {
    const pending = pendingRef.current
    if (!pending || !projectId) return
    pendingRef.current = null

    setSaving(true)
    try {
      const next = await api.saveTimeline(projectId, {
        timeline: pending,
        expected_revision: revisionRef.current,
        autosave: true,
      })
      absorb(next)
      setSavedAt(new Date())
    } catch (err) {
      if (err?.status === 409) {
        toast.error('This project changed in another tab. Reloading it.')
        await load()
      } else {
        // Put it back so the next tick tries again rather than losing the
        // edit silently.
        pendingRef.current = pending
        toast.error(err?.message || 'Could not save your changes.')
      }
    } finally {
      setSaving(false)
    }
  }, [projectId, absorb, toast, load])

  useEffect(() => {
    if (!pendingRef.current) return undefined
    const timer = setTimeout(flush, AUTOSAVE_DELAY)
    return () => clearTimeout(timer)
  }, [document, flush])

  // A pending save must survive the tab closing. `flush` is async and the
  // browser will not wait, but the request is dispatched, which is enough for
  // an edit already made.
  useEffect(() => {
    function onHide() {
      if (pendingRef.current) flush()
    }
    window.addEventListener('pagehide', onHide)
    return () => window.removeEventListener('pagehide', onHide)
  }, [flush])

  // ---- Derived -----------------------------------------------------------

  const tracks = document?.timeline?.tracks || []
  const selected =
    tracks
      .flatMap((track) => track.clips)
      .find((clip) => clip.id === selectedId) || null

  return {
    document,
    tracks,
    assets: document?.assets || [],
    placements: document?.placements || {},
    summary: document?.summary || null,
    canvas: document
      ? { width: document.width, height: document.height, fps: document.fps }
      : null,

    loading,
    error,
    busy,
    saving,
    savedAt,
    reload: load,

    selectedId,
    setSelectedId,
    selected,

    addClip,
    moveClip,
    trimClip,
    splitClip,
    deleteClip,
    reorderTrack,
    updateClip,

    undo,
    redo,
    canUndo: past.length > 0,
    canRedo: future.length > 0,
    flush,
  }
}
