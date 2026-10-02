import { useEffect, useState } from 'react'
import { formatDuration } from '../../../lib/video/format.js'

// ---------------------------------------------------------------------------
// The inspector: the controls for whichever clip is selected.
//
// **Every control writes through the same `update` operation.** There is no
// per-property endpoint and no local model of what a clip is — the panel sends
// a patch and takes the server's normalized clip back, which is why a value
// out of range comes back clamped rather than being enforced twice.
//
// **Sliders commit on release, not on every pixel.** `onChange` fires for each
// step of a range input; posting all of them would be dozens of round trips
// for one drag. The value shown is local while dragging and committed on
// `pointerup`/`change`, which is the same commit-on-release rule the timeline
// drags follow.
//
// The controls offered are exactly the MVP's: transform, speed and volume for
// video; volume, fades and trim for audio; content, font, size, colour,
// position and one animation for text. Deliberately not dozens of effects —
// one video, one audio and one text track have to work reliably first.
// ---------------------------------------------------------------------------

/** A labelled slider that reports only when the drag ends. */
function Slider({ label, value, min, max, step = 0.01, suffix = '', onCommit, format }) {
  const [local, setLocal] = useState(value)

  // Follow the clip when the selection changes, but not while dragging — that
  // would fight the pointer.
  useEffect(() => setLocal(value), [value])

  return (
    <label className="block">
      <span className="mb-1 flex items-center justify-between text-xs text-muted">
        <span>{label}</span>
        <span className="tabular-nums">
          {format ? format(local) : `${Number(local).toFixed(2)}${suffix}`}
        </span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={local}
        onChange={(event) => setLocal(Number(event.target.value))}
        onPointerUp={() => onCommit(local)}
        onKeyUp={() => onCommit(local)}
        className="w-full accent-[var(--accent)]"
      />
    </label>
  )
}

function Section({ title, children }) {
  return (
    <div className="border-t border-line px-4 py-3 first:border-t-0">
      <h3 className="mb-2 text-xs font-bold uppercase tracking-wide text-muted">
        {title}
      </h3>
      <div className="flex flex-col gap-3">{children}</div>
    </div>
  )
}

export default function Inspector({ clip, asset, capabilities, onUpdate, onDelete, busy }) {
  if (!clip) {
    return (
      <div className="card p-6 text-center">
        <p className="text-sm text-muted">
          Select a clip on the timeline to edit it.
        </p>
      </div>
    )
  }

  const set = (patch) => onUpdate(clip.id, patch)
  const editor = capabilities?.editor || {}
  const fonts = editor.fonts || ['Inter', 'Roboto', 'Montserrat', 'Poppins', 'Arial']
  const animations = editor.text_animations || ['none', 'fade', 'slide-up', 'pop']
  const [minSpeed, maxSpeed] = editor.speed_range || [0.25, 4]

  // The columns hold preview, export and this panel side by side, and the
  // panel is the tallest of the three when a clip is selected. Capping it to
  // the viewport — the title pinned, the controls scrolling underneath — is
  // what stops the Text/Style/Position/Timing sections from stretching the
  // whole page past the preview and the timeline.
  return (
    <div className="card flex max-h-[70vh] flex-col lg:max-h-[calc(100vh-7rem)]">
      <div className="flex shrink-0 items-start justify-between gap-2 border-b border-line p-4 pb-3">
        <div className="min-w-0">
          <p className="truncate font-semibold text-body">
            {clip.kind === 'text' ? clip.text || 'Text' : asset?.title || clip.kind}
          </p>
          <p className="text-xs text-muted">
            {clip.kind} · {formatDuration(clip.start)} →{' '}
            {formatDuration(clip.start + clip.duration)}
          </p>
        </div>
        <button
          className="btn btn-ghost btn-sm shrink-0"
          onClick={() => onDelete(clip.id)}
          disabled={busy || clip.locked}
        >
          Delete
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">

      {clip.asset_id && !asset && (
        <div className="mx-4 mb-3 rounded-[10px] border border-rose-300 bg-rose-50 px-3 py-2">
          <p className="text-sm text-rose-700">
            The file this clip uses is no longer in your library. Replace it, or
            delete the clip — exporting will fail until you do.
          </p>
        </div>
      )}

      {/* ---- Video and image ---- */}
      {(clip.kind === 'video' || clip.kind === 'image') && (
        <>
          <Section title="Transform">
            <Slider
              label="Scale" value={clip.scale} min={0.1} max={4} step={0.01}
              format={(v) => `${Math.round(v * 100)}%`}
              onCommit={(value) => set({ scale: value })}
            />
            <Slider
              label="Horizontal" value={clip.x} min={-1} max={1} step={0.005}
              onCommit={(value) => set({ x: value })}
            />
            <Slider
              label="Vertical" value={clip.y} min={-1} max={1} step={0.005}
              onCommit={(value) => set({ y: value })}
            />
            <Slider
              label="Rotation" value={clip.rotation} min={-180} max={180} step={1}
              format={(v) => `${Math.round(v)}°`}
              onCommit={(value) => set({ rotation: value })}
            />
            <label className="block">
              <span className="label">Fit</span>
              <select
                className="select"
                value={clip.fit}
                onChange={(event) => set({ fit: event.target.value })}
              >
                {(editor.fit_modes || ['cover', 'contain']).map((mode) => (
                  <option key={mode} value={mode}>
                    {mode === 'cover' ? 'Fill the frame' : 'Fit inside the frame'}
                  </option>
                ))}
              </select>
            </label>
          </Section>

          <Section title="Crop">
            {['left', 'right', 'top', 'bottom'].map((edge) => (
              <Slider
                key={edge}
                label={edge[0].toUpperCase() + edge.slice(1)}
                value={clip.crop?.[edge] ?? 0}
                min={0}
                max={0.45}
                step={0.005}
                format={(v) => `${Math.round(v * 100)}%`}
                onCommit={(value) => set({ crop: { ...clip.crop, [edge]: value } })}
              />
            ))}
          </Section>

          {clip.kind === 'video' && (
            <Section title="Playback">
              <Slider
                label="Speed" value={clip.speed} min={minSpeed} max={maxSpeed} step={0.05}
                format={(v) => `${Number(v).toFixed(2)}×`}
                onCommit={(value) => set({ speed: value })}
              />
              <Slider
                label="Volume" value={clip.volume} min={0} max={2} step={0.01}
                format={(v) => `${Math.round(v * 100)}%`}
                onCommit={(value) => set({ volume: value })}
              />
              <label className="flex items-center gap-2 text-sm text-body">
                <input
                  type="checkbox"
                  checked={clip.muted}
                  onChange={(event) => set({ muted: event.target.checked })}
                />
                Mute this clip
              </label>
            </Section>
          )}
        </>
      )}

      {/* ---- Audio ---- */}
      {clip.kind === 'audio' && (
        <Section title="Audio">
          <label className="block">
            <span className="label">Role</span>
            <select
              className="select"
              value={clip.role}
              onChange={(event) => set({ role: event.target.value })}
            >
              {(editor.audio_roles || ['voiceover', 'music', 'sfx']).map((role) => (
                <option key={role} value={role}>
                  {role === 'voiceover' ? 'Voice-over' : role[0].toUpperCase() + role.slice(1)}
                </option>
              ))}
            </select>
          </label>
          <Slider
            label="Volume" value={clip.volume} min={0} max={2} step={0.01}
            format={(v) => `${Math.round(v * 100)}%`}
            onCommit={(value) => set({ volume: value })}
          />
          <Slider
            label="Fade in" value={clip.fade_in} min={0} max={Math.max(0.1, clip.duration / 2)}
            step={0.05} suffix="s"
            onCommit={(value) => set({ fade_in: value })}
          />
          <Slider
            label="Fade out" value={clip.fade_out} min={0} max={Math.max(0.1, clip.duration / 2)}
            step={0.05} suffix="s"
            onCommit={(value) => set({ fade_out: value })}
          />
          <Slider
            label="Speed" value={clip.speed} min={minSpeed} max={maxSpeed} step={0.05}
            format={(v) => `${Number(v).toFixed(2)}×`}
            onCommit={(value) => set({ speed: value })}
          />
          <label className="flex items-center gap-2 text-sm text-body">
            <input
              type="checkbox"
              checked={clip.muted}
              onChange={(event) => set({ muted: event.target.checked })}
            />
            Mute
          </label>
        </Section>
      )}

      {/* ---- Text ---- */}
      {clip.kind === 'text' && (
        <>
          <Section title="Text">
            <textarea
              className="input min-h-[80px] resize-y"
              value={clip.text}
              placeholder="Your title…"
              onChange={(event) => set({ text: event.target.value })}
            />
            {editor.text_rendering_available === false && (
              <p className="text-xs text-amber-700">
                This server has no font installed, so text will not appear in the
                export.
              </p>
            )}
          </Section>

          <Section title="Style">
            <label className="block">
              <span className="label">Font</span>
              <select
                className="select"
                value={clip.font_family}
                onChange={(event) => set({ font_family: event.target.value })}
              >
                {fonts.map((font) => (
                  <option key={font} value={font}>{font}</option>
                ))}
              </select>
            </label>
            <Slider
              label="Size" value={clip.font_size} min={12} max={200} step={1}
              format={(v) => `${Math.round(v)}px`}
              onCommit={(value) => set({ font_size: Math.round(value) })}
            />
            <div className="flex gap-3">
              <label className="flex-1">
                <span className="label">Colour</span>
                <input
                  type="color"
                  className="input h-9 p-1"
                  value={clip.color}
                  onChange={(event) => set({ color: event.target.value })}
                />
              </label>
              <label className="flex-1">
                <span className="label">Outline</span>
                <input
                  type="color"
                  className="input h-9 p-1"
                  value={clip.outline === 'transparent' ? '#000000' : clip.outline}
                  onChange={(event) => set({ outline: event.target.value })}
                />
              </label>
            </div>
            <label className="flex items-center gap-2 text-sm text-body">
              <input
                type="checkbox"
                checked={clip.uppercase}
                onChange={(event) => set({ uppercase: event.target.checked })}
              />
              Uppercase
            </label>
          </Section>

          <Section title="Position">
            <label className="block">
              <span className="label">Placement</span>
              <select
                className="select"
                value={clip.position}
                onChange={(event) => set({ position: event.target.value })}
              >
                {(editor.text_positions || ['top', 'center', 'bottom']).map((value) => (
                  <option key={value} value={value}>
                    {value[0].toUpperCase() + value.slice(1)}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="label">Alignment</span>
              <select
                className="select"
                value={clip.align}
                onChange={(event) => set({ align: event.target.value })}
              >
                {(editor.text_alignments || ['left', 'center', 'right']).map((value) => (
                  <option key={value} value={value}>
                    {value[0].toUpperCase() + value.slice(1)}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="label">Animation</span>
              <select
                className="select"
                value={clip.animation}
                onChange={(event) => set({ animation: event.target.value })}
              >
                {animations.map((value) => (
                  <option key={value} value={value}>
                    {value === 'none' ? 'None' : value.replace('-', ' ')}
                  </option>
                ))}
              </select>
            </label>
          </Section>
        </>
      )}

      <Section title="Timing">
        <Slider
          label="Length" value={clip.duration} min={0.1}
          max={Math.max(clip.duration * 2, 30)} step={0.05} suffix="s"
          onCommit={(value) => set({ duration: value })}
        />
        <label className="flex items-center gap-2 text-sm text-body">
          <input
            type="checkbox"
            checked={clip.locked}
            onChange={(event) => set({ locked: event.target.checked })}
          />
          Lock this clip
        </label>
      </Section>
      </div>
    </div>
  )
}
