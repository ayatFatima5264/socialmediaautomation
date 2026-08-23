import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../../lib/api.js'
import { useToast } from '../../context/ToastContext.jsx'
import VideoPageHeader, { VideoEmptyState } from '../../components/video/VideoPageHeader.jsx'
import VideoIcon from '../../components/video/VideoIcon.jsx'
import Spinner from '../../components/Spinner.jsx'
import { formatBytes, formatDuration, platformLabel } from '../../lib/video/format.js'
import { safeFilename, saveBlob } from '../../lib/video/download.js'

// ---------------------------------------------------------------------------
// Export, formats and publishing — the end of the pipeline.
//
// Three panels, in the order somebody actually works through them:
//
//   1. Render    the current export, with its real phase and progress
//   2. Download  every deliverable, and for the ones that are not ready, why
//   3. Reuse     convert to another format, or hand off to a draft post
//
// **Progress is the server's.** The bar reads `progress` and `phase_label` off
// the render row, both written from ffmpeg's own reported position. Nothing
// here advances on a timer.
//
// **Nothing on this page publishes.** "Prepare post" creates a draft and takes
// you to the composer. That is the confirmation step, and it belongs to the
// person, not to this screen.
// ---------------------------------------------------------------------------

const POLL_MS = 1200
const TERMINAL = ['completed', 'failed', 'cancelled']

const GROUP_LABELS = {
  video: 'Video',
  subtitles: 'Subtitles',
  audio: 'Audio',
  thumbnail: 'Thumbnail',
}

function recovery(code) {
  switch (code) {
    case 'missing_asset':
      return 'Replace or remove the missing clip on the timeline, then export again.'
    case 'storage_error':
      return 'The file store could not be reached. Trying again usually works.'
    case 'limit_exceeded':
      return 'Shorten the video, or lower the resolution, and try again.'
    case 'invalid_timeline':
      return 'Add something to the timeline before exporting.'
    case 'timeout':
      return 'The render took too long. A shorter video or draft quality will finish.'
    case 'interrupted':
      return 'The server restarted mid-render. Exporting again should work.'
    default:
      return 'Try again. If it keeps failing, the details above are what to report.'
  }
}

export default function ExportProject() {
  const { id } = useParams()
  const projectId = Number(id)
  const navigate = useNavigate()
  const toast = useToast()

  const [manifest, setManifest] = useState(null)
  const [render, setRender] = useState(null)
  const [formats, setFormats] = useState(null)
  const [targets, setTargets] = useState(null)

  const [quality, setQuality] = useState('standard')
  const [busy, setBusy] = useState(null)
  const [converting, setConverting] = useState(null)
  const [caption, setCaption] = useState('')
  const [publishing, setPublishing] = useState(null)

  const reload = useCallback(async () => {
    try {
      const [exports, renders, formatList, publish] = await Promise.all([
        api.exportManifest(projectId),
        api.listRenders(projectId),
        api.projectFormats(projectId),
        api.publishTargets(projectId),
      ])
      setManifest(exports)
      setRender(renders.active || renders.renders?.[0] || null)
      setFormats(formatList)
      setTargets(publish)
    } catch (err) {
      toast.error(err?.message || 'Could not load this project.')
    }
  }, [projectId, toast])

  useEffect(() => {
    reload()
  }, [reload])

  // Poll only while a render is actually running.
  useEffect(() => {
    if (!render || TERMINAL.includes(render.status)) return undefined

    const timer = setInterval(async () => {
      try {
        const next = await api.getRender(render.id)
        setRender(next)
        if (TERMINAL.includes(next.status)) {
          clearInterval(timer)
          reload()
          if (next.status === 'completed') toast.success('Your video is ready.')
        }
      } catch {
        // A dropped poll is not a failed render.
      }
    }, POLL_MS)

    return () => clearInterval(timer)
  }, [render, reload, toast])

  async function startRender() {
    setBusy('render')
    try {
      setRender(await api.startRender(projectId, { quality }))
    } catch (err) {
      toast.error(err?.message || 'Could not start the export.')
    } finally {
      setBusy(null)
    }
  }

  async function download(kind) {
    setBusy(kind)
    try {
      const blob = await api.downloadExport(projectId, kind)
      saveBlob(blob, `${safeFilename(manifest?.project_name, 'video')}.${kind}`)
    } catch (err) {
      toast.error(err?.message || 'Could not download that file.')
    } finally {
      setBusy(null)
    }
  }

  async function convert(target) {
    setConverting(target.key)
    try {
      const result = await api.convertProject(projectId, { target: target.key })
      toast.success(`Created “${result.name}”. This project is unchanged.`)
      navigate(result.editor_path)
    } catch (err) {
      toast.error(err?.message || 'Could not convert that project.')
    } finally {
      setConverting(null)
    }
  }

  async function prepare(platform) {
    setPublishing(platform)
    try {
      const post = await api.prepareVideoPost(projectId, {
        platform,
        caption: caption.trim() || undefined,
      })
      toast.success('Draft created. Review it before posting.')
      navigate(post.review_path)
    } catch (err) {
      toast.error(err?.message || 'Could not prepare that post.')
    } finally {
      setPublishing(null)
    }
  }

  if (!manifest) {
    return (
      <div className="mx-auto w-full max-w-4xl">
        <VideoPageHeader title="Export" back="/video/projects" backLabel="Back to projects" />
        <div className="skeleton h-64" />
      </div>
    )
  }

  const running = render && !TERMINAL.includes(render.status)
  const groups = ['video', 'subtitles', 'audio', 'thumbnail']

  return (
    <div className="mx-auto w-full max-w-4xl">
      <VideoPageHeader
        title="Export and publish"
        subtitle={`${manifest.project_name} · ${platformLabel(manifest.platform)} · ${
          manifest.aspect_ratio
        } · ${formatDuration(manifest.duration_seconds)}`}
        back={`/video/projects/${projectId}/edit`}
        backLabel="Back to the editor"
      />

      {/* ---- 1. Render ---- */}
      <div className="card mb-4 flex flex-col gap-3 p-4">
        <h2 className="font-semibold text-body">Render</h2>

        {running && (
          <>
            <div>
              <div className="mb-1 flex items-center justify-between text-sm">
                <span className="text-body">{render.phase_label}</span>
                <span className="tabular-nums text-muted">
                  {Math.round((render.progress || 0) * 100)}%
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-inset">
                <div
                  className="h-full rounded-full bg-accent transition-[width] duration-500"
                  style={{ width: `${Math.round((render.progress || 0) * 100)}%` }}
                />
              </div>
            </div>
            <button
              className="btn btn-secondary btn-sm self-start"
              onClick={async () => {
                setRender(await api.cancelRender(render.id))
              }}
            >
              Cancel
            </button>
          </>
        )}

        {!running && (
          <div className="flex flex-wrap items-end gap-3">
            <label className="block">
              <span className="label">Quality</span>
              <select
                className="select w-48"
                value={quality}
                onChange={(event) => setQuality(event.target.value)}
              >
                <option value="draft">Draft — fastest</option>
                <option value="standard">Standard</option>
                <option value="high">High — best</option>
              </select>
            </label>
            <button
              className="btn btn-primary"
              onClick={startRender}
              disabled={busy === 'render' || manifest.duration_seconds <= 0}
            >
              {busy === 'render' ? <Spinner /> : <VideoIcon name="film" className="h-4 w-4" />}
              {render?.status === 'completed' ? 'Render again' : 'Render video'}
            </button>
            {render && (
              <span
                className={`badge border ${
                  render.status === 'completed'
                    ? 'badge-accent'
                    : render.status === 'failed'
                      ? 'border-rose-300 bg-rose-50 text-rose-700'
                      : 'border-line bg-inset text-muted'
                }`}
              >
                {render.phase_label}
              </span>
            )}
          </div>
        )}

        {render?.status === 'failed' && (
          <div className="rounded-[10px] border border-rose-300 bg-rose-50 px-3 py-2">
            <p className="whitespace-pre-wrap text-xs text-rose-700">{render.error}</p>
            <p className="mt-2 text-xs text-rose-700">{recovery(render.error_code)}</p>
            <button
              className="btn btn-primary btn-sm mt-2"
              onClick={async () => setRender(await api.retryRender(render.id))}
            >
              Try again
            </button>
          </div>
        )}
      </div>

      {/* ---- 2. Download ---- */}
      <div className="card mb-4 p-4">
        <h2 className="mb-3 font-semibold text-body">Download</h2>
        <div className="flex flex-col gap-4">
          {groups.map((group) => {
            const items = manifest.items.filter((entry) => entry.group === group)
            if (!items.length) return null
            return (
              <div key={group}>
                <p className="mb-2 text-xs font-bold uppercase tracking-wide text-muted">
                  {GROUP_LABELS[group]}
                </p>
                <ul className="flex flex-col gap-2">
                  {items.map((entry) => (
                    <li
                      key={entry.kind}
                      className="panel flex flex-wrap items-center gap-3 px-3 py-2.5"
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block font-medium text-body">{entry.label}</span>
                        <span className="block text-xs text-muted">
                          {entry.available
                            ? entry.description +
                              (entry.size_bytes ? ` · ${formatBytes(entry.size_bytes)}` : '')
                            : entry.reason}
                        </span>
                      </span>
                      <button
                        className="btn btn-secondary btn-sm shrink-0"
                        disabled={!entry.available || busy === entry.kind}
                        onClick={() => download(entry.kind)}
                      >
                        {busy === entry.kind && <Spinner />}
                        {entry.kind.toUpperCase()}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}
        </div>
      </div>

      {/* ---- 3a. Other formats ---- */}
      {formats?.formats?.length > 0 && (
        <div className="card mb-4 p-4">
          <h2 className="font-semibold text-body">Make another format</h2>
          <p className="mb-3 text-sm text-muted">
            Creates a new project, reframed for the new shape. This one is not
            changed.
          </p>
          <ul className="grid gap-2 sm:grid-cols-2">
            {formats.formats.map((entry) => (
              <li key={entry.key}>
                <button
                  type="button"
                  disabled={!entry.fits || converting !== null}
                  onClick={() => convert(entry)}
                  className="panel flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:border-accent-line disabled:opacity-60"
                  title={entry.reason || entry.description}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block font-medium text-body">{entry.label}</span>
                    <span className="block text-xs text-muted">
                      {entry.fits
                        ? `${entry.aspect_ratio} · ${entry.width}×${entry.height}`
                        : entry.reason}
                    </span>
                  </span>
                  {converting === entry.key && <Spinner />}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ---- 3b. Publishing ---- */}
      <div className="card p-4">
        <h2 className="font-semibold text-body">Publish</h2>
        <p className="mb-3 text-sm text-muted">
          This creates a <strong>draft post</strong> with the video attached. It
          is never posted without you confirming it.
        </p>

        {!targets?.ready && (
          <p className="rounded-[10px] border border-line bg-inset px-3 py-2 text-sm text-muted">
            {targets?.reason || 'Render the video first.'}
          </p>
        )}

        {targets?.ready && (
          <>
            <label className="mb-3 block">
              <span className="label">Caption</span>
              <textarea
                className="input min-h-[70px] resize-y"
                value={caption}
                placeholder="Leave blank to use the project's own script."
                onChange={(event) => setCaption(event.target.value)}
              />
            </label>

            <ul className="flex flex-col gap-2">
              {targets.targets.map((entry) => (
                <li
                  key={entry.platform}
                  className="panel flex flex-wrap items-center gap-3 px-3 py-2.5"
                >
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2 font-medium text-body">
                      {entry.label}
                      {entry.suggested && (
                        <span className="badge badge-accent">Made for this</span>
                      )}
                    </span>
                    {entry.reason && (
                      <span className="block text-xs text-muted">{entry.reason}</span>
                    )}
                  </span>
                  <button
                    className="btn btn-secondary btn-sm shrink-0"
                    disabled={!entry.connected || publishing !== null}
                    onClick={() => prepare(entry.platform)}
                  >
                    {publishing === entry.platform && <Spinner />}
                    Prepare post
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}

        {targets?.export_only?.length > 0 && (
          <div className="mt-3 rounded-[10px] border border-line bg-inset px-3 py-2">
            <p className="text-xs text-muted">
              <strong>
                {targets.export_only.map((key) => platformLabel(key)).join(', ')}
              </strong>{' '}
              — {targets.export_only_note}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
