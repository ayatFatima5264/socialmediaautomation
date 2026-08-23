import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../../lib/api.js'
import { useToast } from '../../../context/ToastContext.jsx'
import { safeFilename, saveBlob } from '../../../lib/video/download.js'
import Spinner from '../../Spinner.jsx'
import VideoIcon from '../VideoIcon.jsx'

// ---------------------------------------------------------------------------
// Export: queue a render, watch it, and deal with it failing.
//
// **Progress is the server's, not a guess.** The bar reads `progress` and
// `stage` off the render row, which the worker writes from ffmpeg's own
// reported position. Nothing here advances on a timer — a bar that moves while
// nothing is happening turns a hung render into one that appears to be working.
//
// **A failure is actionable or it is not worth showing.** `error_code` decides
// what is offered: a missing clip sends the user back to the timeline, a
// storage problem offers a retry, an encoder failure shows the log. "Render
// failed" with a spinner that stops is the thing this panel exists to avoid.
//
// Retry creates a *new* attempt that snapshots the timeline as it is now,
// which is what makes "fix the missing clip, then retry" actually work.
// ---------------------------------------------------------------------------

const POLL_MS = 1200

const STAGE_LABELS = {
  queued: 'Waiting for a slot',
  preparing: 'Checking the timeline',
  downloading: 'Gathering your media',
  scenes: 'Building the picture',
  audio: 'Mixing the audio',
  subtitles: 'Drawing the captions',
  encoding: 'Encoding',
  uploading: 'Saving the file',
  done: 'Finished',
}

/** What to offer for a given failure. The message itself comes from the
 *  server; this is only the next step. */
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

export default function ExportPanel({ projectId, projectName, duration, onOpenTimeline }) {
  const toast = useToast()
  const [render, setRender] = useState(null)
  const [history, setHistory] = useState([])
  const [quality, setQuality] = useState('standard')
  const [starting, setStarting] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const pollRef = useRef(null)

  const refresh = useCallback(async () => {
    if (!projectId) return
    try {
      const data = await api.listRenders(projectId)
      setHistory(data.renders || [])
      // The active job if there is one, otherwise the most recent — so a
      // finished export stays on screen with its download button.
      setRender(data.active || data.renders?.[0] || null)
    } catch {
      // A failed poll is not worth a toast; the next one will report.
    }
  }, [projectId])

  useEffect(() => {
    refresh()
  }, [refresh])

  // Poll only while something is actually running. A finished render is not
  // going to change, and polling it forever is a request every second for the
  // life of the tab.
  useEffect(() => {
    const running = render && !['completed', 'failed', 'cancelled'].includes(render.status)
    if (!running) {
      clearInterval(pollRef.current)
      return undefined
    }

    pollRef.current = setInterval(async () => {
      try {
        const next = await api.getRender(render.id)
        setRender(next)
        if (['completed', 'failed', 'cancelled'].includes(next.status)) {
          clearInterval(pollRef.current)
          refresh()
          if (next.status === 'completed') toast.success('Your video is ready.')
        }
      } catch {
        // Keep polling — a dropped request is not a failed render.
      }
    }, POLL_MS)

    return () => clearInterval(pollRef.current)
  }, [render, refresh, toast])

  async function start() {
    setStarting(true)
    try {
      setRender(await api.startRender(projectId, { quality }))
    } catch (err) {
      toast.error(err?.message || 'Could not start the export.')
    } finally {
      setStarting(false)
    }
  }

  async function retry() {
    setStarting(true)
    try {
      setRender(await api.retryRender(render.id))
    } catch (err) {
      toast.error(err?.message || 'Could not start another export.')
    } finally {
      setStarting(false)
    }
  }

  async function cancel() {
    try {
      setRender(await api.cancelRender(render.id))
    } catch (err) {
      toast.error(err?.message || 'Could not cancel that export.')
    }
  }

  async function download() {
    setDownloading(true)
    try {
      const blob = await api.downloadRender(render.id)
      saveBlob(blob, `${safeFilename(projectName, 'video')}.mp4`)
    } catch (err) {
      toast.error(err?.message || 'Could not download that video.')
    } finally {
      setDownloading(false)
    }
  }

  const running =
    render && !['completed', 'failed', 'cancelled'].includes(render.status)

  return (
    <div className="card p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="font-semibold text-body">Export</h2>
        <Link
          to={`/video/projects/${projectId}/export`}
          className="link-accent text-xs font-semibold"
        >
          All formats
        </Link>
      </div>

      {!running && (
        <div className="flex flex-col gap-3">
          <label className="block">
            <span className="label">Quality</span>
            <select
              className="select"
              value={quality}
              onChange={(event) => setQuality(event.target.value)}
            >
              <option value="draft">Draft — fastest, smallest</option>
              <option value="standard">Standard</option>
              <option value="high">High — slowest, best</option>
            </select>
          </label>

          <button
            className="btn btn-primary"
            onClick={start}
            disabled={starting || duration <= 0}
          >
            {starting ? <Spinner /> : <VideoIcon name="film" className="h-4 w-4" />}
            {starting ? 'Starting…' : 'Export video'}
          </button>

          {duration <= 0 && (
            <p className="text-xs text-muted">
              Add a clip to the timeline first.
            </p>
          )}
        </div>
      )}

      {running && (
        <div className="flex flex-col gap-3">
          <div>
            <div className="mb-1 flex items-center justify-between text-sm">
              <span className="text-body">
                {/* The server's own phase, derived from the stage the worker
                    wrote — not a label this component guesses at. */}
                {render.phase_label || STAGE_LABELS[render.stage] || render.stage}
              </span>
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
          <button className="btn btn-secondary btn-sm" onClick={cancel}>
            Cancel
          </button>
        </div>
      )}

      {render?.status === 'completed' && (
        <div className="mt-3 flex flex-col gap-3">
          <video
            src={render.output_url}
            controls
            preload="metadata"
            className="w-full rounded-[10px] bg-black"
          />
          <div className="flex flex-wrap gap-2">
            <button
              className="btn btn-primary btn-sm"
              onClick={download}
              disabled={downloading}
            >
              {downloading && <Spinner />}
              Download MP4
            </button>
            <button className="btn btn-secondary btn-sm" onClick={() => setRender(null)}>
              Export again
            </button>
          </div>
        </div>
      )}

      {render?.status === 'failed' && (
        <div className="mt-3 flex flex-col gap-3">
          <div className="rounded-[10px] border border-rose-300 bg-rose-50 px-3 py-2">
            <p className="text-sm font-medium text-rose-700">
              The export failed{render.error_stage ? ` while ${
                (STAGE_LABELS[render.error_stage] || render.error_stage).toLowerCase()
              }` : ''}.
            </p>
            <p className="mt-1 whitespace-pre-wrap text-xs text-rose-700/90">
              {render.error}
            </p>
            <p className="mt-2 text-xs text-rose-700">{recovery(render.error_code)}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="btn btn-primary btn-sm" onClick={retry} disabled={starting}>
              {starting && <Spinner />}
              Try again
            </button>
            {render.error_code === 'missing_asset' && (
              <button className="btn btn-secondary btn-sm" onClick={onOpenTimeline}>
                Go to the timeline
              </button>
            )}
          </div>
        </div>
      )}

      {render?.status === 'cancelled' && (
        <p className="mt-3 text-sm text-muted">That export was cancelled.</p>
      )}

      {history.length > 1 && (
        <details className="mt-4">
          <summary className="cursor-pointer text-xs text-muted">
            {history.length} export attempts
          </summary>
          <ul className="mt-2 flex flex-col gap-1">
            {history.map((row) => (
              <li key={row.id} className="flex items-center justify-between text-xs">
                <span className="text-muted">Attempt {row.attempt}</span>
                <span
                  className={
                    row.status === 'completed'
                      ? 'text-emerald-600'
                      : row.status === 'failed'
                        ? 'text-rose-600'
                        : 'text-muted'
                  }
                >
                  {row.status}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}
