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

// The lengths offered as buttons. The server accepts anything in its own
// range; these are the ones worth one tap.
const DURATIONS = [15, 30, 45, 60, 90, 120]

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

        <Field label="Length">
          <select
            className="select"
            value={form.duration_seconds}
            onChange={(event) => set({ duration_seconds: Number(event.target.value) })}
          >
            {DURATIONS.map((value) => (
              <option key={value} value={value}>
                {value < 60 ? `${value} seconds` : `${value / 60} minute${value > 60 ? 's' : ''}`}
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
        {busy ? busyLabel : submitLabel}
      </button>
    </form>
  )
}
