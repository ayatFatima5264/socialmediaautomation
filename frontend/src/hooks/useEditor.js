import { useCallback, useMemo, useRef, useState } from 'react'
import * as doc from '../lib/brandKit/editor/document'

// ---------------------------------------------------------------------------
// Editor state: the document, the selection, and undo/redo.
//
// History keeps whole documents rather than inverse operations. Documents are
// small (a few dozen plain objects) and every operation is already pure, so
// snapshotting is both cheaper to write and impossible to get wrong — there is
// no per-operation undo to forget when a new tool is added.
//
// Drag and resize would otherwise push a snapshot per mousemove and fill the
// stack with hundreds of intermediate states, so continuous gestures commit
// once: `beginGesture()` captures the pre-drag document, live updates bypass
// history, and `endGesture()` pushes the single before/after pair.
// ---------------------------------------------------------------------------

const HISTORY_LIMIT = 60

export default function useEditor(initialDocument) {
  const [present, setPresent] = useState(initialDocument)
  const [past, setPast] = useState([])
  const [future, setFuture] = useState([])
  const [selectedId, setSelectedId] = useState(null)

  // Snapshot taken at the start of a gesture, committed at the end.
  const gestureStart = useRef(null)

  const commit = useCallback((next) => {
    setPresent((current) => {
      const value = typeof next === 'function' ? next(current) : next
      if (value === current) return current
      setPast((p) => [...p, current].slice(-HISTORY_LIMIT))
      setFuture([]) // a new edit invalidates the redo branch
      return value
    })
  }, [])

  // Live update with no history entry — used during a gesture.
  const preview = useCallback((next) => {
    setPresent((current) => (typeof next === 'function' ? next(current) : current))
  }, [])

  const beginGesture = useCallback(() => {
    setPresent((current) => {
      gestureStart.current = current
      return current
    })
  }, [])

  const endGesture = useCallback(() => {
    const before = gestureStart.current
    gestureStart.current = null
    if (!before) return
    setPresent((current) => {
      // Nothing actually moved — don't add a no-op the user has to undo past.
      if (current === before) return current
      setPast((p) => [...p, before].slice(-HISTORY_LIMIT))
      setFuture([])
      return current
    })
  }, [])

  const undo = useCallback(() => {
    setPast((p) => {
      if (!p.length) return p
      const previous = p[p.length - 1]
      setPresent((current) => {
        setFuture((f) => [current, ...f])
        return previous
      })
      return p.slice(0, -1)
    })
  }, [])

  const redo = useCallback(() => {
    setFuture((f) => {
      if (!f.length) return f
      const next = f[0]
      setPresent((current) => {
        setPast((p) => [...p, current].slice(-HISTORY_LIMIT))
        return next
      })
      return f.slice(1)
    })
  }, [])

  // ---- Operations, each wrapping a pure document function ----------------
  const ops = useMemo(
    () => ({
      addLayer: (layer) => {
        commit((d) => doc.addLayer(d, layer))
        setSelectedId(layer.id)
      },
      updateLayer: (id, patch) => commit((d) => doc.updateLayer(d, id, patch)),
      // Geometry changes during a drag: visible immediately, one history entry.
      dragLayer: (id, patch) => preview((d) => doc.updateLayer(d, id, patch)),
      removeLayer: (id) => {
        commit((d) => doc.removeLayer(d, id))
        setSelectedId((s) => (s === id ? null : s))
      },
      duplicateLayer: (id) => commit((d) => doc.duplicateLayer(d, id)),
      bringForward: (id) => commit((d) => doc.bringForward(d, id)),
      sendBackward: (id) => commit((d) => doc.sendBackward(d, id)),
      setSize: (size) => commit((d) => ({ ...d, size })),
      // Swap the whole document in one history step. Used by AI edits, which
      // may touch many layers at once: without this a single instruction
      // would need as many undos as it made changes.
      replaceDocument: (next) => commit(() => next),
    }),
    [commit, preview],
  )

  const selected = useMemo(
    () => present.layers.find((l) => l.id === selectedId) || null,
    [present, selectedId],
  )

  return {
    document: present,
    selected,
    selectedId,
    select: setSelectedId,
    ...ops,
    beginGesture,
    endGesture,
    undo,
    redo,
    canUndo: past.length > 0,
    canRedo: future.length > 0,
  }
}
