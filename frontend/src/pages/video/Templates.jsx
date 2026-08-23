import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../lib/api.js'
import { useToast } from '../../context/ToastContext.jsx'
import { platformLabel } from '../../lib/video/format.js'
import VideoPageHeader, { VideoEmptyState } from '../../components/video/VideoPageHeader.jsx'
import Spinner from '../../components/Spinner.jsx'

// ---------------------------------------------------------------------------
// The template library.
//
// A template is a starting point: picking one creates a real project with that
// canvas, caption style and storyboard, and opens it. There is no preview
// artwork yet and the cards do not pretend there is — each shows the format
// and what the template actually contains, which is the information that
// decides the choice anyway.
//
// Categories come from the templates themselves rather than from a hardcoded
// tab list, so a category added server-side appears here with no change.
// ---------------------------------------------------------------------------

function TemplateCard({ template, onUse, busy }) {
  // The preview box is a fixed height on every card, with the canvas drawn at
  // its real ratio inside it. Sizing the box to the canvas instead makes a row
  // mixing 16:9 and 9:16 templates come out ragged, with the landscape cards'
  // titles sitting higher than their neighbours'.
  const vertical = template.height > template.width
  const frame = vertical
    ? { width: (74 * template.width) / template.height, height: 74 }
    : { width: 100, height: (100 * template.height) / template.width }

  return (
    <div className="card flex flex-col overflow-hidden">
      <div className="flex h-28 items-center justify-center border-b border-line bg-inset">
        {/* The canvas shape at its real ratio — the same device the format
            picker uses, so the two screens describe a format the same way. */}
        <span
          className="rounded-md border-2 border-current text-muted"
          style={{ width: frame.width, height: frame.height }}
          aria-hidden="true"
        />
      </div>

      <div className="flex flex-1 flex-col gap-2 p-4">
        <div>
          <p className="font-semibold text-body">{template.name}</p>
          <p className="mt-1 text-sm leading-snug text-muted">{template.description}</p>
        </div>

        <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-2 text-xs text-muted">
          <span className="badge border border-line bg-inset text-muted">
            {platformLabel(template.platform)}
          </span>
          <span className="tabular-nums">{template.aspect_ratio}</span>
          {template.scene_count > 0 && (
            <span>
              · {template.scene_count} {template.scene_count === 1 ? 'scene' : 'scenes'}
            </span>
          )}
        </div>

        <button
          className="btn btn-primary btn-sm mt-2"
          onClick={() => onUse(template)}
          disabled={busy}
        >
          {busy && <Spinner />}
          {busy ? 'Creating…' : 'Use template'}
        </button>
      </div>
    </div>
  )
}

export default function Templates() {
  const navigate = useNavigate()
  const toast = useToast()

  const [templates, setTemplates] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [category, setCategory] = useState('')
  const [busyKey, setBusyKey] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api
      .videoTemplates()
      .then((data) => {
        // The endpoint answers with an envelope ({templates, counts}), not a
        // bare list — unwrap it, or every consumer below iterates an object.
        if (!cancelled) setTemplates(data?.templates || [])
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

  const categories = useMemo(() => {
    const seen = []
    for (const template of templates) {
      if (template.category && !seen.includes(template.category)) seen.push(template.category)
    }
    return seen
  }, [templates])

  const visible = category
    ? templates.filter((template) => template.category === category)
    : templates

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

  return (
    <div className="mx-auto w-full max-w-6xl">
      <VideoPageHeader
        title="Templates"
        subtitle="Ready-made starting points. Picking one creates a project you can edit."
        back="/video"
        backLabel="Back to Video Studio"
      />

      {categories.length > 1 && (
        <div className="mb-5 flex flex-wrap gap-2">
          <button
            className={`btn btn-sm ${category === '' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setCategory('')}
          >
            All
          </button>
          {categories.map((key) => (
            <button
              key={key}
              className={`btn btn-sm ${category === key ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setCategory(key)}
            >
              {key[0].toUpperCase() + key.slice(1)}
            </button>
          ))}
        </div>
      )}

      {loading && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className="skeleton h-64" />
          ))}
        </div>
      )}

      {!loading && error && (
        <VideoEmptyState icon="alert" title="Could not load templates" description={error} />
      )}

      {!loading && !error && visible.length === 0 && (
        <VideoEmptyState
          icon="layout"
          title="No templates here"
          description="Try another category."
        />
      )}

      {!loading && !error && visible.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {visible.map((template) => (
            <TemplateCard
              key={template.key}
              template={template}
              onUse={use}
              busy={busyKey === template.key}
            />
          ))}
        </div>
      )}
    </div>
  )
}
