import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

import { durationFor, roleFor } from '../lib/toastPolicy'
import { createToastTimers } from '../lib/toastTimers'

const ToastContext = createContext(null)

/**
 * How long a paused toast survives being left alone, in ms.
 *
 * Long enough to finish reading whatever the user was reading it for.
 */
const RESUME_FLOOR = 2000

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const idRef = useRef(0)
  // One manager for the whole provider, held in a ref so its identity is
  // stable and it survives re-renders without becoming a dependency.
  const timersRef = useRef(null)
  if (timersRef.current === null) timersRef.current = createToastTimers()

  const remove = useCallback((id) => {
    timersRef.current.cancel(id)
    setToasts((t) => t.filter((x) => x.id !== id))
  }, [])

  const push = useCallback(
    (type, message) => {
      const id = ++idRef.current
      setToasts((t) => [...t, { id, type, message }])
      // Errors outlive a success: the old code gave every toast the same 4s,
      // which was long enough to read "Saved" and not to read a provider error
      // and decide what to do about it.
      timersRef.current.arm(id, durationFor(type), remove)
    },
    [remove],
  )

  // Hovering or tabbing into a toast pauses its clock, so the message cannot
  // expire out from under someone reading it.
  const pause = useCallback((id) => {
    timersRef.current.pause(id)
  }, [])

  const resume = useCallback((id) => {
    timersRef.current.resume(id, RESUME_FLOOR)
  }, [])

  // Without this the pending timeouts outlive the provider and call setState on
  // an unmounted tree — which is what happens on every sign-out and on hot
  // reload.
  useEffect(() => {
    const timers = timersRef.current
    return () => timers.dispose()
  }, [])

  // Memoised because this is the value every consumer sees. Rebuilt inline it
  // changed identity on each provider render — and the provider re-renders
  // whenever a toast appears or expires — so any effect or callback that
  // depends on `toast` re-ran on every unrelated notification.
  const toast = useMemo(
    () => ({
      success: (m) => push('success', m),
      error: (m) => push('error', m),
      info: (m) => push('info', m),
    }),
    [push],
  )

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <Toaster
        toasts={toasts}
        onClose={remove}
        onPause={pause}
        onResume={resume}
      />
    </ToastContext.Provider>
  )
}

const TONE = {
  success: 'border-emerald-500/40 text-emerald-600',
  error: 'border-rose-500/40 text-rose-600',
  info: 'border-accent-line text-accent',
}

function Toaster({ toasts, onClose, onPause, onResume }) {
  return (
    // The live region. Without it the toasts were visible but silent: a screen
    // reader user had no way of learning a generation had failed, because the
    // only signal was a panel appearing in the corner of the viewport.
    //
    // `polite` on the container, and `role="alert"` on the individual errors
    // below, which are assertive and cut in immediately — a failure is worth
    // interrupting for, a "Saved" is not.
    <div
      aria-live="polite"
      aria-relevant="additions text"
      className="fixed bottom-5 right-5 z-50 flex w-80 flex-col gap-2"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          role={roleFor(t.type)}
          onMouseEnter={() => onPause(t.id)}
          onMouseLeave={() => onResume(t.id)}
          // React's focus handlers bubble, so tabbing to the dismiss button
          // pauses the clock too.
          onFocus={() => onPause(t.id)}
          onBlur={() => onResume(t.id)}
          onClick={() => onClose(t.id)}
          className={`card flex cursor-pointer items-start gap-2 border px-4 py-3 text-sm text-body ${TONE[t.type]}`}
        >
          <span className="flex-1">{t.message}</span>
          <button
            type="button"
            onClick={(e) => {
              // Otherwise the click lands on the card's own handler as well,
              // and the toast is removed twice.
              e.stopPropagation()
              onClose(t.id)
            }}
            aria-label={`Dismiss: ${t.message}`}
            className="-mr-1 -mt-0.5 shrink-0 rounded px-1 text-muted opacity-60 hover:opacity-100 focus:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}
