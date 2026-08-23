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
// ---------------------------------------------------------------------------

const MAX_UNDO = 50

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

  const transcribe = useCallback(
    async (file, options) => {
      setBusy('transcribe')
      setError(null)
      try {
        const result = await api.transcribeMedia(file, options)
        startFrom(result.cues, {
          kind: 'transcription',
          provider: result.provider,
          model: result.model,
          language: result.language,
          duration: result.duration_seconds,
          wordCount: result.word_count,
          mediaUrl: result.source_url,
          assetId: result.source_asset_id,
          translated: result.translated,
          estimated: false,
        })
        toast.success(`Transcribed ${result.cues.length} subtitles.`)
        return result
      } catch (err) {
        const message = err?.message || 'Could not transcribe that file.'
        setError(message)
        toast.error(message)
        return null
      } finally {
        setBusy(null)
      }
    },
    [startFrom, toast],
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
    error,
    clearError: () => setError(null),
    canUndo: undoDepth > 0,
    undo,
    transcribe,
    fromScript,
    importFile,
    startFrom,
    ...editors,
  }
}
