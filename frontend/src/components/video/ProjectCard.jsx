import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import VideoIcon from './VideoIcon.jsx'
import { formatDuration, platformLabel, relativeTime, STATUS_STYLES } from '../../lib/video/format.js'

// ---------------------------------------------------------------------------
// One project in the grid.
//
// The whole card is a link to the project; the actions menu sits on top of it
// and stops propagation, so clicking "Rename" cannot also open the project.
// That is the bug this shape exists to avoid — nesting a <button> inside an
// <a> is invalid HTML and produces exactly that double action.
//
// The poster area shows the project's thumbnail once it has one. Until then it
// shows the aspect ratio and platform rather than a grey box, because before
// the first render that IS what is true about the project.
// ---------------------------------------------------------------------------

function ActionsMenu({ onRename, onDuplicate, onDelete }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    function onDocument(event) {
      if (!ref.current?.contains(event.target)) setOpen(false)
    }
    function onKey(event) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDocument)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocument)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  function run(action) {
    setOpen(false)
    action()
  }

  return (
    <div
      ref={ref}
      className="relative"
      // The card behind this is a link. Without these the menu button would
      // navigate as well as open.
      onClick={(event) => {
        event.preventDefault()
        event.stopPropagation()
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Project actions"
        className="grid h-8 w-8 place-items-center rounded-lg border border-line bg-surface text-muted transition-colors hover:border-accent-line hover:text-body"
      >
        <VideoIcon name="dots" className="h-4 w-4" />
      </button>

      {open && (
        <div role="menu" className="menu absolute right-0 z-20 mt-1 w-40">
          <button className="menu-item" role="menuitem" onClick={() => run(onRename)}>
            <VideoIcon name="pencil" className="h-4 w-4" />
            Rename
          </button>
          <button className="menu-item" role="menuitem" onClick={() => run(onDuplicate)}>
            <VideoIcon name="copy" className="h-4 w-4" />
            Duplicate
          </button>
          <button
            className="menu-item text-rose-600 hover:bg-rose-50"
            role="menuitem"
            onClick={() => run(onDelete)}
          >
            <VideoIcon name="trash" className="h-4 w-4" />
            Delete
          </button>
        </div>
      )}
    </div>
  )
}

export default function ProjectCard({ project, onRename, onDuplicate, onDelete }) {
  const status = STATUS_STYLES[project.status] || STATUS_STYLES.draft

  // The poster box is the same height on every card, whatever the project's
  // orientation — a grid mixing 16:9 and 9:16 posters comes out visibly
  // ragged, with landscape cards floating short beside vertical ones.
  //
  // The orientation is still shown, by drawing the canvas at its real ratio
  // INSIDE that fixed box (the same device the format picker uses). So the
  // shape is legible and the rows still line up.
  const vertical = project.height > project.width
  const frame = vertical
    ? { width: (96 * project.width) / project.height, height: 96 }
    : { width: 128, height: (128 * project.height) / project.width }

  return (
    <div className="card group relative flex flex-col overflow-hidden transition-shadow hover:shadow-[var(--shadow-pop)]">
      <Link
        to={`/video/projects/${project.id}`}
        className="flex flex-1 flex-col focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <div className="relative flex h-32 items-center justify-center overflow-hidden border-b border-line bg-inset">
          {project.thumbnail_url ? (
            <img
              src={project.thumbnail_url}
              alt=""
              loading="lazy"
              className="h-full w-full object-cover"
            />
          ) : (
            <span
              className="grid place-items-center rounded-md border-2 border-current text-muted"
              style={{ width: frame.width, height: frame.height }}
            >
              <VideoIcon name="film" className="h-6 w-6" />
            </span>
          )}

          <span className="absolute bottom-2 left-2 rounded-md bg-black/65 px-1.5 py-0.5 text-[11px] font-semibold text-white">
            {project.aspect_ratio}
          </span>
          {project.duration_seconds > 0 && (
            <span className="absolute bottom-2 right-2 rounded-md bg-black/65 px-1.5 py-0.5 text-[11px] font-semibold tabular-nums text-white">
              {formatDuration(project.duration_seconds)}
            </span>
          )}
        </div>

        <div className="flex flex-1 flex-col gap-2 p-3">
          <p className="truncate font-semibold leading-tight text-body">{project.name}</p>

          <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
            <span className={`badge ${status.className}`}>{status.label}</span>
            <span className="truncate">{platformLabel(project.platform)}</span>
          </div>

          <p className="mt-auto text-xs text-muted">
            Edited {relativeTime(project.updated_at)}
          </p>
        </div>
      </Link>

      <div className="absolute right-2 top-2 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100 max-md:opacity-100">
        <ActionsMenu
          onRename={() => onRename(project)}
          onDuplicate={() => onDuplicate(project)}
          onDelete={() => onDelete(project)}
        />
      </div>
    </div>
  )
}
