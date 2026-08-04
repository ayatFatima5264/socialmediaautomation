import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'

const ToastContext = createContext(null)

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const idRef = useRef(0)

  const remove = useCallback((id) => {
    setToasts((t) => t.filter((x) => x.id !== id))
  }, [])

  const push = useCallback(
    (type, message) => {
      const id = ++idRef.current
      setToasts((t) => [...t, { id, type, message }])
      setTimeout(() => remove(id), 4000)
    },
    [remove],
  )

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
      <Toaster toasts={toasts} onClose={remove} />
    </ToastContext.Provider>
  )
}

const TONE = {
  success: 'border-emerald-500/40 text-emerald-600',
  error: 'border-rose-500/40 text-rose-600',
  info: 'border-accent-line text-accent',
}

function Toaster({ toasts, onClose }) {
  return (
    <div className="fixed bottom-5 right-5 z-50 flex w-80 flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          onClick={() => onClose(t.id)}
          className={`card cursor-pointer border px-4 py-3 text-sm text-body ${TONE[t.type]}`}
        >
          {t.message}
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
