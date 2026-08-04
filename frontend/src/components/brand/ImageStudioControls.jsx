import TemplatePicker from './TemplatePicker.jsx'
import BrandKitControls from './BrandKitControls.jsx'
import { IMAGE_STYLES, IMAGE_STYLE_GROUPS } from '../../lib/constants'
import { getSize } from '../../lib/brandKit/platformSizes'

// ---------------------------------------------------------------------------
// The image settings block: template, style, prompt, brand kit.
//
// Controlled, so the same markup serves the AI Generator's page-level settings
// and the Content Planner's plan default and per-post override. Whoever renders
// it owns the state; this only knows how to display and edit a settings object
// of the shape { templateId, sizeId, img: { style, imagePrompt, … } }.
//
// `idPrefix` keeps label/input associations unique when more than one of these
// is on screen at once — which is exactly what happens in the planner, where a
// plan default and several post overrides can all be open together.
// ---------------------------------------------------------------------------
export default function ImageStudioControls({
  value,
  onChange,
  brandKit,
  brandSettings,
  onBrandSettingsChange,
  brandAvailable,
  idPrefix = 'studio',
  showTemplate = true,
  showBrandKit = true,
  showPrompt = true,
}) {
  const img = value.img || {}

  const patchImg = (patch) => onChange({ img: { ...img, ...patch } })

  return (
    <div className="space-y-3">
      {showTemplate && (
        <TemplatePicker
          templateId={value.templateId}
          sizeId={value.sizeId}
          brandKit={brandKit}
          brandSettings={brandSettings}
          onChange={(patch) => {
            // A new size has to carry the pipeline's aspect ratio with it.
            // Left to the caller this is easy to forget, and the symptom is
            // silent: images generated at the previous frame while the layout
            // is drawn for the new one.
            const next = { ...patch }
            if (patch.sizeId != null) {
              next.img = { ...img, aspectRatio: getSize(patch.sizeId).aspectRatio }
            }
            onChange(next)
          }}
        />
      )}

      <div>
        <label className="label" htmlFor={`${idPrefix}-style`}>
          Image Style
        </label>
        <select
          id={`${idPrefix}-style`}
          className="select"
          value={img.style}
          onChange={(e) => patchImg({ style: e.target.value })}
        >
          {IMAGE_STYLE_GROUPS.map((group) => (
            <optgroup key={group} label={group}>
              {IMAGE_STYLES.filter((s) => s.group === group).map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </div>

      {showPrompt && (
        <div>
          <label
            className="label flex items-center justify-between"
            htmlFor={`${idPrefix}-prompt`}
          >
            <span>Image Prompt</span>
            <span className="text-xs font-normal text-muted">
              {img.imagePrompt?.trim() ? 'Custom' : 'Auto from post'}
            </span>
          </label>
          <textarea
            id={`${idPrefix}-prompt`}
            className="input min-h-20 resize-y"
            maxLength={480}
            placeholder="Describe the image you want. Leave blank to build it from the post."
            value={img.imagePrompt || ''}
            onChange={(e) => patchImg({ imagePrompt: e.target.value })}
          />
          <p className="mt-1.5 text-xs text-muted">
            Independent of the post text — describe the visual, not the caption.
          </p>
        </div>
      )}

      {showBrandKit && (
        <BrandKitControls
          brandKit={brandKit}
          settings={brandSettings}
          onChange={onBrandSettingsChange}
          available={brandAvailable}
        />
      )}
    </div>
  )
}
