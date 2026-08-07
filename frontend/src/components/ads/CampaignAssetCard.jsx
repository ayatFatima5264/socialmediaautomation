import { useState } from 'react'
import { Link } from 'react-router-dom'
import { isMediaKind } from '../../lib/ads/assets'
import { formatRelative } from '../../lib/datetime'

// ---------------------------------------------------------------------------
// One asset in a campaign's library.
//
// Two shapes from one component: a picture or video gets a thumbnail, copy gets
// its words. They share the same header, the same action row and the same
// rename behaviour, because they are the same object to the user — something
// the campaign made, that they now want to rename, reuse or throw away.
//
// ---- Renaming ------------------------------------------------------------
// Inline, committed on blur or Enter and abandoned on Escape. A modal for
// renaming one field is three clicks for a two-character edit.
//
// ---- Download -------------------------------------------------------------
// Media opens in a new tab rather than fetching and re-serving the bytes: the
// generated images live on a third-party host that does not send CORS headers,
// so a `fetch`-then-blob download fails silently in the browser. Copy has no
// host to open, so its "Download" writes a .txt from the text already on the
// page — which is why the two do different things behind the same word.
// ---------------------------------------------------------------------------

function downloadText(asset) {
  const blob = new Blob([asset.body || ''], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${asset.title.replace(/[^\w\- ]+/g, '') || 'copy'}.txt`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

function Thumb({ asset }) {
  const [state, setState] = useState('loading')

  if (asset.kind === 'video') {
    return (
      <video
        src={asset.url}
        muted
        playsInline
        preload="metadata"
        className="h-full w-full bg-inset object-cover"
      />
    )
  }

  return (
    <>
      {state !== 'error' && (
        <img
          src={asset.url}
          alt={asset.title}
          loading="lazy"
          onLoad={() => setState('ok')}
          onError={() => setState('error')}
          className={`h-full w-full object-cover transition-opacity ${
            state === 'ok' ? 'opacity-100' : 'opacity-0'
          }`}
        />
      )}
      {state === 'loading' && <span className="skeleton absolute inset-0" />}
      {state === 'error' && (
        <span className="absolute inset-0 grid place-items-center p-3 text-center text-[11px] leading-snug text-muted">
          The image host is not responding. The link is kept.
        </span>
      )}
    </>
  )
}

export default function CampaignAssetCard({
  asset,
  onRename,
  onEditBody,
  onDuplicate,
  onDelete,
  onAttach,
  editHref,
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(asset.title)
  const [bodyEditing, setBodyEditing] = useState(false)
  const [bodyDraft, setBodyDraft] = useState(asset.body || '')
  const [confirming, setConfirming] = useState(false)

  // A media asset only behaves like one when it actually has a file behind it.
  // Without a URL — a browser-rendered video, a saved shot plan — the actions
  // that open or attach a file would be dead buttons, so it is treated as the
  // text record it is.
  const media = isMediaKind(asset.kind) && Boolean(asset.url)

  function commit() {
    setEditing(false)
    onRename?.(asset, draft)
  }

  return (
    <article className="panel flex flex-col overflow-hidden p-0">
      {media ? (
        <div className="relative aspect-square w-full overflow-hidden bg-inset">
          <Thumb asset={asset} />
        </div>
      ) : bodyEditing ? (
        // Copy is edited where it is read. Sending a headline off to a
        // workspace to change one word — and re-generating it there, which is
        // what that workspace does — would be the long way round to a typo fix.
        <div className="flex-1 p-2.5">
          <textarea
            autoFocus
            rows={5}
            className="input resize-none text-sm"
            value={bodyDraft}
            onChange={(e) => setBodyDraft(e.target.value)}
            aria-label={`Edit ${asset.title}`}
          />
          <div className="mt-2 flex gap-1.5">
            <button
              type="button"
              onClick={() => {
                setBodyEditing(false)
                onEditBody?.(asset, bodyDraft)
              }}
              className="btn btn-primary btn-sm px-2 py-1 text-[11px]"
            >
              Save
            </button>
            <button
              type="button"
              onClick={() => {
                setBodyDraft(asset.body || '')
                setBodyEditing(false)
              }}
              className="btn btn-ghost btn-sm px-2 py-1 text-[11px]"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <p className="min-h-[92px] flex-1 whitespace-pre-wrap p-3 text-sm leading-relaxed text-body">
          {asset.body}
        </p>
      )}

      <div className="flex flex-1 flex-col gap-2 border-t border-line p-2.5">
        <div className="min-w-0">
          {editing ? (
            <input
              autoFocus
              className="input h-8 py-1 text-xs"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={commit}
              onKeyDown={(e) => {
                if (e.key === 'Enter') commit()
                if (e.key === 'Escape') {
                  setDraft(asset.title)
                  setEditing(false)
                }
              }}
              aria-label="Asset name"
            />
          ) : (
            <button
              type="button"
              onClick={() => setEditing(true)}
              title="Rename"
              className="block w-full truncate text-left text-xs font-semibold text-body hover:text-accent"
            >
              {asset.title}
            </button>
          )}

          <p className="mt-0.5 truncate text-[10px] text-muted">
            {[asset.tool, formatRelative(asset.createdAt)].filter(Boolean).join(' · ')}
          </p>
        </div>

        <div className="mt-auto flex flex-wrap gap-1">
          {/* Edit means "change this asset", never "make another one like it".
              Copy is edited in place above; anything with a workspace behind it
              reopens there with its settings restored, and generating replaces
              this asset unless the user asks for a new one. */}
          {!media && onEditBody && !bodyEditing && (
            <button
              type="button"
              onClick={() => {
                setBodyDraft(asset.body || '')
                setBodyEditing(true)
              }}
              className="btn btn-secondary btn-sm px-2 py-1 text-[11px]"
            >
              Edit
            </button>
          )}

          {editHref && (
            <Link to={editHref} className="btn btn-secondary btn-sm px-2 py-1 text-[11px]">
              {asset.meta?.local ? 'Re-render' : 'Edit'}
            </Link>
          )}

          {media ? (
            <a
              href={asset.url}
              target="_blank"
              rel="noreferrer"
              className="btn btn-secondary btn-sm px-2 py-1 text-[11px]"
            >
              Preview
            </a>
          ) : (
            <button
              type="button"
              onClick={() => {
                navigator.clipboard?.writeText(asset.body || '')
              }}
              className="btn btn-secondary btn-sm px-2 py-1 text-[11px]"
            >
              Copy
            </button>
          )}

          <button
            type="button"
            onClick={() => (media ? window.open(asset.url, '_blank') : downloadText(asset))}
            className="btn btn-secondary btn-sm px-2 py-1 text-[11px]"
          >
            Download
          </button>

          <button
            type="button"
            onClick={() => onDuplicate?.(asset)}
            className="btn btn-secondary btn-sm px-2 py-1 text-[11px]"
          >
            Duplicate
          </button>

          <button
            type="button"
            onClick={() => onAttach?.(asset)}
            className="btn btn-secondary btn-sm px-2 py-1 text-[11px]"
            title="Start a post from this asset"
          >
            Use in Post
          </button>

          {/* Delete asks first — there is no undo behind it, the same rule the
              campaign itself follows. */}
          {confirming ? (
            <>
              <button
                type="button"
                onClick={() => onDelete?.(asset)}
                className="btn btn-danger btn-sm px-2 py-1 text-[11px]"
              >
                Delete
              </button>
              <button
                type="button"
                onClick={() => setConfirming(false)}
                className="btn btn-ghost btn-sm px-2 py-1 text-[11px]"
              >
                Keep
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={() => setConfirming(true)}
              className="btn btn-ghost btn-sm px-2 py-1 text-[11px]"
            >
              Delete
            </button>
          )}
        </div>
      </div>
    </article>
  )
}
