import { useEffect, useRef, useState } from 'react'
import MediaLibraryModal from '../../media/MediaLibraryModal.jsx'

// ---------------------------------------------------------------------------
// Picking the image a tool works from.
//
// This one is genuinely wired, not a placeholder: the file input accepts a
// real upload and the Media Library button opens the app's existing picker —
// the same modal the Content Planner uses, which hands back a File whether the
// image came from the stock set or the user's own library. Choosing an image
// costs no model call, so there is no reason to fake it.
//
// Object URLs are revoked when the selection changes or the field unmounts. A
// workspace where someone tries eight product shots would otherwise leak eight
// decoded images for the life of the page.
// ---------------------------------------------------------------------------

export default function UploadField({ multiple = false, hint, onChange }) {
  const [files, setFiles] = useState([])
  const [previews, setPreviews] = useState([])
  const [libraryOpen, setLibraryOpen] = useState(false)
  const inputRef = useRef(null)

  useEffect(() => {
    const urls = files.map((f) => URL.createObjectURL(f))
    setPreviews(urls)
    return () => urls.forEach((u) => URL.revokeObjectURL(u))
  }, [files])

  function replace(next) {
    setFiles(next)
    onChange?.(next)
  }

  function addFiles(incoming) {
    const picked = Array.from(incoming || []).filter((f) => f.type.startsWith('image/'))
    if (!picked.length) return
    replace(multiple ? [...files, ...picked] : [picked[0]])
  }

  return (
    <>
      <div className="panel p-3">
        {previews.length > 0 ? (
          <div className={multiple ? 'grid grid-cols-3 gap-2' : ''}>
            {previews.map((src, i) => (
              <div key={src} className="group relative overflow-hidden rounded-lg border border-line">
                <img
                  src={src}
                  alt={files[i]?.name || 'Selected image'}
                  className={`w-full object-cover ${multiple ? 'aspect-square' : 'aspect-[4/3]'}`}
                />
                <button
                  type="button"
                  onClick={() => replace(files.filter((_, j) => j !== i))}
                  className="absolute right-1.5 top-1.5 grid h-6 w-6 place-items-center rounded-full bg-surface/90 text-xs text-body shadow-sm"
                  aria-label={`Remove ${files[i]?.name || 'image'}`}
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        ) : (
          <div className="grid place-items-center rounded-lg border border-dashed border-field-border px-3 py-6 text-center">
            <span aria-hidden="true" className="text-xl text-muted">
              ⬆
            </span>
            <p className="mt-1.5 text-xs text-muted">{hint || 'PNG or JPG, up to 10 MB'}</p>
          </div>
        )}

        <div className="mt-3 grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="btn btn-secondary btn-sm"
          >
            Upload
          </button>
          <button
            type="button"
            onClick={() => setLibraryOpen(true)}
            className="btn btn-secondary btn-sm"
          >
            Media Library
          </button>
        </div>

        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          multiple={multiple}
          className="hidden"
          onChange={(e) => {
            addFiles(e.target.files)
            // Cleared so re-picking the same file fires change again.
            e.target.value = ''
          }}
        />
      </div>

      <MediaLibraryModal
        open={libraryOpen}
        onCancel={() => setLibraryOpen(false)}
        onSelect={(file) => {
          addFiles([file])
          setLibraryOpen(false)
        }}
      />
    </>
  )
}
