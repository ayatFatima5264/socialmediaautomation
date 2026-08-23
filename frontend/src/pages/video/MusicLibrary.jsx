import { useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import useMusicLibrary from '../../hooks/useMusicLibrary.js'
import VideoPageHeader, { VideoEmptyState } from '../../components/video/VideoPageHeader.jsx'
import VideoIcon from '../../components/video/VideoIcon.jsx'
import Modal from '../../components/video/Modal.jsx'
import Spinner from '../../components/Spinner.jsx'
import AddToProjectModal from '../../components/video/voice/AddToProjectModal.jsx'
import { formatDuration } from '../../lib/video/format.js'

// ---------------------------------------------------------------------------
// The Music Library.
//
// **The licence is on the row, not in the small print.** Every track shows what
// it is licensed under and who to credit before it can be picked, and a track
// that may not be used commercially is visibly unusable rather than failing
// later at the point of adding it. That is the whole premise of this screen:
// the library never holds something you are not allowed to publish.
//
// Uploading requires a positive statement of rights. The checkbox is not a
// formality — the server refuses the upload without it, before the file is
// read, so an unauthorised track never reaches storage at all.
// ---------------------------------------------------------------------------

const SOURCES = [
  { key: '', label: 'Everything' },
  { key: 'catalogue', label: 'Catalogue' },
  { key: 'uploads', label: 'Your uploads' },
]

function LicenceLine({ track }) {
  return (
    <div className="mt-1 flex flex-wrap items-center gap-1.5">
      <span
        className={`badge border text-xs ${
          track.can_use
            ? 'border-line bg-inset text-muted'
            : 'border-amber-300 bg-amber-50 text-amber-800'
        }`}
      >
        {track.license_label}
      </span>
      {track.requires_attribution && (
        <span className="badge border border-line bg-inset text-xs text-muted">
          Credit required
        </span>
      )}
    </div>
  )
}

export default function MusicLibrary() {
  const [params, setParams] = useSearchParams()

  const search = params.get('q') || ''
  const mood = params.get('mood') || ''
  const genre = params.get('genre') || ''
  const duration = params.get('duration') || ''
  const source = params.get('source') || ''

  const library = useMusicLibrary({ search, mood, genre, duration, source })

  const [adding, setAdding] = useState(null)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(null)
  const [form, setForm] = useState({
    title: '',
    artist: '',
    sourceUrl: '',
    attribution: '',
    confirmedRights: false,
  })
  const fileRef = useRef(null)

  function setParam(key, value) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  function FacetRow({ name, options }) {
    if (!options?.length) return null
    const active = params.get(name) || ''
    return (
      <div className="flex flex-wrap gap-1.5">
        {options.map((entry) => (
          <button
            key={entry.key}
            className={`btn btn-sm ${
              active === entry.key ? 'btn-primary' : 'btn-secondary'
            }`}
            onClick={() => setParam(name, active === entry.key ? '' : entry.key)}
          >
            {entry.label}
            <span className="text-xs opacity-70 tabular-nums">{entry.count}</span>
          </button>
        ))}
      </div>
    )
  }

  async function submitUpload() {
    const file = fileRef.current?.files?.[0]
    if (!file) return
    const track = await library.upload(file, form)
    if (track) {
      setUploadOpen(false)
      setForm({
        title: '',
        artist: '',
        sourceUrl: '',
        attribution: '',
        confirmedRights: false,
      })
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div className="mx-auto w-full max-w-6xl">
      <VideoPageHeader
        title="Music Library"
        subtitle={
          library.total
            ? `${library.total} track${library.total === 1 ? '' : 's'} you can use`
            : 'Licensed background tracks, searchable by mood and length.'
        }
        back="/video"
        backLabel="Back to Video Studio"
        actions={
          <button className="btn btn-primary btn-sm" onClick={() => setUploadOpen(true)}>
            <VideoIcon name="plus" className="h-4 w-4" />
            Upload a track
          </button>
        }
      />

      {/* ---- Search and filters ---- */}
      <div className="card mb-4 flex flex-col gap-3 p-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative min-w-0 flex-1">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted">
              <VideoIcon name="search" className="h-4 w-4" />
            </span>
            <input
              className="input pl-9"
              placeholder="Search by mood, instrument or feel…"
              aria-label="Search music"
              value={search}
              onChange={(event) => setParam('q', event.target.value)}
            />
          </div>
          <div className="flex flex-wrap gap-1.5">
            {SOURCES.map((entry) => (
              <button
                key={entry.key || 'all'}
                className={`btn btn-sm ${
                  source === entry.key ? 'btn-primary' : 'btn-secondary'
                }`}
                onClick={() => setParam('source', entry.key)}
              >
                {entry.label}
              </button>
            ))}
          </div>
        </div>

        <FacetRow name="mood" options={library.facets?.moods} />
        <FacetRow name="genre" options={library.facets?.genres} />
        <FacetRow name="duration" options={library.facets?.durations} />

        {!search && library.facets?.suggestions?.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-muted">Try:</span>
            {library.facets.suggestions.map((entry) => (
              <button
                key={entry}
                className="btn btn-ghost btn-sm px-2 text-xs"
                onClick={() => setParam('q', entry)}
              >
                {entry}
              </button>
            ))}
          </div>
        )}
      </div>

      {library.loading && (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className="skeleton h-24" />
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

      {!library.loading && !library.error && library.tracks.length === 0 && (
        <VideoEmptyState
          icon={search ? 'search' : 'music'}
          title={search ? 'Nothing matches that' : 'No tracks yet'}
          description={
            search
              ? 'Try a different word — the catalogue also searches Openverse.'
              : 'Upload a track you have the rights to, or search for one.'
          }
        />
      )}

      {!library.loading && !library.error && library.tracks.length > 0 && (
        <ul className="flex flex-col gap-3">
          {library.tracks.map((track) => (
            <li key={track.id} className="card flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-body" title={track.title}>
                  {track.title}
                </p>
                <p className="truncate text-xs text-muted">
                  {[track.artist, track.mood, track.genre].filter(Boolean).join(' · ')}
                  {track.duration_seconds
                    ? ` · ${formatDuration(track.duration_seconds)}`
                    : ''}
                  {track.bpm ? ` · ${track.bpm} BPM` : ''}
                </p>
                <LicenceLine track={track} />
                {!track.can_use && track.blocked_reason && (
                  <p className="mt-1 text-xs text-amber-700">{track.blocked_reason}</p>
                )}
              </div>

              {track.url && (
                <audio
                  src={track.url}
                  controls
                  preload="none"
                  className="w-full sm:w-64"
                  aria-label={`Preview ${track.title}`}
                />
              )}

              <div className="flex shrink-0 flex-wrap gap-1">
                <button
                  className="btn btn-secondary btn-sm"
                  disabled={!track.can_use || library.busyId === track.id}
                  title={
                    track.can_use
                      ? 'Add this track to a project'
                      : 'This licence does not allow commercial use'
                  }
                  onClick={() => setAdding(track)}
                >
                  {library.busyId === track.id ? <Spinner /> : null}
                  Add to project
                </button>
                {track.source === 'upload' && (
                  <button
                    className="btn btn-ghost btn-sm px-2"
                    aria-label={`Delete ${track.title}`}
                    disabled={library.busyId === track.id}
                    onClick={() => setConfirmDelete(track)}
                  >
                    <VideoIcon name="trash" className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* ---- Upload ---- */}
      <Modal
        open={uploadOpen}
        title="Upload a track"
        description="Only music you hold or have been granted the rights to."
        onClose={() => setUploadOpen(false)}
        footer={
          <>
            <button className="btn btn-ghost" onClick={() => setUploadOpen(false)}>
              Cancel
            </button>
            <button
              className="btn btn-primary"
              disabled={!form.confirmedRights || library.uploading}
              onClick={submitUpload}
            >
              {library.uploading && <Spinner />}
              Upload
            </button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <label className="block">
            <span className="label">Audio file</span>
            <input ref={fileRef} type="file" accept="audio/*" className="input" />
          </label>
          <label className="block">
            <span className="label">Title</span>
            <input
              className="input"
              value={form.title}
              placeholder="Taken from the filename if you leave this empty"
              onChange={(event) => setForm({ ...form, title: event.target.value })}
            />
          </label>
          <label className="block">
            <span className="label">Artist</span>
            <input
              className="input"
              value={form.artist}
              onChange={(event) => setForm({ ...form, artist: event.target.value })}
            />
          </label>
          <label className="block">
            <span className="label">Where it came from (optional)</span>
            <input
              className="input"
              value={form.sourceUrl}
              placeholder="https://…"
              onChange={(event) => setForm({ ...form, sourceUrl: event.target.value })}
            />
          </label>
          <label className="block">
            <span className="label">Attribution to record (optional)</span>
            <input
              className="input"
              value={form.attribution}
              onChange={(event) => setForm({ ...form, attribution: event.target.value })}
            />
          </label>

          <label className="flex items-start gap-2 rounded-lg border border-line bg-inset p-3">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={form.confirmedRights}
              onChange={(event) =>
                setForm({ ...form, confirmedRights: event.target.checked })
              }
            />
            <span className="text-sm text-body">
              I hold the rights to this music, or have been granted permission to
              use it.
              <span className="mt-1 block text-xs text-muted">
                Recorded with the track. Without this the upload is refused before
                the file is read.
              </span>
            </span>
          </label>
        </div>
      </Modal>

      {/* ---- Delete ---- */}
      <Modal
        open={confirmDelete !== null}
        title="Delete this track?"
        onClose={() => setConfirmDelete(null)}
        footer={
          <>
            <button className="btn btn-ghost" onClick={() => setConfirmDelete(null)}>
              Keep it
            </button>
            <button
              className="btn btn-danger"
              onClick={async () => {
                const track = confirmDelete
                setConfirmDelete(null)
                await library.remove(track)
              }}
            >
              Delete
            </button>
          </>
        }
      >
        <p className="text-sm text-body">
          “{confirmDelete?.title}” will be removed from your library. Projects
          already using it keep their copy of the licence and credit.
        </p>
      </Modal>

      <AddToProjectModal
        open={adding !== null}
        take={adding}
        onClose={() => setAdding(null)}
        onAttach={(track, projectId) => library.addToProject(track, projectId)}
      />
    </div>
  )
}
