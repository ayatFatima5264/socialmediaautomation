import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../../lib/api.js'
import { useToast } from '../../context/ToastContext.jsx'
import useTimelineEditor from '../../hooks/useTimelineEditor.js'
import VideoPageHeader, { VideoEmptyState } from '../../components/video/VideoPageHeader.jsx'
import VideoIcon from '../../components/video/VideoIcon.jsx'
import Modal from '../../components/video/Modal.jsx'
import Spinner from '../../components/Spinner.jsx'
import Preview from '../../components/video/editor/Preview.jsx'
import Timeline from '../../components/video/editor/Timeline.jsx'
import Inspector from '../../components/video/editor/Inspector.jsx'
import ExportPanel from '../../components/video/editor/ExportPanel.jsx'
import { formatDuration, relativeTime } from '../../lib/video/format.js'

// ---------------------------------------------------------------------------
// The video editor.
//
// Preview, timeline and export all read one document — the project's timeline
// — and every edit goes back to the server as an operation. There is no second
// model of the video anywhere on this page: what the canvas draws is what the
// encoder will encode, and the geometry it draws with is the encoder's own.
//
// Layout is preview + export on the right, timeline across the bottom, and the
// inspector for the selected clip on the left. That puts the three things an
// edit needs — see it, place it, adjust it — on screen at once, which is the
// only arrangement that does not make trimming a scroll.
// ---------------------------------------------------------------------------

/** The media type of an asset, from its MIME type. `null` when unknown. */
function mediaType(asset) {
  const type = String(asset.content_type || '').split(';')[0].trim().toLowerCase()
  if (type.startsWith('image/')) return 'image'
  if (type.startsWith('audio/')) return 'audio'
  if (type.startsWith('video/')) return 'video'
  return null
}

/** Which track a library asset belongs on, and what kind of clip it becomes.
 *
 *  The MIME type decides first — that is what the file actually is. Its
 *  storage `kind` is a category, not a promise: a PNG uploaded as
 *  `kind: 'upload'` is still an image. When the type never survived ingest,
 *  the shape the probe recorded decides: dimensions and no duration can only
 *  be a still, so it lands on the video track as an image rather than being
 *  mistaken for a video clip.
 */
function targetFor(asset) {
  const type = mediaType(asset)

  if (type === 'image') {
    return { track: 'video', kind: 'image', duration: 4 }
  }
  if (type === 'audio') {
    return { track: 'audio', kind: 'audio', duration: asset.duration_seconds || 10 }
  }
  if (type === 'video') {
    return { track: 'video', kind: 'video', duration: asset.duration_seconds || 5 }
  }

  if (asset.width || asset.height) {
    return asset.duration_seconds
      ? { track: 'video', kind: 'video', duration: asset.duration_seconds || 5 }
      : { track: 'video', kind: 'image', duration: 4 }
  }
  if (asset.kind === 'audio' || asset.kind === 'voice' || asset.kind === 'music') {
    return { track: 'audio', kind: 'audio', duration: asset.duration_seconds || 10 }
  }
  return { track: 'video', kind: 'video', duration: asset.duration_seconds || 5 }
}

// The picker's tabs filter by *media type*, not by the asset's storage kind,
// so a photo uploaded as `kind: 'upload'` still reads as an image.
const PICKER_TABS = [
  { key: 'all', label: 'All' },
  { key: 'video', label: 'Videos' },
  { key: 'image', label: 'Images' },
  { key: 'audio', label: 'Audio' },
]

function AddMediaModal({ open, onClose, onAdd, projectId }) {
  const toast = useToast()
  const [items, setItems] = useState([])
  const [uploads, setUploads] = useState([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [adding, setAdding] = useState(false)
  const [tab, setTab] = useState('all')

  // Selected rows, by key, in the order they were picked. An upload's key is
  // prefixed because `video_assets` and `media_assets` ids are separate
  // sequences that can collide.
  const [selected, setSelected] = useState(() => new Set())

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [library, composer] = await Promise.all([
        api.mediaLibrary({ limit: 200 }),
        api.listComposerUploads({ limit: 100 }),
      ])
      setItems(library.items || [])
      setUploads(composer.items || [])
    } catch (err) {
      toast.error(err?.message || 'Could not load your media.')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => {
    if (open) {
      setSelected(new Set())
      setTab('all')
      load()
    }
  }, [open, load])

  async function upload(files) {
    const list = Array.from(files || [])
    if (!list.length) return
    setUploading(true)
    let stored = 0
    for (const file of list) {
      const kind = file.type.startsWith('image/')
        ? 'image'
        : file.type.startsWith('audio/')
          ? 'music'
          : 'video'
      try {
        await api.uploadVideoMedia(file, { kind })
        stored += 1
      } catch (err) {
        toast.error(`${file.name}: ${err?.message || 'could not be uploaded'}`)
      }
    }
    if (stored > 0) await load()
    setUploading(false)
  }

  // The rows for the current tab: the Video Studio library, then the images
  // this account already uploaded for posts (the composer's `media_assets`),
  // which are not studio assets until they are imported. Selecting one
  // imports it when the user hits Done.
  const libraryRows = useMemo(
    () =>
      items
        .map((item) => ({
          key: String(item.id),
          source: 'library',
          asset: item,
          type: mediaType(item) || (item.width || item.height ? 'image' : null),
          title: item.title,
          target: targetFor(item),
        }))
        .filter((row) => row.type && (tab === 'all' || tab === row.type)),
    [items, tab],
  )

  const uploadRows = useMemo(
    () =>
      uploads
        .map((upload) => ({
          key: `upload:${upload.id}`,
          source: 'upload',
          mediaId: upload.id,
          asset: upload,
          type: mediaType(upload) || 'image',
          title: upload.filename || 'Uploaded image',
          target: { track: 'video', kind: 'image', duration: 4 },
        }))
        .filter((row) => tab === 'all' || tab === row.type),
    [uploads, tab],
  )

  const counts = useMemo(() => {
    const typeOf = (asset) => mediaType(asset) || (asset.width || asset.height ? 'image' : null)
    const of = (type) =>
      items.filter((item) => typeOf(item) === type).length +
      uploads.filter((upload) => (mediaType(upload) || 'image') === type).length
    return {
      all: items.filter((item) => typeOf(item)).length + uploads.length,
      video: of('video'),
      image: of('image'),
      audio: of('audio'),
    }
  }, [items, uploads])

  function toggle(key) {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  async function addSelected() {
    if (adding) return
    if (!selected.size) {
      onClose()
      return
    }
    setAdding(true)
    let added = 0
    let failed = 0
    for (const key of selected) {
      const row =
        libraryRows.find((entry) => entry.key === key) ||
        uploadRows.find((entry) => entry.key === key)
      if (!row) continue
      try {
        let asset = row.asset
        let target = row.target
        if (row.source === 'upload') {
          // Bring the composer image into Video Studio first — de-duplicated,
          // so the second time the same image is picked it returns the same
          // asset — then add it like any library file.
          asset = await api.importComposerUpload(row.mediaId, projectId)
          target = targetFor(asset)
        }
        if (await onAdd(asset, target, { quiet: true })) added += 1
        else failed += 1
      } catch (err) {
        failed += 1
        toast.error(err?.message || `“${row.title}” could not be added.`)
      }
    }
    if (added) {
      toast.success(
        added === 1 ? 'Added 1 clip to the timeline.' : `Added ${added} clips to the timeline.`,
      )
    }
    if (failed) {
      toast.error(
        `${failed} item${failed === 1 ? ' did' : 's did'} not make it onto the timeline.`,
      )
    }
    setSelected(new Set())
    setAdding(false)
    onClose()
  }

  function renderRow(row) {
    const isSelected = selected.has(row.key)
    const { target } = row
    return (
      <li key={row.key}>
        <button
          type="button"
          onClick={() => toggle(row.key)}
          aria-pressed={isSelected}
          className={`panel flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:border-accent-line ${
            isSelected ? 'border-accent' : ''
          }`}
        >
          <span
            className={`grid h-5 w-5 shrink-0 place-items-center rounded border ${
              isSelected
                ? 'border-accent bg-accent text-white'
                : 'border-line bg-inset text-transparent'
            }`}
          >
            <VideoIcon name="check" className="h-3 w-3" />
          </span>
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-inset text-muted">
            <VideoIcon
              name={target.kind === 'image' ? 'image' : target.kind === 'audio' ? 'music' : 'film'}
              className="h-4 w-4"
            />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate font-medium text-body">{row.title}</span>
            <span className="block text-xs text-muted">
              {target.track} track
              {row.source === 'upload' ? ' · from your image uploads' : ''}
              {row.asset.duration_seconds
                ? ` · ${formatDuration(row.asset.duration_seconds)}`
                : ''}
            </span>
          </span>
        </button>
      </li>
    )
  }

  return (
    <Modal
      open={open}
      title="Add media"
      description="Select files, then add them all to the timeline with Done."
      onClose={onClose}
      maxWidth="max-w-2xl"
      footer={
        <>
          <span className="mr-auto text-xs text-muted">
            {selected.size
              ? `${selected.size} selected`
              : 'Nothing selected yet'}
          </span>
          <button className="btn btn-ghost" onClick={onClose} disabled={adding}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={addSelected} disabled={adding}>
            {adding ? <Spinner /> : selected.size ? `Add ${selected.size} to timeline` : 'Done'}
          </button>
        </>
      }
    >
      <label className="panel mb-4 flex w-full cursor-pointer flex-col items-center gap-2 border-dashed px-4 py-5 text-center transition-colors hover:border-accent-line">
        <input
          type="file"
          multiple
          accept="video/*,audio/*,image/*"
          className="hidden"
          onChange={(event) => {
            upload(event.target.files)
            event.target.value = ''
          }}
        />
        {uploading ? <Spinner /> : <VideoIcon name="plus" className="h-6 w-6 text-muted" />}
        <span className="text-sm font-medium text-body">
          {uploading ? 'Uploading…' : 'Upload video, audio or images'}
        </span>
      </label>

      <div className="mb-3 flex flex-wrap gap-1.5">
        {PICKER_TABS.map((entry) => (
          <button
            key={entry.key}
            type="button"
            className={`btn btn-sm ${tab === entry.key ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setTab(entry.key)}
          >
            {entry.label}
            <span className="tabular-nums text-xs opacity-70">{counts[entry.key] ?? 0}</span>
          </button>
        ))}
      </div>

      {loading && (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="skeleton h-12" />
          ))}
        </div>
      )}

      {!loading && items.length === 0 && uploads.length === 0 && (
        <p className="py-6 text-center text-sm text-muted">
          Your library is empty. Upload something above to get started.
        </p>
      )}

      {!loading &&
        (items.length > 0 || uploads.length > 0) &&
        libraryRows.length === 0 &&
        uploadRows.length === 0 && (
          <p className="py-4 text-center text-sm text-muted">
            Nothing {tab === 'all' ? 'here' : `of that type yet`}.
          </p>
        )}

      {!loading &&
        (libraryRows.length > 0 || uploadRows.length > 0) && (
          <ul className="flex max-h-80 flex-col gap-2 overflow-y-auto">
            {libraryRows.map(renderRow)}
            {uploadRows.length > 0 && (
              <li className="pt-2">
                <p className="px-1 text-xs font-bold uppercase tracking-wide text-muted">
                  Your image uploads
                </p>
              </li>
            )}
            {uploadRows.map(renderRow)}
          </ul>
        )}
    </Modal>
  )
}

export default function Editor() {
  const { id } = useParams()
  const projectId = Number(id)
  const navigate = useNavigate()
  const toast = useToast()

  const editor = useTimelineEditor(projectId)
  const [project, setProject] = useState(null)
  const [capabilities, setCapabilities] = useState(null)
  const [time, setTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [adding, setAdding] = useState(false)

  useEffect(() => {
    let cancelled = false
    api
      .getVideoProject(projectId)
      .then((data) => !cancelled && setProject(data))
      .catch(() => {})
    api
      .videoCapabilities()
      .then((data) => !cancelled && setCapabilities(data))
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [projectId])

  // Undo/redo shortcuts. Skipped while a field has focus so Ctrl+Z in a text
  // box undoes the typing, not the last clip move.
  useEffect(() => {
    function onKey(event) {
      const tag = event.target?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      if (!(event.metaKey || event.ctrlKey)) return

      if (event.key.toLowerCase() === 'z') {
        event.preventDefault()
        if (event.shiftKey) editor.redo()
        else editor.undo()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [editor])

  const duration = editor.summary?.duration_seconds || 0

  // Keep the playhead inside the video: deleting the last clip must not leave
  // it stranded past the end.
  useEffect(() => {
    if (time > duration) setTime(duration)
  }, [duration, time])

  // `quiet` lets the picker add several clips and toast once at the end
  // instead of one toast per clip.
  async function addFromLibrary(item, target, { quiet = false } = {}) {
    const added = await editor.addClip(target.track, {
      kind: target.kind,
      asset_id: item.id,
      duration: Math.min(target.duration, 60),
      label: item.title,
    })
    if (added && !quiet) toast.success(`Added “${item.title}”.`)
    return Boolean(added)
  }

  async function addText() {
    await editor.addClip('text', {
      kind: 'text',
      text: 'Your title',
      duration: 3,
    })
  }

  if (editor.loading) {
    return (
      <div className="mx-auto w-full max-w-7xl">
        <VideoPageHeader title="Editor" back="/video/projects" backLabel="Back to projects" />
        <div className="skeleton h-96" />
      </div>
    )
  }

  if (editor.error) {
    return (
      <div className="mx-auto w-full max-w-3xl">
        <VideoPageHeader title="Editor" back="/video/projects" backLabel="Back to projects" />
        <VideoEmptyState icon="alert" title="Could not open this project" description={editor.error} />
      </div>
    )
  }

  return (
    <div className="mx-auto w-full max-w-7xl">
      <VideoPageHeader
        title={project?.name || 'Editor'}
        subtitle={
          editor.saving
            ? 'Saving…'
            : editor.savedAt
              ? `Saved ${relativeTime(editor.savedAt)}`
              : 'Every change is saved automatically'
        }
        back={`/video/projects/${projectId}`}
        backLabel="Back to the project"
        actions={
          <>
            <button
              className="btn btn-ghost btn-sm"
              onClick={editor.undo}
              disabled={!editor.canUndo}
              title="Undo (Ctrl+Z)"
            >
              Undo
            </button>
            <button
              className="btn btn-ghost btn-sm"
              onClick={editor.redo}
              disabled={!editor.canRedo}
              title="Redo (Ctrl+Shift+Z)"
            >
              Redo
            </button>
            <button className="btn btn-secondary btn-sm" onClick={addText}>
              <VideoIcon name="captions" className="h-4 w-4" />
              Add text
            </button>
            <button className="btn btn-primary btn-sm" onClick={() => setAdding(true)}>
              <VideoIcon name="plus" className="h-4 w-4" />
              Add media
            </button>
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)_300px]">
        <div className="order-2 lg:order-1">
          <Inspector
            clip={editor.selected}
            asset={editor.assets.find((a) => a.id === editor.selected?.asset_id)}
            capabilities={capabilities}
            onUpdate={editor.updateClip}
            onDelete={editor.deleteClip}
            busy={editor.busy}
          />
        </div>

        <div className="order-1 lg:order-2">
          <div className="card p-4">
            <Preview
              tracks={editor.tracks}
              assets={editor.assets}
              placements={editor.placements}
              canvas={editor.canvas}
              duration={duration}
              time={time}
              playing={playing}
              onTime={setTime}
              onPlayingChange={setPlaying}
            />
          </div>
        </div>

        <div className="order-3">
          <ExportPanel
            projectId={projectId}
            projectName={project?.name}
            duration={duration}
            onOpenTimeline={() => {
              const missing = editor.tracks
                .flatMap((track) => track.clips)
                .find((clip) => clip.asset_id && !editor.assets.some((a) => a.id === clip.asset_id))
              if (missing) editor.setSelectedId(missing.id)
            }}
          />
        </div>
      </div>

      <div className="mt-4">
        <Timeline
          tracks={editor.tracks}
          assets={editor.assets}
          duration={duration}
          time={time}
          selectedId={editor.selectedId}
          onSelect={editor.setSelectedId}
          onSeek={(at) => {
            setPlaying(false)
            setTime(at)
          }}
          onMove={editor.moveClip}
          onTrim={editor.trimClip}
          onSplit={editor.splitClip}
          onDelete={editor.deleteClip}
          busy={editor.busy}
        />
      </div>

      <AddMediaModal
        open={adding}
        onClose={() => setAdding(false)}
        onAdd={addFromLibrary}
        projectId={projectId}
      />
    </div>
  )
}
