import BrandOverlay from './BrandOverlay.jsx'
import {
  CONTENT_TEMPLATES,
  TEMPLATE_CATEGORIES,
  buildContentLayers,
  getContentTemplate,
} from '../../lib/brandKit/contentTemplates'
import { buildBrandLayers } from '../../lib/brandKit/templates'
import { PLATFORM_SIZES, aspectOf, getSize } from '../../lib/brandKit/platformSizes'
import { paletteOf } from '../../lib/brandKit/layers'

// ---------------------------------------------------------------------------
// Template + platform-size selection.
//
// Every tile previews with the real layer pipeline and representative
// placeholder copy, so the thumbnail cannot drift from what the template
// actually produces — the alternative, hand-drawn mocks, go stale the first
// time a layout changes.
//
// Choosing a template sets its default size, since a Story template at 1:1
// would be the wrong shape. The size control stays independent afterwards, so
// deliberately rendering a Quote at Pinterest proportions is still one click.
// ---------------------------------------------------------------------------

// Stand-in copy for the tiles. Short enough to fit every slot budget.
const SAMPLE = {
  headline: 'Your headline goes here',
  subtext: 'A supporting line with the detail that matters',
  cta: 'Learn more',
  badge: 'New',
  price: '£49',
}

function TemplateTile({ template, brandKit, brandSettings, active, onSelect }) {
  const size = getSize(template.defaultSize)
  const { primary, secondary } = paletteOf(brandKit)
  const aspect = aspectOf(template.defaultSize)

  const layers = [
    ...buildContentLayers(template.id, SAMPLE, { brandKit, slideIndex: 0 }),
    ...(brandSettings?.enabled ? buildBrandLayers(brandKit, brandSettings) : []),
  ]

  return (
    <button
      type="button"
      onClick={() => onSelect(template)}
      title={`${template.label} — ${size.label}`}
      className={`group overflow-hidden rounded-xl border-2 text-left transition ${
        active ? 'border-accent shadow-sm' : 'border-line hover:border-accent-line'
      }`}
    >
      <div
        className="relative w-full"
        style={{
          aspectRatio: size.dimensions.join(' / '),
          background: `linear-gradient(140deg, ${secondary}, ${primary})`,
        }}
      >
        <BrandOverlay layers={layers} aspect={aspect} idPrefix={`tpl-${template.id}`} />
      </div>
      <div
        className={`px-2 py-1.5 ${active ? 'bg-accent text-accent-contrast' : ''}`}
      >
        <div className="truncate text-[11px] font-bold">{template.label}</div>
        <div className={`truncate text-[10px] ${active ? 'opacity-80' : 'text-muted'}`}>
          {size.label}
        </div>
      </div>
    </button>
  )
}

export default function TemplatePicker({
  templateId,
  sizeId,
  brandKit,
  brandSettings,
  onChange,
}) {
  const template = getContentTemplate(templateId)

  return (
    <div className="space-y-4">
      <div>
        <div className="label mb-2">Template</div>
        {TEMPLATE_CATEGORIES.map((category) => (
          <div key={category} className="mb-3 last:mb-0">
            <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted">
              {category}
            </div>
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-5">
              {CONTENT_TEMPLATES.filter((t) => t.category === category).map((t) => (
                <TemplateTile
                  key={t.id}
                  template={t}
                  brandKit={brandKit}
                  brandSettings={brandSettings}
                  active={t.id === template.id}
                  // Selecting a template also adopts its natural size.
                  onSelect={(tpl) => onChange({ templateId: tpl.id, sizeId: tpl.defaultSize })}
                />
              ))}
            </div>
          </div>
        ))}
      </div>

      <div>
        <div className="label mb-2 flex items-center justify-between">
          <span>Platform size</span>
          <span className="text-xs font-normal text-muted">
            {getSize(sizeId).dimensions.join(' × ')} px
          </span>
        </div>
        <div className="flex flex-wrap gap-2">
          {PLATFORM_SIZES.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => onChange({ sizeId: s.id })}
              title={s.hint}
              className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${
                s.id === sizeId
                  ? 'border-accent bg-accent-soft text-accent'
                  : 'border-line text-muted hover:border-accent-line'
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
        <p className="mt-1.5 text-xs text-muted">
          Controls the generated image dimensions. Layouts are proportional, so changing size
          never breaks the design.
        </p>
      </div>
    </div>
  )
}
