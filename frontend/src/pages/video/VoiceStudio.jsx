import { useCallback, useMemo, useRef, useState } from 'react'
import { api } from '../../lib/api.js'
import { useToast } from '../../context/ToastContext.jsx'
import { formatDuration, relativeTime } from '../../lib/video/format.js'
import { safeFilename, saveBlob } from '../../lib/video/download.js'
import VideoIcon from '../../components/video/VideoIcon.jsx'
import VideoPageHeader from '../../components/video/VideoPageHeader.jsx'
import AudioPreview from '../../components/video/voice/AudioPreview.jsx'
import AddToProjectModal from '../../components/video/voice/AddToProjectModal.jsx'
import Spinner from '../../components/Spinner.jsx'
import useVoiceStudio from '../../hooks/useVoiceStudio.js'

// ---------------------------------------------------------------------------
// Voice Studio.
//
// Independent by construction: nothing on this page needs a project, and the
// only place a project appears is the "Add to Project" dialog, which is an
// explicit action on a take that already exists.
//
// Two columns that scroll separately (`.split-*`, as the Generator and Create
// Post already do): the script on the left, the controls and the player on the
// right. Scrolling a long script must not push the Generate button off screen.
// ---------------------------------------------------------------------------

// A paragraph break is what separates one regenerable block from the next —
// the same rule the server applies in `voice.split_segments`. Duplicated here
// only to *count* them for the UI; the authoritative split is the server's, and
// the regenerate action sends the text rather than an index into a local guess.
function countSegments(text) {
  return text.split(/\n\s*\n+/).filter((block) => block.trim()).length
}

function Slider({ id, label, value, min, max, step, onChange, disabled, format }) {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between">
        <label className="label mb-0" htmlFor={id}>
          {label}
        </label>
        <span className="text-xs tabular-nums text-muted">{format(value)}</span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(Number(event.target.value))}
        className="w-full accent-[var(--accent)] disabled:opacity-50"
      />
    </div>
  )
}

export default function VoiceStudio() {
  const toast = useToast()
  const studio = useVoiceStudio()
  const {
    catalogue, catalogueError, loadingCatalogue, reloadCatalogue,
    voicesForLanguage, selectedVoice,
    text, setText, characters, maxCharacters, overLimit,
    settings, update, setLanguage,
    takes, current, setCurrent, previewUrl,
    generating, previewing, error, clearError,
    preview, generate, remove, attach, restore,
  } = studio

  const fileRef = useRef(null)
  const textRef = useRef(null)
  const [importing, setImporting] = useState(false)
  const [downloading, setDownloading] = useState(null)
  const [attaching, setAttaching] = useState(null)
  const [selection, setSelection] = useState(null)

  const segmentCount = useMemo(() => countSegments(text), [text])
  // Prosody is disabled per-voice rather than globally: Groq's PlayAI and the
  // `/audio/speech` API have no pitch or volume parameter, and a slider that
  // silently does nothing is worse than one that is visibly unavailable.
  const prosody = selectedVoice?.supports_prosody !== false

  // The audio the player is showing: a stored take if there is one, otherwise
  // the unsaved preview. Never both — generating clears the preview.
  const playerSrc = current?.url || previewUrl
  const playerLabel = current
    ? current.title
    : previewUrl
      ? 'Preview (not saved)'
      : null

  // ---- import ------------------------------------------------------------
  async function importScript(event) {
    const file = event.target.files?.[0]
    event.target.value = '' // so choosing the same file twice fires again
    if (!file) return

    setImporting(true)
    try {
      if (/\.(txt|md|markdown)$/i.test(file.name)) {
        // Plain text needs no server round trip.
        setText(await file.text())
      } else {
        // PDF, DOCX and anything else go through the extractor the "Create
        // From" flow already uses — one implementation, not two.
        const data = await api.extractFile(file)
        const body = [data?.title, data?.content || data?.text].filter(Boolean).join('\n\n')
        if (!body.trim()) throw new Error('No readable text in that file.')
        setText(body)
      }
      toast.success(`Imported ${file.name}.`)
    } catch (err) {
      toast.error(err?.message || 'Could not read that file.')
    } finally {
      setImporting(false)
    }
  }

  // ---- regeneration ------------------------------------------------------
  const rememberSelection = useCallback(() => {
    const node = textRef.current
    if (!node) return
    const { selectionStart, selectionEnd } = node
    setSelection(
      selectionEnd > selectionStart
        ? { start: selectionStart, end: selectionEnd, text: node.value.slice(selectionStart, selectionEnd) }
        : null,
    )
  }, [])

  async function generateSelection() {
    if (!selection?.text.trim()) return
    await generate({
      body: selection.text,
      title: `Selection — ${selection.text.trim().slice(0, 40)}`,
    })
  }

  // ---- download ----------------------------------------------------------
  async function download(take, format) {
    setDownloading(`${take.id}:${format}`)
    try {
      const blob = await api.downloadVoiceTake(take.id, format)
      saveBlob(blob, `${safeFilename(take.title)}.${format}`)
    } catch (err) {
      toast.error(err?.message || `Could not download the ${format.toUpperCase()}.`)
    } finally {
      setDownloading(null)
    }
  }

  // ---- catalogue failure -------------------------------------------------
  if (!loadingCatalogue && catalogueError) {
    return (
      <div className="mx-auto w-full max-w-3xl">
        <VideoPageHeader
          title="Voice Studio"
          subtitle="Convert your text into natural-sounding voice."
          back="/video"
          backLabel="Back to Video Studio"
        />
        <div className="card flex flex-col items-center gap-3 px-6 py-12 text-center">
          <span className="grid h-12 w-12 place-items-center rounded-full bg-inset text-muted">
            <VideoIcon name="alert" className="h-6 w-6" />
          </span>
          <p className="max-w-md text-sm text-muted">{catalogueError}</p>
          <button className="btn btn-secondary btn-sm" onClick={reloadCatalogue}>
            Try again
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="split-shell mx-auto w-full max-w-6xl">
      <VideoPageHeader
        title="Voice Studio"
        subtitle="Convert your text into natural-sounding voice."
        back="/video"
        backLabel="Back to Video Studio"
        actions={
          <span className="badge border border-line bg-inset text-muted">
            Works without a project
          </span>
        }
      />

      <div className="split-grid lg:grid-cols-[minmax(0,1fr)_380px]">
        {/* ---- Text ------------------------------------------------- */}
        <section className="split-pane">
          <div className="card flex flex-col p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-semibold text-body">Text</h2>
              <div className="flex items-center gap-2">
                <input
                  ref={fileRef}
                  type="file"
                  accept=".txt,.md,.markdown,.pdf,.doc,.docx"
                  onChange={importScript}
                  className="hidden"
                />
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => fileRef.current?.click()}
                  disabled={importing}
                >
                  {importing ? <Spinner /> : <VideoIcon name="document" className="h-4 w-4" />}
                  {importing ? 'Reading…' : 'Import script'}
                </button>
                {text && (
                  <button className="btn btn-ghost btn-sm" onClick={() => setText('')}>
                    Clear
                  </button>
                )}
              </div>
            </div>

            <textarea
              ref={textRef}
              className="input min-h-[300px] resize-y font-normal leading-relaxed"
              placeholder="Write or paste your script here.&#10;&#10;Leave a blank line between sections — each one can be regenerated on its own.&#10;&#10;Type [pause] where you want a beat."
              value={text}
              onChange={(event) => setText(event.target.value)}
              onSelect={rememberSelection}
              onBlur={rememberSelection}
            />

            <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs">
              <span className={overLimit ? 'font-semibold text-rose-600' : 'text-muted'}>
                <span className="tabular-nums">{characters.toLocaleString()}</span> /{' '}
                <span className="tabular-nums">{maxCharacters.toLocaleString()}</span>{' '}
                characters
                {overLimit && ' — too long to generate in one go'}
              </span>
              {segmentCount > 1 && (
                <span className="text-muted">
                  {segmentCount} sections — each can be regenerated separately
                </span>
              )}
            </div>

            {error && (
              <div className="mt-3 flex items-start justify-between gap-3 rounded-[10px] border border-rose-300 bg-rose-50 px-3 py-2">
                <p className="text-sm text-rose-700">{error}</p>
                <button
                  className="shrink-0 text-rose-500 hover:text-rose-700"
                  onClick={clearError}
                  aria-label="Dismiss"
                >
                  ✕
                </button>
              </div>
            )}

            <div className="mt-4 flex flex-wrap items-center gap-2">
              <button
                className="btn btn-primary"
                onClick={() => generate()}
                disabled={generating || !text.trim() || overLimit || !settings.voiceId}
              >
                {generating ? <Spinner /> : <VideoIcon name="mic" className="h-4 w-4" />}
                {generating ? 'Generating…' : 'Generate Voice'}
              </button>

              <button
                className="btn btn-secondary"
                onClick={preview}
                disabled={previewing || generating || !text.trim() || !settings.voiceId}
              >
                {previewing ? <Spinner /> : <VideoIcon name="play" className="h-4 w-4" />}
                {previewing ? 'Previewing…' : 'Preview voice'}
              </button>

              {/* Only offered when there IS a selection — a button that needs a
                  precondition the user cannot see is a button that looks broken. */}
              {selection?.text.trim() && (
                <button
                  className="btn btn-ghost"
                  onClick={generateSelection}
                  disabled={generating}
                  title={`Generate just the ${selection.text.trim().length} selected characters`}
                >
                  <VideoIcon name="sparkle" className="h-4 w-4" />
                  Generate selection
                </button>
              )}
            </div>
          </div>

          {/* ---- Takes ---------------------------------------------- */}
          {takes.length > 0 && (
            <div className="card mt-4 p-4">
              <h2 className="mb-3 font-semibold text-body">Your voice-overs</h2>
              <ul className="flex flex-col gap-2">
                {takes.map((take) => (
                  <li
                    key={take.id}
                    className={`panel flex flex-wrap items-center gap-2 px-3 py-2 ${
                      current?.id === take.id ? 'border-accent-line' : ''
                    }`}
                  >
                    <button
                      className="min-w-0 flex-1 text-left"
                      onClick={() => setCurrent(take)}
                      title="Play this take"
                    >
                      <span className="block truncate text-sm font-medium text-body">
                        {take.title}
                      </span>
                      <span className="block text-xs tabular-nums text-muted">
                        {formatDuration(take.duration_seconds)} · {take.voice_id} ·{' '}
                        {relativeTime(take.created_at)}
                        {take.project_id ? ' · in a project' : ''}
                      </span>
                    </button>

                    <div className="flex shrink-0 items-center gap-1">
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => restore(take)}
                        title="Load this take's text and settings back into the panel"
                      >
                        Reuse
                      </button>
                      <button
                        className="btn btn-ghost btn-sm text-rose-600"
                        onClick={() => remove(take)}
                        aria-label={`Delete ${take.title}`}
                      >
                        <VideoIcon name="trash" className="h-4 w-4" />
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        {/* ---- Settings + preview ----------------------------------- */}
        <section className="split-pane flex flex-col gap-4">
          <div className="card p-4">
            <h2 className="mb-3 font-semibold text-body">Voice settings</h2>

            {loadingCatalogue ? (
              <div className="flex flex-col gap-3">
                {Array.from({ length: 6 }).map((_, index) => (
                  <div key={index} className="skeleton h-10" />
                ))}
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                <div>
                  <label className="label" htmlFor="language">
                    Language
                  </label>
                  <select
                    id="language"
                    className="select"
                    value={settings.language}
                    onChange={(event) => setLanguage(event.target.value)}
                  >
                    {catalogue.languages.map((language) => (
                      <option key={language.code} value={language.code}>
                        {language.label} ({language.voices})
                      </option>
                    ))}
                  </select>
                  {catalogue.languages.find((l) => l.code === settings.language)?.note && (
                    <p className="mt-1 text-xs text-muted">
                      {catalogue.languages.find((l) => l.code === settings.language).note}
                    </p>
                  )}
                </div>

                <div>
                  <label className="label" htmlFor="voice">
                    Voice
                  </label>
                  <select
                    id="voice"
                    className="select"
                    value={settings.voiceId}
                    onChange={(event) => update({ voiceId: event.target.value })}
                  >
                    {voicesForLanguage.length === 0 && (
                      <option value="">No voices for this language</option>
                    )}
                    {voicesForLanguage.map((voice) => (
                      <option key={voice.id} value={voice.id}>
                        {voice.label} · {voice.gender}
                      </option>
                    ))}
                  </select>
                  {selectedVoice && (
                    <p className="mt-1 text-xs text-muted">
                      Provided by {selectedVoice.provider}
                      {selectedVoice.styles?.length > 0 &&
                        ` · ${selectedVoice.styles.slice(0, 3).join(', ')}`}
                    </p>
                  )}
                </div>

                <div>
                  <label className="label" htmlFor="style">
                    Style
                  </label>
                  <select
                    id="style"
                    className="select"
                    value={settings.style}
                    onChange={(event) => update({ style: event.target.value })}
                  >
                    {catalogue.styles.map((style) => (
                      <option key={style.key} value={style.key}>
                        {style.label}
                      </option>
                    ))}
                  </select>
                  <p className="mt-1 text-xs text-muted">
                    {catalogue.styles.find((s) => s.key === settings.style)?.description}
                  </p>
                </div>

                <Slider
                  id="rate"
                  label="Speed"
                  value={settings.rate}
                  min={0.5}
                  max={2}
                  step={0.05}
                  onChange={(rate) => update({ rate })}
                  format={(v) => `${v.toFixed(2)}×`}
                />
                <Slider
                  id="pitch"
                  label="Pitch"
                  value={settings.pitch}
                  min={0.5}
                  max={1.5}
                  step={0.05}
                  disabled={!prosody}
                  onChange={(pitch) => update({ pitch })}
                  format={(v) => `${v.toFixed(2)}×`}
                />
                <Slider
                  id="volume"
                  label="Volume"
                  value={settings.volume}
                  min={0}
                  max={1}
                  step={0.05}
                  disabled={!prosody}
                  onChange={(volume) => update({ volume })}
                  format={(v) => `${Math.round(v * 100)}%`}
                />

                {!prosody && (
                  <p className="text-xs text-muted">
                    {selectedVoice?.provider} has no pitch or volume control, so
                    those two are unavailable for this voice.
                  </p>
                )}
              </div>
            )}
          </div>

          <div className="card p-4">
            <h2 className="mb-3 font-semibold text-body">Preview</h2>
            <AudioPreview
              src={playerSrc}
              duration={current?.duration_seconds || 0}
              label={playerLabel}
            />

            {current ? (
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => download(current, 'mp3')}
                  disabled={downloading !== null}
                >
                  {downloading === `${current.id}:mp3` ? <Spinner /> : null}
                  Download MP3
                </button>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => download(current, 'wav')}
                  disabled={downloading !== null}
                >
                  {downloading === `${current.id}:wav` ? <Spinner /> : null}
                  Download WAV
                </button>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => setAttaching(current)}
                >
                  <VideoIcon name="plus" className="h-4 w-4" />
                  Add to Project
                </button>
              </div>
            ) : (
              <p className="mt-3 text-xs text-muted">
                {previewUrl
                  ? 'This is an unsaved preview. Generate to keep it, download it, or add it to a project.'
                  : 'Generate a voice-over to download it or add it to a project.'}
              </p>
            )}
          </div>
        </section>
      </div>

      <AddToProjectModal
        open={attaching !== null}
        take={attaching}
        onClose={() => setAttaching(null)}
        onAttach={attach}
      />
    </div>
  )
}
