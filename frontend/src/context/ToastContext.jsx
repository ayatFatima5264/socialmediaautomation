import { createContext, useCallback, useContext, useRef, useState } from 'react'

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

  const toast = {
    success: (m) => push('success', m),
    error: (m) => push('error', m),
    info: (m) => push('info', m),
  }

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <Toaster toasts={toasts} onClose={remove} />
    </ToastContext.Provider>
  )
}

const TONE = {
  success: 'border-emerald-500/40 text-emerald-600 dark:text-emerald-300',
  error: 'border-rose-500/40 text-rose-600 dark:text-rose-300',
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
