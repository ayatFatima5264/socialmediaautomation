import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../../lib/api.js'
import { useToast } from '../../context/ToastContext.jsx'
import { CREATE_MODES } from '../../lib/video/tools.js'
import VideoIcon, { tintClass } from '../../components/video/VideoIcon.jsx'
import VideoPageHeader from '../../components/video/VideoPageHeader.jsx'
import Spinner from '../../components/Spinner.jsx'

// ---------------------------------------------------------------------------
// Create Video — pick how to start, pick a format, get a project.
//
// Everything on this page is real: the modes are the backend's `project_type`
// values, the platforms come from `/api/video/capabilities` rather than from a
// copy in JavaScript, and the button posts to `/api/video/projects` and
// navigates to what comes back.
//
// Modes whose *generation* step is not built yet (AI Video, From Audio, …) are
// marked `ready: false` in the registry. They still create a real project of
// that type — which is genuinely useful, it opens on the right canvas — and the
// card says the generation part is coming rather than implying it will write a
// script. Offering them as though they were finished is the one thing this
// screen must not do.
// ---------------------------------------------------------------------------

function ModeCard({ mode, selected, onSelect }) {
  return (
    <button
      type="button"
      onClick={() => onSelect(mode.key)}
      aria-pressed={selected}
      className={`card flex flex-col items-center gap-2 p-4 text-center transition-all hover:shadow-[var(--shadow-pop)] ${
        selected ? 'ring-2 ring-accent' : ''
      }`}
      style={selected ? { borderColor: 'var(--accent)' } : undefined}
    >
      <span
        className={`grid h-11 w-11 place-items-center rounded-[10px] ${tintClass(mode.tint)}`}
      >
        <VideoIcon name={mode.icon} />
      </span>
      <span className="font-semibold text-body">{mode.name}</span>
      <span className="text-xs leading-snug text-muted">{mode.description}</span>
      {!mode.ready && (
        <span className="badge border border-line bg-inset text-muted">
          Setup only for now
        </span>
      )}
    </button>
  )
}

function PresetCard({ preset, selected, onSelect }) {
  return (
    <button
      type="button"
      onClick={() => onSelect(preset.key)}
      aria-pressed={selected}
      className={`card flex flex-col items-center gap-1.5 px-3 py-3 transition-all hover:shadow-[var(--shadow-pop)] ${
        selected ? 'ring-2 ring-accent' : ''
      }`}
      style={selected ? { borderColor: 'var(--accent)' } : undefined}
    >
      {/* The shape of the canvas, drawn at the preset's real ratio. It reads
          faster than "9:16" does and it cannot disagree with the numbers,
          because it is derived from them. */}
      <span
        className="rounded-[4px] border-2 border-current text-muted"
        style={{
          width: preset.width >= preset.height ? 34 : (34 * preset.width) / preset.height,
          height: preset.width >= preset.height ? (34 * preset.height) / preset.width : 34,
        }}
        aria-hidden="true"
      />
      <span className="text-center text-[13px] font-semibold leading-tight text-body">
        {preset.label}
      </span>
      <span className="text-[11px] tabular-nums text-muted">{preset.aspect_ratio}</span>
    </button>
  )
}

export default function CreateVideo() {
  const navigate = useNavigate()
  const toast = useToast()
  const [params] = useSearchParams()

  // A mode can be pre-selected by the caller — the Repurpose tool card links
  // here with ?mode=repurpose rather than duplicating this screen.
  const initialMode = params.get('mode')
  const [mode, setMode] = useState(
    CREATE_MODES.some((m) => m.key === initialMode) ? initialMode : 'blank',
  )
  const [platform, setPlatform] = useState('youtube_shorts')
  const [name, setName] = useState('')
  const [custom, setCustom] = useState({ width: 1080, height: 1080, fps: 30 })

  const [presets, setPresets] = useState([])
  const [limits, setLimits] = useState(null)
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    let cancelled = false
    api
      .videoCapabilities()
      .then((data) => {
        if (cancelled) return
        setPresets(data.presets || [])
        setLimits(data.limits || null)
      })
      .catch((err) => {
        if (!cancelled) toast.error(err?.message || 'Could not load the video formats.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [toast])

  const selectedPreset = useMemo(
    () => presets.find((p) => p.key === platform),
    [presets, platform],
  )
  const isCustom = platform === 'custom'

  async function create() {
    setCreating(true)
    try {
      const project = await api.createVideoProject({
        name: name.trim() || undefined,
        project_type: mode,
        platform,
        // Only sent for Custom; for every other preset the server's numbers
        // win, which is what keeps "TikTok" from meaning two different canvases.
        ...(isCustom
          ? {
              width: Number(custom.width) || 1080,
              height: Number(custom.height) || 1080,
              fps: Number(custom.fps) || 30,
            }
          : {}),
      })
      toast.success(`Created “${project.name}”.`)
      navigate(`/video/projects/${project.id}`)
    } catch (err) {
      toast.error(err?.message || 'Could not create that project.')
      setCreating(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-4xl">
      <VideoPageHeader
        title="Create Video"
        subtitle="Choose how you want to start."
        back="/video"
        backLabel="Back to Video Studio"
      />

      <section className="mb-7">
        <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-body">
          How do you want to start?
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {CREATE_MODES.map((item) => (
            <ModeCard
              key={item.key}
              mode={item}
              selected={mode === item.key}
              onSelect={(key) => {
                // A mode with its own screen goes there instead of being
                // selected here — see `to` in CREATE_MODES.
                const target = CREATE_MODES.find((m) => m.key === key)?.to
                if (target) navigate(target)
                else setMode(key)
              }}
            />
          ))}
        </div>
      </section>

      <section className="mb-7">
        <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-body">
          Platform &amp; format
        </h2>

        {loading ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
            {Array.from({ length: 7 }).map((_, index) => (
              <div key={index} className="skeleton h-24" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
            {presets.map((preset) => (
              <PresetCard
                key={preset.key}
                preset={preset}
                selected={platform === preset.key}
                onSelect={setPlatform}
              />
            ))}
          </div>
        )}

        {selectedPreset && !isCustom && (
          <p className="mt-3 text-sm text-muted">
            {selectedPreset.description}{' '}
            <span className="tabular-nums">
              {selectedPreset.width}×{selectedPreset.height}, {selectedPreset.fps}fps
            </span>
          </p>
        )}

        {isCustom && (
          <div className="panel mt-3 grid grid-cols-1 gap-3 p-4 sm:grid-cols-3">
            {[
              { key: 'width', label: 'Width (px)', min: 64, max: 7680 },
              { key: 'height', label: 'Height (px)', min: 64, max: 7680 },
              { key: 'fps', label: 'Frames per second', min: 1, max: 60 },
            ].map((field) => (
              <div key={field.key}>
                <label className="label" htmlFor={`custom-${field.key}`}>
                  {field.label}
                </label>
                <input
                  id={`custom-${field.key}`}
                  type="number"
                  className="input"
                  min={field.min}
                  max={field.max}
                  value={custom[field.key]}
                  onChange={(event) =>
                    setCustom((c) => ({ ...c, [field.key]: event.target.value }))
                  }
                />
              </div>
            ))}
            {limits && (
              <p className="text-xs text-muted sm:col-span-3">
                Anything above {limits.max_resolution_height}p is scaled down to fit
                the current render limit.
              </p>
            )}
          </div>
        )}
      </section>

      <section className="mb-7">
        <label className="label" htmlFor="project-name">
          Project name <span className="font-normal text-muted">(optional)</span>
        </label>
        <input
          id="project-name"
          className="input max-w-md"
          placeholder="Untitled project"
          value={name}
          maxLength={200}
          onChange={(event) => setName(event.target.value)}
        />
      </section>

      <div className="flex flex-wrap items-center gap-3">
        <button className="btn btn-primary" onClick={create} disabled={creating || loading}>
          {creating && <Spinner />}
          {creating ? 'Creating…' : 'Create project'}
        </button>
        <button
          className="btn btn-ghost"
          onClick={() => navigate('/video')}
          disabled={creating}
        >
          Cancel
        </button>
      </div>

      {limits && (
        <p className="mt-4 text-xs text-muted">{limits.reason}</p>
      )}
    </div>
  )
}
