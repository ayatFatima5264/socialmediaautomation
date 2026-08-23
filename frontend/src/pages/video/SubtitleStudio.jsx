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
// **Any one input is enough.** The first step offers four of them — a
// recording, a document, a pasted script, an existing subtitle file — and each
// works on its own. None of them is a prerequisite for another, and the studio
// never asks for a second file before it will use the first.
//
// The one place two inputs are better than one is a recording *plus* the script
// it was read from, because they answer different questions: the audio knows
// when each word was said and which words were actually said; the script knows
// how those words are spelled. That is offered inside the recording card, as an
// optional extra, phrased as what it buys rather than as another required field.
//
// The four steps are steps, not tabs: Edit and Export are unreachable until
// there are cues to edit, and saying so with a disabled step is clearer than
// letting someone open an empty editor and wonder what they did wrong.
// ---------------------------------------------------------------------------

const STEPS = [
  { key: 'upload', label: 'Add' },
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

const DOCUMENT_ACCEPT = '.txt,.md,.markdown,.rtf,.docx,.pdf'
const DOCUMENT_HINT = 'TXT, MD, RTF, DOCX or PDF'

function megabytes(bytes) {
  return `${(bytes / (1024 * 1024)).toFixed(bytes < 1024 * 1024 ? 2 : 1)} MB`
}

function StepNav({ step, setStep, hasCues, hasMedia }) {
  return (
    <div className="mb-5 flex flex-wrap gap-1 rounded-[10px] border border-line bg-inset p-1">
      {STEPS.map((item, index) => {
        const locked =
          ((item.key === 'edit' || item.key === 'export') && !hasCues) ||
          (item.key === 'transcribe' && !hasMedia)
        const active = step === item.key
        return (
          <button
            key={item.key}
            type="button"
            disabled={locked}
            onClick={() => setStep(item.key)}
            title={
              locked
                ? item.key === 'transcribe'
                  ? 'Choose a video or audio file first'
                  : 'Add or transcribe some subtitles first'
                : undefined
            }
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

/** One of the four inputs. The letter is not decoration — it is what makes it
 *  obvious at a glance that these are alternatives rather than a sequence. */
function InputCard({ letter, title, description, ready, children }) {
  return (
    <section
      className={`card flex flex-col p-5 transition-colors ${
        ready ? 'border-accent-line' : ''
      }`}
    >
      <div className="flex items-start gap-3">
        <span
          className={`grid h-7 w-7 shrink-0 place-items-center rounded-lg text-xs font-bold ${
            ready ? 'bg-emerald-100 text-emerald-700' : 'bg-inset text-muted'
          }`}
        >
          {ready ? <VideoIcon name="check" className="h-4 w-4" /> : letter}
        </span>
        <div className="min-w-0">
          <h2 className="font-semibold text-body">{title}</h2>
          <p className="mt-0.5 text-sm text-muted">{description}</p>
        </div>
      </div>
      <div className="mt-4 flex flex-1 flex-col">{children}</div>
    </section>
  )
}

/** A chosen file, with the way to change your mind about it. */
function ChosenFile({ name, detail, onChange, onClear, changeLabel = 'Change' }) {
  return (
    <div className="panel flex items-center gap-3 px-3 py-2">
      <VideoIcon name="check" className="h-4 w-4 shrink-0 text-emerald-600" />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-body">{name}</span>
        {detail && <span className="block text-xs text-muted">{detail}</span>}
      </span>
      {onChange && (
        <button type="button" className="btn btn-ghost btn-sm shrink-0" onClick={onChange}>
          {changeLabel}
        </button>
      )}
      <button
        type="button"
        className="shrink-0 rounded p-1 text-muted hover:text-rose-600"
        onClick={onClear}
        aria-label={`Remove ${name}`}
      >
        <VideoIcon name="trash" className="h-4 w-4" />
      </button>
    </div>
  )
}

/** The optional script that goes *with* a recording.
 *
 *  Either half is enough — a file or pasted text — and neither is required.
 *  It lives inside the recording card rather than beside it because that is
 *  what it is: a refinement of one input, not a fifth input. */
function MatchingScript({ file, text, onFile, onText, busy }) {
  const inputRef = useRef(null)
  const [mode, setMode] = useState(null) // null | 'paste'

  return (
    <div className="mt-4 border-t border-line pt-4">
      <p className="text-sm font-medium text-body">
        Matching script <span className="font-normal text-muted">(optional)</span>
      </p>
      <p className="mt-0.5 text-xs text-muted">
        Have the original script? Add it to improve transcription accuracy. The
        timing still comes from the audio, and anything the speaker said
        differently is kept.
      </p>

      <input
        ref={inputRef}
        type="file"
        accept={DOCUMENT_ACCEPT}
        className="hidden"
        onChange={(event) => {
          const chosen = event.target.files?.[0] || null
          event.target.value = ''
          if (chosen) {
            onFile(chosen)
            onText('')
            setMode(null)
          }
        }}
      />

      {file ? (
        <div className="mt-3">
          <ChosenFile
            name={file.name}
            detail={megabytes(file.size)}
            onChange={() => inputRef.current?.click()}
            onClear={() => onFile(null)}
          />
        </div>
      ) : mode === 'paste' || text ? (
        <div className="mt-3">
          <textarea
            className="input min-h-[110px] resize-y text-sm"
            placeholder="Paste the script the speaker was reading from…"
            value={text}
            disabled={busy}
            onChange={(event) => onText(event.target.value)}
          />
          <button
            type="button"
            className="btn btn-ghost btn-sm mt-2"
            onClick={() => {
              onText('')
              setMode(null)
            }}
          >
            Remove script
          </button>
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => inputRef.current?.click()}
            disabled={busy}
          >
            <VideoIcon name="document" className="h-4 w-4" />
            Upload a document
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setMode('paste')}
            disabled={busy}
          >
            Paste it instead
          </button>
        </div>
      )}
    </div>
  )
}

/** What the pipeline is doing, stage by stage.
 *
 *  Every line here is a real boundary the client actually observes — a request
 *  that has returned, or bytes that have left the machine — so a tick means
 *  something finished rather than that a timer elapsed. */
function ProgressStages({ progress }) {
  if (!progress) return null
  const { stages, labels, current, done, percent } = progress

  return (
    <ul className="panel mt-4 flex flex-col gap-2 p-3">
      {stages.map((stage) => {
        const finished = done.includes(stage)
        const active = stage === current
        return (
          <li key={stage} className="flex items-center gap-2 text-sm">
            <span className="grid h-4 w-4 shrink-0 place-items-center">
              {finished ? (
                <VideoIcon name="check" className="h-4 w-4 text-emerald-600" />
              ) : active ? (
                <Spinner />
              ) : (
                <span className="h-1.5 w-1.5 rounded-full bg-[var(--line)]" />
              )}
            </span>
            <span className={active ? 'font-medium text-body' : finished ? 'text-body' : 'text-muted'}>
              {labels[stage] || stage}
              {active && stage === 'upload' && typeof percent === 'number' && (
                <span className="ml-1 tabular-nums text-muted">{percent}%</span>
              )}
            </span>
          </li>
        )
      })}
    </ul>
  )
}

/** What comparing the script with the audio actually did.
 *
 *  Non-blocking by design: a mismatch is information, not a failure, and the
 *  track is usable either way. */
function AlignmentNotice({ report }) {
  if (!report) return null

  const tone = report.warning
    ? 'border-amber-300 bg-amber-50 text-amber-800'
    : report.applied
      ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
      : 'border-line bg-inset text-muted'

  return (
    <div className={`mb-3 rounded-[10px] border px-3 py-2 text-sm ${tone}`}>
      <p className="font-medium">{report.warning || report.message}</p>
      {report.warning && report.message && (
        <p className="mt-0.5 text-xs opacity-90">{report.message}</p>
      )}
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
    busy, progress, error, clearError, canUndo, undo,
    transcribe, fromScript, fromDocument, alignWithScript, importFile,
    update, insert, remove, split, merge, shift, normalize, searchReplace,
  } = studio

  const [step, setStep] = useState('upload')

  // A: the recording, and the script that goes with it.
  const [file, setFile] = useState(null)
  const [referenceFile, setReferenceFile] = useState(null)
  const [referenceText, setReferenceText] = useState('')
  const [language, setLanguage] = useState('')
  const [translate, setTranslate] = useState(false)

  // B: a document on its own.
  const [documentFile, setDocumentFile] = useState(null)
  const [documentDuration, setDocumentDuration] = useState('')

  // C: a pasted script on its own.
  const [script, setScript] = useState('')
  const [scriptDuration, setScriptDuration] = useState('')

  // Editing.
  const [find, setFind] = useState('')
  const [replace, setReplace] = useState('')
  const [wholeWord, setWholeWord] = useState(false)
  const [caseSensitive, setCaseSensitive] = useState(false)
  const [shiftBy, setShiftBy] = useState('0.5')
  const [lateScript, setLateScript] = useState('')
  const [downloading, setDownloading] = useState(null)
  const [exported, setExported] = useState([])
  const [attaching, setAttaching] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)

  const mediaRef = useRef(null)
  const fileRef = useRef(null)
  const documentRef = useRef(null)
  const importRef = useRef(null)
  const lateScriptRef = useRef(null)

  const hasCues = cues.length > 0
  const isVideo = file?.type?.startsWith('video/') || false
  const hasReference = Boolean(referenceFile || referenceText.trim())

  // Once there are cues, the Edit step is where the work happens.
  useEffect(() => {
    if (hasCues && (step === 'upload' || step === 'transcribe')) setStep('edit')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasCues])

  const mediaUrl = useMemo(() => source?.mediaUrl || null, [source])

  async function runTranscribe() {
    if (!file) return
    await transcribe(file, {
      language: language || undefined,
      translateToEnglish: translate,
      styleKey: style?.key,
      referenceFile,
      referenceText,
    })
  }

  /** Correct the open track against a script chosen after the fact — which is
   *  how an imported SRT gets the benefit of the original document. */
  async function alignFromFile(chosen) {
    try {
      const document = await api.subtitlesFromDocument(chosen)
      await alignWithScript(document.text)
    } catch (err) {
      toast.error(err?.message || 'Could not read that document.')
    }
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
    return api.attachSubtitles({
      cues,
      project_id: projectId,
      language: source?.language?.slice(0, 2) || 'en',
      label: source?.filename || null,
      style: style || {},
      source:
        source?.kind === 'script' || source?.kind === 'document'
          ? 'script'
          : source?.kind === 'import'
            ? 'upload'
            : 'transcription',
    })
  }

  return (
    <div className="mx-auto w-full max-w-6xl">
      <VideoPageHeader
        title="Subtitle Studio"
        subtitle="Generate, edit and export subtitles from a recording, a document, a script — or a recording and its script together."
        back="/video"
        backLabel="Back to Video Studio"
        actions={
          <span className="badge border border-line bg-inset text-muted">
            Works without a project
          </span>
        }
      />

      <StepNav step={step} setStep={setStep} hasCues={hasCues} hasMedia={Boolean(file)} />

      {error && (
        <div className="mb-4 flex items-start justify-between gap-3 rounded-[10px] border border-rose-300 bg-rose-50 px-3 py-2">
          <p className="text-sm text-rose-700">{error}</p>
          <button className="shrink-0 text-rose-500 hover:text-rose-700" onClick={clearError} aria-label="Dismiss">
            ✕
          </button>
        </div>
      )}

      {/* ================= ADD ================= */}
      {step === 'upload' && (
        <>
          <div className="mb-4 flex flex-wrap items-baseline gap-x-2">
            <h2 className="text-lg font-semibold text-body">Create subtitles</h2>
            <p className="text-sm text-muted">
              Start with whichever you have. Any one of these is enough.
            </p>
          </div>

          <div className="grid items-start gap-4 lg:grid-cols-2">
            {/* ---- A. Video / audio ---- */}
            <InputCard
              letter="A"
              title="Video or audio"
              description="Transcribed with real timings taken from the recording itself."
              ready={Boolean(file)}
            >
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

              {file ? (
                <ChosenFile
                  name={file.name}
                  detail={`${megabytes(file.size)}${file.type ? ` · ${file.type}` : ''}`}
                  onChange={() => fileRef.current?.click()}
                  onClear={() => setFile(null)}
                />
              ) : (
                <button
                  type="button"
                  onClick={() => fileRef.current?.click()}
                  className="panel flex w-full flex-col items-center gap-2 border-dashed px-4 py-8 text-center transition-colors hover:border-accent-line"
                >
                  <VideoIcon name="film" className="h-7 w-7 text-muted" />
                  <span className="text-sm font-medium text-body">
                    Upload video or audio
                  </span>
                  <span className="text-xs text-muted">MP4, MOV, WebM, MP3, WAV, M4A</span>
                </button>
              )}

              {file && (
                <MatchingScript
                  file={referenceFile}
                  text={referenceText}
                  onFile={setReferenceFile}
                  onText={setReferenceText}
                  busy={Boolean(busy)}
                />
              )}

              {file && (
                <button className="btn btn-primary mt-4 w-full" onClick={() => setStep('transcribe')}>
                  Continue
                </button>
              )}
            </InputCard>

            {/* ---- B. Document ---- */}
            <InputCard
              letter="B"
              title="Document"
              description="A written script in a file. There is no audio, so the timing is estimated."
              ready={Boolean(documentFile)}
            >
              <input
                ref={documentRef}
                type="file"
                accept={DOCUMENT_ACCEPT}
                className="hidden"
                onChange={(event) => {
                  setDocumentFile(event.target.files?.[0] || null)
                  event.target.value = ''
                }}
              />

              {documentFile ? (
                <ChosenFile
                  name={documentFile.name}
                  detail={megabytes(documentFile.size)}
                  onChange={() => documentRef.current?.click()}
                  onClear={() => setDocumentFile(null)}
                />
              ) : (
                <button
                  type="button"
                  onClick={() => documentRef.current?.click()}
                  className="panel flex w-full flex-col items-center gap-2 border-dashed px-4 py-8 text-center transition-colors hover:border-accent-line"
                >
                  <VideoIcon name="document" className="h-7 w-7 text-muted" />
                  <span className="text-sm font-medium text-body">Upload a document</span>
                  <span className="text-xs text-muted">{DOCUMENT_HINT}</span>
                </button>
              )}

              <div className="mt-3 flex flex-wrap items-end gap-3">
                <div className="min-w-0 flex-1">
                  <label className="label" htmlFor="document-duration">
                    Target length <span className="font-normal text-muted">(optional)</span>
                  </label>
                  <input
                    id="document-duration"
                    className="input"
                    inputMode="decimal"
                    placeholder="e.g. 30, 60 or 120 (seconds)"
                    value={documentDuration}
                    onChange={(event) => setDocumentDuration(event.target.value)}
                  />
                </div>
                <button
                  className="btn btn-primary"
                  disabled={!documentFile || Boolean(busy)}
                  onClick={() =>
                    fromDocument(documentFile, {
                      durationSeconds: Number(documentDuration) || null,
                    })
                  }
                >
                  {busy === 'document' && <Spinner />}
                  Create subtitles
                </button>
              </div>
              <p className="mt-2 text-xs text-muted">
                Timing is estimated because this input does not contain audio.
                Give a target length and the words are fitted to it exactly.
              </p>

              {busy === 'document' && <ProgressStages progress={progress} />}
            </InputCard>

            {/* ---- C. Script ---- */}
            <InputCard
              letter="C"
              title="Script"
              description="Paste the words. Each sentence becomes a subtitle."
              ready={Boolean(script.trim())}
            >
              <textarea
                className="input min-h-[140px] resize-y text-sm"
                placeholder="Paste your script here…"
                value={script}
                onChange={(event) => setScript(event.target.value)}
              />
              <div className="mt-3 flex flex-wrap items-end gap-3">
                <div className="min-w-0 flex-1">
                  <label className="label" htmlFor="script-duration">
                    Target length <span className="font-normal text-muted">(optional)</span>
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
            </InputCard>

            {/* ---- D. Existing subtitle file ---- */}
            <InputCard
              letter="D"
              title="Existing subtitle file"
              description="Open an SRT or WebVTT file to edit, restyle or convert it."
              ready={source?.kind === 'import'}
            >
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
                className="btn btn-secondary self-start"
                onClick={() => importRef.current?.click()}
                disabled={busy === 'import'}
              >
                {busy === 'import' ? <Spinner /> : <VideoIcon name="document" className="h-4 w-4" />}
                Open SRT or VTT
              </button>
              <p className="mt-3 text-xs text-muted">
                The timings come from the file. You can correct its wording
                against the original script once it is open.
              </p>
            </InputCard>
          </div>
        </>
      )}

      {/* ================= TRANSCRIBE ================= */}
      {step === 'transcribe' && (
        <section className="card mx-auto max-w-2xl p-5">
          <h2 className="font-semibold text-body">Transcribe</h2>
          <p className="mt-1 text-sm text-muted">
            {file
              ? hasReference
                ? 'The timing and the spoken words come from your recording. Your script is used to correct the wording where the two agree.'
                : 'Your recording is transcribed with the timings taken from the audio.'
              : 'Go back and choose a file first.'}
          </p>

          <ul className="mt-3 flex flex-col gap-1.5 text-sm">
            <li className="flex items-center gap-2">
              <VideoIcon name="check" className="h-4 w-4 shrink-0 text-emerald-600" />
              <span className="min-w-0 truncate text-body">
                {file ? `${isVideo ? 'Video' : 'Audio'} — ${file.name}` : 'No recording chosen'}
              </span>
            </li>
            {hasReference && (
              <li className="flex items-center gap-2">
                <VideoIcon name="check" className="h-4 w-4 shrink-0 text-emerald-600" />
                <span className="min-w-0 truncate text-body">
                  Matching script — {referenceFile ? referenceFile.name : 'pasted text'}
                </span>
              </li>
            )}
          </ul>

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
                {busy === 'transcribe' ? 'Working…' : 'Transcribe now'}
              </button>
              <button className="btn btn-ghost" onClick={() => setStep('upload')} disabled={busy === 'transcribe'}>
                Back
              </button>
            </div>

            {busy === 'transcribe' && <ProgressStages progress={progress} />}
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
                {source?.alignment?.applied && (
                  <span className="badge border border-emerald-200 bg-emerald-50 text-emerald-700">
                    Script applied
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

              <AlignmentNotice report={source?.alignment} />

              {source?.truncated && (
                <div className="mb-3 rounded-[10px] border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                  That document was longer than the reader's limit, so the last
                  part of it is not in these subtitles.
                </div>
              )}

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

          <section className="flex flex-col gap-4">
            <div className="card h-fit p-4">
              <h2 className="mb-3 font-semibold text-body">Style</h2>
              <StylePanel
                style={style}
                options={styleOptions}
                onChange={setStyle}
                sampleText={cues[0]?.text}
              />
            </div>

            {/* Correcting against a script after the fact. Offered only where
                the timings are real — estimated cues have nothing to align to,
                and re-timing is not what this does. */}
            {!source?.estimated && (
              <div className="card h-fit p-4">
                <h2 className="font-semibold text-body">Correct against a script</h2>
                <p className="mt-1 text-xs text-muted">
                  Timing stays exactly as it is. Only wording the script and the
                  audio already agree on is changed, and anything said
                  differently is kept.
                </p>

                <input
                  ref={lateScriptRef}
                  type="file"
                  accept={DOCUMENT_ACCEPT}
                  className="hidden"
                  onChange={(event) => {
                    const chosen = event.target.files?.[0]
                    event.target.value = ''
                    if (chosen) alignFromFile(chosen)
                  }}
                />

                <textarea
                  className="input mt-3 min-h-[90px] resize-y text-sm"
                  placeholder="Paste the script…"
                  value={lateScript}
                  onChange={(event) => setLateScript(event.target.value)}
                />
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    className="btn btn-secondary btn-sm"
                    disabled={!lateScript.trim() || Boolean(busy)}
                    onClick={() => alignWithScript(lateScript)}
                  >
                    {busy === 'align' && <Spinner />}
                    Apply script
                  </button>
                  <button
                    className="btn btn-ghost btn-sm"
                    disabled={Boolean(busy)}
                    onClick={() => lateScriptRef.current?.click()}
                  >
                    <VideoIcon name="document" className="h-4 w-4" />
                    Upload a document
                  </button>
                </div>
              </div>
            )}
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

            {source?.estimated && (
              <p className="mt-3 rounded-[10px] border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                These timings are estimated from reading speed, because this
                track was made from text rather than from a recording.
              </p>
            )}

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
