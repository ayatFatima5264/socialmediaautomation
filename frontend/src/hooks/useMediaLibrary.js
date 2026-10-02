import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api.js'
import { useToast } from '../context/ToastContext.jsx'

// ---------------------------------------------------------------------------
// The Media Library's state.
//
// Same three rules `useVideoProjects` follows, for the same reasons:
//
//   * **A stale response never wins.** Filters change faster than requests come
//     back, and a sequence guard is what stops the answer to "images" landing
//     after the user has already switched to "music". An AbortController would
//     also work; a counter is simpler and does not depend on the fetch being
//     cancellable.
//   * **Loading errors stay on screen; mutation errors toast.** A failed load
//     needs an explanation next to the empty grid. A failed rename needs to be
//     noticed and then forgotten.
//   * **Nothing is optimistic.** A file appears in the grid when the server has
//     stored it. An upload that failed must not sit there looking available.
//
// The one thing specific to this hook: **delete is a two-step conversation.**
// The server answers 409 with the list of projects using a file, and `remove`
// surfaces that as a returned conflict rather than throwing, so the page can
// show the list and offer "delete anyway" instead of a toast the user cannot
// act on.
// ---------------------------------------------------------------------------

const PAGE_SIZE = 48

export default function useMediaLibrary({
  filter = 'all',
  search = '',
  projectId = null,
  sort = 'newest',
} = {}) {
  const toast = useToast()

  const [items, setItems] = useState([])
  const [filters, setFilters] = useState([])
  const [total, setTotal] = useState(0)
  const [storageBytes, setStorageBytes] = useState(0)

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [uploading, setUploading] = useState(false)

  const seqRef = useRef(0)

  const load = useCallback(async () => {
    const seq = ++seqRef.current
    setLoading(true)
    setError(null)
    try {
      const data = await api.mediaLibrary({
        filter,
        search: search || undefined,
        projectId: projectId || undefined,
        sort,
        limit: PAGE_SIZE,
      })
      if (seq !== seqRef.current) return // a newer request already answered
      setItems(data.items || [])
      setFilters(data.filters || [])
      setTotal(data.total || 0)
      setStorageBytes(data.storage_bytes || 0)
    } catch (err) {
      if (seq !== seqRef.current) return
      setError(err?.message || 'Could not load your media.')
    } finally {
      if (seq === seqRef.current) setLoading(false)
    }
  }, [filter, search, projectId, sort])

  // Debounced only while typing. Switching a filter tab should feel instant.
  useEffect(() => {
    const timer = setTimeout(load, search ? 300 : 0)
    return () => clearTimeout(timer)
  }, [load, search])

  // ---- Mutations ---------------------------------------------------------

  // `kind` is passed through only when a caller names one. This hook is the
  // Media Library's own upload path, and the screen has no "what is this for"
  // control — the user drops in a file, not a file *as a clip* — so the server
  // infers the kind from the media type. It used to default to 'upload', which
  // is what put every photo and every clip into the same bucket as an MP3: they
  // appeared under the Audio tab and under neither Images nor Videos.
  const upload = useCallback(
    async (files, { kind } = {}) => {
      const list = Array.from(files || [])
      if (!list.length) return []

      setUploading(true)
      const stored = []
      const failed = []

      // Sequential, not Promise.all. These are video files on somebody's home
      // connection; eight parallel uploads share the same pipe and all of them
      // finish later than the first would have on its own.
      for (const file of list) {
        try {
          stored.push(await api.uploadVideoMedia(file, { kind }))
        } catch (err) {
          failed.push(`${file.name}: ${err?.message || 'could not be uploaded'}`)
        }
      }
      setUploading(false)

      // Reported separately so one rejected file does not read as "the upload
      // failed" when the other seven worked.
      if (stored.length) {
        toast.success(
          stored.length === 1
            ? `Added “${stored[0].title}”.`
            : `Added ${stored.length} files.`,
        )
      }
      for (const message of failed) toast.error(message)

      if (stored.length) await load()
      return stored
    },
    [load, toast],
  )

  const rename = useCallback(
    async (item, title) => {
      setBusyId(item.id)
      try {
        const updated = await api.renameMedia(item.id, title)
        setItems((current) =>
          current.map((row) => (row.id === item.id ? { ...row, ...updated } : row)),
        )
        toast.success(`Renamed to “${updated.title}”.`)
        return updated
      } catch (err) {
        toast.error(err?.message || 'Could not rename that file.')
        throw err
      } finally {
        setBusyId(null)
      }
    },
    [toast],
  )

  const attach = useCallback(
    async (item, targetProjectId) => {
      setBusyId(item.id)
      try {
        const updated = await api.attachMedia(item.id, targetProjectId)
        setItems((current) =>
          current.map((row) => (row.id === item.id ? { ...row, ...updated } : row)),
        )
        return updated
      } catch (err) {
        toast.error(err?.message || 'Could not add that file to the project.')
        throw err
      } finally {
        setBusyId(null)
      }
    },
    [toast],
  )

  const detach = useCallback(
    async (item) => {
      setBusyId(item.id)
      try {
        const updated = await api.detachMedia(item.id)
        setItems((current) =>
          current.map((row) => (row.id === item.id ? { ...row, ...updated } : row)),
        )
        toast.success('Removed from the project. The file is still in your library.')
        return updated
      } catch (err) {
        toast.error(err?.message || 'Could not remove that file from the project.')
        throw err
      } finally {
        setBusyId(null)
      }
    },
    [toast],
  )

  /** Delete a file.
   *
   *  Returns `{ deleted: true }`, or `{ deleted: false, conflict: message }`
   *  when projects are using it. The conflict is returned rather than thrown
   *  because it is not a failure — it is the server asking a question, and the
   *  caller's job is to put it to the user and call again with `force`. */
  const remove = useCallback(
    async (item, { force = false } = {}) => {
      setBusyId(item.id)
      try {
        await api.deleteMedia(item.id, { force })
        setItems((current) => current.filter((row) => row.id !== item.id))
        setTotal((current) => Math.max(0, current - 1))
        toast.success(`Deleted “${item.title}”.`)
        return { deleted: true }
      } catch (err) {
        if (err?.status === 409) return { deleted: false, conflict: err.message }
        toast.error(err?.message || 'Could not delete that file.')
        throw err
      } finally {
        setBusyId(null)
      }
    },
    [toast],
  )

  return {
    items,
    filters,
    total,
    storageBytes,
    loading,
    error,
    busyId,
    uploading,
    reload: load,
    upload,
    rename,
    attach,
    detach,
    remove,
  }
}
