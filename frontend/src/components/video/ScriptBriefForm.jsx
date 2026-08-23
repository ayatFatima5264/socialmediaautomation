import { useState } from 'react'
import VideoIcon from './VideoIcon.jsx'
import Spinner from '../Spinner.jsx'

// ---------------------------------------------------------------------------
// The brief — the eight inputs a script is written from.
//
// Shared by AI Video and Script Studio. The option lists come from the server
// (`/api/video/ai/options`) rather than being hardcoded here, so a tone the
// generator understands and a tone the form offers cannot drift apart.
//
// `submitLabel` is the only thing the two callers disagree about: one is
// starting a video, the other is only writing a script.
// ---------------------------------------------------------------------------

// The lengths worth one tap. The server sends this list (`options.durations`)
// for the same reason it sends the tones — a length the form offers and the
// generator refuses is a control that does nothing. This copy is the fallback
// for a server that has not been deployed yet.
const DURATIONS = [15, 30, 45, 60, 90, 120, 180, 300, 600, 900, 1200, 1500, 1800]

function durationLabel(seconds) {
  if (seconds < 60) return `${seconds} seconds`
  const minutes = seconds / 60
  // 90 seconds is "1.5 minutes"; 600 is "10 minutes", not "10.0".
  const shown = Number.isInteger(minutes) ? minutes : minutes.toFixed(1)
  return `${shown} minute${minutes === 1 ? '' : 's'}`
}

function Field({ label, hint, children }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  )
}

export default function ScriptBriefForm({
  options,
  onSubmit,
  busy,
  submitLabel = 'Write the script',
  busyLabel = 'Writing the script…',
  // The longest length this form may offer. Script Studio leaves it open —
  // writing a half-hour script is free. The video flow passes the render limit,
  // because offering a length the renderer will refuse is a wall at the end of
  // a long generation rather than a choice made up front.
  maxDuration = Infinity,
}) {
  const [form, setForm] = useState({
    topic: '',
    language: 'en-US',
    tone: 'friendly',
    audience: 'a general audience',
    duration_seconds: 30,
    platform: 'youtube_shorts',
    content_type: 'educational',
    instructions: '',
    visual_mode: 'natural',
  })

  const set = (patch) => setForm((current) => ({ ...current, ...patch }))

  const durations = (options?.durations?.length ? options.durations : DURATIONS).filter(
    (value) => value <= maxDuration,
  )

  // A script longer than this deployment will render is still worth writing —
  // but the user should hear that here, not after the generation, from the
  // export screen.
  // A long script is written in passes, which is tens of seconds rather than
  // a few. Saying so beats a spinner that looks identical to a hung request.
  const waiting =
    form.duration_seconds > 240
      ? `Writing ${durationLabel(form.duration_seconds)} of script — this takes a moment…`
      : busyLabel

  const renderCap = Number(options?.max_video_seconds) || 0
  const lengthHint =
    renderCap && form.duration_seconds > renderCap
      ? `Rendering is limited to ${durationLabel(renderCap)} on this plan. ` +
        'A script this long is yours to keep, edit and export as text.'
      : null

  return (
    <form
      className="card flex flex-col gap-4 p-5"
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit(form)
      }}
    >
      <Field label="What is the video about?">
        <textarea
          className="input min-h-[80px] resize-y"
          placeholder="How compound interest works, and why starting at 25 beats starting at 35"
          value={form.topic}
          onChange={(event) => set({ topic: event.target.value })}
          required
          minLength={3}
        />
      </Field>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Language">
          <select
            className="select"
            value={form.language}
            onChange={(event) => set({ language: event.target.value })}
          >
            {(options?.languages || []).map((entry) => (
              <option key={entry.code} value={entry.code}>
                {entry.label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Tone">
          <select
            className="select"
            value={form.tone}
            onChange={(event) => set({ tone: event.target.value })}
          >
            {(options?.tones || []).map((value) => (
              <option key={value} value={value}>
                {value[0].toUpperCase() + value.slice(1)}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Who is it for?">
          <input
            className="input"
            value={form.audience}
            onChange={(event) => set({ audience: event.target.value })}
            placeholder="People in their twenties"
          />
        </Field>

        <Field label="Content type">
          <select
            className="select"
            value={form.content_type}
            onChange={(event) => set({ content_type: event.target.value })}
          >
            {(options?.content_types || []).map((value) => (
              <option key={value} value={value}>
                {value[0].toUpperCase() + value.slice(1)}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Platform">
          <select
            className="select"
            value={form.platform}
            onChange={(event) => set({ platform: event.target.value })}
          >
            {(options?.platforms || []).map((entry) => (
              <option key={entry.key} value={entry.key}>
                {entry.label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Length" hint={lengthHint}>
          <select
            className="select"
            value={form.duration_seconds}
            onChange={(event) => set({ duration_seconds: Number(event.target.value) })}
          >
            {durations.map((value) => (
              <option key={value} value={value}>
                {durationLabel(value)}
              </option>
            ))}
          </select>
        </Field>
      </div>

      <Field
        label="Look"
        hint={
          form.visual_mode === 'animated'
            ? 'Animated text on generated backgrounds. No footage — the words are the video.'
            : 'Real photography behind the narration, from stock or generated.'
        }
      >
        <div className="flex gap-2">
          {(options?.visual_modes || ['natural', 'animated']).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => set({ visual_mode: mode })}
              className={`btn btn-sm flex-1 ${
                form.visual_mode === mode ? 'btn-primary' : 'btn-secondary'
              }`}
            >
              {mode === 'natural' ? 'Natural' : 'Animated'}
            </button>
          ))}
        </div>
      </Field>

      <Field label="Anything else? (optional)">
        <textarea
          className="input min-h-[60px] resize-y"
          placeholder="Mention our free calculator. Avoid jargon."
          value={form.instructions}
          onChange={(event) => set({ instructions: event.target.value })}
        />
      </Field>

      <button
        className="btn btn-primary"
        type="submit"
        disabled={busy || form.topic.trim().length < 3}
      >
        {busy ? <Spinner /> : <VideoIcon name="sparkle" className="h-4 w-4" />}
        {busy ? waiting : submitLabel}
      </button>
    </form>
  )
}
