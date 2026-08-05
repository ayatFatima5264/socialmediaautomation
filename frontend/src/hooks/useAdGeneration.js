import { useCallback, useState } from 'react'
import { useToast } from '../context/ToastContext.jsx'

// ---------------------------------------------------------------------------
// The generate → result cycle every ad tool shares.
//
// One place for the three states a generation has (idle, running, returned) and
// for the one rule that matters when it fails: show the server's message and
// KEEP the previous result on screen. Blanking the panel on a rate-limit or a
// dropped connection throws away work the user could still copy from, and tells
// them nothing about what went wrong.
// ---------------------------------------------------------------------------

export default function useAdGeneration(call) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const toast = useToast()

  const run = useCallback(
    async (payload) => {
      setLoading(true)
      try {
        const result = await call(payload)
        setData(result)
        return result
      } catch (err) {
        toast.error(err?.message || 'Generation failed. Try again.')
        return null
      } finally {
        setLoading(false)
      }
    },
    [call, toast],
  )

  return { data, loading, run, reset: () => setData(null) }
}
