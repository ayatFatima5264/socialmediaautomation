import { Link, useParams } from 'react-router-dom'
import { getTool } from '../../lib/video/tools.js'
import VideoIcon, { tintClass } from '../../components/video/VideoIcon.jsx'
import VideoPageHeader from '../../components/video/VideoPageHeader.jsx'
import NotFound from '../NotFound.jsx'

// ---------------------------------------------------------------------------
// The page a tool gets before it is built.
//
// Generated from the tool's registry entry, so there is no second place where
// a description could disagree with the card that linked here. It states
// plainly that the tool is not ready and offers the things that ARE — which is
// the difference between a placeholder and a dead end.
//
// A slug that is not in the registry falls through to the app's 404 rather
// than rendering an empty shell for a tool that was never planned.
// ---------------------------------------------------------------------------

export default function VideoToolPlaceholder() {
  const { slug } = useParams()
  const tool = getTool(slug)

  if (!tool) return <NotFound />

  return (
    <div className="mx-auto w-full max-w-3xl">
      <VideoPageHeader
        title={tool.name}
        subtitle={tool.description}
        back="/video"
        backLabel="Back to Video Studio"
      />

      <div className="card p-6">
        <div className="flex items-start gap-4">
          <span
            className={`grid h-12 w-12 shrink-0 place-items-center rounded-[10px] ${tintClass(
              tool.tint,
            )}`}
          >
            <VideoIcon name={tool.icon} className="h-6 w-6" />
          </span>
          <div className="min-w-0">
            <span className="badge border border-line bg-inset text-muted">
              Not built yet
            </span>
            <p className="mt-3 text-body">{tool.longDescription}</p>
          </div>
        </div>

        {tool.capabilities?.length > 0 && (
          <div className="panel mt-5 p-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
              What it will do
            </p>
            <ul className="flex flex-col gap-2">
              {tool.capabilities.map((capability) => (
                <li key={capability} className="flex items-start gap-2 text-sm text-body">
                  <span className="mt-0.5 shrink-0 text-accent">
                    <VideoIcon name="check" className="h-4 w-4" />
                  </span>
                  {capability}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="mt-6 flex flex-wrap gap-2">
          <Link to="/video/create" className="btn btn-primary">
            Create a video
          </Link>
          <Link to="/video/projects" className="btn btn-secondary">
            View your projects
          </Link>
        </div>
      </div>
    </div>
  )
}
