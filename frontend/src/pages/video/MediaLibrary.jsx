import { useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import useMediaLibrary from '../../hooks/useMediaLibrary.js'
import { useToast } from '../../context/ToastContext.jsx'
import VideoPageHeader, { VideoEmptyState } from '../../components/video/VideoPageHeader.jsx'
import VideoIcon from '../../components/video/VideoIcon.jsx'
import Modal from '../../components/video/Modal.jsx'
import Spinner from '../../components/Spinner.jsx'
import AddToProjectModal from '../../components/video/voice/AddToProjectModal.jsx'
import { formatBytes, formatDuration, relativeTime } from '../../lib/video/format.js'

// ---------------------------------------------------------------------------
// The Media Library — everything Video Studio can use, in one place.
//
// Search, filter, preview, reuse and delete, over the same assets every studio
// writes to: an uploaded clip, a generated voice-over, a stock photo, a
// finished render, a thumbnail.
//
// **Deleting is a conversation, not a button.** The server answers 409 with
// the projects using a file; this page shows that list and offers "delete
// anyway". A library where deleting is instant is a library where somebody
// empties a project they were half way through.
//
// Filters come from the server with live counts, so the tab row is what the
// account actually contains rather than a hardcoded list.
// ---------------------------------------------------------------------------

const SORTS = [
  { value: 'newest', label: 'Newest first' },
  { value: 'oldest', label: 'Oldest first' },
  { value: 'name', label: 'By name' },
  { value: 'largest', label: 'Largest first' },
  { value: 'longest', label: 'Longest first' },
]

function Preview({ item }) {
  if (item.content_type?.startsWith('image/')) {
    return (
      <img src={item.url} alt={item.title} className="h-full w-full object-cover" />
    )
  }
  if (item.content_type?.startsWith('video/')) {
    return (
      <video
        src={item.url}
        preload="metadata"
        controls
        className="h-full w-full bg-black object-contain"
      />
    )
  }
  if (item.content_type?.startsWith('audio/')) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-2 p-2">
        <VideoIcon name="music" className="h-6 w-6 text-muted" />
        <audio src={item.url} controls className="w-full" />
      </div>
    )
  }
  return (
    <span className="grid h-full w-full place-items-center text-muted">
      <VideoIcon name="captions" className="h-6 w-6" />
    </span>
  )
}

export default function MediaLibrary() {
  const toast = useToast()
  const [params, setParams] = useSearchParams()

  const filter = params.get('filter') || 'all'
  const search = params.get('q') || ''
  const sort = params.get('sort') || 'newest'

  const library = useMediaLibrary({ filter, search, sort })

  const [renaming, setRenaming] = useState(null)
  const [title, setTitle] = useState('')
  const [attaching, setAttaching] = useState(null)
  const [conflict, setConflict] = useState(null)
  const uploadRef = useRef(null)

  function setParam(key, value) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  async function remove(item, force = false) {
    const result = await library.remove(item, { force })
    if (result?.conflict) setConflict({ item, message: result.conflict })
    else setConflict(null)
  }

  return (
    <div className="mx-auto w-full max-w-6xl">
      <VideoPageHeader
        title="Media Library"
        subtitle={
          library.total
            ? `${library.total} file${library.total === 1 ? '' : 's'} · ${formatBytes(
                library.storageBytes,
              )} stored`
            : 'Everything Video Studio can use.'
        }
        back="/video"
        backLabel="Back to Video Studio"
        actions={
          <>
            <input
              ref={uploadRef}
              type="file"
              multiple
              accept="video/*,audio/*,image/*"
              className="hidden"
              onChange={(event) => {
                library.upload(event.target.files)
                event.target.value = ''
              }}
            />
            <button
              className="btn btn-primary btn-sm"
              onClick={() => uploadRef.current?.click()}
              disabled={library.uploading}
            >
              {library.uploading ? <Spinner /> : <VideoIcon name="plus" className="h-4 w-4" />}
              {library.uploading ? 'Uploading…' : 'Upload'}
            </button>
          </>
        }
      />

      {/* ---- Filters ---- */}
      <div className="card mb-4 flex flex-col gap-3 p-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative min-w-0 flex-1">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted">
              <VideoIcon name="search" className="h-4 w-4" />
            </span>
            <input
              className="input pl-9"
              placeholder="Search your files…"
              aria-label="Search media"
              value={search}
              onChange={(event) => setParam('q', event.target.value)}
            />
          </div>
          <select
            className="select sm:w-44"
            value={sort}
            aria-label="Sort"
            onChange={(event) => setParam('sort', event.target.value)}
          >
            {SORTS.map((entry) => (
              <option key={entry.value} value={entry.value}>{entry.label}</option>
            ))}
          </select>
        </div>

        <div className="flex flex-wrap gap-1.5">
          {library.filters.map((entry) => (
            <button
              key={entry.key}
              className={`btn btn-sm ${
                filter === entry.key ? 'btn-primary' : 'btn-secondary'
              }`}
              onClick={() => setParam('filter', entry.key === 'all' ? '' : entry.key)}
            >
              {entry.label}
              <span className="text-xs opacity-70 tabular-nums">{entry.count}</span>
            </button>
          ))}
        </div>
      </div>

      {library.loading && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, index) => (
            <div key={index} className="skeleton h-56" />
          ))}
        </div>
      )}

      {!library.loading && library.error && (
        <div className="card flex flex-wrap items-center justify-between gap-3 p-4">
          <p className="text-sm text-rose-600">{library.error}</p>
          <button className="btn btn-secondary btn-sm" onClick={library.reload}>
            Try again
          </button>
        </div>
      )}

      {!library.loading && !library.error && library.items.length === 0 && (
        <VideoEmptyState
          icon={search ? 'search' : 'image'}
          title={search ? 'Nothing matches that' : 'Your library is empty'}
          description={
            search
              ? 'Try another word, or a different filter.'
              : 'Upload a video, an image or some audio to get started.'
          }
        />
      )}

      {!library.loading && !library.error && library.items.length > 0 && (
        <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {library.items.map((item) => (
            <li key={item.id} className="card flex flex-col overflow-hidden">
              <div className="h-32 border-b border-line bg-inset">
                <Preview item={item} />
              </div>

              <div className="flex flex-1 flex-col gap-1 p-3">
                <p className="truncate text-sm font-medium text-body" title={item.title}>
                  {item.title}
                </p>
                <p className="text-xs text-muted">
                  {item.kind} · {formatBytes(item.size_bytes)}
                  {item.duration_seconds
                    ? ` · ${formatDuration(item.duration_seconds)}`
                    : ''}
                </p>
                <p className="text-xs text-muted">{relativeTime(item.created_at)}</p>

                {item.usage.length > 0 && (
                  <p className="mt-1 text-xs text-muted">
                    Used in{' '}
                    {item.usage.map((entry) => entry.project_name).join(', ')}
                  </p>
                )}

                <div className="mt-auto flex flex-wrap gap-1 pt-2">
                  <button
                    className="btn btn-ghost btn-sm px-2 text-xs"
                    onClick={() => {
                      setRenaming(item)
                      setTitle(item.title)
                    }}
                  >
                    Rename
                  </button>
                  <button
                    className="btn btn-ghost btn-sm px-2 text-xs"
                    onClick={() => setAttaching(item)}
                  >
                    Use
                  </button>
                  {item.project_id && (
                    <button
                      className="btn btn-ghost btn-sm px-2 text-xs"
                      onClick={() => library.detach(item)}
                    >
                      Detach
                    </button>
                  )}
                  <button
                    className="btn btn-ghost btn-sm ml-auto px-2"
                    aria-label={`Delete ${item.title}`}
                    disabled={library.busyId === item.id}
                    onClick={() => remove(item)}
                  >
                    {library.busyId === item.id ? (
                      <Spinner />
                    ) : (
                      <VideoIcon name="trash" className="h-3.5 w-3.5" />
                    )}
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* ---- Rename ---- */}
      <Modal
        open={renaming !== null}
        title="Rename file"
        description="The original filename is kept, so search still finds it either way."
        onClose={() => setRenaming(null)}
        footer={
          <>
            <button className="btn btn-ghost" onClick={() => setRenaming(null)}>
              Cancel
            </button>
            <button
              className="btn btn-primary"
              disabled={!title.trim()}
              onClick={async () => {
                await library.rename(renaming, title.trim())
                setRenaming(null)
              }}
            >
              Save
            </button>
          </>
        }
      >
        <input
          className="input"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          aria-label="New name"
        />
      </Modal>

      {/* ---- Delete conflict ---- */}
      <Modal
        open={conflict !== null}
        title="This file is in use"
        onClose={() => setConflict(null)}
        footer={
          <>
            <button className="btn btn-ghost" onClick={() => setConflict(null)}>
              Keep it
            </button>
            <button
              className="btn btn-danger"
              onClick={async () => {
                const item = conflict.item
                setConflict(null)
                await remove(item, true)
              }}
            >
              Delete anyway
            </button>
          </>
        }
      >
        <p className="text-sm text-body">{conflict?.message}</p>
        <p className="mt-2 text-sm text-muted">
          Those places will be left empty — the scenes and clips stay, with
          nothing in them, so you can put something else there.
        </p>
      </Modal>

      <AddToProjectModal
        open={attaching !== null}
        take={attaching}
        onClose={() => setAttaching(null)}
        onAttach={(item, projectId) => library.attach(item, projectId)}
      />
    </div>
  )
}
