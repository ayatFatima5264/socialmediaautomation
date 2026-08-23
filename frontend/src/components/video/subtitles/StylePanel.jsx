import { useMemo } from 'react'

// ---------------------------------------------------------------------------
// Subtitle styling, with a preview that renders the real thing.
//
// The preview is the point. Every control here changes how text sits over
// video, and none of it can be judged from a number — 44px is meaningless
// until you see it against a frame. So the panel draws an actual caption over
// a stand-in video area, using the same CSS the burn-in step will reproduce.
//
// The vocabularies (fonts, positions, alignments, animations) come from the
// server, not from a list in here. The renderer has to understand every value
// the editor can produce, so there is one list and the API serves it.
// ---------------------------------------------------------------------------

/** The CSS a cue is drawn with. Shared by the preview and the player overlay
 *  so the two cannot disagree about what a style looks like. */
export function cueTextStyle(style) {
  if (!style) return {}

  const outline =
    style.outline && style.outline !== 'none' && style.outline_width > 0
      ? `${style.outline_width}px ${style.outline}`
      : null

  return {
    fontFamily: `${style.font_family}, system-ui, sans-serif`,
    fontSize: `${style.font_size}px`,
    fontWeight: style.font_weight,
    color: style.color,
    backgroundColor:
      style.background && style.background !== 'transparent' ? style.background : 'transparent',
    textTransform: style.uppercase ? 'uppercase' : 'none',
    // Stroke via paint-order where supported, with a shadow fallback so the
    // outline is visible in browsers that ignore it rather than vanishing.
    WebkitTextStroke: outline || undefined,
    paintOrder: outline ? 'stroke fill' : undefined,
    textShadow: style.shadow ? '0 2px 6px rgba(0,0,0,0.65)' : 'none',
    textAlign: style.align,
    lineHeight: 1.25,
    padding: style.background && style.background !== 'transparent' ? '0.15em 0.5em' : 0,
    borderRadius: 6,
    display: 'inline-block',
    maxWidth: '92%',
  }
}

const POSITION_CLASS = {
  top: 'items-start pt-4',
  center: 'items-center',
  bottom: 'items-end pb-4',
}

const ALIGN_CLASS = {
  left: 'justify-start text-left',
  center: 'justify-center text-center',
  right: 'justify-end text-right',
}

function Field({ label, hint, children }) {
  return (
    <div>
      <label className="label">{label}</label>
      {children}
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  )
}

function Slider({ label, value, min, max, step = 1, onChange, format }) {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between">
        <label className="label mb-0">{label}</label>
        <span className="text-xs tabular-nums text-muted">{format(value)}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="w-full accent-[var(--accent)]"
        aria-label={label}
      />
    </div>
  )
}

function Colour({ label, value, onChange, allowTransparent = false }) {
  const transparent = !value || value === 'transparent' || value === 'none'
  // A colour input cannot express "none", so the swatch and the toggle are
  // separate controls rather than one that lies about its state.
  return (
    <div>
      <label className="label">{label}</label>
      <div className="flex items-center gap-2">
        <input
          type="color"
          value={transparent ? '#000000' : rgbaToHex(value)}
          onChange={(event) => onChange(event.target.value)}
          className="h-9 w-12 cursor-pointer rounded-lg border border-line bg-surface p-1"
          aria-label={label}
        />
        {allowTransparent && (
          <label className="flex items-center gap-1.5 text-xs text-muted">
            <input
              type="checkbox"
              checked={transparent}
              onChange={(event) => onChange(event.target.checked ? 'none' : '#000000')}
              className="accent-[var(--accent)]"
            />
            None
          </label>
        )}
      </div>
    </div>
  )
}

/** `rgba(0,0,0,0.35)` -> `#000000`, so the swatch shows something sensible for
 *  a preset colour that carries alpha the input cannot represent. */
function rgbaToHex(value) {
  if (typeof value !== 'string') return '#000000'
  if (value.startsWith('#')) return value.slice(0, 7)
  const match = value.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i)
  if (!match) return '#000000'
  return `#${match.slice(1, 4).map((n) => Number(n).toString(16).padStart(2, '0')).join('')}`
}

export default function StylePanel({ style, options, onChange, sampleText }) {
  const preview = useMemo(() => cueTextStyle(style), [style])

  if (!style || !options) {
    return (
      <div className="flex flex-col gap-3">
        {Array.from({ length: 6 }).map((_, index) => (
          <div key={index} className="skeleton h-10" />
        ))}
      </div>
    )
  }

  const set = (patch) => onChange({ ...style, ...patch })

  return (
    <div className="flex flex-col gap-4">
      {/* ---- Preview ------------------------------------------------- */}
      <div>
        <label className="label">Preview</label>
        <div
          className={`relative flex overflow-hidden rounded-[10px] border border-line ${
            POSITION_CLASS[style.position] || POSITION_CLASS.bottom
          } ${ALIGN_CLASS[style.align] || ALIGN_CLASS.center}`}
          style={{
            // A dark stand-in for video. Subtitles are judged against footage,
            // and a caption previewed on white tells you nothing about how it
            // will read over a real frame.
            background:
              'linear-gradient(140deg, #1d2b24 0%, #35473d 45%, #22312a 100%)',
            aspectRatio: '16 / 9',
            padding: '0 0.75rem',
          }}
        >
          <span
            style={{
              ...preview,
              // The preview box is much smaller than a 1080p frame, so the font
              // size is scaled to match what the proportion will actually be.
              fontSize: `${Math.max(9, style.font_size * 0.28)}px`,
            }}
          >
            {sampleText || 'The quick brown fox jumps over the lazy dog'}
          </span>
        </div>
        <p className="mt-1 text-xs text-muted">
          Shown at preview scale — the exported size is {style.font_size}px on a
          1080p frame.
        </p>
      </div>

      {/* ---- Presets ------------------------------------------------- */}
      <Field label="Preset" hint={options.presets.find((p) => p.key === style.key)?.description}>
        <select
          className="select"
          value={style.key}
          onChange={(event) => {
            const chosen = options.presets.find((p) => p.key === event.target.value)
            if (chosen) onChange(chosen)
          }}
        >
          {options.presets.map((preset) => (
            <option key={preset.key} value={preset.key}>
              {preset.label}
            </option>
          ))}
        </select>
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Font">
          <select
            className="select"
            value={style.font_family}
            onChange={(event) => set({ font_family: event.target.value })}
          >
            {options.fonts.map((font) => (
              <option key={font} value={font}>
                {font}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Weight">
          <select
            className="select"
            value={style.font_weight}
            onChange={(event) => set({ font_weight: Number(event.target.value) })}
          >
            {[400, 500, 600, 700, 800, 900].map((weight) => (
              <option key={weight} value={weight}>
                {weight}
              </option>
            ))}
          </select>
        </Field>
      </div>

      <Slider
        label="Size"
        value={style.font_size}
        min={12}
        max={200}
        onChange={(font_size) => set({ font_size })}
        format={(v) => `${v}px`}
      />

      <div className="grid grid-cols-2 gap-3">
        <Colour label="Text colour" value={style.color} onChange={(color) => set({ color })} />
        <Colour
          label="Background"
          value={style.background}
          allowTransparent
          onChange={(background) =>
            set({ background: background === 'none' ? 'transparent' : background })
          }
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Colour
          label="Outline"
          value={style.outline}
          allowTransparent
          onChange={(outline) => set({ outline })}
        />
        <Slider
          label="Outline width"
          value={style.outline_width}
          min={0}
          max={12}
          onChange={(outline_width) => set({ outline_width })}
          format={(v) => `${v}px`}
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Position">
          <select
            className="select"
            value={style.position}
            onChange={(event) => set({ position: event.target.value })}
          >
            {options.positions.map((position) => (
              <option key={position} value={position}>
                {position[0].toUpperCase() + position.slice(1)}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Alignment">
          <select
            className="select"
            value={style.align}
            onChange={(event) => set({ align: event.target.value })}
          >
            {options.alignments.map((align) => (
              <option key={align} value={align}>
                {align[0].toUpperCase() + align.slice(1)}
              </option>
            ))}
          </select>
        </Field>
      </div>

      <Field
        label="Animation"
        hint="How each subtitle appears. “None” is right for most long-form video."
      >
        <select
          className="select"
          value={style.animation}
          onChange={(event) => set({ animation: event.target.value })}
        >
          {options.animations.map((animation) => (
            <option key={animation} value={animation}>
              {animation === 'none' ? 'None' : animation.replace('-', ' ')}
            </option>
          ))}
        </select>
      </Field>

      <div className="flex flex-col gap-2">
        {[
          { key: 'shadow', label: 'Drop shadow' },
          { key: 'uppercase', label: 'Uppercase' },
        ].map((toggle) => (
          <label key={toggle.key} className="flex items-center gap-2 text-sm text-body">
            <input
              type="checkbox"
              checked={Boolean(style[toggle.key])}
              onChange={(event) => set({ [toggle.key]: event.target.checked })}
              className="accent-[var(--accent)]"
            />
            {toggle.label}
          </label>
        ))}

        <label className="flex items-center gap-2 text-sm text-body">
          <input
            type="checkbox"
            checked={Boolean(style.word_highlight)}
            onChange={(event) => set({ word_highlight: event.target.checked })}
            className="accent-[var(--accent)]"
          />
          Word highlighting
        </label>
        {style.word_highlight && (
          <div className="pl-6">
            <Colour
              label="Highlight colour"
              value={style.highlight_color || '#159A68'}
              onChange={(highlight_color) => set({ highlight_color })}
            />
            <p className="mt-1 text-xs text-muted">
              Highlights the spoken word as it is said. Needs per-word timings —
              transcribed subtitles have them; script-timed ones do not.
            </p>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Slider
          label="Characters per line"
          value={style.max_chars_per_line}
          min={12}
          max={80}
          onChange={(max_chars_per_line) => set({ max_chars_per_line })}
          format={(v) => `${v}`}
        />
        <Slider
          label="Lines per subtitle"
          value={style.max_lines}
          min={1}
          max={4}
          onChange={(max_lines) => set({ max_lines })}
          format={(v) => `${v}`}
        />
      </div>
    </div>
  )
}
