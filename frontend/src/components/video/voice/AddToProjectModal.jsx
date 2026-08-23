import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../../lib/api.js'
import { useToast } from '../../../context/ToastContext.jsx'
import { platformLabel } from '../../../lib/video/format.js'
import Modal from '../Modal.jsx'
import Spinner from '../../Spinner.jsx'

// ---------------------------------------------------------------------------
// "Add to Project" — pick which one.
//
// The list is loaded when the dialog opens rather than kept on the page: Voice
// Studio works with no project at all, and fetching a project list on every
// visit would be a request for something most sessions never use.
//
// A user with no projects gets a link to create one instead of an empty box.
// That is the case this dialog is most likely to hit, because Voice Studio is
// the tool people reach for before they have started a video.
// ---------------------------------------------------------------------------

export default function AddToProjectModal({ open, take, onClose, onAttach }) {
  const toast = useToast()
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busyId, setBusyId] = useState(null)

  useEffect(() => {
    if (!open) return undefined
    let cancelled = false

    setLoading(true)
    setError(null)
    api
      .listVideoProjects({ limit: 100 })
      .then((data) => {
        if (!cancelled) setProjects(data.projects || [])
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || 'Could not load your projects.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [open])

  async function attach(project) {
    setBusyId(project.id)
    try {
      await onAttach(take, project.id)
      toast.success(`Added to “${project.name}”.`)
      onClose()
    } catch {
      // The hook has already reported it; keep the dialog open so another
      // project can be tried.
      setBusyId(null)
    }
  }

  return (
    <Modal
      open={open}
      title="Add to project"
      description="The voice-over stays in your library either way — this makes it available inside the project too."
      onClose={onClose}
      maxWidth="max-w-lg"
      footer={
        <button className="btn btn-ghost" onClick={onClose}>
          Cancel
        </button>
      }
    >
      {loading && (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 3 }).map((_, index) => (
            <div key={index} className="skeleton h-14" />
          ))}
        </div>
      )}

      {!loading && error && <p className="text-sm text-rose-600">{error}</p>}

      {!loading && !error && projects.length === 0 && (
        <div className="panel flex flex-col items-center gap-3 p-6 text-center">
          <p className="text-sm text-muted">
            You have no video projects yet. Create one and this voice-over can go
            straight into it.
          </p>
          <Link to="/video/create" className="btn btn-primary btn-sm" onClick={onClose}>
            Create a project
          </Link>
        </div>
      )}

      {!loading && !error && projects.length > 0 && (
        <ul className="flex max-h-80 flex-col gap-2 overflow-y-auto">
          {projects.map((project) => {
            const already = take?.project_id === project.id
            return (
              <li key={project.id}>
                <button
                  type="button"
                  onClick={() => attach(project)}
                  disabled={busyId !== null || already}
                  className="panel flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:border-accent-line disabled:opacity-60"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium text-body">
                      {project.name}
                    </span>
                    <span className="block text-xs text-muted">
                      {platformLabel(project.platform)} · {project.aspect_ratio}
                    </span>
                  </span>
                  {busyId === project.id && <Spinner />}
                  {already && <span className="badge badge-accent">Added</span>}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </Modal>
  )
}
