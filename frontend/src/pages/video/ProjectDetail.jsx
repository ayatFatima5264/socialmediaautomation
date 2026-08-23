import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError } from '../../lib/api.js'
import { useToast } from '../../context/ToastContext.jsx'
import { formatDuration, platformLabel, relativeTime, STATUS_STYLES } from '../../lib/video/format.js'
import VideoIcon from '../../components/video/VideoIcon.jsx'
import VideoPageHeader from '../../components/video/VideoPageHeader.jsx'
import Modal from '../../components/video/Modal.jsx'
import Spinner from '../../components/Spinner.jsx'

// ---------------------------------------------------------------------------
// One project, opened.
//
// This is the project's *settings and status* page, not the timeline editor —
// that lands in a later phase, and the button that will open it says so rather
// than pretending. What it does own is everything about a project that exists
// before there is an edit to make: its name, its description, its notes, its
// format, and the actions that apply to the whole thing.
//
// Saving goes through the same optimistic-concurrency contract the editor will
// use: the revision loaded is sent back, and a 409 means somebody else saved
// first. Rather than silently discarding either version, the user is told and
// offered a reload — which is the only honest resolution when two edits to
// free text conflict.
// ---------------------------------------------------------------------------

function Stat({ label, value, hint }) {
  return (
    <div className="panel p-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-1 font-semibold tabular-nums text-body">{value}</p>
      {hint && <p className="text-xs text-muted">{hint}</p>}
    </div>
  )
}

export default function ProjectDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const toast = useToast()

  const [project, setProject] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [conflict, setConflict] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)

  // The editable copy, kept apart from the loaded project so "Save" knows what
  // changed and "Discard" has something to go back to.
  const [draft, setDraft] = useState({ name: '', description: '', notes: '' })

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getVideoProject(id)
      setProject(data)
      setDraft({
        name: data.name || '',
        description: data.description || '',
        notes: data.notes || '',
      })
      setConflict(false)
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 404
          ? 'That project does not exist, or it belongs to another account.'
          : err?.message || 'Could not load that project.',
      )
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  const dirty =
    project &&
    (draft.name.trim() !== (project.name || '') ||
      draft.description !== (project.description || '') ||
      draft.notes !== (project.notes || ''))

  async function save() {
    if (!dirty || saving) return
    setSaving(true)
    try {
      const updated = await api.updateVideoProject(project.id, {
        name: draft.name.trim() || undefined,
        description: draft.description,
        notes: draft.notes,
        expected_revision: project.revision,
      })
      setProject(updated)
      setDraft({
        name: updated.name || '',
        description: updated.description || '',
        notes: updated.notes || '',
      })
      toast.success('Project saved.')
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // Two edits to the same free text cannot be merged for the user. Say
        // what happened and let them decide, rather than picking a winner.
        setConflict(true)
      } else {
        toast.error(err?.message || 'Could not save that project.')
      }
    } finally {
      setSaving(false)
    }
  }

  async function duplicate() {
    try {
      const copy = await api.duplicateVideoProject(project.id)
      toast.success(`Duplicated as “${copy.name}”.`)
      navigate(`/video/projects/${copy.id}`)
    } catch (err) {
      toast.error(err?.message || 'Could not duplicate that project.')
    }
  }

  async function remove() {
    setDeleting(true)
    try {
      await api.deleteVideoProject(project.id)
      toast.success(`Deleted “${project.name}”.`)
      navigate('/video/projects')
    } catch (err) {
      toast.error(err?.message || 'Could not delete that project.')
      setDeleting(false)
    }
  }

  if (loading) {
    return (
      <div className="mx-auto w-full max-w-4xl">
        <div className="skeleton mb-6 h-10 w-64" />
        <div className="skeleton mb-4 h-32" />
        <div className="skeleton h-64" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="mx-auto w-full max-w-4xl">
        <VideoPageHeader title="Project" back="/video/projects" backLabel="Back to projects" />
        <div className="card flex flex-col items-center gap-3 px-6 py-12 text-center">
          <span className="grid h-12 w-12 place-items-center rounded-full bg-inset text-muted">
            <VideoIcon name="alert" className="h-6 w-6" />
          </span>
          <p className="max-w-sm text-sm text-muted">{error}</p>
          <button className="btn btn-secondary btn-sm" onClick={() => navigate('/video/projects')}>
            Back to projects
          </button>
        </div>
      </div>
    )
  }

  const status = STATUS_STYLES[project.status] || STATUS_STYLES.draft

  return (
    <div className="mx-auto w-full max-w-4xl">
      <VideoPageHeader
        title={project.name}
        subtitle={`${platformLabel(project.platform)} · edited ${relativeTime(project.updated_at)}`}
        back="/video/projects"
        backLabel="Back to projects"
        actions={
          <>
            <button className="btn btn-secondary" onClick={duplicate}>
              <VideoIcon name="copy" className="h-4 w-4" />
              Duplicate
            </button>
            <Link
              to={`/video/projects/${project.id}/export`}
              className="btn btn-secondary"
            >
              <VideoIcon name="film" className="h-4 w-4" />
              Export
            </Link>
            <Link to={`/video/projects/${project.id}/edit`} className="btn btn-primary">
              <VideoIcon name="timeline" className="h-4 w-4" />
              Open editor
            </Link>
          </>
        }
      />

      {conflict && (
        <div className="card mb-5 flex flex-wrap items-center justify-between gap-3 border-amber-300 bg-amber-50 p-4">
          <p className="text-sm text-amber-900">
            This project was changed somewhere else — another tab or device.
            Reload to get the latest version before saving again.
          </p>
          <button className="btn btn-secondary btn-sm" onClick={load}>
            Reload project
          </button>
        </div>
      )}

      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label="Status"
          value={<span className={`badge ${status.className}`}>{status.label}</span>}
        />
        <Stat
          label="Format"
          value={project.aspect_ratio}
          hint={`${project.width}×${project.height} · ${project.fps}fps`}
        />
        <Stat
          label="Duration"
          value={formatDuration(project.duration_seconds)}
          hint={project.duration_seconds === 0 ? 'Nothing on the timeline yet' : undefined}
        />
        <Stat
          label="Contents"
          value={`${project.scene_count} ${project.scene_count === 1 ? 'scene' : 'scenes'}`}
          hint={`${project.audio_count} audio · ${project.subtitle_count} subtitle`}
        />
      </div>

      <section className="card mb-5 p-5">
        <h2 className="mb-4 font-semibold text-body">Project details</h2>

        <div className="mb-4">
          <label className="label" htmlFor="name">
            Name
          </label>
          <input
            id="name"
            className="input"
            value={draft.name}
            maxLength={200}
            onChange={(event) => setDraft((d) => ({ ...d, name: event.target.value }))}
          />
        </div>

        <div className="mb-4">
          <label className="label" htmlFor="description">
            Description <span className="font-normal text-muted">(optional)</span>
          </label>
          <input
            id="description"
            className="input"
            placeholder="What is this video about?"
            value={draft.description}
            onChange={(event) => setDraft((d) => ({ ...d, description: event.target.value }))}
          />
        </div>

        <div>
          <label className="label" htmlFor="notes">
            Notes <span className="font-normal text-muted">(only you see these)</span>
          </label>
          <textarea
            id="notes"
            className="input min-h-24 resize-y"
            placeholder="Reminders, links, things to change…"
            value={draft.notes}
            onChange={(event) => setDraft((d) => ({ ...d, notes: event.target.value }))}
          />
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-2">
          <button
            className="btn btn-primary"
            onClick={save}
            disabled={!dirty || saving || !draft.name.trim()}
          >
            {saving && <Spinner />}
            {saving ? 'Saving…' : 'Save changes'}
          </button>
          {dirty && (
            <button
              className="btn btn-ghost"
              disabled={saving}
              onClick={() =>
                setDraft({
                  name: project.name || '',
                  description: project.description || '',
                  notes: project.notes || '',
                })
              }
            >
              Discard
            </button>
          )}
          <span className="text-xs text-muted">
            {dirty ? 'Unsaved changes' : `Revision ${project.revision}`}
          </span>
        </div>
      </section>

      <section className="card border-rose-200 p-5">
        <h2 className="font-semibold text-body">Delete this project</h2>
        <p className="mt-1 max-w-prose text-sm text-muted">
          Removes the project and its scenes, audio layers and subtitle tracks.
          Any voice-overs, uploads or renders you made stay in your library.
        </p>
        <button className="btn btn-danger mt-4" onClick={() => setConfirmDelete(true)}>
          <VideoIcon name="trash" className="h-4 w-4" />
          Delete project
        </button>
      </section>

      <Modal
        open={confirmDelete}
        title="Delete this project?"
        description={`“${project.name}” will be removed. This cannot be undone.`}
        onClose={deleting ? () => {} : () => setConfirmDelete(false)}
        footer={
          <>
            <button
              className="btn btn-ghost"
              onClick={() => setConfirmDelete(false)}
              disabled={deleting}
            >
              Cancel
            </button>
            <button className="btn btn-danger" onClick={remove} disabled={deleting}>
              {deleting && <Spinner />}
              {deleting ? 'Deleting…' : 'Delete project'}
            </button>
          </>
        }
      />
    </div>
  )
}
