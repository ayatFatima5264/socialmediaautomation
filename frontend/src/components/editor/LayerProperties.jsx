import { useRef } from 'react'
import { LAYER_TYPES, FONT_FAMILIES } from '../../lib/brandKit/layers'
import {
  Field,
  CompactSelect,
  CompactSlider,
  CompactColor,
  Segmented,
  MiniButton,
} from './controls.jsx'

// ---------------------------------------------------------------------------
// Properties for the selected layer, in the compact two-column form.
//
// Controls are still driven by the layer's TYPE, so adding a layer type means
// adding a case here and nothing else. Functionality is unchanged from the
// stacked version — every property that could be edited before can still be
// edited, in roughly half the vertical space.
// ---------------------------------------------------------------------------

export default function LayerProperties({ layer, onChange, onReplaceImage, onBrowseLibrary }) {
  const fileRef = useRef(null)
  if (!layer) return null

  const set = (patch) => onChange(layer.id, patch)
  const isText = layer.type === LAYER_TYPES.TEXT
  const isImage = layer.type === LAYER_TYPES.IMAGE
  const isBackground = layer.type === LAYER_TYPES.BACKGROUND
  const isStroke = layer.type === LAYER_TYPES.LINE || layer.type === LAYER_TYPES.ARROW
  const isFilled = layer.type === LAYER_TYPES.RECT || layer.type === LAYER_TYPES.ELLIPSE

  return (
    <div className="space-y-0.5">
      {isText && (
        <>
          <Field label="Text" stack>
            <textarea
              className="min-h-14 w-full resize-y rounded-md border border-field-border bg-field px-2 py-1.5 text-xs text-body outline-none focus:border-accent"
              value={layer.text || ''}
              onChange={(e) => set({ text: e.target.value })}
              placeholder="Your text"
            />
          </Field>

          <Field label="Font">
            <CompactSelect
              value={layer.fontFamily || FONT_FAMILIES[0].value}
              onChange={(fontFamily) => set({ fontFamily })}
              style={{ fontFamily: layer.fontFamily }}
              options={FONT_FAMILIES.map((f) => ({
                value: f.value,
                label: f.label,
                style: { fontFamily: f.value },
              }))}
            />
          </Field>

          <Field label="Size">
            <CompactSlider
              min={0.012}
              max={0.22}
              step={0.002}
              value={layer.size?.h ?? 0.05}
              onChange={(h) => set({ size: { ...layer.size, h } })}
              format={(v) => Math.round(v * 1000)}
            />
          </Field>

          <Field label="Colour">
            <CompactColor value={layer.fill} onChange={(fill) => set({ fill })} />
          </Field>

          <Field label="Style">
            <div className="flex gap-1">
              <Segmented
                value={(layer.weight || 600) >= 700 ? 'b' : ''}
                onChange={() => set({ weight: (layer.weight || 600) >= 700 ? 400 : 800 })}
                options={[{ value: 'b', label: 'B', title: 'Bold', className: 'font-black' }]}
              />
              <Segmented
                value={layer.italic ? 'i' : ''}
                onChange={() => set({ italic: !layer.italic })}
                options={[{ value: 'i', label: 'I', title: 'Italic', className: 'italic' }]}
              />
            </div>
          </Field>

          <Field label="Align">
            <Segmented
              value={layer.align || 'left'}
              onChange={(align) => set({ align })}
              options={[
                { value: 'left', label: '←', title: 'Left' },
                { value: 'center', label: '↔', title: 'Centre' },
                { value: 'right', label: '→', title: 'Right' },
              ]}
            />
          </Field>
        </>
      )}

      {isBackground && (
        <>
          <Field label="Type">
            <Segmented
              wide
              value={layer.gradient ? 'gradient' : 'solid'}
              onChange={(mode) =>
                set(
                  mode === 'gradient'
                    ? { gradient: { from: layer.fill || '#1f8a5b', to: '#0b3d2e', angle: 180 } }
                    : { gradient: null },
                )
              }
              options={[
                { value: 'solid', label: 'Solid' },
                { value: 'gradient', label: 'Gradient' },
              ]}
            />
          </Field>

          {layer.gradient ? (
            <>
              <Field label="From">
                <CompactColor
                  value={layer.gradient.from}
                  onChange={(from) => set({ gradient: { ...layer.gradient, from } })}
                />
              </Field>
              <Field label="To">
                <CompactColor
                  value={layer.gradient.to}
                  onChange={(to) => set({ gradient: { ...layer.gradient, to } })}
                />
              </Field>
              <Field label="Angle">
                <Segmented
                  wide
                  value={layer.gradient.angle === 90 ? 90 : 180}
                  onChange={(angle) => set({ gradient: { ...layer.gradient, angle } })}
                  options={[
                    { value: 180, label: 'Vertical' },
                    { value: 90, label: 'Horizontal' },
                  ]}
                />
              </Field>
            </>
          ) : (
            <Field label="Colour">
              <CompactColor value={layer.fill} onChange={(fill) => set({ fill })} />
            </Field>
          )}
        </>
      )}

      {isFilled && (
        <>
          <Field label="Fill">
            <CompactColor value={layer.fill} onChange={(fill) => set({ fill })} fallback="#1f8a5b" />
          </Field>
          {layer.type === LAYER_TYPES.RECT && (
            <Field label="Radius">
              <CompactSlider
                min={0}
                max={0.12}
                step={0.004}
                value={layer.radius ?? 0}
                onChange={(radius) => set({ radius })}
                format={(v) => Math.round(v * 1000)}
              />
            </Field>
          )}
        </>
      )}

      {isStroke && (
        <>
          <Field label="Colour">
            <CompactColor value={layer.stroke} onChange={(stroke) => set({ stroke })} />
          </Field>
          <Field label="Weight">
            <CompactSlider
              min={0.002}
              max={0.03}
              step={0.001}
              value={layer.strokeWidth ?? 0.006}
              onChange={(strokeWidth) => set({ strokeWidth })}
              format={(v) => Math.round(v * 1000)}
            />
          </Field>
        </>
      )}

      {isImage && (
        <>
          <Field label="Source">
            <MiniButton onClick={() => fileRef.current?.click()} title="Replace this image">
              ⇄ Replace
            </MiniButton>
            {onBrowseLibrary && (
              <MiniButton
                onClick={() => onBrowseLibrary(layer.id)}
                title="Replace from your media library"
              >
                🖼 Library
              </MiniButton>
            )}
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) onReplaceImage(layer.id, f)
                e.target.value = ''
              }}
            />
          </Field>
          <Field label="Fit">
            <Segmented
              wide
              value={layer.keepAspect === false ? 'fill' : 'contain'}
              onChange={(mode) => set({ keepAspect: mode === 'contain' })}
              options={[
                { value: 'contain', label: 'Fit' },
                { value: 'fill', label: 'Crop' },
              ]}
            />
          </Field>
        </>
      )}

      {!isBackground && (
        <>
          <Field label="Rotate">
            <CompactSlider
              min={-180}
              max={180}
              step={1}
              value={layer.rotation || 0}
              onChange={(rotation) => set({ rotation })}
              format={(v) => `${v}°`}
            />
          </Field>
          <Field label="Opacity">
            <CompactSlider
              min={0.05}
              max={1}
              step={0.05}
              value={layer.opacity ?? 1}
              onChange={(opacity) => set({ opacity })}
              format={(v) => `${Math.round(v * 100)}%`}
            />
          </Field>
        </>
      )}
    </div>
  )
}
