import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import BrandOverlay from './BrandOverlay.jsx'
import {
  CONTENT_TEMPLATES,
  TEMPLATE_FACETS,
  getContentTemplate,
  previewFor,
  templateMatches,
} from '../../lib/brandKit/contentTemplates'
import { composeLayers } from '../../lib/brandKit/imageRequest'
import { PLATFORM_SIZES, aspectOf, getSize } from '../../lib/brandKit/platformSizes'

// ---------------------------------------------------------------------------
// Template library.
//
// The full catalogue is too tall to live in the generator's filter column, so
// it moved here: browsing is a separate, deliberate act, and the sidebar keeps
// only the answer.
//
// Selection is staged. Picking a card changes a draft, not the page — nothing
// reaches the generator until "Use Template" is pressed, so Cancel is a true
// undo and an accidental click costs nothing.
//
// Every tile renders through the real layer pipeline with placeholder copy, so
// a preview cannot drift from what the template actually produces.
// ---------------------------------------------------------------------------

function TemplateCard({ template, brandKit, brandSettings, selected, onSelect }) {
  const size = getSize(template.defaultSize)
  const [w, h] = size.dimensions
  const landscape = w > h

  // Each template previews as itself — its own palette and its own copy —
  // rather than every tile sharing the Brand Kit's colours and one line of
  // filler. Same layout geometry; only the paint and the words differ.
  const preview = previewFor(template.id)
  const [previewFrom, previewTo] = preview.palette

  // Composed through the shared pipeline, which passes the frame's aspect and
  // runs the layout validator. Building the layers by hand skipped both, and
  // the validator is precisely what stops the headline, the supporting line
  // and the CTA landing on top of each other.
  const layers = composeLayers({
    templateId: template.id,
    sizeId: template.defaultSize,
    content: preview.copy,
    brandKit,
    brandSettings,
    brandAvailable: true,
  })

  return (
    <button
      type="button"
      onClick={() => onSelect(template)}
      aria-pressed={selected}
      className={`group relative flex flex-col overflow-hidden rounded-xl border-2 text-left transition ${
        selected
          ? 'border-accent shadow-md'
          : 'border-line hover:border-accent-line hover:shadow-sm'
      }`}
    >
      {/* Fixed-height stage, artwork sized from whichever edge binds. Portrait
          templates bind on height, landscape on width — so a 9:16 Story and a
          1.91:1 LinkedIn post both sit centred without distortion.
          The stage is tall enough that the widest ratio (1.91:1) still fits
          inside it at the four-column breakpoint. */}
      <div className="flex h-40 shrink-0 items-center justify-center bg-inset p-3 sm:h-56">
        <div
          className={`relative overflow-hidden rounded-md shadow-sm ${
            landscape ? 'w-full' : 'h-full'
          }`}
          style={{
            aspectRatio: size.dimensions.join(' / '),
            background: `linear-gradient(140deg, ${previewFrom}, ${previewTo})`,
          }}
        >
          <BrandOverlay
            layers={layers}
            aspect={aspectOf(template.defaultSize)}
            idPrefix={`lib-${template.id}`}
          />
        </div>
      </div>

      {preview.badge && !selected && (
        <span
          className={`absolute left-2 top-2 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white shadow ${
            preview.badge === 'New' ? 'bg-sky-600' : 'bg-rose-600'
          }`}
        >
          {preview.badge}
        </span>
      )}

      {selected && (
        <span
          className="absolute right-2 top-2 grid h-7 w-7 place-items-center rounded-full bg-accent text-sm font-bold text-accent-contrast shadow"
          aria-hidden="true"
        >
          ✓
        </span>
      )}

      <div className="min-w-0 flex-1 border-t border-line px-3 py-2">
        <div className="flex items-baseline gap-2">
          <span className="min-w-0 flex-1 truncate text-sm font-semibold">{template.label}</span>
          <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wide text-muted">
            {preview.style}
          </span>
        </div>
        <div className="mt-0.5 truncate text-xs text-muted">
          {template.platform || 'Any platform'} · {template.purpose || 'Any purpose'}
        </div>
        <div className="mt-0.5 truncate text-[11px] text-muted">
          {size.dimensions.join(' × ')} px
          {template.industries?.length ? ` · ${template.industries.slice(0, 2).join(', ')}` : ''}
        </div>
      </div>
    </button>
  )
}

// Two chip roles, deliberately not the same shape. Solid pills filter the
// catalogue; square outlined ones set the output size. They used to look
// identical, which read as "clicking Facebook picks the Facebook template" —
// it does not, and the checkmark staying put looked like a broken control.
function Chip({ active, children, onClick, variant = 'filter' }) {
  const shape =
    variant === 'filter'
      ? `rounded-full ${
          active
            ? 'border-accent bg-accent text-accent-contrast'
            : 'border-line text-muted hover:border-accent-line hover:text-body'
        }`
      : `rounded-lg ${
          active
            ? 'border-accent bg-accent-soft text-accent'
            : 'border-line text-muted hover:border-accent-line hover:text-body'
        }`

  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`shrink-0 border px-3 py-1 text-xs font-semibold transition ${shape}`}
    >
      {children}
    </button>
  )
}

export default function TemplateLibraryModal({
  open,
  templateId,
  sizeId,
  brandKit,
  brandSettings,
  onCancel,
  onApply,
}) {
  const [draftTemplate, setDraftTemplate] = useState(templateId)
  const [draftSize, setDraftSize] = useState(sizeId)
  const [search, setSearch] = useState('')
  const [facet, setFacet] = useState('platform')
  // One active value per axis, so Platform and Purpose can narrow together.
  const [filters, setFilters] = useState({})

  // Opening is what resets the draft: the modal stays mounted between opens, so
  // without this a cancelled session would leak into the next one.
  useEffect(() => {
    if (!open) return
    setDraftTemplate(templateId)
    setDraftSize(sizeId)
    setSearch('')
    setFacet('platform')
    setFilters({})
  }, [open, templateId, sizeId])

  useEffect(() => {
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && onCancel()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onCancel])

  const results = useMemo(
    () => CONTENT_TEMPLATES.filter((t) => templateMatches(t, { search, ...filters })),
    [search, filters],
  )

  if (!open) return null

  const activeFacet = TEMPLATE_FACETS.find((f) => f.key === facet)
  const activeCount = Object.values(filters).filter(Boolean).length
  const selected = getContentTemplate(draftTemplate)

  function pick(template) {
    setDraftTemplate(template.id)
    // Adopting the template's natural size: a Story laid out at 1:1 is the
    // wrong shape. The size control below stays free afterwards.
    setDraftSize(template.defaultSize)
  }

  function setFilter(key, value) {
    setFilters((prev) => ({ ...prev, [key]: prev[key] === value ? undefined : value }))
  }

  // Portalled to <body> on purpose. The picker that owns this modal lives
  // inside the generator's <form>, and rendering here would mean Enter in the
  // search box submits that form — plus the panel's overflow would clip it.
  return createPortal(
    <div
      className="fixed inset-0 z-40 grid place-items-center bg-black/50 p-2 backdrop-blur-sm sm:p-6"
      onClick={onCancel}
      role="dialog"
      aria-modal="true"
      aria-label="Choose a template"
    >
      <div
        className="card flex h-[92vh] w-full max-w-[1600px] flex-col overflow-hidden sm:h-[88vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ---- Header ---- */}
        <div className="shrink-0 border-b border-line p-3 sm:p-4">
          <div className="flex items-center gap-3">
            <h2 className="text-base font-bold sm:text-lg">Choose a Template</h2>
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search templates…"
              aria-label="Search templates"
              className="input ml-auto hidden max-w-xs sm:block"
            />
            <button
              type="button"
              onClick={onCancel}
              aria-label="Close"
              className="btn btn-ghost btn-sm ml-auto shrink-0 sm:ml-0"
            >
              ✕
            </button>
          </div>

          {/* Search drops to its own row on phones, where it cannot share
              space with the title without squeezing both. */}
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search templates…"
            aria-label="Search templates"
            className="input mt-2 sm:hidden"
          />

          <div className="mt-3 flex items-center gap-4 border-b border-line">
            {TEMPLATE_FACETS.map((f) => (
              <button
                key={f.key}
                type="button"
                onClick={() => setFacet(f.key)}
                className={`-mb-px border-b-2 pb-2 text-sm font-semibold transition ${
                  facet === f.key
                    ? 'border-accent text-accent'
                    : 'border-transparent text-muted hover:text-body'
                }`}
              >
                {f.label}
                {filters[f.key] && <span className="ml-1 text-xs">•</span>}
              </button>
            ))}
            {activeCount > 0 && (
              <button
                type="button"
                onClick={() => setFilters({})}
                className="ml-auto pb-2 text-xs font-medium text-muted hover:text-body"
              >
                Clear filters
              </button>
            )}
          </div>

          <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
            <Chip active={!filters[facet]} onClick={() => setFilter(facet, undefined)}>
              All
            </Chip>
            {activeFacet.values.map((value) => (
              <Chip
                key={value}
                active={filters[facet] === value}
                onClick={() => setFilter(facet, value)}
              >
                {value}
              </Chip>
            ))}
          </div>
        </div>

        {/* ---- Results ---- */}
        <div className="min-h-0 flex-1 overflow-y-auto p-3 sm:p-4">
          {results.length === 0 ? (
            <div className="grid h-full place-items-center p-8 text-center">
              <div>
                <div className="text-3xl">🔍</div>
                <div className="mt-3 font-medium">No templates match those filters.</div>
                <button
                  type="button"
                  onClick={() => {
                    setSearch('')
                    setFilters({})
                  }}
                  className="btn btn-secondary btn-sm mt-4"
                >
                  Reset filters
                </button>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
              {results.map((t) => (
                <TemplateCard
                  key={t.id}
                  template={t}
                  brandKit={brandKit}
                  brandSettings={brandSettings}
                  selected={t.id === draftTemplate}
                  onSelect={pick}
                />
              ))}
            </div>
          )}
        </div>

        {/* ---- Footer ---- */}
        <div className="shrink-0 border-t border-line p-3 sm:p-4">
          <div className="mb-3">
            <div className="mb-1.5 text-xs font-semibold">
              Output size{' '}
              <span className="font-normal text-muted">
                — the pixel dimensions. Does not change which template is selected.
              </span>
            </div>
            <div className="flex gap-2 overflow-x-auto pb-1">
              {PLATFORM_SIZES.map((s) => (
                <Chip
                  key={s.id}
                  variant="size"
                  active={s.id === draftSize}
                  onClick={() => setDraftSize(s.id)}
                >
                  {s.label}
                </Chip>
              ))}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* States the actual outcome. The card above shows each template's
                natural size, which stops matching once a different output size
                is chosen — so the truth belongs here, next to the button. */}
            <span className="min-w-0 flex-1 truncate text-xs text-muted">
              Selected: <span className="font-semibold text-body">{selected.label}</span>
              {' · '}
              <span className="font-semibold text-body">
                {getSize(draftSize).dimensions.join(' × ')} px
              </span>
              {draftSize !== selected.defaultSize && (
                <span className="text-muted"> (custom size)</span>
              )}
            </span>
            <button type="button" onClick={onCancel} className="btn btn-ghost">
              Cancel
            </button>
            <button
              type="button"
              onClick={() => onApply({ templateId: draftTemplate, sizeId: draftSize })}
              className="btn btn-primary"
            >
              Use Template
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  )
}
