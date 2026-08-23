import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api.js'
import { useToast } from '../context/ToastContext.jsx'

// ---------------------------------------------------------------------------
// The projects list, and the four things you can do to a project.
//
// Every action calls the real endpoint and then reconciles local state from
// what the server returned — never from what the client hoped would happen.
// The one exception is delete, where the row is removed locally after a 204
// because there is nothing left to read back.
//
// Search is debounced and filtering happens server-side. The list is paged in
// SQL, so a client-side `.filter()` over a full download would be wrong as
// soon as an account has more projects than one page.
//
// A request whose response arrives after a newer one is discarded (`seqRef`).
// Typing "coffee" fires five requests and they do not necessarily come back in
// order; without this the grid can settle on the results for "coff".
// ---------------------------------------------------------------------------

const PAGE_SIZE = 24

export default function useVideoProjects({ search = '', platform = '', status = '' } = {}) {
  const [projects, setProjects] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busyId, setBusyId] = useState(null)

  const toast = useToast()
  const seqRef = useRef(0)

  const load = useCallback(async () => {
    const seq = ++seqRef.current
    setLoading(true)
    setError(null)
    try {
      const data = await api.listVideoProjects({
        search: search || undefined,
        platform: platform || undefined,
        status: status || undefined,
        limit: PAGE_SIZE,
      })
      if (seq !== seqRef.current) return // a newer request already answered
      setProjects(data.projects || [])
      setTotal(data.total || 0)
    } catch (err) {
      if (seq !== seqRef.current) return
      setError(err?.message || 'Could not load your projects.')
    } finally {
      if (seq === seqRef.current) setLoading(false)
    }
  }, [search, platform, status])

  // 300ms is long enough that a typed word is one request and short enough
  // that the grid does not feel like it is lagging behind the field.
  useEffect(() => {
    const timer = setTimeout(load, search ? 300 : 0)
    return () => clearTimeout(timer)
  }, [load, search])

  const create = useCallback(
    async (body) => {
      const project = await api.createVideoProject(body)
      // Prepended rather than refetched: the new project sorts first by
      // updated_at anyway, and a refetch would drop the user's scroll.
      setProjects((current) => [project, ...current])
      setTotal((current) => current + 1)
      return project
    },
    [],
  )

  const rename = useCallback(
    async (project, name) => {
      setBusyId(project.id)
      try {
        const updated = await api.renameVideoProject(project.id, name)
        setProjects((current) =>
          current.map((p) => (p.id === project.id ? { ...p, ...updated } : p)),
        )
        toast.success(`Renamed to “${updated.name}”.`)
        return updated
      } catch (err) {
        toast.error(err?.message || 'Could not rename that project.')
        throw err
      } finally {
        setBusyId(null)
      }
    },
    [toast],
  )

  const duplicate = useCallback(
    async (project) => {
      setBusyId(project.id)
      try {
        const copy = await api.duplicateVideoProject(project.id)
        setProjects((current) => [copy, ...current])
        setTotal((current) => current + 1)
        toast.success(`Duplicated as “${copy.name}”.`)
        return copy
      } catch (err) {
        toast.error(err?.message || 'Could not duplicate that project.')
        throw err
      } finally {
        setBusyId(null)
      }
    },
    [toast],
  )

  const remove = useCallback(
    async (project) => {
      setBusyId(project.id)
      try {
        await api.deleteVideoProject(project.id)
        setProjects((current) => current.filter((p) => p.id !== project.id))
        setTotal((current) => Math.max(0, current - 1))
        toast.success(`Deleted “${project.name}”.`)
      } catch (err) {
        toast.error(err?.message || 'Could not delete that project.')
        throw err
      } finally {
        setBusyId(null)
      }
    },
    [toast],
  )

  return {
    projects,
    total,
    loading,
    error,
    busyId,
    reload: load,
    create,
    rename,
    duplicate,
    remove,
  }
}
