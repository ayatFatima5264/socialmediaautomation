import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../../lib/api.js'
import { STATUS_FILTERS } from '../../lib/video/format.js'
import ProjectCard from '../../components/video/ProjectCard.jsx'
import VideoIcon from '../../components/video/VideoIcon.jsx'
import VideoPageHeader, { VideoEmptyState } from '../../components/video/VideoPageHeader.jsx'
import ProjectDialogs, { useProjectDialogs } from '../../components/video/ProjectDialogs.jsx'
import useVideoProjects from '../../hooks/useVideoProjects.js'

// ---------------------------------------------------------------------------
// Every project, searchable and filterable.
//
// The search box and both filters live in the URL, not in component state.
// That is what makes a filtered view shareable, survivable across a reload,
// and correct when the user presses Back — three things a `useState` version
// gets wrong and nobody notices until they are relied on.
//
// Filtering happens on the server (see useVideoProjects). The client never
// downloads everything and filters locally, because the list is paged and that
// would quietly start showing the wrong results once an account outgrew a page.
// ---------------------------------------------------------------------------

export default function Projects() {
  const [params, setParams] = useSearchParams()
  const [platforms, setPlatforms] = useState([])

  const search = params.get('q') || ''
  const platform = params.get('platform') || ''
  const status = params.get('status') || ''

  const { projects, total, loading, error, reload, rename, duplicate, remove } =
    useVideoProjects({ search, platform, status })
  const dialogs = useProjectDialogs({ rename, duplicate, remove })

  // The platform list is the server's, not a copy — a preset added in
  // presets.py appears in this dropdown with no frontend change.
  useEffect(() => {
    let cancelled = false
    api
      .videoCapabilities()
      .then((data) => {
        if (!cancelled) setPlatforms(data.presets || [])
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  function setParam(key, value) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  const filtered = Boolean(search || platform || status)

  return (
    <div className="mx-auto w-full max-w-6xl">
      <VideoPageHeader
        title="Projects"
        subtitle={
          loading
            ? 'Loading your projects…'
            : filtered
              ? `${projects.length} of ${total} ${total === 1 ? 'project' : 'projects'}`
              : `${total} ${total === 1 ? 'project' : 'projects'}`
        }
        back="/video"
        backLabel="Back to Video Studio"
        actions={
          <Link to="/video/create" className="btn btn-primary">
            <VideoIcon name="plus" className="h-4 w-4" />
            New project
          </Link>
        }
      />

      {/* Controls stack on a phone and sit in a row from `sm` up. The search
          field grows; the two selects keep their width so they stay tappable. */}
      <div className="card mb-5 flex flex-col gap-3 p-3 sm:flex-row sm:items-center">
        <div className="relative min-w-0 flex-1">
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted">
            <VideoIcon name="search" className="h-4 w-4" />
          </span>
          <input
            className="input pl-9"
            placeholder="Search projects…"
            aria-label="Search projects"
            value={search}
            onChange={(event) => setParam('q', event.target.value)}
          />
        </div>

        <select
          className="select sm:w-48"
          aria-label="Filter by platform"
          value={platform}
          onChange={(event) => setParam('platform', event.target.value)}
        >
          <option value="">All platforms</option>
          {platforms.map((preset) => (
            <option key={preset.key} value={preset.key}>
              {preset.label}
            </option>
          ))}
        </select>

        <select
          className="select sm:w-40"
          aria-label="Filter by status"
          value={status}
          onChange={(event) => setParam('status', event.target.value)}
        >
          {STATUS_FILTERS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>

        {filtered && (
          <button
            className="btn btn-ghost btn-sm shrink-0"
            onClick={() => setParams(new URLSearchParams(), { replace: true })}
          >
            Clear
          </button>
        )}
      </div>

      {loading && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, index) => (
            <div key={index} className="skeleton h-56" />
          ))}
        </div>
      )}

      {!loading && error && (
        <div className="card flex flex-wrap items-center justify-between gap-3 p-4">
          <p className="text-sm text-rose-600">{error}</p>
          <button className="btn btn-secondary btn-sm" onClick={reload}>
            Try again
          </button>
        </div>
      )}

      {!loading && !error && projects.length === 0 && (
        <VideoEmptyState
          icon={filtered ? 'search' : 'film'}
          title={filtered ? 'No projects match those filters' : 'No projects yet'}
          description={
            filtered
              ? 'Try a different search term, or clear the filters to see everything.'
              : 'Start with an idea, a script, or a blank canvas — whichever you have.'
          }
          action={
            filtered ? (
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => setParams(new URLSearchParams(), { replace: true })}
              >
                Clear filters
              </button>
            ) : (
              <Link to="/video/create" className="btn btn-primary btn-sm">
                Create your first video
              </Link>
            )
          }
        />
      )}

      {!loading && !error && projects.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {projects.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              onRename={dialogs.openRename}
              onDuplicate={dialogs.confirmDuplicate}
              onDelete={dialogs.openDelete}
            />
          ))}
        </div>
      )}

      <ProjectDialogs {...dialogs} />
    </div>
  )
}
