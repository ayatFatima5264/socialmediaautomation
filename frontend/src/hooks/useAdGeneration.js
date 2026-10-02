import { useCallback, useEffect, useRef, useState } from 'react'
import { useToast } from '../context/ToastContext.jsx'
import {
  GENERATION_DEADLINE,
  RUN_ENDED,
  createGenerationRun,
  isAbortError,
} from '../lib/generationRun'

// ---------------------------------------------------------------------------
// The generate → result cycle every ad tool shares.
//
// One place for the three states a generation has (idle, running, returned) and
// for the one rule that matters when it fails: show the server's message and
// KEEP the previous result on screen. Blanking the panel on a rate-limit or a
// dropped connection throws away work the user could still copy from, and tells
// them nothing about what went wrong.
//
// BUG-10 added the three things that were missing when a generation went wrong
// in a way the server could not see:
//
//   * a deadline, so a request that never answers is given up on rather than
//     leaving the panel on "Generating…" for as long as the user waits;
//   * `cancel`, so the wait is the user's to end and not only the clock's;
//   * a run identity, so a response that arrives after the user has moved on
//     cannot overwrite the results they are looking at now.
//
// The run is created once and kept in a ref: rebuilding it on each render would
// lose the timer and the identity it exists to hold.
// ---------------------------------------------------------------------------

export default function useAdGeneration(call, { deadline = GENERATION_DEADLINE } = {}) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [elapsed, setElapsed] = useState(null)
  const toast = useToast()

  const runRef = useRef(null)
  if (runRef.current === null) runRef.current = createGenerationRun({ deadline })

  // A tick so the progress line moves. Only while a run is in flight — a
  // permanent interval would outlive the page.
  useEffect(() => {
    if (!loading) return undefined
    const started = runRef.current
    const id = setInterval(() => setElapsed(started.elapsed()), 500)
    return () => clearInterval(id)
  }, [loading])

  // Unmount. Without this the request keeps running, the timer keeps counting,
  // and a response that lands afterwards calls setData on a component that is
  // gone.
  useEffect(() => {
    const started = runRef.current
    return () => started.dispose()
  }, [])

  const run = useCallback(
    async (payload) => {
      const started = runRef.current
      // A second click supersedes the first rather than racing it: two
      // generations writing to the same state is how the older answer wins.
      const { id, signal } = started.start()

      setLoading(true)
      setElapsed(0)

      try {
        const result = await call(payload, { signal })
        if (!started.isCurrent(id)) return null
        setData(result)
        return result
      } catch (err) {
        const reason = started.reason()

        if (reason === RUN_ENDED.TIMED_OUT) {
          toast.error(
            'That took longer than 90 seconds and was stopped. The image host may be ' +
              'rate-limiting — try again, or generate fewer images at once.',
          )
          return null
        }

        // Cancelled by the user, or superseded by a newer run. Neither is a
        // failure worth a red toast, and neither should say why — the user
        // knows, they did it.
        if (reason === RUN_ENDED.CANCELLED || reason === RUN_ENDED.SUPERSEDED) {
          return null
        }

        // An abort we did not initiate. Treated as a network failure, which is
        // what it almost always is.
        if (isAbortError(err)) {
          if (started.isCurrent(id)) toast.error('The request was cancelled.')
          return null
        }

        // Only report if this is still the run the user is looking at.
        if (!started.isCurrent(id)) return null
        toast.error(err?.message || 'Generation failed. Try again.')
        return null
      } finally {
        if (started.isCurrent(id)) {
          started.finish()
          setLoading(false)
          setElapsed(null)
        }
      }
    },
    [call, toast],
  )

  /** End the current run. The previous results stay on screen. */
  const cancel = useCallback(() => {
    runRef.current.cancel()
    setLoading(false)
    setElapsed(null)
  }, [])

  return {
    data,
    loading,
    run,
    cancel,
    elapsed,
    reset: () => setData(null),
  }
}
