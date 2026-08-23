import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api.js'
import { VIDEO_CATEGORIES, toolsInCategory } from '../../lib/video/tools.js'
import ProjectCard from '../../components/video/ProjectCard.jsx'
import ToolCard from '../../components/video/ToolCard.jsx'
import VideoIcon from '../../components/video/VideoIcon.jsx'
import VideoPageHeader, { VideoEmptyState } from '../../components/video/VideoPageHeader.jsx'
import ProjectDialogs, { useProjectDialogs } from '../../components/video/ProjectDialogs.jsx'
import useVideoProjects from '../../hooks/useVideoProjects.js'

// ---------------------------------------------------------------------------
// The Video Studio home.
//
// Two jobs: say what the studio can do, and get the user back into whatever
// they were working on. The tool grid answers the first, Recent Projects the
// second — and the recent list comes before nothing else, because returning to
// yesterday's project is the most common reason to open this page at all.
// ---------------------------------------------------------------------------

const RECENT_LIMIT = 4

// A deployment keeping video bytes in Postgres is a development configuration.
// Saying so is the honest thing: the alternative is a user building a library
// on storage that was never meant to hold it.
function StorageNotice({ capabilities }) {
  if (!capabilities || capabilities.storage_is_persistent) return null

  return (
    <div className="card mb-6 flex items-start gap-3 border-amber-300 bg-amber-50 p-4">
      <span className="mt-0.5 shrink-0 text-amber-700">
        <VideoIcon name="alert" className="h-5 w-5" />
      </span>
      <div className="text-sm">
        <p className="font-semibold text-amber-900">
          This deployment is using development file storage
        </p>
        <p className="mt-1 text-amber-800">
          Uploads and renders are being kept in the database instead of object
          storage. It works, but it is not sized for video — set the{' '}
          <code className="rounded bg-amber-100 px-1 py-0.5 text-[12px]">R2_*</code>{' '}
          environment variables before relying on it.
        </p>
      </div>
    </div>
  )
}

export default function VideoStudio() {
  const [capabilities, setCapabilities] = useState(null)
  const { projects, loading, error, reload, rename, duplicate, remove } = useVideoProjects()
  const dialogs = useProjectDialogs({ rename, duplicate, remove })

  useEffect(() => {
    let cancelled = false
    api
      .videoCapabilities()
      .then((data) => {
        if (!cancelled) setCapabilities(data)
      })
      // A failed capabilities call must not blank the page — the tool grid and
      // the projects list are both useful without it. The notice simply does
      // not render, which is the safe direction to fail in.
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  const recent = projects.slice(0, RECENT_LIMIT)

  return (
    <div className="mx-auto w-full max-w-6xl">
      <VideoPageHeader
        title="Video Studio"
        subtitle="Create, edit, repurpose and publish videos for all your social platforms."
        actions={
          <Link to="/video/create" className="btn btn-primary">
            <VideoIcon name="plus" className="h-4 w-4" />
            New project
          </Link>
        }
      />

      <StorageNotice capabilities={capabilities} />

      {VIDEO_CATEGORIES.map((category) => (
        <section key={category.key} className="mb-8">
          <div className="mb-3">
            <h2 className="text-sm font-bold uppercase tracking-wide text-body">
              {category.label}
            </h2>
            <p className="text-sm text-muted">{category.description}</p>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {toolsInCategory(category.key).map((tool) => (
              <ToolCard key={tool.slug} tool={tool} />
            ))}
          </div>
        </section>
      ))}

      <section>
        <div className="mb-3 flex items-end justify-between gap-3">
          <div>
            <h2 className="text-sm font-bold uppercase tracking-wide text-body">
              Recent projects
            </h2>
            <p className="text-sm text-muted">Pick up where you left off.</p>
          </div>
          {projects.length > 0 && (
            <Link to="/video/projects" className="link-accent text-sm font-semibold">
              View all
            </Link>
          )}
        </div>

        {loading && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: RECENT_LIMIT }).map((_, index) => (
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

        {!loading && !error && recent.length === 0 && (
          <VideoEmptyState
            title="No projects yet"
            description="Start with an idea, a script, or a blank canvas — whichever you have."
            action={
              <Link to="/video/create" className="btn btn-primary btn-sm">
                Create your first video
              </Link>
            }
          />
        )}

        {!loading && !error && recent.length > 0 && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {recent.map((project) => (
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
      </section>

      <ProjectDialogs {...dialogs} />
    </div>
  )
}
