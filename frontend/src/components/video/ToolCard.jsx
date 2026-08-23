import { Link } from 'react-router-dom'
import VideoIcon, { tintClass } from './VideoIcon.jsx'
import { toolPath } from '../../lib/video/tools.js'

// ---------------------------------------------------------------------------
// A tool card on the Video Studio Overview.
//
// A tool that is built links to its page. One that is not links to its
// placeholder, which explains what it will do — and the card says "Coming
// soon" rather than looking identical to a working one. That distinction is
// the whole reason `built` is in the registry: a grid where half the cards
// silently do nothing is worse than a grid that admits which half.
// ---------------------------------------------------------------------------

export default function ToolCard({ tool }) {
  return (
    <Link
      to={toolPath(tool)}
      className="card group flex flex-col gap-3 p-4 transition-shadow hover:shadow-[var(--shadow-pop)] focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
    >
      <div className="flex items-start justify-between gap-2">
        <span
          className={`grid h-10 w-10 shrink-0 place-items-center rounded-[10px] ${tintClass(
            tool.tint,
          )}`}
        >
          <VideoIcon name={tool.icon} />
        </span>
        {!tool.built && (
          <span className="badge border border-line bg-inset text-muted">Coming soon</span>
        )}
      </div>

      <div className="min-w-0">
        <p className="font-semibold text-body group-hover:text-accent">{tool.name}</p>
        <p className="mt-1 text-sm leading-snug text-muted">{tool.description}</p>
      </div>
    </Link>
  )
}
