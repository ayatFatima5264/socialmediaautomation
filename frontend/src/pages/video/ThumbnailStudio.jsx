import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../lib/api.js'
import { useToast } from '../../context/ToastContext.jsx'
import VideoPageHeader from '../../components/video/VideoPageHeader.jsx'
import VideoIcon from '../../components/video/VideoIcon.jsx'
import Spinner from '../../components/Spinner.jsx'
import ScenePicker from '../../components/video/ScenePicker.jsx'
import AddToProjectModal from '../../components/video/voice/AddToProjectModal.jsx'
import { safeFilename, saveBlob } from '../../lib/video/download.js'

// ---------------------------------------------------------------------------
// Thumbnail Studio.
//
// **The preview is the server's renderer.** Every change re-requests the image
// from `/thumbnails/preview`, which calls the same function the download does.
// Nothing is drawn in the browser, so there is no second implementation to
// disagree with the file — the same rule the video preview follows.
//
// The cost is a round trip per edit, paid for by debouncing and by rendering
// the preview at a fraction of full size. What it buys is that "what you see"
// and "what you get" are the same sentence.
//
// Layout: controls on the left, the picture on the right, saved thumbnails
// underneath. The picture is the thing being judged, so it gets the space.
// ---------------------------------------------------------------------------

// Long enough that typing a headline is one render, short enough that the
// picture keeps up with a slider.
const PREVIEW_DELAY = 350

function Field({ label, children, hint }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  )
}

export default function ThumbnailStudio() {
  const toast = useToast()
  const [params] = useSearchParams()
  const projectId = params.get('project') ? Number(params.get('project')) : null

  const [options, setOptions] = useState(null)
  const [design, setDesign] = useState(null)
  const [form, setForm] = useState({
    template: 'bold_center',
    headline: '',
    kicker: '',
    format: 'youtube',
    palette: 'mint',
    use_brand: true,
    background_asset_id: null,
    logo_asset_id: null,
  })

  const [preview, setPreview] = useState(null)
  const [rendering, setRendering] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState([])
  const [variants, setVariants] = useState([])
  const [picking, setPicking] = useState(null)   // 'background' | 'logo'
  const [prompt, setPrompt] = useState('')
  const [generating, setGenerating] = useState(false)
  const [attaching, setAttaching] = useState(null)

  // The object URL currently on screen. Revoked when replaced, or every
  // keystroke pins another full-size PNG in memory for the life of the tab.
  const urlRef = useRef(null)
  const seqRef = useRef(0)

  const showPreview = useCallback((blob) => {
    const next = URL.createObjectURL(blob)
    if (urlRef.current) URL.revokeObjectURL(urlRef.current)
    urlRef.current = next
    setPreview(next)
  }, [])

  useEffect(
    () => () => {
      if (urlRef.current) URL.revokeObjectURL(urlRef.current)
    },
    [],
  )

  useEffect(() => {
    api.thumbnailOptions().then(setOptions).catch(() => {})
    reloadSaved()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const reloadSaved = useCallback(async () => {
    try {
      setSaved(await api.listThumbnails())
    } catch {
      // A failed listing is not worth interrupting the studio for.
    }
  }, [])

  // ---- The design follows the form ---------------------------------------

  useEffect(() => {
    let cancelled = false
    api
      .thumbnailDesign(form)
      .then((next) => !cancelled && setDesign(next))
      .catch((err) => !cancelled && toast.error(err?.message || 'Could not build that.'))
    return () => {
      cancelled = true
    }
  }, [form, toast])

  // ---- The preview follows the design ------------------------------------

  useEffect(() => {
    if (!design) return undefined
    const seq = ++seqRef.current
    setRendering(true)

    const timer = setTimeout(async () => {
      try {
        // Half size: the composition is identical because every dimension in a
        // design is a proportion of the canvas.
        const blob = await api.previewThumbnail(design, { scale: 0.5 })
        if (seq !== seqRef.current) return // a newer edit already answered
        showPreview(blob)
      } catch (err) {
        if (seq === seqRef.current) toast.error(err?.message || 'Could not draw that.')
      } finally {
        if (seq === seqRef.current) setRendering(false)
      }
    }, PREVIEW_DELAY)

    return () => clearTimeout(timer)
  }, [design, showPreview, toast])

  // ---- Actions -----------------------------------------------------------

  const set = (patch) => setForm((current) => ({ ...current, ...patch }))

  function editLayer(id, patch) {
    setDesign((current) => ({
      ...current,
      layers: current.layers.map((layer) =>
        layer.id === id ? { ...layer, ...patch } : layer,
      ),
    }))
  }

  async function makeVariations() {
    if (!design) return
    try {
      const body = await api.thumbnailVariations(design, 4)
      // Rendered as thumbnails of themselves, small and in parallel — four
      // quarter-size previews is cheaper than one full-size one.
      const rendered = await Promise.all(
        body.designs.map(async (entry) => ({
          design: entry,
          url: URL.createObjectURL(
            await api.previewThumbnail(entry, { scale: 0.25 }),
          ),
        })),
      )
      setVariants((current) => {
        current.forEach((entry) => URL.revokeObjectURL(entry.url))
        return rendered
      })
    } catch (err) {
      toast.error(err?.message || 'Could not make variations.')
    }
  }

  async function save() {
    if (!design) return
    setSaving(true)
    try {
      const row = await api.saveThumbnail({
        design,
        project_id: projectId ?? undefined,
      })
      toast.success(
        projectId ? 'Saved and set as the project thumbnail.' : 'Thumbnail saved.',
      )
      await reloadSaved()
      return row
    } catch (err) {
      toast.error(err?.message || 'Could not save that thumbnail.')
      return null
    } finally {
      setSaving(false)
    }
  }

  async function download(format) {
    const row = saved[0] ? null : await save()
    const target = row || saved[0]
    if (!target) return
    try {
      const blob = await api.downloadThumbnail(target.id, format)
      saveBlob(blob, `${safeFilename(target.title, 'thumbnail')}.${format}`)
    } catch (err) {
      toast.error(err?.message || 'Could not download that.')
    }
  }

  const headline = design?.layers?.find((layer) => layer.type === 'text')

  return (
    <div className="mx-auto w-full max-w-6xl">
      <VideoPageHeader
        title="Thumbnail Studio"
        subtitle="Design a cover for YouTube and every social format. The preview is the file."
        back="/video"
        backLabel="Back to Video Studio"
        actions={
          <>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => download('jpg')}
              disabled={!design}
            >
              JPG
            </button>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => download('png')}
              disabled={!design}
            >
              PNG
            </button>
            <button className="btn btn-primary btn-sm" onClick={save} disabled={saving || !design}>
              {saving && <Spinner />}
              Save
            </button>
          </>
        }
      />

      {options?.text_rendering_available === false && (
        <div className="card mb-4 border-amber-300 bg-amber-50 p-4">
          <p className="text-sm text-amber-900">
            This server has no font installed, so headlines will not be drawn
            correctly. Everything else works.
          </p>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[340px_minmax(0,1fr)]">
        {/* ---- Controls ---- */}
        <div className="card flex flex-col gap-4 p-4">
          <Field label="Headline">
            <textarea
              className="input min-h-[64px] resize-y"
              value={form.headline}
              placeholder="How compound interest works"
              onChange={(event) => set({ headline: event.target.value })}
            />
          </Field>

          <Field label="Kicker (optional)" hint="A small line, or the number for a list.">
            <input
              className="input"
              value={form.kicker}
              onChange={(event) => set({ kicker: event.target.value })}
            />
          </Field>

          <Field label="Format">
            <select
              className="select"
              value={form.format}
              onChange={(event) => set({ format: event.target.value })}
            >
              {(options?.formats || []).map((entry) => (
                <option key={entry.key} value={entry.key}>
                  {entry.label} — {entry.width}×{entry.height}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Layout">
            <select
              className="select"
              value={form.template}
              onChange={(event) => set({ template: event.target.value })}
            >
              {(options?.templates || []).map((entry) => (
                <option key={entry.key} value={entry.key}>
                  {entry.name}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Colours">
            <div className="flex flex-wrap gap-1.5">
              {(options?.palettes || []).map((entry) => (
                <button
                  key={entry.key}
                  type="button"
                  onClick={() => set({ palette: entry.key, use_brand: false })}
                  aria-label={entry.label}
                  title={entry.label}
                  className={`h-8 w-8 rounded-md border-2 ${
                    form.palette === entry.key && !form.use_brand
                      ? 'border-accent'
                      : 'border-line'
                  }`}
                  style={{
                    background: `linear-gradient(135deg, ${entry.colors[0]}, ${entry.colors[1]})`,
                  }}
                />
              ))}
            </div>
          </Field>

          <label className="flex items-center gap-2 text-sm text-body">
            <input
              type="checkbox"
              checked={form.use_brand}
              onChange={(event) => set({ use_brand: event.target.checked })}
            />
            Use my Brand Kit colours and logo
          </label>

          <div className="flex flex-wrap gap-2">
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => setPicking('background')}
            >
              <VideoIcon name="image" className="h-4 w-4" />
              {form.background_asset_id ? 'Change background' : 'Background image'}
            </button>
            {form.background_asset_id && (
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => set({ background_asset_id: null })}
              >
                Remove
              </button>
            )}
            <button className="btn btn-secondary btn-sm" onClick={() => setPicking('logo')}>
              Logo
            </button>
          </div>

          <div className="panel flex flex-col gap-2 p-3">
            <p className="text-xs font-bold uppercase tracking-wide text-muted">
              Generate a background
            </p>
            <input
              className="input text-sm"
              value={prompt}
              placeholder="a quiet library at dusk"
              onChange={(event) => setPrompt(event.target.value)}
            />
            <button
              className="btn btn-secondary btn-sm"
              disabled={generating || prompt.trim().length < 3}
              onClick={async () => {
                setGenerating(true)
                try {
                  const image = await api.generateThumbnailBackground(
                    prompt.trim(),
                    form.format,
                  )
                  set({ background_asset_id: image.asset_id })
                  toast.success('Background generated.')
                } catch (err) {
                  toast.error(err?.message || 'That image could not be generated.')
                } finally {
                  setGenerating(false)
                }
              }}
            >
              {generating ? <Spinner /> : <VideoIcon name="sparkle" className="h-4 w-4" />}
              {generating ? 'Generating…' : 'Generate with AI'}
            </button>
          </div>

          {/* Fine control over the headline, once it exists. */}
          {headline && (
            <div className="panel flex flex-col gap-3 p-3">
              <p className="text-xs font-bold uppercase tracking-wide text-muted">
                Headline
              </p>
              <label className="block">
                <span className="mb-1 flex justify-between text-xs text-muted">
                  <span>Size</span>
                  <span className="tabular-nums">
                    {Math.round(headline.font_size * 100)}%
                  </span>
                </span>
                <input
                  type="range"
                  min="0.04" max="0.32" step="0.005"
                  value={headline.font_size}
                  onChange={(event) =>
                    editLayer(headline.id, { font_size: Number(event.target.value) })
                  }
                  className="w-full accent-[var(--accent)]"
                />
              </label>
              <div className="flex gap-2">
                <label className="flex-1">
                  <span className="label">Colour</span>
                  <input
                    type="color"
                    className="input h-9 p-1"
                    value={headline.color}
                    onChange={(event) =>
                      editLayer(headline.id, { color: event.target.value })
                    }
                  />
                </label>
                <label className="flex-1">
                  <span className="label">Font</span>
                  <select
                    className="select"
                    value={headline.font_family}
                    onChange={(event) =>
                      editLayer(headline.id, { font_family: event.target.value })
                    }
                  >
                    {(options?.fonts || []).map((font) => (
                      <option key={font} value={font}>{font}</option>
                    ))}
                  </select>
                </label>
              </div>
              <label className="block">
                <span className="label">Position</span>
                <select
                  className="select"
                  value={headline.anchor}
                  onChange={(event) =>
                    editLayer(headline.id, { anchor: event.target.value })
                  }
                >
                  {(options?.anchors || []).map((value) => (
                    <option key={value} value={value}>
                      {value.replace('-', ' ')}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          )}

          <button className="btn btn-secondary" onClick={makeVariations} disabled={!design}>
            <VideoIcon name="sparkle" className="h-4 w-4" />
            Make variations
          </button>
        </div>

        {/* ---- The picture ---- */}
        <div className="flex flex-col gap-4">
          <div className="card relative grid place-items-center overflow-hidden bg-inset p-4">
            {preview ? (
              <img
                src={preview}
                alt="Thumbnail preview"
                className="max-h-[54vh] w-auto max-w-full rounded-lg"
              />
            ) : (
              <div className="grid h-64 place-items-center text-sm text-muted">
                Type a headline to see it.
              </div>
            )}
            {rendering && (
              <span className="absolute right-3 top-3 rounded-full bg-black/60 px-2 py-1 text-xs text-white">
                Drawing…
              </span>
            )}
          </div>

          {variants.length > 0 && (
            <div className="card p-4">
              <h2 className="mb-3 font-semibold text-body">Variations</h2>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {variants.map((entry, index) => (
                  <button
                    key={index}
                    type="button"
                    onClick={() => setDesign(entry.design)}
                    className="overflow-hidden rounded-lg border border-line transition-colors hover:border-accent-line"
                  >
                    <img src={entry.url} alt="" className="w-full" />
                  </button>
                ))}
              </div>
            </div>
          )}

          {saved.length > 0 && (
            <div className="card p-4">
              <h2 className="mb-3 font-semibold text-body">Saved</h2>
              <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {saved.map((row) => (
                  <li key={row.id} className="flex flex-col gap-1">
                    <img
                      src={row.url}
                      alt={row.title}
                      className="w-full rounded-lg border border-line"
                    />
                    <div className="flex items-center gap-1">
                      <button
                        className="btn btn-ghost btn-sm flex-1 px-1 text-xs"
                        onClick={() => row.design?.layers && setDesign(row.design)}
                        title="Open this design again"
                      >
                        Edit
                      </button>
                      <button
                        className="btn btn-ghost btn-sm px-1 text-xs"
                        onClick={() => setAttaching(row)}
                      >
                        Use
                      </button>
                      <button
                        className="btn btn-ghost btn-sm px-1"
                        aria-label="Delete"
                        onClick={async () => {
                          await api.deleteThumbnail(row.id)
                          reloadSaved()
                        }}
                      >
                        <VideoIcon name="trash" className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>

      <ScenePicker
        open={picking !== null}
        scene={null}
        onClose={() => setPicking(null)}
        onPick={(item) =>
          set(
            picking === 'logo'
              ? { logo_asset_id: item.id }
              : { background_asset_id: item.id },
          )
        }
      />

      <AddToProjectModal
        open={attaching !== null}
        take={attaching}
        onClose={() => setAttaching(null)}
        onAttach={async (row, target) => {
          await api.attachThumbnail(row.id, target)
          await reloadSaved()
        }}
      />
    </div>
  )
}
