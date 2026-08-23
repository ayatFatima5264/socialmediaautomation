import { useCallback, useEffect, useState } from 'react'
import { api } from '../../lib/api.js'
import { useToast } from '../../context/ToastContext.jsx'
import Modal from './Modal.jsx'
import VideoIcon from './VideoIcon.jsx'
import Spinner from '../Spinner.jsx'
import { formatDuration } from '../../lib/video/format.js'

// ---------------------------------------------------------------------------
// "Use my own picture for this scene."
//
// The fourth visual source, alongside stock, AI generation and a card — and
// the one that has to be a picker rather than a button, because only the user
// knows which of their files belongs on this beat.
//
// It writes through the same scene PATCH every other edit uses (`asset_id`),
// so a hand-picked visual is not a special case anywhere downstream: the
// storyboard, the timeline build and the renderer all treat it exactly like a
// generated one.
// ---------------------------------------------------------------------------

export default function ScenePicker({ open, scene, onClose, onPick }) {
  const toast = useToast()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState(null)
  const [uploading, setUploading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      // Only what can sit on a scene: stills and footage. A voice-over in this
      // list would be a file the user can pick and then not see.
      const data = await api.mediaLibrary({ filter: 'image', limit: 100 })
      const video = await api.mediaLibrary({ filter: 'video', limit: 100 })
      setItems([...(data.items || []), ...(video.items || [])])
    } catch (err) {
      toast.error(err?.message || 'Could not load your media.')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => {
    if (open) load()
  }, [open, load])

  async function upload(files) {
    const list = Array.from(files || [])
    if (!list.length) return
    setUploading(true)
    try {
      for (const file of list) {
        await api.uploadVideoMedia(file, {
          kind: file.type.startsWith('video/') ? 'video' : 'image',
        })
      }
      await load()
    } catch (err) {
      toast.error(err?.message || 'That file could not be uploaded.')
    } finally {
      setUploading(false)
    }
  }

  return (
    <Modal
      open={open}
      title="Use your own visual"
      description={
        scene
          ? `For “${scene.title || 'this scene'}”. It replaces whatever is there now.`
          : undefined
      }
      onClose={onClose}
      maxWidth="max-w-2xl"
      footer={
        <button className="btn btn-ghost" onClick={onClose}>
          Cancel
        </button>
      }
    >
      <label className="panel mb-4 flex w-full cursor-pointer flex-col items-center gap-2 border-dashed px-4 py-5 text-center transition-colors hover:border-accent-line">
        <input
          type="file"
          multiple
          accept="image/*,video/*"
          className="hidden"
          onChange={(event) => {
            upload(event.target.files)
            event.target.value = ''
          }}
        />
        {uploading ? <Spinner /> : <VideoIcon name="plus" className="h-5 w-5 text-muted" />}
        <span className="text-sm font-medium text-body">
          {uploading ? 'Uploading…' : 'Upload an image or clip'}
        </span>
      </label>

      {loading && (
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
          {Array.from({ length: 8 }).map((_, index) => (
            <div key={index} className="skeleton aspect-square" />
          ))}
        </div>
      )}

      {!loading && items.length === 0 && (
        <p className="py-6 text-center text-sm text-muted">
          You have no images or clips yet. Upload one above.
        </p>
      )}

      {!loading && items.length > 0 && (
        <ul className="grid max-h-80 grid-cols-3 gap-2 overflow-y-auto sm:grid-cols-4">
          {items.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                disabled={busyId !== null}
                onClick={async () => {
                  setBusyId(item.id)
                  await onPick(item)
                  setBusyId(null)
                  onClose()
                }}
                className="group relative aspect-square w-full overflow-hidden rounded-lg border border-line bg-inset transition-colors hover:border-accent-line disabled:opacity-60"
                title={item.title}
              >
                {item.content_type?.startsWith('image/') ? (
                  <img
                    src={item.url}
                    alt={item.title}
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <span className="grid h-full w-full place-items-center text-muted">
                    <VideoIcon name="film" className="h-5 w-5" />
                  </span>
                )}
                {item.duration_seconds ? (
                  <span className="absolute bottom-1 right-1 rounded bg-black/70 px-1 text-[10px] tabular-nums text-white">
                    {formatDuration(item.duration_seconds)}
                  </span>
                ) : null}
                {busyId === item.id && (
                  <span className="absolute inset-0 grid place-items-center bg-black/40">
                    <Spinner className="text-white" />
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  )
}
