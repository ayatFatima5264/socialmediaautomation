import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../../lib/api.js'
import { useToast } from '../../context/ToastContext.jsx'
import { formatDuration, platformLabel } from '../../lib/video/format.js'
import VideoPageHeader, { VideoEmptyState } from '../../components/video/VideoPageHeader.jsx'
import VideoIcon from '../../components/video/VideoIcon.jsx'
import Modal from '../../components/video/Modal.jsx'
import Spinner from '../../components/Spinner.jsx'
import TemplatePreview from '../../components/video/TemplatePreview.jsx'

// ---------------------------------------------------------------------------
// The template library.
//
// A template is a starting point: picking one creates a real project with that
// canvas, caption style and storyboard, and opens it.
//
// **The card draws the template, not a picture of one.** `TemplatePreview`
// renders from the same definition the project is built from — the real ratio,
// the real colours, the caption bar the template actually burns in, the scene
// strip at real durations. So the preview cannot advertise a look the template
// does not produce, which is the only kind of preview worth showing when there
// is no rendered video behind it.
//
// Categories come from the templates themselves rather than a hardcoded tab
// list, so one added server-side appears here with no change.
// ---------------------------------------------------------------------------

const ROLE_LABELS = {
  hook: 'Hook',
  intro: 'Intro',
  point: 'Content',
  step: 'Step',
  proof: 'Proof',
  quote: 'Quote',
  product: 'Product',
  cta: 'CTA',
  outro: 'Outro',
}

const MEDIA_LABELS = {
  footage: 'Footage',
  image: 'Image',
  product: 'Product shot',
  screen: 'Screen recording',
  'b-roll': 'B-roll',
  'text-only': 'Text only',
  speaker: 'Speaker',
}

function TemplateCard({ template, onUse, onPreview, busy }) {
  const category = template.category_label || template.category

  return (
    <div className="card flex flex-col overflow-hidden">
      <button
        type="button"
        className="group relative flex h-40 items-center justify-center border-b border-line bg-inset p-3"
        onClick={() => onPreview(template)}
        aria-label={`Preview ${template.name}`}
      >
        <TemplatePreview template={template} className="h-full w-auto rounded-md shadow-sm" />
        <span className="absolute inset-0 flex items-center justify-center bg-black/0 opacity-0 transition group-hover:bg-black/30 group-hover:opacity-100">
          <span className="badge bg-white/95 text-slate-900">Preview</span>
        </span>
      </button>

      <div className="flex flex-1 flex-col gap-2 p-4">
        <div>
          <p className="font-semibold text-body">{template.name}</p>
          <p className="mt-1 text-sm leading-snug text-muted">{template.description}</p>
        </div>

        <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-2 text-xs text-muted">
          <span className="badge border border-line bg-inset text-muted">
            {platformLabel(template.platform)}
          </span>
          {/* Only when it says something the platform badge does not — most
              templates are categorised by their surface, so showing both put
              "YouTube YouTube" on half the grid. */}
          {category !== platformLabel(template.platform) && (
            <span className="badge border border-line bg-inset text-muted">{category}</span>
          )}
          <span className="tabular-nums">{template.aspect_ratio}</span>
          {template.scene_count > 0 && (
            <span>
              · {template.scene_count} {template.scene_count === 1 ? 'scene' : 'scenes'}
            </span>
          )}
          {template.estimated_seconds > 0 && (
            <span className="tabular-nums">
              · ≈ {formatDuration(template.estimated_seconds)}
            </span>
          )}
        </div>

        <div className="mt-2 flex gap-2">
          <button
            className="btn btn-secondary btn-sm flex-1"
            onClick={() => onPreview(template)}
          >
            Preview
          </button>
          <button
            className="btn btn-primary btn-sm flex-1"
            onClick={() => onUse(template)}
            disabled={busy}
          >
            {busy && <Spinner />}
            {busy ? 'Creating…' : 'Use template'}
          </button>
        </div>
      </div>
    </div>
  )
}

function PreviewModal({ template, detail, loading, onClose, onUse, busy }) {
  const shown = detail || template
  if (!template) return null

  const scenes = detail?.scenes || []
  const total = scenes.reduce((sum, scene) => sum + (scene.duration_seconds || 0), 0)

  return (
    <Modal
      open
      title={template.name}
      description={template.description}
      onClose={onClose}
      maxWidth="max-w-3xl"
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose}>
            Close
          </button>
          <button className="btn btn-primary" onClick={() => onUse(template)} disabled={busy}>
            {busy && <Spinner />}
            Use template
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-4 sm:flex-row">
        <div className="flex shrink-0 justify-center sm:w-56">
          <TemplatePreview
            template={shown}
            detailed
            className="max-h-72 w-auto rounded-lg shadow"
          />
        </div>

        <div className="min-w-0 flex-1">
          <div className="mb-3 flex flex-wrap gap-1.5 text-xs text-muted">
            <span className="badge border border-line bg-inset">
              {platformLabel(template.platform)}
            </span>
            <span className="badge border border-line bg-inset">{template.aspect_ratio}</span>
            <span className="badge border border-line bg-inset">
              {template.width}×{template.height}
            </span>
            {total > 0 && (
              <span className="badge border border-line bg-inset tabular-nums">
                ≈ {formatDuration(total)}
              </span>
            )}
            {detail?.music && (
              <span className="badge border border-line bg-inset capitalize">
                ♪ {detail.music.mood}
              </span>
            )}
          </div>

          {loading && <div className="skeleton h-32" />}

          {!loading && scenes.length === 0 && (
            <p className="text-sm text-muted">
              An empty canvas — no storyboard. You start from a blank timeline at
              this size.
            </p>
          )}

          {!loading && scenes.length > 0 && (
            <ol className="flex flex-col gap-2">
              {scenes.map((scene, index) => (
                <li
                  key={index}
                  className="panel flex flex-col gap-1 p-2.5"
                >
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-sm font-medium text-body">
                      {index + 1}. {scene.title}
                    </span>
                    {scene.role && (
                      <span className="badge border border-line bg-inset text-xs text-muted">
                        {ROLE_LABELS[scene.role] || scene.role}
                      </span>
                    )}
                    <span className="ml-auto text-xs tabular-nums text-muted">
                      {formatDuration(scene.duration_seconds || 0)}
                    </span>
                  </div>
                  {scene.prompt && (
                    <p className="text-xs italic leading-snug text-muted">
                      {scene.prompt}
                    </p>
                  )}
                  <div className="flex flex-wrap gap-1 text-[11px] text-muted">
                    {scene.media && <span>{MEDIA_LABELS[scene.media] || scene.media}</span>}
                    {scene.transition && <span>· {scene.transition}</span>}
                    {scene.animation && scene.animation !== 'none' && (
                      <span>· {scene.animation}</span>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          )}

          <p className="mt-3 text-xs text-muted">
            The grey lines are prompts, not script. They show in the editor to
            guide what you write and are never narrated or exported — every
            scene starts with no words in it.
          </p>
        </div>
      </div>
    </Modal>
  )
}

export default function Templates() {
  const navigate = useNavigate()
  const toast = useToast()
  const [params, setParams] = useSearchParams()

  const category = params.get('category') || ''
  const search = params.get('q') || ''

  const [templates, setTemplates] = useState([])
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busyKey, setBusyKey] = useState(null)

  const [previewing, setPreviewing] = useState(null)
  const [detail, setDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api
      .videoTemplates()
      .then((data) => {
        if (cancelled) return
        // The endpoint answers with an envelope ({templates, categories}), not
        // a bare list — unwrap it, or every consumer below iterates an object.
        setTemplates(data?.templates || [])
        setCategories(data?.categories || [])
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || 'Could not load the templates.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  function setParam(key, value) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  // Filtered here rather than refetched: the whole library is a couple of dozen
  // rows, and a round trip per keystroke would be slower than the typing.
  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return templates.filter((template) => {
      if (category && template.category !== category) return false
      if (!needle) return true
      return [
        template.name,
        template.description,
        template.category,
        template.category_label,
        platformLabel(template.platform),
      ]
        .filter(Boolean)
        .some((field) => field.toLowerCase().includes(needle))
    })
  }, [templates, category, search])

  async function openPreview(template) {
    setPreviewing(template)
    setDetail(null)
    setDetailLoading(true)
    try {
      setDetail(await api.videoTemplate(template.key))
    } catch {
      setDetail(null)
    } finally {
      setDetailLoading(false)
    }
  }

  async function use(template) {
    setBusyKey(template.key)
    try {
      const project = await api.createVideoProject({
        project_type: 'blank',
        template_key: template.key,
        platform: template.platform,
      })
      toast.success(`Created “${project.name}” from ${template.name}.`)
      navigate(`/video/projects/${project.id}`)
    } catch (err) {
      toast.error(err?.message || 'Could not create a project from that template.')
      setBusyKey(null)
    }
  }

  const counts = useMemo(() => {
    const map = {}
    for (const entry of categories) map[entry.key] = entry.count
    return map
  }, [categories])

  const tabs = categories.length
    ? categories
    : [...new Set(templates.map((t) => t.category))].map((key) => ({ key, label: key }))

  return (
    <div className="mx-auto w-full max-w-6xl">
      <VideoPageHeader
        title="Templates"
        subtitle="Ready-made starting points. Picking one creates a project you can edit."
        back="/video"
        backLabel="Back to Video Studio"
      />

      <div className="card mb-5 flex flex-col gap-3 p-3">
        <div className="relative">
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted">
            <VideoIcon name="search" className="h-4 w-4" />
          </span>
          <input
            className="input pl-9"
            placeholder="Search templates — a format, a platform, a purpose…"
            aria-label="Search templates"
            value={search}
            onChange={(event) => setParam('q', event.target.value)}
          />
        </div>

        {tabs.length > 1 && (
          <div className="flex flex-wrap gap-1.5">
            <button
              className={`btn btn-sm ${category === '' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setParam('category', '')}
            >
              All
              <span className="text-xs opacity-70 tabular-nums">{templates.length}</span>
            </button>
            {tabs.map((entry) => (
              <button
                key={entry.key}
                className={`btn btn-sm ${
                  category === entry.key ? 'btn-primary' : 'btn-secondary'
                }`}
                onClick={() => setParam('category', category === entry.key ? '' : entry.key)}
              >
                {entry.label || entry.key}
                {counts[entry.key] != null && (
                  <span className="text-xs opacity-70 tabular-nums">{counts[entry.key]}</span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {loading && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, index) => (
            <div key={index} className="skeleton h-80" />
          ))}
        </div>
      )}

      {!loading && error && (
        <VideoEmptyState icon="alert" title="Could not load templates" description={error} />
      )}

      {!loading && !error && visible.length === 0 && (
        <VideoEmptyState
          icon={search ? 'search' : 'layout'}
          title={search ? 'Nothing matches that' : 'No templates here'}
          description={search ? 'Try another word.' : 'Try another category.'}
        />
      )}

      {!loading && !error && visible.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {visible.map((template) => (
            <TemplateCard
              key={template.key}
              template={template}
              onUse={use}
              onPreview={openPreview}
              busy={busyKey === template.key}
            />
          ))}
        </div>
      )}

      {previewing && (
        <PreviewModal
          template={previewing}
          detail={detail}
          loading={detailLoading}
          busy={busyKey === previewing.key}
          onClose={() => setPreviewing(null)}
          onUse={use}
        />
      )}
    </div>
  )
}
