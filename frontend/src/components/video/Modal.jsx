import { useEffect, useRef } from 'react'

// ---------------------------------------------------------------------------
// The modal shell every Video Studio dialog uses.
//
// Same visual construction as ScheduleModal (dimmed backdrop, `.card` panel,
// actions bottom-right) — factored out because this module needs four of them
// and four copies of a focus trap is four places for it to be slightly wrong.
//
// What it adds over a plain div:
//   * Escape closes it, and a click on the backdrop does too, but a click
//     inside never does (a drag that starts in a text field and ends on the
//     backdrop must not throw the dialog away).
//   * Focus moves into the panel on open and returns to whatever opened it on
//     close, so a keyboard user is not dropped back at the top of the page.
//   * `aria-modal` and a labelled heading, so a screen reader announces it as
//     a dialog rather than reading the page behind it.
// ---------------------------------------------------------------------------

export default function Modal({
  open,
  title,
  description,
  onClose,
  children,
  footer,
  maxWidth = 'max-w-md',
}) {
  const panelRef = useRef(null)
  const restoreRef = useRef(null)

  useEffect(() => {
    if (!open) return undefined

    restoreRef.current = document.activeElement
    // The panel itself, not the first field: a destructive dialog should not
    // open with the confirm button already focused.
    panelRef.current?.focus()

    function onKeyDown(event) {
      if (event.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', onKeyDown)

    return () => {
      document.removeEventListener('keydown', onKeyDown)
      // Only restore if the trigger is still in the document — a dialog that
      // deleted the row it was opened from has nothing to go back to.
      const previous = restoreRef.current
      if (previous && document.contains(previous)) previous.focus?.()
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4 backdrop-blur-sm"
      onMouseDown={(event) => {
        // mouseDown, not click: a click fires when press and release land on
        // different elements, which is exactly what a text selection dragged
        // out of the panel looks like.
        if (event.target === event.currentTarget) onClose?.()
      }}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`card w-full ${maxWidth} p-5 focus:outline-none`}
      >
        <h3 className="text-lg font-bold text-body">{title}</h3>
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}

        {children && <div className="mt-4">{children}</div>}

        {footer && <div className="mt-5 flex flex-wrap justify-end gap-2">{footer}</div>}
      </div>
    </div>
  )
}
