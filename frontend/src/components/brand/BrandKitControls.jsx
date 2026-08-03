import { Link } from 'react-router-dom'
import BrandOverlay from './BrandOverlay.jsx'
import { TEMPLATES, buildBrandLayers, getTemplate } from '../../lib/brandKit/templates'
import { LOGO_POSITIONS, paletteOf } from '../../lib/brandKit/layers'

// ---------------------------------------------------------------------------
// The "Apply Brand Kit" control block.
//
// Reusable: the Generator embeds it, and any future surface that produces
// images (Create Post, Content Planner) can drop in the same component with
// the same `settings` shape from useBrandKit().
//
// Every option previews live against a neutral swatch, because the effect of
// picking "Editorial" over "Badge" is not something a label can convey.
// ---------------------------------------------------------------------------

// A miniature of the current template, rendered with the real layer pipeline
// rather than a hand-drawn mock — so the preview cannot drift from the output.
function TemplatePreview({ brandKit, settings, template, active, onSelect }) {
  const { primary, secondary } = paletteOf(brandKit)
  const layers = buildBrandLayers(brandKit, { ...settings, template: template.id })

  return (
    <button
      type="button"
      onClick={() => onSelect(template.id)}
      title={template.description}
      className={`group relative overflow-hidden rounded-lg border-2 transition ${
        active ? 'border-accent' : 'border-line hover:border-accent-line'
      }`}
    >
      <div
        className="relative aspect-square w-full"
        style={{ background: `linear-gradient(135deg, ${secondary}, ${primary})` }}
      >
        <BrandOverlay layers={layers} aspect={1} idPrefix={`tpl-${template.id}`} />
      </div>
      <div
        className={`px-1.5 py-1 text-[10px] font-semibold ${
          active ? 'bg-accent text-accent-contrast' : 'text-muted'
        }`}
      >
        {template.label}
      </div>
    </button>
  )
}

export default function BrandKitControls({ brandKit, settings, onChange, available, compact }) {
  const template = getTemplate(settings.template)

  // Nothing to apply — point at the place that fixes it instead of showing a
  // toggle that would appear broken.
  if (!available) {
    return (
      <div className="rounded-xl border border-line bg-inset p-4">
        <div className="text-sm font-semibold">Brand Kit</div>
        <p className="mt-1 text-sm text-muted">
          Add your logo, brand colours, and contact details to overlay them on generated
          images.
        </p>
        <Link to="/business-profile" className="btn btn-secondary btn-sm mt-3">
          Set up Brand Kit
        </Link>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-line bg-inset p-4">
      <label className="flex cursor-pointer items-start gap-3">
        <input
          type="checkbox"
          checked={settings.enabled}
          onChange={(e) => onChange({ enabled: e.target.checked })}
          className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--accent)]"
        />
        <span className="min-w-0">
          <span className="block text-sm font-semibold">Apply Brand Kit</span>
          <span className="mt-0.5 block text-xs leading-relaxed text-muted">
            Overlays your logo and details as sharp, editable layers after the image is
            generated — and steers the AI toward your brand colours.
          </span>
        </span>
      </label>

      {settings.enabled && (
        <div className="mt-4 space-y-4 border-t border-line pt-4">
          <div>
            <div className="label mb-2">Template</div>
            <div className="grid grid-cols-4 gap-2">
              {TEMPLATES.map((t) => (
                <TemplatePreview
                  key={t.id}
                  template={t}
                  brandKit={brandKit}
                  settings={settings}
                  active={settings.template === t.id}
                  onSelect={(id) => onChange({ template: id })}
                />
              ))}
            </div>
            <p className="mt-1.5 text-xs text-muted">{template.description}</p>
          </div>

          {!compact && (
            <div>
              <div className="label mb-2">Logo position</div>
              <div className="grid grid-cols-4 gap-2">
                {LOGO_POSITIONS.map((p) => (
                  <button
                    key={p.value}
                    type="button"
                    onClick={() => onChange({ logoPosition: p.value })}
                    className={`rounded-lg border px-2 py-1.5 text-xs font-medium transition ${
                      settings.logoPosition === p.value
                        ? 'border-accent bg-accent-soft text-accent'
                        : 'border-line text-muted hover:border-accent-line'
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {template.usesContact && (
            <label className="flex cursor-pointer items-center gap-2.5">
              <input
                type="checkbox"
                checked={settings.includeContact}
                onChange={(e) => onChange({ includeContact: e.target.checked })}
                className="h-4 w-4 accent-[var(--accent)]"
              />
              <span className="text-sm">Include website, phone and email</span>
            </label>
          )}
        </div>
      )}
    </div>
  )
}
