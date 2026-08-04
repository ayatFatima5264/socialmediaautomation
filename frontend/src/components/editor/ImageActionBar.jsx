import { useRef } from 'react'

// ---------------------------------------------------------------------------
// The six things you can do to a generated image.
//
// One definition, so the AI Generator and the Content Planner cannot end up
// with different verbs, different labels, or a button that exists on one page
// and not the other. Every action is optional: pass only the handlers a given
// surface actually supports and the rest are simply not rendered.
//
// "Edit" and "AI Edit" both open the same editor — AI Edit just asks it to
// start on the AI panel, because that is the difference the user cares about.
// ---------------------------------------------------------------------------
export default function ImageActionBar({
  onEdit,
  onAiEdit,
  onRegenerate,
  onBrowseLibrary,
  onReplace,
  onDownload,
  onRemove,
  busy = false,
  size = 'sm',
}) {
  const fileRef = useRef(null)

  const cls = `btn btn-ghost btn-${size}`

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {onEdit && (
        <button type="button" onClick={onEdit} disabled={busy} className={cls} title="Open the image editor">
          ✎ Edit
        </button>
      )}
      {onAiEdit && (
        <button type="button" onClick={onAiEdit} disabled={busy} className={cls} title="Change the image with a prompt">
          ✦ AI Edit
        </button>
      )}
      {onRegenerate && (
        <button type="button" onClick={onRegenerate} disabled={busy} className={cls} title="Generate fresh artwork">
          ↻ Regenerate
        </button>
      )}
      {/* Sits next to Replace because they answer the same question — use a
          different picture — and differ only in where it comes from. */}
      {onBrowseLibrary && (
        <button
          type="button"
          onClick={onBrowseLibrary}
          disabled={busy}
          className={cls}
          title="Choose from your media library"
        >
          🖼 Library
        </button>
      )}
      {onReplace && (
        <>
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={busy}
            className={cls}
            title="Upload your own image"
          >
            ⬆ Replace
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0]
              // Reset first: picking the same file twice must still fire.
              e.target.value = ''
              if (file) onReplace(file)
            }}
          />
        </>
      )}
      {onDownload && (
        <button type="button" onClick={onDownload} disabled={busy} className={cls} title="Download the image">
          ⬇ Download
        </button>
      )}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          disabled={busy}
          className={`btn btn-${size} text-rose-500 hover:text-rose-400`}
          title="Remove the image from this post"
        >
          ✕ Remove
        </button>
      )}
    </div>
  )
}
