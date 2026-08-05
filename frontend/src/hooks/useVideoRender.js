import { useCallback, useEffect, useRef, useState } from 'react'
import { useToast } from '../context/ToastContext.jsx'
import { canRender, downloadVideo, renderVideo } from '../lib/ads/videoRender'

// ---------------------------------------------------------------------------
// Driving a browser-side video render.
//
// Recording is real time, so progress is not decoration — without it a
// fifteen-second clip looks like a hung button. The hook exposes it, plus a
// cancel, and holds the finished blob as an object URL for playback.
//
// The previous render's object URL is revoked whenever a new one replaces it
// and on unmount. Re-rendering six times otherwise leaves six decoded videos
// pinned in memory for the life of the page.
// ---------------------------------------------------------------------------

export default function useVideoRender() {
  const [progress, setProgress] = useState(0)
  const [rendering, setRendering] = useState(false)
  const [result, setResult] = useState(null) // { url, blob, extension }
  const abortRef = useRef(null)
  const urlRef = useRef(null)
  const toast = useToast()

  const replaceUrl = useCallback((next) => {
    if (urlRef.current) URL.revokeObjectURL(urlRef.current)
    urlRef.current = next
  }, [])

  useEffect(() => () => replaceUrl(null), [replaceUrl])

  const render = useCallback(
    async (opts) => {
      if (!canRender()) {
        toast.error('This browser cannot record video. Try Chrome, Edge or Firefox.')
        return null
      }
      const controller = new AbortController()
      abortRef.current = controller

      setRendering(true)
      setProgress(0)
      try {
        const { blob, extension } = await renderVideo({
          ...opts,
          signal: controller.signal,
          onProgress: setProgress,
        })
        const url = URL.createObjectURL(blob)
        replaceUrl(url)
        const next = { url, blob, extension }
        setResult(next)
        return next
      } catch (err) {
        toast.error(err?.message || 'Rendering failed.')
        return null
      } finally {
        setRendering(false)
        abortRef.current = null
      }
    },
    [replaceUrl, toast],
  )

  const cancel = useCallback(() => abortRef.current?.abort(), [])

  const save = useCallback(
    (stem) => {
      if (!result) return
      downloadVideo(result.blob, result.extension, stem)
    },
    [result],
  )

  return { render, cancel, save, rendering, progress, result, supported: canRender() }
}
