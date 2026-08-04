import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import MediaBrowser from './MediaBrowser.jsx'
import { useToast } from '../../context/ToastContext.jsx'
import mediaStore, { assetToFile } from '../../lib/media/store'

// ---------------------------------------------------------------------------
// Picking an image from the Media Library.
//
// Selection is staged, like the template library: clicking a tile moves a
// draft, and nothing reaches the caller until "Use Image" — so Cancel is a
// true undo and a mis-click costs nothing. Double-clicking a tile is the
// shortcut for people who already know which one they want.
//
// The caller is handed a File, not an asset. Every surface that can already
// receive an image — the editor's Replace, the planner's swap — accepts a File
// from a file input, so the library slots into those paths untouched. It also
// resolves the difference the caller must not have to care about: a stock
// asset is a static URL that could be persisted, an upload is an object URL
// that could not, and both become bytes here.
// ---------------------------------------------------------------------------

export default function MediaLibraryModal({
  open,
  onCancel,
  onSelect,
  title = 'Choose an Image',
  confirmLabel = 'Use Image',
}) {
  const toast = useToast()
  const [draft, setDraft] = useState(null)
  const [busy, setBusy] = useState(false)

  // The modal stays mounted between opens, so opening is what clears the last
  // session's selection — otherwise a cancelled pick would come back.
  useEffect(() => {
    if (open) {
      setDraft(null)
      setBusy(false)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && onCancel()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onCancel])

  if (!open) return null

  async function apply(asset) {
    if (!asset || busy) return
    setBusy(true)
    try {
      const file = await assetToFile(asset)
      // Recorded before handing over, so "recently used" reflects the choice
      // even if what the caller does next fails.
      await mediaStore.markUsed(asset.id)
      onSelect(file, asset)
    } catch (err) {
      toast.error(err.message || 'Could not load that image')
      setBusy(false)
    }
  }

  // z-[60], above the z-50 the image editor's full-screen overlay uses: the
  // editor opens this from inside itself, and anything lower opens behind it.
  return createPortal(
    <div
      className="fixed inset-0 z-[60] grid place-items-center bg-black/50 p-2 backdrop-blur-sm sm:p-6"
      onClick={onCancel}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div
        className="card flex h-[92vh] w-full max-w-[1400px] flex-col overflow-hidden sm:h-[88vh]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-center gap-3 border-b border-line p-3 sm:p-4">
          <h2 className="text-base font-bold sm:text-lg">{title}</h2>
          <button
            type="button"
            onClick={onCancel}
            aria-label="Close"
            className="btn btn-ghost btn-sm ml-auto shrink-0"
          >
            ✕
          </button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col p-3 sm:p-4">
          <MediaBrowser
            selectedId={draft?.id}
            onSelect={setDraft}
            onActivate={apply}
            manage
          />
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2 border-t border-line p-3 sm:p-4">
          <span className="min-w-0 flex-1 truncate text-xs text-muted">
            {draft ? (
              <>
                Selected: <span className="font-semibold text-body">{draft.title || 'Untitled'}</span>
                {draft.width ? ` · ${draft.width} × ${draft.height} px` : ''}
              </>
            ) : (
              'Pick an image, or double-click one to use it straight away.'
            )}
          </span>
          <button type="button" onClick={onCancel} className="btn btn-ghost">
            Cancel
          </button>
          <button
            type="button"
            onClick={() => apply(draft)}
            disabled={!draft || busy}
            className="btn btn-primary"
          >
            {busy ? 'Loading…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
