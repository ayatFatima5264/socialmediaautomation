import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../lib/api.js'
import { useToast } from '../../context/ToastContext.jsx'
import { formatDuration } from '../../lib/video/format.js'
import { safeFilename, saveBlob } from '../../lib/video/download.js'
import VideoIcon from '../../components/video/VideoIcon.jsx'
import VideoPageHeader from '../../components/video/VideoPageHeader.jsx'
import CueEditor from '../../components/video/subtitles/CueEditor.jsx'
import StylePanel, { cueTextStyle } from '../../components/video/subtitles/StylePanel.jsx'
import AddToProjectModal from '../../components/video/voice/AddToProjectModal.jsx'
import Spinner from '../../components/Spinner.jsx'
import useSubtitleStudio from '../../hooks/useSubtitleStudio.js'

// ---------------------------------------------------------------------------
// Subtitle Studio.
//
// Independent by construction: no project is needed to reach any of this, and
// the only place one appears is "Add to Project", which acts on a track that
// already exists.
//
// The four steps of the mockup are steps, not tabs: Edit and Export are
// unreachable until there are cues to edit, and saying so with a disabled step
// is clearer than letting someone open an empty editor and wonder what they
// did wrong. Once a track exists all four stay open, because coming back to
// re-transcribe with a different language is a normal thing to do.
// ---------------------------------------------------------------------------

const STEPS = [
  { key: 'upload', label: 'Upload' },
  { key: 'transcribe', label: 'Transcribe' },
  { key: 'edit', label: 'Edit' },
  { key: 'export', label: 'Export' },
]

// Whisper takes a bare ISO-639-1 code. Offering the whole ISO list would be a
// dropdown nobody can use; these are the languages this product is aimed at,
// plus automatic detection, which is the right default.
const LANGUAGES = [
  { code: '', label: 'Detect automatically' },
  { code: 'en', label: 'English' },
  { code: 'ur', label: 'Urdu' },
  { code: 'hi', label: 'Hindi' },
  { code: 'ar', label: 'Arabic' },
  { code: 'es', label: 'Spanish' },
  { code: 'fr', label: 'French' },
  { code: 'de', label: 'German' },
  { code: 'pt', label: 'Portuguese' },
  { code: 'zh', label: 'Chinese' },
]

function StepNav({ step, setStep, hasCues }) {
  return (
    <div className="mb-5 flex flex-wrap gap-1 rounded-[10px] border border-line bg-inset p-1">
      {STEPS.map((item, index) => {
        const locked = (item.key === 'edit' || item.key === 'export') && !hasCues
        const active = step === item.key
        return (
          <button
            key={item.key}
            type="button"
            disabled={locked}
            onClick={() => setStep(item.key)}
            title={locked ? 'Add or transcribe some subtitles first' : undefined}
            className={`flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition-colors ${
              active
                ? 'bg-surface text-accent shadow-[var(--shadow)]'
                : locked
                  ? 'cursor-not-allowed text-muted opacity-50'
                  : 'text-muted hover:text-body'
            }`}
          >
            <span className="grid h-5 w-5 place-items-center rounded-full border border-current text-[11px] tabular-nums">
              {index + 1}
            </span>
            {item.label}
          </button>
        )
      })}
    </div>
  )
}

/** The caption drawn over the media while it plays — the same CSS the style
 *  panel previews, so what is seen here is what the style actually is. */
function PlayerOverlay({ cues, style, currentTime }) {
  const cue = cues.find((c) => currentTime >= c.start && currentTime < c.end)
  if (!cue || !style) return null

  const place =
    style.position === 'top'
      ? 'items-start pt-3'
      : style.position === 'center'
        ? 'items-center'
        : 'items-end pb-3'
  const align =
    style.align === 'left'
      ? 'justify-start'
      : style.align === 'right'
        ? 'justify-end'
        : 'justify-center'

  return (
    <div className={`pointer-events-none absolute inset-0 flex px-3 ${place} ${align}`}>
      <span
        style={{
          ...cueTextStyle(style),
          fontSize: `${Math.max(10, style.font_size * 0.3)}px`,
          whiteSpace: 'pre-line',
        }}
      >
        {cue.text}
      </span>
    </div>
  )
}

export default function SubtitleStudio() {
  const toast = useToast()
  const studio = useSubtitleStudio()
  const {
    cues, duration, source, style, setStyle, styleOptions,
    busy, error, clearError, canUndo, undo,
    transcribe, fromScript, importFile,
    update, insert, remove, split, merge, shift, normalize, searchReplace,
  } = studio

  const [step, setStep] = useState('upload')
  const [file, setFile] = useState(null)
  const [language, setLanguage] = useState('')
  const [translate, setTranslate] = useState(false)
  const [script, setScript] = useState('')
  const [scriptDuration, setScriptDuration] = useState('')
  const [find, setFind] = useState('')
  const [replace, setReplace] = useState('')
  const [wholeWord, setWholeWord] = useState(false)
  const [caseSensitive, setCaseSensitive] = useState(false)
  const [shiftBy, setShiftBy] = useState('0.5')
  const [downloading, setDownloading] = useState(null)
  const [exported, setExported] = useState([])
  const [attaching, setAttaching] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)

  const mediaRef = useRef(null)
  const fileRef = useRef(null)
  const importRef = useRef(null)

  const hasCues = cues.length > 0
  const isVideo = file?.type?.startsWith('video/') || false

  // Once there are cues, the Edit step is where the work happens.
  useEffect(() => {
    if (hasCues && (step === 'upload' || step === 'transcribe')) setStep('edit')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasCues])

  const mediaUrl = useMemo(() => {
    if (source?.mediaUrl) return source.mediaUrl
    return null
  }, [source])

  async function runTranscribe() {
    if (!file) return
    await transcribe(file, {
      language: language || undefined,
      translateToEnglish: translate,
      styleKey: style?.key,
    })
  }

  async function runExport(format) {
    setDownloading(format)
    try {
      const stored = await api.exportSubtitles({
        cues,
        format,
        title: source?.filename?.replace(/\.[^.]+$/, '') || 'subtitles',
        language: source?.language || null,
      })
      const blob = await api.downloadSubtitleFile(stored.id, format)
      saveBlob(blob, `${safeFilename(stored.title.replace(/\.[^.]+$/, ''), 'subtitles')}.${format}`)
      setExported((current) => [stored, ...current.filter((f) => f.id !== stored.id)])
      toast.success(`Exported ${format.toUpperCase()} — saved to your library too.`)
    } catch (err) {
      toast.error(err?.message || `Could not export ${format.toUpperCase()}.`)
    } finally {
      setDownloading(null)
    }
  }

  async function attach(_take, projectId) {
    const track = await api.attachSubtitles({
      cues,
      project_id: projectId,
      language: source?.language?.slice(0, 2) || 'en',
      label: source?.filename || null,
      style: style || {},
      source: source?.kind === 'script' ? 'script' : source?.kind === 'import' ? 'upload' : 'transcription',
    })
    return track
  }

  return (
    <div className="mx-auto w-full max-w-6xl">
      <VideoPageHeader
        title="Subtitle Studio"
        subtitle="Generate, edit and export subtitles from video, audio or a script."
        back="/video"
        backLabel="Back to Video Studio"
        actions={
          <span className="badge border border-line bg-inset text-muted">
            Works without a project
          </span>
        }
      />

      <StepNav step={step} setStep={setStep} hasCues={hasCues} />

      {error && (
        <div className="mb-4 flex items-start justify-between gap-3 rounded-[10px] border border-rose-300 bg-rose-50 px-3 py-2">
          <p className="text-sm text-rose-700">{error}</p>
          <button className="shrink-0 text-rose-500 hover:text-rose-700" onClick={clearError} aria-label="Dismiss">
            ✕
          </button>
        </div>
      )}

      {/* ================= UPLOAD ================= */}
      {step === 'upload' && (
        <div className="grid gap-4 lg:grid-cols-2">
          <section className="card p-5">
            <h2 className="font-semibold text-body">Video or audio</h2>
            <p className="mt-1 text-sm text-muted">
              Upload a recording and it will be transcribed into timed subtitles.
            </p>

            <input
              ref={fileRef}
              type="file"
              accept="video/*,audio/*"
              className="hidden"
              onChange={(event) => {
                setFile(event.target.files?.[0] || null)
                event.target.value = ''
              }}
            />

            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="panel mt-4 flex w-full flex-col items-center gap-2 border-dashed px-4 py-10 text-center transition-colors hover:border-accent-line"
            >
              <VideoIcon name="film" className="h-7 w-7 text-muted" />
              <span className="text-sm font-medium text-body">
                {file ? file.name : 'Choose a video or audio file'}
              </span>
              <span className="text-xs text-muted">
                {file
                  ? `${(file.size / (1024 * 1024)).toFixed(1)} MB`
                  : 'MP4, MOV, WebM, MP3, WAV, M4A'}
              </span>
            </button>

            {file && (
              <button className="btn btn-primary mt-4 w-full" onClick={() => setStep('transcribe')}>
                Continue
              </button>
            )}
          </section>

          <div className="flex flex-col gap-4">
            <section className="card p-5">
              <h2 className="font-semibold text-body">From a script</h2>
              <p className="mt-1 text-sm text-muted">
                No recording? Paste the words and they will be timed for you.
              </p>
              <textarea
                className="input mt-3 min-h-[140px] resize-y text-sm"
                placeholder="Paste your script. Each sentence becomes a subtitle."
                value={script}
                onChange={(event) => setScript(event.target.value)}
              />
              <div className="mt-3 flex flex-wrap items-end gap-3">
                <div className="min-w-0 flex-1">
                  <label className="label" htmlFor="script-duration">
                    Fit to length <span className="font-normal text-muted">(optional)</span>
                  </label>
                  <input
                    id="script-duration"
                    className="input"
                    inputMode="decimal"
                    placeholder="e.g. 30 (seconds)"
                    value={scriptDuration}
                    onChange={(event) => setScriptDuration(event.target.value)}
                  />
                </div>
                <button
                  className="btn btn-primary"
                  disabled={!script.trim() || busy === 'script'}
                  onClick={() => fromScript(script, Number(scriptDuration) || null)}
                >
                  {busy === 'script' && <Spinner />}
                  Time script
                </button>
              </div>
              <p className="mt-2 text-xs text-muted">
                Without a length, timing is estimated from reading speed — an
                estimate, not a measurement.
              </p>
            </section>

            <section className="card p-5">
              <h2 className="font-semibold text-body">Existing subtitle file</h2>
              <p className="mt-1 text-sm text-muted">
                Open an SRT or WebVTT file to edit, restyle or convert it.
              </p>
              <input
                ref={importRef}
                type="file"
                accept=".srt,.vtt,text/vtt,application/x-subrip"
                className="hidden"
                onChange={(event) => {
                  const chosen = event.target.files?.[0]
                  event.target.value = ''
                  if (chosen) importFile(chosen)
                }}
              />
              <button
                className="btn btn-secondary mt-3"
                onClick={() => importRef.current?.click()}
                disabled={busy === 'import'}
              >
                {busy === 'import' ? <Spinner /> : <VideoIcon name="document" className="h-4 w-4" />}
                Open SRT or VTT
              </button>
            </section>
          </div>
        </div>
      )}

      {/* ================= TRANSCRIBE ================= */}
      {step === 'transcribe' && (
        <section className="card mx-auto max-w-2xl p-5">
          <h2 className="font-semibold text-body">Transcribe</h2>
          <p className="mt-1 text-sm text-muted">
            {file ? file.name : 'Go back and choose a file first.'}
          </p>

          <div className="mt-4 flex flex-col gap-3">
            <div>
              <label className="label" htmlFor="language">
                Spoken language
              </label>
              <select
                id="language"
                className="select"
                value={language}
                onChange={(event) => setLanguage(event.target.value)}
              >
                {LANGUAGES.map((item) => (
                  <option key={item.code} value={item.code}>
                    {item.label}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-muted">
                Detection is reliable for clear speech; naming the language helps
                with background noise or heavy accents.
              </p>
            </div>

            <label className="flex items-start gap-2 text-sm text-body">
              <input
                type="checkbox"
                checked={translate}
                onChange={(event) => setTranslate(event.target.checked)}
                className="mt-0.5 accent-[var(--accent)]"
              />
              <span>
                Translate to English
                <span className="block text-xs text-muted">
                  Transcribes and translates in one pass. Per-word timings are
                  unavailable when translating, so word highlighting will not work.
                </span>
              </span>
            </label>

            <div className="flex flex-wrap gap-2">
              <button
                className="btn btn-primary"
                onClick={runTranscribe}
                disabled={!file || busy === 'transcribe'}
              >
                {busy === 'transcribe' ? <Spinner /> : <VideoIcon name="captions" className="h-4 w-4" />}
                {busy === 'transcribe' ? 'Transcribing…' : 'Transcribe now'}
              </button>
              <button className="btn btn-ghost" onClick={() => setStep('upload')}>
                Back
              </button>
            </div>

            {busy === 'transcribe' && (
              <p className="text-xs text-muted">
                Audio is extracted and sent for transcription. A few minutes of
                media usually takes a few seconds.
              </p>
            )}
          </div>
        </section>
      )}

      {/* ================= EDIT ================= */}
      {step === 'edit' && hasCues && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
          <section className="flex flex-col gap-4">
            {mediaUrl && (
              <div className="card overflow-hidden">
                <div className="relative bg-black">
                  {isVideo || source?.kind === 'transcription' ? (
                    <video
                      ref={mediaRef}
                      src={mediaUrl}
                      controls
                      className="max-h-[280px] w-full bg-black"
                      onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
                    />
                  ) : (
                    <audio
                      ref={mediaRef}
                      src={mediaUrl}
                      controls
                      className="w-full"
                      onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
                    />
                  )}
                  <PlayerOverlay cues={cues} style={style} currentTime={currentTime} />
                </div>
              </div>
            )}

            <div className="card p-4">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <h2 className="font-semibold text-body">Subtitles</h2>
                <span className="text-xs text-muted">
                  {formatDuration(duration)} total
                </span>
                {source?.estimated && (
                  <span className="badge border border-amber-300 bg-amber-50 text-amber-700">
                    Estimated timing
                  </span>
                )}
                {source?.provider && (
                  <span className="badge border border-line bg-inset text-muted">
                    {source.provider} · {source.language}
                  </span>
                )}
                <div className="ml-auto flex items-center gap-2">
                  <button className="btn btn-ghost btn-sm" onClick={undo} disabled={!canUndo}>
                    Undo
                  </button>
                  <button className="btn btn-ghost btn-sm" onClick={normalize} disabled={Boolean(busy)}>
                    Tidy timings
                  </button>
                </div>
              </div>

              {/* ---- Search & replace ---- */}
              <div className="panel mb-3 flex flex-wrap items-end gap-2 p-3">
                <div className="min-w-[8rem] flex-1">
                  <label className="label" htmlFor="find">Find</label>
                  <input id="find" className="input" value={find} onChange={(e) => setFind(e.target.value)} />
                </div>
                <div className="min-w-[8rem] flex-1">
                  <label className="label" htmlFor="replace">Replace with</label>
                  <input id="replace" className="input" value={replace} onChange={(e) => setReplace(e.target.value)} />
                </div>
                <button
                  className="btn btn-secondary btn-sm"
                  disabled={!find || Boolean(busy)}
                  onClick={() => searchReplace({ find, replace, whole_word: wholeWord, case_sensitive: caseSensitive })}
                >
                  Replace all
                </button>
                <div className="flex w-full flex-wrap gap-3 text-xs text-muted">
                  <label className="flex items-center gap-1.5">
                    <input type="checkbox" checked={caseSensitive} onChange={(e) => setCaseSensitive(e.target.checked)} className="accent-[var(--accent)]" />
                    Match case
                  </label>
                  <label className="flex items-center gap-1.5">
                    <input type="checkbox" checked={wholeWord} onChange={(e) => setWholeWord(e.target.checked)} className="accent-[var(--accent)]" />
                    Whole word
                  </label>
                  <label className="ml-auto flex items-center gap-1.5">
                    Shift all by
                    <input
                      className="input w-20 px-2 py-1 text-center text-xs tabular-nums"
                      value={shiftBy}
                      onChange={(e) => setShiftBy(e.target.value)}
                      aria-label="Shift all subtitles by seconds"
                    />
                    s
                    <button className="btn btn-ghost btn-sm px-2" onClick={() => shift(Number(shiftBy) || 0)} disabled={Boolean(busy)}>
                      −/+
                    </button>
                  </label>
                </div>
              </div>

              <CueEditor
                cues={cues}
                busy={busy}
                onUpdate={update}
                onInsert={insert}
                onDelete={remove}
                onSplit={split}
                onMerge={merge}
                currentTime={currentTime}
                onSeek={(seconds) => {
                  if (mediaRef.current) {
                    mediaRef.current.currentTime = seconds
                    setCurrentTime(seconds)
                  }
                }}
              />
            </div>
          </section>

          <section className="card h-fit p-4">
            <h2 className="mb-3 font-semibold text-body">Style</h2>
            <StylePanel
              style={style}
              options={styleOptions}
              onChange={setStyle}
              sampleText={cues[0]?.text}
            />
          </section>
        </div>
      )}

      {/* ================= EXPORT ================= */}
      {step === 'export' && hasCues && (
        <div className="grid gap-4 lg:grid-cols-2">
          <section className="card p-5">
            <h2 className="font-semibold text-body">Export</h2>
            <p className="mt-1 text-sm text-muted">
              {cues.length} subtitles · {formatDuration(duration)}. Every export is
              saved to your library as well as downloaded.
            </p>

            <div className="mt-4 flex flex-wrap gap-2">
              {[
                { key: 'srt', label: 'Download SRT' },
                { key: 'vtt', label: 'Download VTT' },
                { key: 'txt', label: 'Download TXT' },
              ].map((format) => (
                <button
                  key={format.key}
                  className="btn btn-secondary"
                  onClick={() => runExport(format.key)}
                  disabled={downloading !== null}
                >
                  {downloading === format.key && <Spinner />}
                  {format.label}
                </button>
              ))}
              <button className="btn btn-primary" onClick={() => setAttaching(true)}>
                <VideoIcon name="plus" className="h-4 w-4" />
                Add to Project
              </button>
            </div>

            <p className="mt-3 text-xs text-muted">
              SRT and VTT carry the timings. TXT is the words only — useful for a
              transcript, not for captions.
            </p>
          </section>

          <section className="card p-5">
            <h2 className="font-semibold text-body">Exported files</h2>
            {exported.length === 0 ? (
              <p className="mt-2 text-sm text-muted">
                Nothing exported yet in this session.
              </p>
            ) : (
              <ul className="mt-3 flex flex-col gap-2">
                {exported.map((item) => (
                  <li key={item.id} className="panel flex items-center gap-2 px-3 py-2">
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-body">{item.title}</span>
                      <span className="block text-xs text-muted">
                        {item.format.toUpperCase()} · {item.cue_count} cues ·{' '}
                        {(item.size_bytes / 1024).toFixed(1)} KB
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}

      <AddToProjectModal
        open={attaching}
        take={null}
        onClose={() => setAttaching(false)}
        onAttach={attach}
      />
    </div>
  )
}
