import { useState } from 'react'
import MediaBrowser from '../components/media/MediaBrowser.jsx'
import HelpTip from '../components/HelpTip.jsx'
import { SCOPE_USER } from '../lib/media/store'

// ---------------------------------------------------------------------------
// The Media Library as a destination.
//
// The picker modal answers "which image for this post?". This page answers the
// questions that have nowhere else to live: what is in my library, what did
// that upload get called, and get rid of the one I added twice. Same browser
// component, so the two cannot show different libraries.
//
// Selecting a tile here opens the details strip rather than choosing anything —
// there is no post waiting for an answer.
// ---------------------------------------------------------------------------

function DetailRow({ label, children }) {
  if (!children) return null
  return (
    <div className="flex gap-2">
      <dt className="w-24 shrink-0 text-xs font-semibold text-muted">{label}</dt>
      <dd className="min-w-0 flex-1 text-xs">{children}</dd>
    </div>
  )
}

export default function MediaLibrary() {
  const [selected, setSelected] = useState(null)

  return (
    <div className="mx-auto max-w-6xl space-y-3 pb-4">
      <header className="flex items-center gap-2">
        <h1 className="text-lg font-bold">Media Library</h1>
        <HelpTip label="About the Media Library">
          Every image you can drop into a design. <strong>Stock</strong> is the set that ships with
          AutoSocial AI, already sorted by category. <strong>My Library</strong> is yours — uploads
          are kept in this browser, so they stay on this device and are never sent anywhere until
          you put one in a post.
        </HelpTip>
      </header>

      <div className="card p-3 sm:p-4">
        <MediaBrowser
          fill={false}
          manage
          selectedId={selected?.id}
          onSelect={(asset) => setSelected((prev) => (prev?.id === asset.id ? null : asset))}
        />
      </div>

      {/* Details for the selected image. Below the grid rather than in a rail:
          on a phone a side panel would push the grid to a single column, and
          this is reference material, not a control surface. */}
      {selected && (
        <div className="card flex flex-col gap-4 p-3 sm:flex-row sm:p-4">
          <img
            src={selected.thumbUrl || selected.url}
            alt=""
            className="h-32 w-32 shrink-0 rounded-lg object-cover"
          />
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline gap-2">
              <h2 className="min-w-0 truncate text-sm font-bold">
                {selected.title || 'Untitled'}
              </h2>
              <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wide text-muted">
                {selected.scope === SCOPE_USER ? 'My Library' : 'Stock'}
              </span>
            </div>
            <dl className="mt-2 space-y-1">
              <DetailRow label="Size">
                {selected.width
                  ? `${selected.width} × ${selected.height} px · ${selected.orientation}`
                  : selected.orientation}
              </DetailRow>
              <DetailRow label="Categories">{(selected.categories || []).join(', ')}</DetailRow>
              <DetailRow label="Tags">{(selected.tags || []).join(', ')}</DetailRow>
              <DetailRow label="Colours">
                {selected.colors?.length ? (
                  <span className="flex flex-wrap gap-1">
                    {selected.colors.map((c) => (
                      <span
                        key={c}
                        title={c}
                        style={{ background: c }}
                        className="h-4 w-4 rounded border border-line"
                      />
                    ))}
                  </span>
                ) : null}
              </DetailRow>
            </dl>
            <div className="mt-3 flex flex-wrap gap-2">
              <a
                href={selected.url}
                target="_blank"
                rel="noreferrer"
                className="btn btn-secondary btn-sm"
              >
                Open full size
              </a>
              <a
                href={selected.url}
                download={`${(selected.title || 'image').replace(/[^\w-]+/g, '-').toLowerCase()}.webp`}
                className="btn btn-ghost btn-sm"
              >
                ⬇ Download
              </a>
              <button type="button" onClick={() => setSelected(null)} className="btn btn-ghost btn-sm">
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
