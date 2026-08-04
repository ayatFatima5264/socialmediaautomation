import { useState } from 'react'
import BrandOverlay from './BrandOverlay.jsx'
import TemplateLibraryModal from './TemplateLibraryModal.jsx'
import { getContentTemplate, PREVIEW_SAMPLE } from '../../lib/brandKit/contentTemplates'
import { composeLayers } from '../../lib/brandKit/imageRequest'
import { aspectOf, getSize } from '../../lib/brandKit/platformSizes'
import { paletteOf } from '../../lib/brandKit/layers'

// ---------------------------------------------------------------------------
// Compact template selector for the generator's filter column.
//
// The catalogue used to be a full grid here, which pushed every other control
// below the fold and got worse with each template added. What the sidebar owes
// the user is the current answer, not the whole question — so it shows the
// selection and a way in, and the browsing happens in TemplateLibraryModal.
//
// The thumbnail renders through the same layer pipeline as the library and the
// export, so it cannot drift from the template it claims to show.
// ---------------------------------------------------------------------------

const SAMPLE = {
  headline: 'Your headline goes here',
  subtext: 'A supporting line with the detail that matters',
  cta: 'Learn more',
  badge: 'New',
  price: '£49',
}

function Thumbnail({ template, sizeId, brandKit, brandSettings }) {
  const { primary, secondary } = paletteOf(brandKit)
  const size = getSize(sizeId)
  const [w, h] = size.dimensions

  // Shared pipeline: passes the frame's aspect and runs the layout validator,
  // so the thumbnail shows the same corrected design the export produces.
  const layers = composeLayers({
    templateId: template.id,
    sizeId,
    content: PREVIEW_SAMPLE,
    brandKit,
    brandSettings,
    brandAvailable: true,
  })

  return (
    <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-lg bg-inset p-1">
      <div
        className={`relative overflow-hidden rounded ${w > h ? 'w-full' : 'h-full'}`}
        style={{
          aspectRatio: size.dimensions.join(' / '),
          background: `linear-gradient(140deg, ${secondary}, ${primary})`,
        }}
      >
        <BrandOverlay
          layers={layers}
          aspect={aspectOf(sizeId)}
          idPrefix={`sel-${template.id}`}
        />
      </div>
    </div>
  )
}

export default function TemplatePicker({
  templateId,
  sizeId,
  brandKit,
  brandSettings,
  onChange,
}) {
  const [libraryOpen, setLibraryOpen] = useState(false)
  const template = getContentTemplate(templateId)

  return (
    <div>
      <div className="label mb-1.5">Template</div>

      <div className="rounded-xl border border-line p-2.5">
        <div className="flex items-center gap-2.5">
          <Thumbnail
            template={template}
            sizeId={sizeId}
            brandKit={brandKit}
            brandSettings={brandSettings}
          />
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-semibold">{template.label}</div>
            <div className="truncate text-xs text-muted">
              {template.platform || 'Any platform'} · {template.purpose || 'Any purpose'}
            </div>
            <div className="text-[11px] text-muted">
              {getSize(sizeId).dimensions.join(' × ')} px
            </div>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setLibraryOpen(true)}
          className="btn btn-secondary btn-sm mt-2.5 w-full"
        >
          Choose Template
        </button>
      </div>

      <TemplateLibraryModal
        open={libraryOpen}
        templateId={templateId}
        sizeId={sizeId}
        brandKit={brandKit}
        brandSettings={brandSettings}
        onCancel={() => setLibraryOpen(false)}
        onApply={(patch) => {
          onChange(patch)
          setLibraryOpen(false)
        }}
      />
    </div>
  )
}
