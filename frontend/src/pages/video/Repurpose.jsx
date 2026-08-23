import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api.js'
import { useToast } from '../../context/ToastContext.jsx'
import VideoPageHeader, { VideoEmptyState } from '../../components/video/VideoPageHeader.jsx'
import VideoIcon from '../../components/video/VideoIcon.jsx'
import Spinner from '../../components/Spinner.jsx'
import { formatDuration } from '../../lib/video/format.js'

// ---------------------------------------------------------------------------
// Smart Repurpose — pick a long video, review the clips, then create them.
//
// **Three steps, and the middle one is the point.** The moments are proposed,
// shown with their timings and hooks, and every field is editable *before* any
// project exists. Nothing is rendered here and nothing is published: creating
// the shorts opens them in the editor, which is where the user decides what to
// export.
//
// The clips are shown as a list with their source range, not as a set of
// finished-looking cards. What the user is checking is whether the cut lands
// in the right place, and a thumbnail does not tell them that — the timings
// and the transcript do.
// ---------------------------------------------------------------------------

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
    </label>
  )
}

function MomentCard({ moment, index, duration, onChange, onRemove, disabled }) {
  const length = moment.end - moment.start
  const tooLong = length > 90
  const tooShort = length < 15

  return (
    <li className="panel flex flex-col gap-3 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="badge border border-line bg-inset text-muted">
          {index + 1}
        </span>
        <input
          className="input min-w-0 flex-1 font-medium"
          value={moment.title}
          onChange={(event) => onChange({ title: event.target.value })}
          placeholder="Clip title"
        />
        <span
          className={`badge shrink-0 border ${
            tooLong || tooShort
              ? 'border-amber-300 bg-amber-50 text-amber-800'
              : 'border-line bg-inset text-muted'
          }`}
        >
          {formatDuration(length)}
        </span>
        <button
          className="btn btn-ghost btn-sm shrink-0 px-2"
          onClick={onRemove}
          disabled={disabled}
          aria-label="Remove this clip"
        >
          <VideoIcon name="trash" className="h-3.5 w-3.5" />
        </button>
      </div>

      {moment.reason && (
        <p className="text-xs italic text-muted">{moment.reason}</p>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Starts at">
          <input
            className="input"
            type="number"
            step="0.5"
            min="0"
            max={duration}
            value={moment.start}
            onChange={(event) => onChange({ start: Number(event.target.value) })}
          />
        </Field>
        <Field label="Ends at">
          <input
            className="input"
            type="number"
            step="0.5"
            min="0"
            max={duration}
            value={moment.end}
            onChange={(event) => onChange({ end: Number(event.target.value) })}
          />
        </Field>
      </div>

      <Field label="Hook — the first thing on screen">
        <input
          className="input"
          value={moment.hook}
          onChange={(event) => onChange({ hook: event.target.value })}
        />
      </Field>

      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Call to action">
          <input
            className="input"
            value={moment.cta}
            onChange={(event) => onChange({ cta: event.target.value })}
          />
        </Field>
        <Field label="Framing">
          <input
            type="range"
            min="-0.5"
            max="0.5"
            step="0.02"
            value={moment.focus_x}
            onChange={(event) => onChange({ focus_x: Number(event.target.value) })}
            className="w-full accent-[var(--accent)]"
            aria-label="Horizontal framing"
          />
          <span className="text-xs text-muted">
            {moment.focus_x === 0
              ? 'Centred'
              : moment.focus_x < 0
                ? 'Shifted left'
                : 'Shifted right'}
          </span>
        </Field>
      </div>

      {(tooLong || tooShort) && (
        <p className="text-xs text-amber-700">
          {tooLong
            ? 'Longer than 90 seconds — it will be skipped for platforms with a shorter limit.'
            : 'Under 15 seconds — there is not much room for a hook and a payoff.'}
        </p>
      )}

      {moment.transcript && (
        <details>
          <summary className="cursor-pointer text-xs text-muted">
            What is said here
          </summary>
          <p className="mt-1 text-xs leading-relaxed text-muted">
            {moment.transcript}
          </p>
        </details>
      )}
    </li>
  )
}

export default function Repurpose() {
  const toast = useToast()

  const [options, setOptions] = useState(null)
  const [sources, setSources] = useState([])
  const [assetId, setAssetId] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [moments, setMoments] = useState([])
  const [targets, setTargets] = useState(['youtube_shorts'])
  const [analyzing, setAnalyzing] = useState(false)
  const [creating, setCreating] = useState(false)
  const [created, setCreated] = useState(null)
  const [uploading, setUploading] = useState(false)

  const loadSources = useCallback(async () => {
    try {
      const data = await api.mediaLibrary({ filter: 'video', limit: 100 })
      setSources(data.items || [])
    } catch {
      // The picker being empty is visible on its own.
    }
  }, [])

  useEffect(() => {
    api.repurposeTargets().then(setOptions).catch(() => {})
    loadSources()
  }, [loadSources])

  async function upload(files) {
    const file = Array.from(files || [])[0]
    if (!file) return
    setUploading(true)
    try {
      const asset = await api.uploadVideoMedia(file, { kind: 'video' })
      await loadSources()
      setAssetId(asset.id)
    } catch (err) {
      toast.error(err?.message || 'That file could not be uploaded.')
    } finally {
      setUploading(false)
    }
  }

  async function analyze() {
    if (!assetId) return
    setAnalyzing(true)
    setCreated(null)
    try {
      const result = await api.analyzeForRepurpose(assetId, { count: 5 })
      setAnalysis(result)
      setMoments(result.moments || [])
      if (!result.moments?.length) {
        toast.error('No sections long enough to cut were found in that video.')
      }
    } catch (err) {
      toast.error(err?.message || 'That video could not be analysed.')
    } finally {
      setAnalyzing(false)
    }
  }

  async function create() {
    if (!assetId || !moments.length || !targets.length) return
    setCreating(true)
    try {
      const result = await api.createShorts({
        asset_id: assetId,
        moments,
        targets,
      })
      setCreated(result)
      toast.success(
        `Created ${result.shorts.length} project${
          result.shorts.length === 1 ? '' : 's'
        }. Nothing has been exported.`,
      )
    } catch (err) {
      toast.error(err?.message || 'Those clips could not be created.')
    } finally {
      setCreating(false)
    }
  }

  const selected = sources.find((row) => row.id === assetId)

  return (
    <div className="mx-auto w-full max-w-4xl">
      <VideoPageHeader
        title="Smart Repurpose"
        subtitle="Turn a long video into shorts. You review every clip before anything is made."
        back="/video"
        backLabel="Back to Video Studio"
      />

      {options?.transcription_available === false && (
        <div className="card mb-4 border-amber-300 bg-amber-50 p-4">
          <p className="text-sm text-amber-900">
            No transcription provider is configured on this server, so the
            sections cannot be found automatically.
          </p>
        </div>
      )}

      {/* ---- 1. The source ---- */}
      <div className="card mb-4 flex flex-col gap-3 p-4">
        <h2 className="font-semibold text-body">1. The long video</h2>

        <label className="panel flex w-full cursor-pointer flex-col items-center gap-2 border-dashed px-4 py-5 text-center transition-colors hover:border-accent-line">
          <input
            type="file"
            accept="video/*"
            className="hidden"
            onChange={(event) => {
              upload(event.target.files)
              event.target.value = ''
            }}
          />
          {uploading ? <Spinner /> : <VideoIcon name="film" className="h-5 w-5 text-muted" />}
          <span className="text-sm font-medium text-body">
            {uploading ? 'Uploading…' : 'Upload a video'}
          </span>
        </label>

        {sources.length > 0 && (
          <Field label="…or pick one you already have">
            <select
              className="select"
              value={assetId ?? ''}
              onChange={(event) =>
                setAssetId(event.target.value ? Number(event.target.value) : null)
              }
            >
              <option value="">Choose a video…</option>
              {sources.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.title}
                  {row.duration_seconds
                    ? ` — ${formatDuration(row.duration_seconds)}`
                    : ''}
                </option>
              ))}
            </select>
          </Field>
        )}

        <button
          className="btn btn-primary self-start"
          onClick={analyze}
          disabled={!assetId || analyzing}
        >
          {analyzing ? <Spinner /> : <VideoIcon name="scissors" className="h-4 w-4" />}
          {analyzing ? 'Finding the good bits…' : 'Find the clips'}
        </button>

        {selected && !analysis && (
          <p className="text-xs text-muted">
            Transcribing a long video takes a moment. Nothing is created yet.
          </p>
        )}
      </div>

      {/* ---- 2. Review ---- */}
      {analysis && (
        <div className="card mb-4 flex flex-col gap-3 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold text-body">2. Review the clips</h2>
            <span className="text-xs text-muted">
              {formatDuration(analysis.duration_seconds)} source
              {analysis.cached ? ' · using the saved transcript' : ''}
            </span>
          </div>

          {analysis.overlaps?.length > 0 && (
            <p className="rounded-[10px] border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              Some clips cover the same footage. That is fine if you meant it —
              adjust the times if you did not.
            </p>
          )}

          {moments.length === 0 ? (
            <VideoEmptyState
              icon="scissors"
              title="No clips proposed"
              description="Nothing in this video was long enough to stand alone."
            />
          ) : (
            <ul className="flex flex-col gap-3">
              {moments.map((moment, index) => (
                <MomentCard
                  key={index}
                  moment={moment}
                  index={index}
                  duration={analysis.duration_seconds}
                  disabled={creating}
                  onChange={(patch) =>
                    setMoments((current) =>
                      current.map((row, i) => (i === index ? { ...row, ...patch } : row)),
                    )
                  }
                  onRemove={() =>
                    setMoments((current) => current.filter((_, i) => i !== index))
                  }
                />
              ))}
            </ul>
          )}
        </div>
      )}

      {/* ---- 3. Create ---- */}
      {analysis && moments.length > 0 && (
        <div className="card flex flex-col gap-3 p-4">
          <h2 className="font-semibold text-body">3. Make the projects</h2>

          <Field label="For which platforms">
            <div className="flex flex-wrap gap-2">
              {(options?.targets || []).map((entry) => {
                const on = targets.includes(entry.key)
                return (
                  <button
                    key={entry.key}
                    type="button"
                    onClick={() =>
                      setTargets((current) =>
                        on
                          ? current.filter((key) => key !== entry.key)
                          : [...current, entry.key],
                      )
                    }
                    className={`btn btn-sm ${on ? 'btn-primary' : 'btn-secondary'}`}
                  >
                    {entry.label}
                    <span className="text-xs opacity-70">
                      ≤{entry.max_seconds}s
                    </span>
                  </button>
                )
              })}
            </div>
          </Field>

          <p className="text-xs text-muted">
            This creates {moments.length * targets.length} new project
            {moments.length * targets.length === 1 ? '' : 's'}. Your original
            video and project are not changed, and nothing is exported or
            posted.
          </p>

          <button
            className="btn btn-primary self-start"
            onClick={create}
            disabled={creating || !targets.length}
          >
            {creating && <Spinner />}
            Create the projects
          </button>
        </div>
      )}

      {/* ---- Results ---- */}
      {created && (
        <div className="card mt-4 p-4">
          <h2 className="mb-3 font-semibold text-body">
            {created.shorts.length} project
            {created.shorts.length === 1 ? '' : 's'} ready to edit
          </h2>

          <ul className="flex flex-col gap-2">
            {created.shorts.map((short) => (
              <li key={short.project_id}>
                <Link
                  to={short.editor_path}
                  className="panel flex items-center gap-3 px-3 py-2.5 transition-colors hover:border-accent-line"
                >
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-inset text-muted">
                    <VideoIcon name="timeline" className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium text-body">
                      {short.name}
                    </span>
                    <span className="block text-xs text-muted">
                      {short.aspect_ratio} · {formatDuration(short.duration_seconds)}
                    </span>
                  </span>
                  <span className="badge border border-line bg-inset text-muted">
                    Open
                  </span>
                </Link>
              </li>
            ))}
          </ul>

          {created.skipped?.length > 0 && (
            <div className="mt-3 rounded-[10px] border border-amber-300 bg-amber-50 px-3 py-2">
              <p className="text-xs font-medium text-amber-900">
                {created.skipped.length} were skipped:
              </p>
              <ul className="mt-1 list-disc pl-5 text-xs text-amber-800">
                {created.skipped.map((entry, index) => (
                  <li key={index}>
                    {entry.title} for {entry.target} — {entry.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
