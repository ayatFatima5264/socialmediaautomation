import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import EditorCanvas from './EditorCanvas.jsx'
import LayerProperties from './LayerProperties.jsx'
import MediaLibraryModal from '../media/MediaLibraryModal.jsx'
import AiEditPanel from './AiEditPanel.jsx'
import { MiniButton } from './controls.jsx'
import useEditor from '../../hooks/useEditor'
import {
  documentFromImage,
  newImageLayer,
  newLogoLayer,
  newShapeLayer,
  newTextLayer,
  layerLabel,
} from '../../lib/brandKit/editor/document'
import { LAYER_TYPES, sortLayers } from '../../lib/brandKit/layers'
import { rasterizeBranded, RasterizeError } from '../../lib/brandKit/rasterize'
import { applyOperations, summarizeLayers } from '../../lib/brandKit/editor/aiOps'
import { api } from '../../lib/api'

// ---------------------------------------------------------------------------
// The editor shell: toolbar on top, tool panel on the LEFT, canvas centred.
//
// Layout rules that drive the structure below:
//   • The page never scrolls. The shell is a fixed-height flex column, and the
//     only scrollable region is the left panel — so the canvas can never be
//     pushed out of view by a long list of properties.
//   • One accordion section open at a time. Selecting a layer opens the
//     section that owns it, which is what removes almost all the scrolling.
//   • The right side is deliberately empty so the canvas reads as centred.
//
// This is a layout change only: every control, operation and shortcut behaves
// exactly as before.
// ---------------------------------------------------------------------------

const SHAPES = [
  { kind: 'rectangle', label: 'Rectangle', glyph: '▭' },
  { kind: 'circle', label: 'Circle', glyph: '●' },
  { kind: 'line', label: 'Line', glyph: '─' },
  { kind: 'arrow', label: 'Arrow', glyph: '→' },
]

// Which panel section owns a given layer type — used to auto-open the right
// section when the selection changes on the canvas.
function sectionForLayer(layer) {
  if (!layer) return null
  if (layer.type === LAYER_TYPES.TEXT) return 'text'
  if (layer.type === LAYER_TYPES.BACKGROUND) return 'background'
  if (layer.type === LAYER_TYPES.IMAGE) return /logo/i.test(layer.id) ? 'logo' : 'image'
  return 'shapes'
}

function Section({ id, title, icon, open, onToggle, children, badge }) {
  return (
    <section className="border-b border-line">
      <button
        type="button"
        onClick={() => onToggle(id)}
        aria-expanded={open}
        className={`flex w-full items-center gap-2 px-3 py-2.5 text-left text-xs font-bold transition ${
          open ? 'text-accent' : 'text-body hover:bg-inset'
        }`}
      >
        <span className="w-4 shrink-0 text-center text-sm opacity-80">{icon}</span>
        <span className="flex-1">{title}</span>
        {badge != null && (
          <span className="rounded-full bg-inset px-1.5 text-[10px] font-semibold text-muted">
            {badge}
          </span>
        )}
        <span className={`shrink-0 text-[10px] transition ${open ? 'rotate-180' : ''}`}>▾</span>
      </button>
      {open && <div className="px-3 pb-3">{children}</div>}
    </section>
  )
}

function readFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(new Error('Could not read that file.'))
    reader.readAsDataURL(file)
  })
}

export default function ImageEditor({
  open, imageUrl, size, layers = [], brandKit, style, onSave, onClose, onRegenerate,
  // Which panel the editor opens on. "AI Edit" is the same editor as "Edit" —
  // it just starts where the user was heading, rather than making them find it.
  initialSection = 'text',
  // Offered only from the empty state, when there is no artwork to edit yet.
  onGenerate,
}) {
  const initial = useMemo(
    () => documentFromImage({ imageUrl, size, overlayLayers: layers }),
    [imageUrl, size, layers],
  )

  const ed = useEditor(initial)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [aiBusy, setAiBusy] = useState(false)
  const [aiResult, setAiResult] = useState(null)
  const [section, setSection] = useState(initialSection)
  const [panelOpen, setPanelOpen] = useState(false) // mobile / tablet drawer
  const imageFileRef = useRef(null)
  const logoFileRef = useRef(null)
  // What the media library is currently being opened for: adding a new image
  // layer, or replacing the source of an existing one. Null means closed.
  const [libraryFor, setLibraryFor] = useState(null)

  // Is there anything on the canvas? Judged from the document, not the props,
  // so an image added by upload after opening empty counts too.
  const hasArtwork = ed.document.layers.some(
    (l) => l.type !== LAYER_TYPES.BACKGROUND && (l.type !== LAYER_TYPES.IMAGE || l.src),
  )

  // Largest box of the document's aspect that fits the available area.
  const stageRef = useRef(null)
  const [stage, setStage] = useState({ w: 0, h: 0 })
  const docW = ed.document.size.width
  const docH = ed.document.size.height

  useEffect(() => {
    const el = stageRef.current
    if (!el) return
    const fit = () => {
      const { width, height } = el.getBoundingClientRect()
      // Padding is on the element, so subtract it to get the usable area.
      const cs = getComputedStyle(el)
      const availW = width - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)
      const availH = height - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom)
      const ratio = docW / docH
      if (!(availW > 0 && availH > 0 && ratio > 0)) return
      const w = Math.min(availW, availH * ratio)
      setStage({ w, h: w / ratio })
    }
    fit()
    const ro = new ResizeObserver(fit)
    ro.observe(el)
    return () => ro.disconnect()
  }, [docW, docH])

  const toggleSection = (id) => setSection((s) => (s === id ? null : id))

  // Selecting on the canvas opens the owning section, so the controls for what
  // you just clicked are always the ones on screen.
  const selectedSection = sectionForLayer(ed.selected)
  useEffect(() => {
    if (selectedSection) setSection(selectedSection)
  }, [ed.selectedId, selectedSection])

  useEffect(() => {
    if (!open) return
    const onKey = (e) => {
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target?.tagName)
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') {
        e.preventDefault()
        e.shiftKey ? ed.redo() : ed.undo()
      } else if (!typing && (e.key === 'Delete' || e.key === 'Backspace') && ed.selectedId) {
        e.preventDefault()
        ed.removeLayer(ed.selectedId)
      } else if (e.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, ed, onClose])

  const addFile = useCallback(
    async (file, asLogo) => {
      setError('')
      try {
        const src = await readFile(file)
        ed.addLayer(asLogo ? newLogoLayer(src) : newImageLayer(src))
      } catch (err) {
        setError(err.message)
      }
    },
    [ed],
  )

  const replaceImage = useCallback(
    async (layerId, file) => {
      setError('')
      try {
        ed.updateLayer(layerId, { src: await readFile(file) })
      } catch (err) {
        setError(err.message)
      }
    },
    [ed],
  )

  async function applyAiEdit(instruction) {
    setAiBusy(true)
    setError('')
    try {
      const res = await api.imageEdit({
        instruction,
        layers: summarizeLayers(ed.document),
        style: style || null,
      })
      const out = applyOperations(ed.document, res.operations, { brandKit })
      if (out.document !== ed.document) ed.replaceDocument(out.document)
      if (out.regeneration && onRegenerate) {
        const url = await onRegenerate(out.regeneration)
        if (url) ed.updateLayer('base-image', { src: url })
      }
      setAiResult({ ...res, applied: out.applied, skipped: out.skipped })
    } catch (err) {
      setError(err?.message || 'Could not apply that edit.')
    } finally {
      setAiBusy(false)
    }
  }

  async function regenerateArtwork() {
    if (!onRegenerate) return
    setAiBusy(true)
    setError('')
    try {
      const url = await onRegenerate({ style: null, prompt: null })
      if (url) ed.updateLayer('base-image', { src: url })
    } catch (err) {
      setError(err?.message || 'Could not regenerate the image.')
    } finally {
      setAiBusy(false)
    }
  }

  async function save() {
    setSaving(true)
    setError('')
    try {
      const { dataUrl } = await rasterizeBranded(null, ed.document.layers, {
        width: ed.document.size.width,
        height: ed.document.size.height,
      })
      onSave(dataUrl)
    } catch (err) {
      setError(err instanceof RasterizeError ? err.message : 'Could not export the image.')
    } finally {
      setSaving(false)
    }
  }

  if (!open) return null

  const ordered = sortLayers(ed.document.layers).slice().reverse()
  const sel = ed.selected
  const background = ed.document.layers.find((l) => l.type === LAYER_TYPES.BACKGROUND)

  // Shown inside whichever section owns the selection.
  const selectedControls = (types) =>
    sel && types.includes(sectionForLayer(sel)) ? (
      <>
        <div className="mb-1.5 truncate rounded-md bg-inset px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-muted">
          {layerLabel(sel)}
        </div>
        <LayerProperties
          layer={sel}
          onChange={ed.updateLayer}
          onReplaceImage={replaceImage}
          onBrowseLibrary={(layerId) => setLibraryFor({ mode: 'replace', layerId })}
        />
        {sel.type !== LAYER_TYPES.BACKGROUND && (
          <div className="mt-2 grid grid-cols-2 gap-1.5 border-t border-line pt-2">
            <MiniButton onClick={() => ed.bringForward(sel.id)} title="Bring forward">↑ Forward</MiniButton>
            <MiniButton onClick={() => ed.sendBackward(sel.id)} title="Send backward">↓ Back</MiniButton>
            <MiniButton onClick={() => ed.duplicateLayer(sel.id)} title="Duplicate">⧉ Copy</MiniButton>
            <MiniButton onClick={() => ed.removeLayer(sel.id)} title="Delete" tone="danger">✕ Delete</MiniButton>
          </div>
        )}
      </>
    ) : (
      <p className="text-[11px] leading-relaxed text-muted">
        Select an element on the canvas to edit it.
      </p>
    )

  const panel = (
    <>
      <Section id="text" title="Text" icon="T" open={section === 'text'} onToggle={toggleSection}>
        <MiniButton onClick={() => ed.addLayer(newTextLayer())} title="Add a text box">
          + Add text
        </MiniButton>
        <div className="mt-2">{selectedControls(['text'])}</div>
      </Section>

      <Section id="image" title="Image" icon="▣" open={section === 'image'} onToggle={toggleSection}>
        <div className="flex flex-wrap gap-1.5">
          <MiniButton onClick={() => imageFileRef.current?.click()}>+ Add image</MiniButton>
          <MiniButton
            onClick={() => setLibraryFor({ mode: 'add' })}
            title="Choose from your media library"
          >
            🖼 Library
          </MiniButton>
        </div>
        <div className="mt-2">{selectedControls(['image'])}</div>
      </Section>

      <Section id="logo" title="Logo" icon="◈" open={section === 'logo'} onToggle={toggleSection}>
        <MiniButton onClick={() => logoFileRef.current?.click()}>+ Add logo</MiniButton>
        <div className="mt-2">{selectedControls(['logo'])}</div>
      </Section>

      <Section id="shapes" title="Shapes" icon="◆" open={section === 'shapes'} onToggle={toggleSection}>
        <div className="grid grid-cols-4 gap-1.5">
          {SHAPES.map((s) => (
            <MiniButton key={s.kind} onClick={() => ed.addLayer(newShapeLayer(s.kind))} title={s.label}>
              {s.glyph}
            </MiniButton>
          ))}
        </div>
        <div className="mt-2">{selectedControls(['shapes'])}</div>
      </Section>

      <Section id="background" title="Background" icon="▤" open={section === 'background'} onToggle={toggleSection}>
        {background && (
          <LayerProperties
            layer={background}
            onChange={ed.updateLayer}
            onReplaceImage={replaceImage}
            onBrowseLibrary={(layerId) => setLibraryFor({ mode: 'replace', layerId })}
          />
        )}
      </Section>

      <Section
        id="layers" title="Layers" icon="≡" badge={ordered.length}
        open={section === 'layers'} onToggle={toggleSection}
      >
        <ul className="space-y-0.5">
          {ordered.map((l) => (
            <li key={l.id}>
              <button
                type="button"
                onClick={() => ed.select(l.id)}
                className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[11px] transition ${
                  l.id === ed.selectedId
                    ? 'bg-accent-soft font-semibold text-accent'
                    : 'text-muted hover:bg-inset'
                }`}
              >
                <span className="w-3 shrink-0 text-center opacity-70">
                  {l.type === LAYER_TYPES.TEXT ? 'T' : l.type === LAYER_TYPES.IMAGE ? '▣' : '◆'}
                </span>
                <span className="truncate">{layerLabel(l)}</span>
              </button>
            </li>
          ))}
        </ul>
      </Section>

      <Section id="ai" title="AI edit" icon="✦" open={section === 'ai'} onToggle={toggleSection}>
        <AiEditPanel
          busy={aiBusy}
          lastResult={aiResult}
          onApply={applyAiEdit}
          onRegenerate={regenerateArtwork}
          onRevert={() => { ed.replaceDocument(initial); setAiResult(null) }}
          originalDocument={initial}
          currentDocument={ed.document}
          dirty={ed.document !== initial}
          bare
        />
      </Section>
    </>
  )

  return (
    <div className="fixed inset-0 z-50 flex h-full flex-col overflow-hidden bg-page">
      {/* ---- Toolbar ---------------------------------------------------- */}
      <header className="flex shrink-0 items-center gap-2 border-b border-line bg-surface px-3 py-2">
        <button
          onClick={() => setPanelOpen((v) => !v)}
          className="btn btn-ghost btn-sm lg:hidden"
          aria-label="Toggle tools"
        >
          ☰
        </button>
        <span className="text-sm font-bold">Edit image</span>

        <span className="mx-1 hidden h-5 w-px bg-line sm:block" />
        <div className="hidden items-center gap-1.5 sm:flex">
          <MiniButton onClick={() => ed.addLayer(newTextLayer())} title="Add text">T Text</MiniButton>
          <MiniButton onClick={() => imageFileRef.current?.click()} title="Add image">▣ Image</MiniButton>
          <MiniButton onClick={() => logoFileRef.current?.click()} title="Add logo">◈ Logo</MiniButton>
        </div>

        <span className="mx-1 h-5 w-px bg-line" />
        <MiniButton onClick={ed.undo} disabled={!ed.canUndo} title="Undo (Ctrl+Z)">↶ Undo</MiniButton>
        <MiniButton onClick={ed.redo} disabled={!ed.canRedo} title="Redo (Ctrl+Shift+Z)">↷ Redo</MiniButton>

        <div className="ml-auto flex items-center gap-2">
          <button onClick={onClose} className="btn btn-ghost btn-sm">Cancel</button>
          <button onClick={save} disabled={saving} className="btn btn-primary btn-sm">
            {saving ? 'Saving…' : 'Save image'}
          </button>
        </div>
      </header>

      {error && (
        <div className="shrink-0 border-b border-rose-400/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-600">
          {error}
        </div>
      )}

      {/* ---- Workspace: panel | canvas | (empty) ------------------------ */}
      <div className="flex min-h-0 flex-1">
        {/* Left panel — the only scrollable region on the page. */}
        <aside className="hidden w-72 shrink-0 overflow-y-auto border-r border-line bg-surface lg:block">
          {panel}
        </aside>

        {/* Canvas — centred, takes the remaining space, never scrolls.
            The stage is sized in JS rather than by `aspect-ratio` alone: the
            canvas SVGs are absolutely positioned at h-full/w-full, so a stage
            with no definite size collapses to nothing and the whole document
            renders invisibly. Measuring also keeps the drag maths honest,
            since pointer positions are read from this box. */}
        <main ref={stageRef} className="flex min-w-0 flex-1 items-center justify-center overflow-hidden p-4 md:p-6">
          {hasArtwork ? (
            <div style={{ width: stage.w || undefined, height: stage.h || undefined }}>
              <EditorCanvas
                document={ed.document}
                selectedId={ed.selectedId}
                onSelect={ed.select}
                onDrag={ed.dragLayer}
                onGestureStart={ed.beginGesture}
                onGestureEnd={ed.endGesture}
              />
            </div>
          ) : (
            /* Only when there is genuinely nothing to edit. An existing image
               must never land here — that reads as "your work was lost". */
            <div className="max-w-sm text-center">
              <div className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-accent-soft text-xl">
                ▣
              </div>
              <div className="mt-4 font-medium">No image loaded.</div>
              <p className="mt-1 text-sm text-muted">
                Generate one from your post, or upload your own to start editing.
              </p>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {onGenerate && (
                  <button
                    type="button"
                    onClick={onGenerate}
                    className="btn btn-primary btn-sm"
                  >
                    ✦ Generate Image
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => imageFileRef.current?.click()}
                  className="btn btn-secondary btn-sm"
                >
                  ⬆ Upload Image
                </button>
                <button
                  type="button"
                  onClick={() => setLibraryFor({ mode: 'add' })}
                  className="btn btn-secondary btn-sm"
                >
                  🖼 Media Library
                </button>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* ---- Tablet / mobile drawer ------------------------------------- */}
      {panelOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/40 lg:hidden"
            onClick={() => setPanelOpen(false)}
          />
          <div className="fixed inset-x-0 bottom-0 z-50 max-h-[70vh] overflow-y-auto rounded-t-2xl border-t border-line bg-surface shadow-lg lg:hidden">
            <div className="sticky top-0 flex items-center justify-between border-b border-line bg-surface px-3 py-2">
              <span className="text-xs font-bold">Tools</span>
              <button onClick={() => setPanelOpen(false)} className="btn btn-ghost btn-sm">Done</button>
            </div>
            {panel}
          </div>
        </>
      )}

      {/* A library pick arrives as a File, so it joins the same two paths an
          upload already takes — add a layer, or re-source an existing one. */}
      <MediaLibraryModal
        open={!!libraryFor}
        onCancel={() => setLibraryFor(null)}
        onSelect={(file) => {
          const target = libraryFor
          setLibraryFor(null)
          if (target?.mode === 'replace') replaceImage(target.layerId, file)
          else addFile(file, false)
        }}
        confirmLabel={libraryFor?.mode === 'replace' ? 'Replace Image' : 'Add Image'}
      />

      <input
        ref={imageFileRef} type="file" accept="image/*" className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) addFile(f, false); e.target.value = '' }}
      />
      <input
        ref={logoFileRef} type="file" accept="image/*" className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) addFile(f, true); e.target.value = '' }}
      />
    </div>
  )
}
