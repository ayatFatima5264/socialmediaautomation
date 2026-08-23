import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../lib/api.js'
import { useToast } from '../context/ToastContext.jsx'

// ---------------------------------------------------------------------------
// Subtitle Studio's state: the track, its style, and the edits.
//
// **Every edit round-trips to the server.** That looks like an odd choice for
// something as interactive as a cue list, and it is deliberate: the rules that
// make a track valid — no overlaps, no negative durations, minimum readable
// length, the flicker gap — live in one place, and a client-side copy of them
// would drift. Each operation is one small request returning the whole track,
// and the track is a few hundred cues at most.
//
// What that buys, beyond correctness: undo is free. Every edit pushes the
// previous track onto a stack, so any of them can be taken back — including
// the destructive ones (merge, search/replace) that a user is most likely to
// regret.
//
// **Inputs are independent.** A recording, a document, a pasted script and an
// existing subtitle file each produce a track on their own; supplying a script
// *with* a recording runs one extra step that corrects the wording without
// touching the timing. Nothing here requires two inputs, and nothing refuses
// one because another is missing.
// ---------------------------------------------------------------------------

const MAX_UNDO = 50

// The stages `generate` actually passes through, in order. Each one is a real
// boundary — a request that has finished, or bytes that have left the machine —
// rather than a caption on a timer, which is the difference between progress
// and theatre.
const STAGE_LABELS = {
  document: 'Reading your script',
  upload: 'Uploading',
  transcribe: 'Transcribing the audio',
  align: 'Comparing the transcript with your script',
  cues: 'Preparing subtitles',
}

export default function useSubtitleStudio() {
  const toast = useToast()

  const [cues, setCues] = useState([])
  const [style, setStyle] = useState(null)
  const [styleOptions, setStyleOptions] = useState(null)

  // Where the cues came from, and what we know about them. Kept so the UI can
  // be honest — script-timed cues are estimates and must not be presented as
  // measured ones.
  const [source, setSource] = useState(null)

  const [busy, setBusy] = useState(null) // a label, so buttons can show which
  const [error, setError] = useState(null)

  // What the pipeline is doing right now: which stages this run has, which are
  // finished, and the real upload percentage while bytes are moving.
  const [progress, setProgress] = useState(null)

  const undoStack = useRef([])
  const [undoDepth, setUndoDepth] = useState(0)

  // ---- style catalogue ---------------------------------------------------
  useEffect(() => {
    let cancelled = false
    api
      .subtitleStyles()
      .then((data) => {
        if (cancelled) return
        setStyleOptions(data)
        setStyle((current) => current || data.presets.find((p) => p.key === data.default_preset) || data.presets[0])
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || 'Could not load the subtitle styles.')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const remember = useCallback((previous) => {
    undoStack.current = [...undoStack.current.slice(-(MAX_UNDO - 1)), previous]
    setUndoDepth(undoStack.current.length)
  }, [])

  /** Run an edit, keeping the previous track for undo and surfacing failures.
   *
   *  A refused edit ("only adjacent cues can be merged") is not an exception
   *  the user caused by accident — it is the answer to what they asked for, so
   *  it is shown and the track is left exactly as it was. */
  const run = useCallback(
    async (label, operation, { silent = false } = {}) => {
      setBusy(label)
      setError(null)
      const previous = cues
      try {
        const result = await operation(previous)
        remember(previous)
        setCues(result.cues)
        return result
      } catch (err) {
        const message = err?.message || 'That edit could not be applied.'
        setError(message)
        if (!silent) toast.error(message)
        return null
      } finally {
        setBusy(null)
      }
    },
    [cues, remember, toast],
  )

  const undo = useCallback(() => {
    const stack = undoStack.current
    if (!stack.length) return
    const previous = stack[stack.length - 1]
    undoStack.current = stack.slice(0, -1)
    setUndoDepth(undoStack.current.length)
    setCues(previous)
  }, [])

  // ---- loading a track ---------------------------------------------------
  const startFrom = useCallback((nextCues, nextSource) => {
    undoStack.current = []
    setUndoDepth(0)
    setCues(nextCues)
    setSource(nextSource)
    setError(null)
  }, [])

  /** Transcribe a recording, optionally correcting it against a script.
   *
   *  The one entry point for every media-backed workflow, because they are the
   *  same workflow with one optional step in the middle:
   *
   *      [read the document] -> upload -> transcribe -> [align] -> cues
   *
   *  The bracketed stages only happen when a reference was supplied. Nothing
   *  here requires one, and a missing document is not an error — it is the
   *  ordinary case.
   *
   *  The document is read *first*, before a single byte of video is uploaded.
   *  A corrupt DOCX should cost the user a second, not a full transcription. */
  const transcribe = useCallback(
    async (file, options = {}) => {
      const { referenceFile = null, referenceText = '', ...transcribeOptions } = options

      const hasReference = Boolean(referenceFile || referenceText.trim())
      const stages = [
        ...(referenceFile ? ['document'] : []),
        'upload',
        'transcribe',
        ...(hasReference ? ['align'] : []),
        'cues',
      ]

      const advance = (stage, percent = null) =>
        setProgress({
          stages,
          labels: STAGE_LABELS,
          current: stage,
          done: stages.slice(0, stages.indexOf(stage)),
          percent,
        })

      setBusy('transcribe')
      setError(null)
      advance(stages[0])

      try {
        // ---- the reference, if there is one --------------------------------
        let script = referenceText.trim()
        if (referenceFile) {
          const document = await api.subtitlesFromDocument(referenceFile)
          script = document.text
        }

        // ---- the recording -------------------------------------------------
        advance('upload', 0)
        const result = await api.transcribeMedia(file, {
          ...transcribeOptions,
          onProgress: (percent) => advance('upload', percent),
          onUploaded: () => advance('transcribe'),
        })

        // ---- the correction, if there is a script --------------------------
        let cues = result.cues
        let alignment = null
        if (script) {
          advance('align')
          const aligned = await api.alignSubtitles(cues, script, transcribeOptions.styleKey)
          cues = aligned.cues
          alignment = aligned.alignment
        }

        advance('cues')
        startFrom(cues, {
          kind: 'transcription',
          provider: result.provider,
          model: result.model,
          language: result.language,
          duration: result.duration_seconds,
          wordCount: result.word_count,
          mediaUrl: result.source_url,
          assetId: result.source_asset_id,
          filename: file.name,
          translated: result.translated,
          // Timing came off the audio, whether or not a script was involved.
          estimated: false,
          alignment,
          referenceName: referenceFile?.name || (script ? 'Pasted script' : null),
        })

        if (alignment?.applied) {
          toast.success(`${cues.length} subtitles, corrected against your script.`)
        } else if (alignment) {
          // The script was supplied and deliberately not used. Saying so is
          // the whole point of the report — otherwise it looks ignored.
          toast.info(alignment.message || 'Your script did not match this recording.')
        } else {
          toast.success(`Transcribed ${cues.length} subtitles.`)
        }
        return { ...result, cues, alignment }
      } catch (err) {
        const message = err?.message || 'Could not transcribe that file.'
        setError(message)
        toast.error(message)
        return null
      } finally {
        setBusy(null)
        setProgress(null)
      }
    },
    [startFrom, toast],
  )

  /** A document on its own: read it, then time its words. No audio involved,
   *  so the timing is an estimate unless a target length was given — and the
   *  `estimated` flag carries that straight through to the UI. */
  const fromDocument = useCallback(
    async (file, { durationSeconds = null, wordsPerMinute = null } = {}) => {
      setBusy('document')
      setError(null)
      setProgress({
        stages: ['document', 'cues'],
        labels: { document: 'Reading the document', cues: 'Creating subtitles and estimating timing' },
        current: 'document',
        done: [],
        percent: null,
      })
      try {
        const result = await api.subtitlesFromDocument(file, {
          durationSeconds,
          wordsPerMinute,
          styleKey: style?.key,
        })
        startFrom(result.cues, {
          kind: 'document',
          filename: result.filename,
          documentKind: result.kind,
          wordCount: result.word_count,
          duration: result.duration_seconds,
          truncated: result.truncated,
          estimated: result.estimated,
        })
        toast.success(`Created ${result.cues.length} subtitles from ${result.filename}.`)
        return result
      } catch (err) {
        const message = err?.message || 'Could not read that document.'
        setError(message)
        toast.error(message)
        return null
      } finally {
        setBusy(null)
        setProgress(null)
      }
    },
    [startFrom, style, toast],
  )

  /** Apply a script to the track that is already open.
   *
   *  Reachable after an import as well as after a transcription: an SRT from
   *  somewhere else has real timings too, and correcting its wording against
   *  the original script is the same operation. */
  const alignWithScript = useCallback(
    async (script) => {
      if (!script?.trim()) return null
      setBusy('align')
      setError(null)
      const previous = cues
      try {
        const result = await api.alignSubtitles(previous, script, style?.key)
        remember(previous)
        setCues(result.cues)
        setSource((current) => ({ ...(current || {}), alignment: result.alignment }))
        toast[result.alignment.applied ? 'success' : 'info'](
          result.alignment.message || 'Compared your script with the audio.',
        )
        return result
      } catch (err) {
        const message = err?.message || 'Could not compare that script with the audio.'
        setError(message)
        toast.error(message)
        return null
      } finally {
        setBusy(null)
      }
    },
    [cues, remember, style, toast],
  )

  const fromScript = useCallback(
    async (text, durationSeconds) => {
      setBusy('script')
      setError(null)
      try {
        const result = await api.subtitlesFromScript({
          text,
          duration_seconds: durationSeconds || null,
          style_key: style?.key,
        })
        startFrom(result.cues, {
          kind: 'script',
          duration: result.duration_seconds,
          // The honest flag: with no audio behind it, the timing is a guess.
          estimated: result.estimated,
        })
        toast.success(`Timed ${result.cues.length} subtitles from your script.`)
        return result
      } catch (err) {
        const message = err?.message || 'Could not time that script.'
        setError(message)
        toast.error(message)
        return null
      } finally {
        setBusy(null)
      }
    },
    [style, startFrom, toast],
  )

  const importFile = useCallback(
    async (file) => {
      setBusy('import')
      setError(null)
      try {
        const result = await api.importSubtitleFile(file)
        startFrom(result.cues, { kind: 'import', filename: file.name, estimated: false })
        toast.success(`Opened ${result.cues.length} subtitles from ${file.name}.`)
        return result
      } catch (err) {
        const message = err?.message || 'Could not read that subtitle file.'
        setError(message)
        toast.error(message)
        return null
      } finally {
        setBusy(null)
      }
    },
    [startFrom, toast],
  )

  // ---- edits -------------------------------------------------------------
  const editors = useMemo(
    () => ({
      update: (index, patch) =>
        run('update', (current) => api.updateCue(current, index, patch), { silent: true }),
      insert: (index) => run('insert', (current) => api.insertCue(current, { index })),
      remove: (index) => run('delete', (current) => api.deleteCue(current, index)),
      split: (index, at) => run('split', (current) => api.splitCue(current, index, at)),
      merge: (indices) => run('merge', (current) => api.mergeCues(current, indices)),
      shift: (offset) => run('shift', (current) => api.shiftCues(current, offset)),
      normalize: () => run('normalize', (current) => api.normalizeCues(current)),
      searchReplace: async (body) => {
        const result = await run('replace', (current) => api.searchReplaceCues(current, body))
        if (result) {
          toast[result.replacements ? 'success' : 'info'](
            result.replacements
              ? `Replaced ${result.replacements} occurrence${result.replacements === 1 ? '' : 's'}.`
              : `No matches for “${body.find}”.`,
          )
        }
        return result
      },
    }),
    [run, toast],
  )

  const duration = useMemo(
    () => cues.reduce((longest, cue) => Math.max(longest, cue.end), 0),
    [cues],
  )

  return {
    cues,
    setCues,
    duration,
    source,
    style,
    setStyle,
    styleOptions,
    busy,
    progress,
    error,
    clearError: () => setError(null),
    canUndo: undoDepth > 0,
    undo,
    transcribe,
    fromScript,
    fromDocument,
    alignWithScript,
    importFile,
    startFrom,
    ...editors,
  }
}
