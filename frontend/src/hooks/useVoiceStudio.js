import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, ApiError } from '../lib/api.js'
import { useToast } from '../context/ToastContext.jsx'

// ---------------------------------------------------------------------------
// Voice Studio's state: the catalogue, the settings, and the takes.
//
// Three things it is careful about:
//
//   * **Every state is real.** `generating`, `previewing`, `catalogueError` and
//     `error` are set by actual requests. Nothing is optimistic — a take
//     appears in the list when the server has stored it, not when the button
//     was clicked, because a voice-over that failed to save must not sit in the
//     library looking available.
//   * **Errors are kept, not just toasted.** A toast disappears after four
//     seconds; a failed generation needs an explanation that stays on screen
//     next to the button that failed. Both happen.
//   * **No project is required.** `projectId` is only ever sent by `attach`.
// ---------------------------------------------------------------------------

const DEFAULT_SETTINGS = {
  language: 'en-US',
  voiceId: '',
  style: 'default',
  rate: 1,
  pitch: 1,
  volume: 1,
}

export default function useVoiceStudio() {
  const toast = useToast()

  const [catalogue, setCatalogue] = useState(null)
  const [catalogueError, setCatalogueError] = useState(null)
  const [loadingCatalogue, setLoadingCatalogue] = useState(true)

  const [settings, setSettings] = useState(DEFAULT_SETTINGS)
  const [text, setText] = useState('')

  const [takes, setTakes] = useState([])
  const [current, setCurrent] = useState(null)

  const [generating, setGenerating] = useState(false)
  const [previewing, setPreviewing] = useState(false)
  const [error, setError] = useState(null)

  // The preview's object URL, revoked when it is replaced or the page closes.
  // Without this every preview pins its audio in memory for the life of the
  // tab.
  const previewUrlRef = useRef(null)
  const [previewUrl, setPreviewUrl] = useState(null)

  const replacePreviewUrl = useCallback((next) => {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current)
    previewUrlRef.current = next
    setPreviewUrl(next)
  }, [])

  useEffect(() => () => replacePreviewUrl(null), [replacePreviewUrl])

  // ---- catalogue ---------------------------------------------------------
  const loadCatalogue = useCallback(async () => {
    setLoadingCatalogue(true)
    setCatalogueError(null)
    try {
      const data = await api.voiceCatalogue()
      setCatalogue(data)

      // Pick a sensible starting voice: the first one in the default language,
      // else the first voice there is. Leaving it unset would make the first
      // Generate fail on "choose a voice" for no reason.
      setSettings((current) => {
        if (current.voiceId) return current
        const preferred =
          data.voices.find((v) => v.language === current.language) || data.voices[0]
        return preferred
          ? { ...current, voiceId: preferred.id, language: preferred.language }
          : current
      })
    } catch (err) {
      setCatalogueError(
        err?.message || 'Could not load the voice catalogue. Try again in a moment.',
      )
    } finally {
      setLoadingCatalogue(false)
    }
  }, [])

  const loadTakes = useCallback(async () => {
    try {
      setTakes(await api.listVoiceTakes({ limit: 50 }))
    } catch {
      // The library is supporting information; failing to load it must not
      // block generating a new one.
    }
  }, [])

  useEffect(() => {
    loadCatalogue()
    loadTakes()
  }, [loadCatalogue, loadTakes])

  // ---- derived -----------------------------------------------------------
  const voicesForLanguage = useMemo(() => {
    if (!catalogue) return []
    return catalogue.voices.filter((v) => v.language === settings.language)
  }, [catalogue, settings.language])

  const selectedVoice = useMemo(
    () => catalogue?.voices.find((v) => v.id === settings.voiceId) || null,
    [catalogue, settings.voiceId],
  )

  const characters = text.length
  const maxCharacters = catalogue?.max_characters ?? 5000
  const overLimit = characters > maxCharacters

  // ---- settings ----------------------------------------------------------
  const update = useCallback((patch) => {
    setSettings((current) => ({ ...current, ...patch }))
  }, [])

  const setLanguage = useCallback(
    (language) => {
      // Changing language must also move to a voice that speaks it, or the
      // panel shows Urdu selected while an English voice is still armed.
      const next = catalogue?.voices.find((v) => v.language === language)
      setSettings((current) => ({
        ...current,
        language,
        voiceId: next ? next.id : '',
      }))
    },
    [catalogue],
  )

  // ---- actions -----------------------------------------------------------
  const preview = useCallback(async () => {
    if (!text.trim() || !settings.voiceId || previewing) return null
    setPreviewing(true)
    setError(null)
    try {
      const result = await api.previewVoice({
        text,
        voice_id: settings.voiceId,
        style: settings.style,
        rate: settings.rate,
        pitch: settings.pitch,
        volume: settings.volume,
      })

      // base64 -> Blob -> object URL. The preview is never stored server-side,
      // so this is the only copy and it lives exactly as long as the page needs.
      const binary = atob(result.audio_base64)
      const bytes = new Uint8Array(binary.length)
      for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
      replacePreviewUrl(URL.createObjectURL(new Blob([bytes], { type: result.content_type })))

      if (result.truncated) {
        toast.info(
          `Previewing the first ${result.characters} characters. Generate to hear all of it.`,
        )
      }
      return result
    } catch (err) {
      const message = err?.message || 'Could not preview that voice.'
      setError(message)
      toast.error(message)
      return null
    } finally {
      setPreviewing(false)
    }
  }, [text, settings, previewing, replacePreviewUrl, toast])

  const generate = useCallback(
    async ({ body, segmentIndex = null, title = null } = {}) => {
      const source = (body ?? text).trim()
      if (!source) {
        setError('Enter some text first.')
        return null
      }
      if (!settings.voiceId) {
        setError('Choose a voice first.')
        return null
      }

      setGenerating(true)
      setError(null)
      try {
        const take = await api.generateVoice({
          text: source,
          voice_id: settings.voiceId,
          style: settings.style,
          rate: settings.rate,
          pitch: settings.pitch,
          volume: settings.volume,
          title: title || undefined,
          segment_index: segmentIndex,
        })
        setTakes((list) => [take, ...list])
        setCurrent(take)
        // The stored take supersedes any preview — leaving both would give two
        // players showing different audio.
        replacePreviewUrl(null)
        toast.success('Voice-over ready.')
        return take
      } catch (err) {
        const message =
          err instanceof ApiError && err.status === 429
            ? err.message
            : err?.message || 'Could not generate that voice-over.'
        setError(message)
        toast.error(message)
        return null
      } finally {
        setGenerating(false)
      }
    },
    [text, settings, replacePreviewUrl, toast],
  )

  const remove = useCallback(
    async (take) => {
      try {
        await api.deleteVoiceTake(take.id)
        setTakes((list) => list.filter((t) => t.id !== take.id))
        setCurrent((c) => (c?.id === take.id ? null : c))
        toast.success('Voice-over deleted.')
      } catch (err) {
        toast.error(err?.message || 'Could not delete that voice-over.')
      }
    },
    [toast],
  )

  const attach = useCallback(
    async (take, projectId) => {
      try {
        const updated = await api.attachVoiceTake(take.id, projectId)
        setTakes((list) => list.map((t) => (t.id === take.id ? updated : t)))
        setCurrent((c) => (c?.id === take.id ? updated : c))
        return updated
      } catch (err) {
        toast.error(err?.message || 'Could not add that voice-over to the project.')
        throw err
      }
    },
    [toast],
  )

  /** Load a take's text and settings back into the panel — what "use these
   *  settings again" needs, and the starting point for a regeneration. */
  const restore = useCallback(
    (take) => {
      setCurrent(take)
      replacePreviewUrl(null)
      if (take.text) setText(take.text)
      setSettings((current) => ({
        ...current,
        voiceId: take.voice_id || current.voiceId,
        style: take.style || current.style,
        rate: take.rate ?? current.rate,
        pitch: take.pitch ?? current.pitch,
        volume: take.volume ?? current.volume,
        language:
          catalogue?.voices.find((v) => v.id === take.voice_id)?.language ||
          current.language,
      }))
    },
    [catalogue, replacePreviewUrl],
  )

  return {
    // catalogue
    catalogue,
    catalogueError,
    loadingCatalogue,
    reloadCatalogue: loadCatalogue,
    voicesForLanguage,
    selectedVoice,

    // text
    text,
    setText,
    characters,
    maxCharacters,
    overLimit,

    // settings
    settings,
    update,
    setLanguage,

    // takes
    takes,
    current,
    setCurrent,
    previewUrl,

    // state
    generating,
    previewing,
    error,
    clearError: () => setError(null),

    // actions
    preview,
    generate,
    remove,
    attach,
    restore,
  }
}
