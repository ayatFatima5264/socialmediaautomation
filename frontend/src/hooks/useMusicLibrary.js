import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api.js'
import { useToast } from '../context/ToastContext.jsx'

// ---------------------------------------------------------------------------
// The Music Library's data.
//
// Searching is debounced because a text search the local catalogue answers
// thinly is forwarded to Openverse by the server — so every keystroke would be
// a third-party request, not just a database query.
//
// The last request wins. Typing "cinem" then "cinematic" can return in either
// order, and a slow earlier response overwriting a newer one is the bug this
// counter exists to prevent.
// ---------------------------------------------------------------------------

const PAGE_SIZE = 40

export default function useMusicLibrary({ search, mood, genre, duration, source }) {
  const toast = useToast()

  const [tracks, setTracks] = useState([])
  const [total, setTotal] = useState(0)
  const [facets, setFacets] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [uploading, setUploading] = useState(false)
  const [busyId, setBusyId] = useState(null)

  const requestId = useRef(0)

  const loadFacets = useCallback(async () => {
    try {
      setFacets(await api.musicFacets())
    } catch {
      // The filter row is an aid, not the page. Losing it should not blank
      // the results the user came for.
      setFacets(null)
    }
  }, [])

  const load = useCallback(async () => {
    const ticket = ++requestId.current
    setLoading(true)
    setError('')
    try {
      const data = await api.musicLibrary({
        search,
        mood,
        genre,
        duration,
        source,
        limit: PAGE_SIZE,
      })
      if (ticket !== requestId.current) return
      setTracks(data.items || [])
      setTotal(data.total ?? (data.items || []).length)
    } catch (err) {
      if (ticket !== requestId.current) return
      setError(err?.message || 'Could not load the music library.')
      setTracks([])
    } finally {
      if (ticket === requestId.current) setLoading(false)
    }
  }, [search, mood, genre, duration, source])

  useEffect(() => {
    loadFacets()
  }, [loadFacets])

  useEffect(() => {
    // Only the text search is debounced. A filter click is a deliberate act and
    // should feel immediate.
    if (!search) {
      load()
      return undefined
    }
    const timer = window.setTimeout(load, 350)
    return () => window.clearTimeout(timer)
  }, [load, search])

  const upload = useCallback(
    async (file, fields) => {
      if (!file) return null
      setUploading(true)
      try {
        const track = await api.uploadMusic(file, fields)
        toast.success(`Added “${track.title}” to your library.`)
        await Promise.all([load(), loadFacets()])
        return track
      } catch (err) {
        toast.error(err?.message || 'Could not upload that track.')
        return null
      } finally {
        setUploading(false)
      }
    },
    [load, loadFacets, toast],
  )

  const addToProject = useCallback(
    async (track, projectId) => {
      setBusyId(track.id)
      try {
        await api.addMusicToProject(track.id, { project_id: projectId })
        toast.success(`“${track.title}” added to the project.`)
        return true
      } catch (err) {
        // A licence refusal is a 403 with the server's own sentence. Showing it
        // verbatim matters: the rule is the server's, and paraphrasing a
        // licensing decision in the UI is how the two drift apart.
        toast.error(err?.message || 'Could not add that track.')
        return false
      } finally {
        setBusyId(null)
      }
    },
    [toast],
  )

  const remove = useCallback(
    async (track) => {
      setBusyId(track.id)
      try {
        await api.deleteMusicTrack(track.id)
        setTracks((current) => current.filter((row) => row.id !== track.id))
        setTotal((current) => Math.max(0, current - 1))
        loadFacets()
        return true
      } catch (err) {
        toast.error(err?.message || 'Could not delete that track.')
        return false
      } finally {
        setBusyId(null)
      }
    },
    [loadFacets, toast],
  )

  return {
    tracks,
    total,
    facets,
    loading,
    error,
    uploading,
    busyId,
    reload: load,
    upload,
    addToProject,
    remove,
  }
}
