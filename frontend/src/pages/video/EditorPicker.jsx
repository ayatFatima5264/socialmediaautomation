import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api.js'
import VideoPageHeader, { VideoEmptyState } from '../../components/video/VideoPageHeader.jsx'
import VideoIcon from '../../components/video/VideoIcon.jsx'
import { formatDuration, platformLabel, relativeTime } from '../../lib/video/format.js'

// ---------------------------------------------------------------------------
// "Video Editor" reached from the Overview, where no project is open yet.
//
// The editor edits *a project*, so its real route is
// /video/projects/:id/edit. This page exists because the tool card has to lead
// somewhere: it asks which project, rather than guessing at the most recent
// one and dropping somebody into a video they were not thinking about.
// ---------------------------------------------------------------------------

export default function EditorPicker() {
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    api
      .listVideoProjects({ limit: 50 })
      .then((data) => !cancelled && setProjects(data.projects || []))
      .catch((err) => !cancelled && setError(err?.message || 'Could not load your projects.'))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="mx-auto w-full max-w-3xl">
      <VideoPageHeader
        title="Video Editor"
        subtitle="Pick a project to edit. The timeline, the preview and the export all work from the same project."
        back="/video"
        backLabel="Back to Video Studio"
        actions={
          <Link to="/video/create" className="btn btn-primary btn-sm">
            <VideoIcon name="plus" className="h-4 w-4" />
            New project
          </Link>
        }
      />

      {loading && (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="skeleton h-16" />
          ))}
        </div>
      )}

      {!loading && error && (
        <VideoEmptyState icon="alert" title="Could not load projects" description={error} />
      )}

      {!loading && !error && projects.length === 0 && (
        <VideoEmptyState
          icon="film"
          title="No projects yet"
          description="Create one and it opens straight in the editor."
          action={
            <Link to="/video/create" className="btn btn-primary btn-sm">
              Create a project
            </Link>
          }
        />
      )}

      {!loading && !error && projects.length > 0 && (
        <ul className="flex flex-col gap-2">
          {projects.map((project) => (
            <li key={project.id}>
              <Link
                to={`/video/projects/${project.id}/edit`}
                className="panel flex items-center gap-3 px-4 py-3 transition-colors hover:border-accent-line"
              >
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-inset text-muted">
                  <VideoIcon name="timeline" className="h-5 w-5" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium text-body">{project.name}</span>
                  <span className="block text-xs text-muted">
                    {platformLabel(project.platform)} · {project.aspect_ratio} ·{' '}
                    {formatDuration(project.duration_seconds)} · edited{' '}
                    {relativeTime(project.updated_at)}
                  </span>
                </span>
                <span className="badge border border-line bg-inset text-muted">Open</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
