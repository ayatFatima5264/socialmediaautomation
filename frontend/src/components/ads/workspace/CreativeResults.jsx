import { useState } from 'react'

// ---------------------------------------------------------------------------
// Generated creatives, and the one honest thing a grid of AI images must do:
// survive an image that does not load.
//
// The image endpoints hand back URLs on third-party hosts. Those hosts
// rate-limit, time out, and occasionally return an error page with a 200. A
// plain <img> grid answers all of that with a broken-image icon and no
// explanation, so each tile tracks its own load state and says what happened.
//
// Selection is local to the grid: the chosen tile is what the rail's Download
// acts on, so a user comparing four versions downloads the one they are
// looking at rather than the first one generated.
// ---------------------------------------------------------------------------

/**
 * Was this image generated, or substituted?
 *
 * The image chain falls back to a keyword-matched stock photo when the AI host
 * rate-limits or errors. That photo is perfectly usable — but it is not a
 * generated creative, and the difference has to be visible or the user comes to
 * believe generation is working when it is not.
 */
function sourceBadge(source) {
  if (!source) return null
  if (source.startsWith('pollinations')) return null // generated — the norm, no badge
  if (source === 'loremflickr') return 'Stock photo'
  if (source === 'picsum') return 'Placeholder'
  return source
}

function Tile({ src, label, source, selected, onSelect }) {
  const [state, setState] = useState('loading')
  const badge = sourceBadge(source)

  return (
    <button
      type="button"
      onClick={() => onSelect?.(src)}
      className={`group relative block overflow-hidden rounded-xl border-2 text-left transition ${
        selected ? 'border-accent' : 'border-line hover:border-accent-line'
      }`}
    >
      <div className="relative aspect-square w-full bg-inset">
        {state !== 'error' && (
          <img
            src={src}
            alt={label || 'Generated creative'}
            loading="lazy"
            onLoad={() => setState('ok')}
            onError={() => setState('error')}
            className={`h-full w-full object-cover transition-opacity ${
              state === 'ok' ? 'opacity-100' : 'opacity-0'
            }`}
          />
        )}

        {state === 'loading' && (
          <div className="absolute inset-0 grid place-items-center">
            <span className="skeleton h-full w-full" />
          </div>
        )}

        {badge && state !== 'error' && (
          <span className="absolute left-2 top-2 rounded-md bg-amber-500/90 px-1.5 py-0.5 text-[10px] font-bold text-white shadow-sm">
            {badge}
          </span>
        )}

        {state === 'error' && (
          <div className="absolute inset-0 grid place-items-center p-3 text-center">
            <span className="text-xs leading-relaxed text-muted">
              This one didn&apos;t load — the image host may be rate-limiting. Generate
              again.
            </span>
          </div>
        )}
      </div>

      {label && (
        <span className="block truncate border-t border-line px-2.5 py-1.5 text-[11px] font-medium text-body">
          {label}
        </span>
      )}
    </button>
  )
}

export default function CreativeResults({
  images,
  labels = [],
  sources = [],
  selected,
  onSelect,
  columns = 2,
}) {
  if (!images?.length) return null

  return (
    <div
      className={`grid gap-3 ${columns === 3 ? 'sm:grid-cols-3' : 'sm:grid-cols-2'}`}
    >
      {images.map((src, i) => (
        <Tile
          key={`${src}-${i}`}
          src={src}
          label={labels[i]}
          source={sources[i]}
          selected={selected === src}
          onSelect={onSelect}
        />
      ))}
    </div>
  )
}
