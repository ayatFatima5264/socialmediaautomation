import { useState } from 'react'
import VideoIcon from './VideoIcon.jsx'
import Spinner from '../Spinner.jsx'
import { formatDuration } from '../../lib/video/format.js'
import { safeFilename, saveBlob } from '../../lib/video/download.js'

// ---------------------------------------------------------------------------
// The script, as a form.
//
// Shared by AI Video and Script Studio so there is one script editor, not two
// that drift. Both show the same fields, rewrite a section the same way, and
// hand back the same document shape; only the buttons underneath differ, which
// is what `footer` is for.
//
// **Every part is a field, and every part can be rewritten alone.** Rewriting
// the whole script to fix one weak hook throws away the lines the user already
// accepted — usually the reason they stayed. The per-section button sends the
// rest of the script as context the model is told not to touch.
// ---------------------------------------------------------------------------

function Field({ label, hint, action, children }) {
  return (
    <div className="block">
      <div className="flex items-end justify-between gap-2">
        <span className="label">{label}</span>
        {action}
      </div>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </div>
  )
}

// The script as the plain text a person would paste into a teleprompter or a
// document — headings included, because a bare wall of narration is not
// something you can find your place in.
export function scriptToText(script) {
  const lines = []
  if (script.title) lines.push(script.title, '')
  if (script.hook) lines.push('HOOK', script.hook, '')
  if (script.introduction) lines.push('INTRODUCTION', script.introduction, '')
  ;(script.main_points || []).forEach((point, index) => {
    lines.push((point.heading || `POINT ${index + 1}`).toUpperCase())
    lines.push(point.text || '', '')
  })
  if (script.ending) lines.push('ENDING', script.ending, '')
  if (script.cta) lines.push('CALL TO ACTION', script.cta, '')
  if (script.estimated_seconds) {
    lines.push(`— about ${formatDuration(script.estimated_seconds)} of narration`)
  }
  return lines.join('\n').trim() + '\n'
}

export default function ScriptEditor({
  script,
  onChange,
  onRewrite,
  busy = false,
  footer = null,
  subtitle = 'Every part is editable. Nothing is generated again unless you ask.',
}) {
  const [rewriting, setRewriting] = useState('')
  const [copied, setCopied] = useState(false)

  const set = (patch) => onChange({ ...script, ...patch })

  const setPoint = (index, patch) => {
    const points = [...(script.main_points || [])]
    points[index] = { ...points[index], ...patch }
    set({ main_points: points })
  }

  const over = script.fits_budget === false

  async function rewrite(section, pointId = '') {
    if (!onRewrite) return
    const key = pointId || section
    setRewriting(key)
    try {
      await onRewrite(section, pointId)
    } finally {
      setRewriting('')
    }
  }

  // A rewrite button only for the sections the server will rewrite, and only
  // when a handler was given — Script Studio has one, a read-only view would
  // not.
  const RewriteButton = ({ section, pointId = '' }) =>
    onRewrite ? (
      <button
        type="button"
        className="btn btn-ghost btn-sm px-2 text-xs"
        disabled={busy || rewriting !== ''}
        onClick={() => rewrite(section, pointId)}
        title="Rewrite just this part, keeping the rest of the script"
      >
        {rewriting === (pointId || section) ? (
          <Spinner />
        ) : (
          <VideoIcon name="sparkle" className="h-3.5 w-3.5" />
        )}
        Rewrite
      </button>
    ) : null

  async function copyAll() {
    try {
      await navigator.clipboard.writeText(scriptToText(script))
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  function download() {
    const name = safeFilename(script.title || script.brief?.topic || 'script', 'script')
    saveBlob(
      new Blob([scriptToText(script)], { type: 'text/plain;charset=utf-8' }),
      `${name}.txt`,
    )
  }

  return (
    <div className="card flex flex-col gap-4 p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="font-semibold text-body">The script</h2>
          <p className="text-sm text-muted">{subtitle}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`badge border ${
              over
                ? 'border-amber-300 bg-amber-50 text-amber-800'
                : 'border-line bg-inset text-muted'
            }`}
          >
            ≈ {formatDuration(script.estimated_seconds || 0)}
            {over ? ' — longer than asked for' : ''}
          </span>
          <button type="button" className="btn btn-ghost btn-sm px-2" onClick={copyAll}>
            <VideoIcon name={copied ? 'check' : 'copy'} className="h-4 w-4" />
            {copied ? 'Copied' : 'Copy'}
          </button>
          <button type="button" className="btn btn-ghost btn-sm px-2" onClick={download}>
            <VideoIcon name="document" className="h-4 w-4" />
            Download
          </button>
        </div>
      </div>

      <Field label="Title" action={<RewriteButton section="title" />}>
        <input
          className="input"
          value={script.title || ''}
          onChange={(event) => set({ title: event.target.value })}
        />
      </Field>

      <Field
        label="Hook"
        hint="The first line. It has about three seconds to work."
        action={<RewriteButton section="hook" />}
      >
        <textarea
          className="input min-h-[60px] resize-y"
          value={script.hook || ''}
          onChange={(event) => set({ hook: event.target.value })}
        />
      </Field>

      <Field label="Introduction" action={<RewriteButton section="introduction" />}>
        <textarea
          className="input min-h-[60px] resize-y"
          value={script.introduction || ''}
          onChange={(event) => set({ introduction: event.target.value })}
        />
      </Field>

      <div className="flex flex-col gap-3">
        <span className="label mb-0">Main points</span>
        {(script.main_points || []).map((point, index) => (
          <div key={point.id || index} className="panel flex flex-col gap-2 p-3">
            <div className="flex items-center gap-2">
              <input
                className="input flex-1 font-medium"
                value={point.heading || ''}
                placeholder={`Point ${index + 1}`}
                onChange={(event) => setPoint(index, { heading: event.target.value })}
              />
              <RewriteButton section="point" pointId={point.id} />
              <button
                type="button"
                className="btn btn-ghost btn-sm shrink-0"
                onClick={() =>
                  set({
                    main_points: (script.main_points || []).filter((_, i) => i !== index),
                  })
                }
              >
                Remove
              </button>
            </div>
            <textarea
              className="input min-h-[70px] resize-y"
              value={point.text || ''}
              onChange={(event) => setPoint(index, { text: event.target.value })}
            />
          </div>
        ))}
        <button
          type="button"
          className="btn btn-secondary btn-sm self-start"
          onClick={() =>
            set({
              main_points: [
                ...(script.main_points || []),
                {
                  // Ids have to stay unique for the rewrite call to find the
                  // right point after some have been removed.
                  id: `p${Date.now().toString(36)}`,
                  heading: '',
                  text: '',
                },
              ],
            })
          }
        >
          <VideoIcon name="plus" className="h-4 w-4" />
          Add a point
        </button>
      </div>

      <Field label="Ending" action={<RewriteButton section="ending" />}>
        <textarea
          className="input min-h-[60px] resize-y"
          value={script.ending || ''}
          onChange={(event) => set({ ending: event.target.value })}
        />
      </Field>

      <Field label="Call to action" action={<RewriteButton section="cta" />}>
        <input
          className="input"
          value={script.cta || ''}
          onChange={(event) => set({ cta: event.target.value })}
        />
      </Field>

      {footer && <div className="flex flex-wrap gap-2">{footer}</div>}
    </div>
  )
}
