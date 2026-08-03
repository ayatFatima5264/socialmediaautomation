import { useRef, useState } from 'react'
import BrandOverlay from './BrandOverlay.jsx'
import { buildBrandLayers } from '../../lib/brandKit/templates'
import { isHex, paletteOf } from '../../lib/brandKit/layers'

// ---------------------------------------------------------------------------
// Brand Kit editor — logo, colours, and contact details.
//
// Lives in its own component so the Business Profile page composes it rather
// than growing another 200 lines, and so onboarding can reuse it later.
//
// The logo is stored as a data: URL rather than uploaded to a file store. The
// API runs on an ephemeral disk, so uploaded files would not survive a
// redeploy; a single small logo per user is well within what a TEXT column
// handles, and it sidesteps blob-storage infrastructure entirely. A remote URL
// is also accepted, with the caveat that exporting a branded image needs the
// host to send CORS headers — which is why upload is presented first.
// ---------------------------------------------------------------------------

const MAX_LOGO_BYTES = 512 * 1024 // 512 KB — generous for a logo, safe for a row

function ColorSwatch({ value, onChange, onRemove, index }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-line bg-surface p-1.5">
      <input
        type="color"
        value={isHex(value) ? value : '#1f8a5b'}
        onChange={(e) => onChange(e.target.value)}
        className="h-8 w-8 cursor-pointer rounded border-0 bg-transparent p-0"
        aria-label={`Brand colour ${index + 1}`}
      />
      <input
        className="w-24 bg-transparent font-mono text-xs uppercase outline-none"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="#1F8A5B"
        maxLength={7}
      />
      <button
        type="button"
        onClick={onRemove}
        className="px-1 text-muted transition hover:text-rose-500"
        aria-label={`Remove colour ${index + 1}`}
      >
        ×
      </button>
    </div>
  )
}

export default function BrandKitFields({ value, onChange }) {
  const fileRef = useRef(null)
  const [error, setError] = useState('')
  const colors = value.brand_colors || []

  function pickLogo(file) {
    setError('')
    if (!file) return
    if (!file.type.startsWith('image/')) {
      setError('That file is not an image.')
      return
    }
    if (file.size > MAX_LOGO_BYTES) {
      setError(`Logo must be under ${Math.round(MAX_LOGO_BYTES / 1024)} KB. Try a PNG or SVG.`)
      return
    }
    const reader = new FileReader()
    reader.onload = () => onChange({ logo_url: String(reader.result) })
    reader.onerror = () => setError('Could not read that file.')
    reader.readAsDataURL(file)
  }

  const setColor = (i, hex) => {
    const next = [...colors]
    next[i] = hex
    onChange({ brand_colors: next })
  }

  // Live preview using the real pipeline, so what's shown here is exactly what
  // the Generator will overlay.
  const { primary, secondary } = paletteOf(value)
  const previewLayers = buildBrandLayers(value, {
    template: 'footer-bar',
    logoPosition: 'bottom-right',
    includeContact: true,
  })

  return (
    <div className="space-y-6">
      {/* ---- Logo ---------------------------------------------------- */}
      <div>
        <div className="label mb-2">Logo</div>
        <div className="flex flex-wrap items-center gap-4">
          <div className="grid h-20 w-20 shrink-0 place-items-center overflow-hidden rounded-xl border border-line bg-inset">
            {value.logo_url ? (
              <img
                src={value.logo_url}
                alt="Your logo"
                className="h-full w-full object-contain p-1.5"
              />
            ) : (
              <span className="text-xs text-muted">None</span>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="btn btn-secondary btn-sm"
            >
              {value.logo_url ? 'Replace logo' : 'Upload logo'}
            </button>
            {value.logo_url && (
              <button
                type="button"
                onClick={() => onChange({ logo_url: null })}
                className="btn btn-ghost btn-sm"
              >
                Remove
              </button>
            )}
            <input
              ref={fileRef}
              type="file"
              accept="image/png,image/jpeg,image/svg+xml,image/webp"
              className="hidden"
              onChange={(e) => {
                pickLogo(e.target.files?.[0])
                e.target.value = ''
              }}
            />
          </div>
        </div>
        <p className="mt-2 text-xs text-muted">
          PNG with a transparent background works best. Under 512 KB.
        </p>
        {error && <p className="mt-1.5 text-xs font-medium text-rose-500">{error}</p>}
      </div>

      {/* ---- Colours ------------------------------------------------- */}
      <div>
        <div className="label mb-2 flex items-center justify-between">
          <span>Brand colours</span>
          <span className="text-xs font-normal text-muted">First is primary</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {colors.map((c, i) => (
            <ColorSwatch
              key={i}
              index={i}
              value={c}
              onChange={(hex) => setColor(i, hex)}
              onRemove={() => onChange({ brand_colors: colors.filter((_, j) => j !== i) })}
            />
          ))}
          {colors.length < 4 && (
            <button
              type="button"
              onClick={() => onChange({ brand_colors: [...colors, '#1f8a5b'] })}
              className="rounded-lg border border-dashed border-line px-3 py-2 text-sm font-medium text-muted transition hover:border-accent-line hover:text-accent"
            >
              + Add colour
            </button>
          )}
        </div>
        <p className="mt-2 text-xs text-muted">
          Used for overlay bars and badges, and to steer the AI's palette.
        </p>
      </div>

      {/* ---- Contact ------------------------------------------------- */}
      <div className="grid gap-5 sm:grid-cols-2">
        <div>
          <label className="label mb-2">Phone</label>
          <input
            className="input"
            type="tel"
            placeholder="+92 300 1234567"
            value={value.phone || ''}
            onChange={(e) => onChange({ phone: e.target.value })}
          />
        </div>
        <div>
          <label className="label mb-2">
            Email <span className="text-xs font-normal text-muted">Optional</span>
          </label>
          <input
            className="input"
            type="email"
            placeholder="hello@example.com"
            value={value.email || ''}
            onChange={(e) => onChange({ email: e.target.value })}
          />
        </div>
      </div>

      <div>
        <label className="label mb-2">
          Address <span className="text-xs font-normal text-muted">Optional</span>
        </label>
        <input
          className="input"
          placeholder="123 High Street, Lahore"
          value={value.address || ''}
          onChange={(e) => onChange({ address: e.target.value })}
        />
      </div>

      {/* ---- Live preview -------------------------------------------- */}
      <div>
        <div className="label mb-2">Preview</div>
        <div
          className="relative aspect-[16/9] w-full max-w-sm overflow-hidden rounded-xl border border-line"
          style={{ background: `linear-gradient(135deg, ${secondary}, ${primary})` }}
        >
          <BrandOverlay layers={previewLayers} aspect={16 / 9} idPrefix="brandkit-preview" />
        </div>
        <p className="mt-2 text-xs text-muted">
          Rendered with the same layer engine the Generator uses, so this is exactly how your
          branding will appear.
        </p>
      </div>
    </div>
  )
}
