import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useToast } from '../../context/ToastContext.jsx'
import mediaStore, {
  ORIENTATIONS,
  SCOPE_DEFAULT,
  SCOPE_USER,
  assetMatches,
  facetsOf,
} from '../../lib/media/store'

// ---------------------------------------------------------------------------
// Browsing and searching the Media Library.
//
// One component, two surfaces: the picker modal and the /media page. They
// differ only in what a tile click means and whether the managing controls
// appear, so they share this rather than growing two grids that drift apart.
//
// Assets are loaded once and filtered in memory. The library is a few hundred
// images — small enough that a round trip to IndexedDB per keystroke would buy
// nothing and cost a visibly laggy search box. `assetMatches` comes from the
// store so "what counts as a match" has exactly one definition.
// ---------------------------------------------------------------------------

const SCOPE_TABS = [
  { key: '', label: 'All' },
  { key: SCOPE_USER, label: 'My Library' },
  { key: SCOPE_DEFAULT, label: 'Stock' },
]

// Which facet the chip row is currently showing. Same pattern as the template
// library: one row of chips, a tab to say which axis it filters on — a page
// with every axis expanded at once is unreadable on a phone.
const FACET_TABS = [
  { key: 'category', label: 'Category' },
  { key: 'tag', label: 'Tag' },
  { key: 'orientation', label: 'Shape' },
]

function Chip({ active, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`shrink-0 rounded-full border px-3 py-1 text-xs font-semibold capitalize transition ${
        active
          ? 'border-accent bg-accent text-accent-contrast'
          : 'border-line text-muted hover:border-accent-line hover:text-body'
      }`}
    >
      {children}
    </button>
  )
}

function AssetTile({ asset, selected, onSelect, onActivate, manage, onFavorite, onDelete, onRename }) {
  const [renaming, setRenaming] = useState(false)
  const [draft, setDraft] = useState(asset.title || '')
  const mine = asset.scope === SCOPE_USER

  function commitRename() {
    // Enter commits and then blurs, which would otherwise commit a second time
    // against a title the reload has not caught up with yet.
    if (!renaming) return
    setRenaming(false)
    const next = draft.trim()
    if (next && next !== asset.title) onRename(asset, next)
    else setDraft(asset.title || '')
  }

  return (
    <div
      className={`group relative overflow-hidden rounded-xl border-2 transition ${
        selected ? 'border-accent shadow-md' : 'border-line hover:border-accent-line hover:shadow-sm'
      }`}
    >
      <button
        type="button"
        onClick={() => onSelect?.(asset)}
        onDoubleClick={() => onActivate?.(asset)}
        aria-pressed={selected}
        aria-label={asset.title || 'Untitled image'}
        className="block w-full"
      >
        {/* Square stage with a cover crop: a grid of mixed aspect ratios that
            each keep their own shape reads as broken rather than varied. The
            tile is a crop; the asset itself is never altered. */}
        <div className="aspect-square bg-inset">
          <img
            src={asset.thumbUrl || asset.url}
            alt=""
            loading="lazy"
            decoding="async"
            className="h-full w-full object-cover"
          />
        </div>
      </button>

      {selected && (
        <span
          className="pointer-events-none absolute left-2 top-2 grid h-6 w-6 place-items-center rounded-full bg-accent text-xs font-bold text-accent-contrast shadow"
          aria-hidden="true"
        >
          ✓
        </span>
      )}

      {/* Managing controls sit on the tile and appear on hover or keyboard
          focus. Only My Library assets get them — the stock set is shared and
          read-only, so a delete button there would be a lie. */}
      {manage && mine && (
        <div className="absolute right-1.5 top-1.5 flex gap-1 opacity-0 transition group-hover:opacity-100 group-focus-within:opacity-100">
          <button
            type="button"
            onClick={() => onFavorite(asset)}
            title={asset.isFavorite ? 'Remove from favourites' : 'Add to favourites'}
            className="grid h-7 w-7 place-items-center rounded-full bg-black/60 text-xs text-white backdrop-blur transition hover:bg-black/80"
          >
            {asset.isFavorite ? '★' : '☆'}
          </button>
          <button
            type="button"
            onClick={() => {
              setDraft(asset.title || '')
              setRenaming(true)
            }}
            title="Rename"
            className="grid h-7 w-7 place-items-center rounded-full bg-black/60 text-xs text-white backdrop-blur transition hover:bg-black/80"
          >
            ✎
          </button>
          <button
            type="button"
            onClick={() => onDelete(asset)}
            title="Delete from My Library"
            className="grid h-7 w-7 place-items-center rounded-full bg-black/60 text-xs text-white backdrop-blur transition hover:bg-rose-600"
          >
            ✕
          </button>
        </div>
      )}

      {/* A favourite stays visible without hovering — it is the asset's state,
          not a control. */}
      {asset.isFavorite && (
        <span className="pointer-events-none absolute bottom-[3.1rem] right-2 text-sm text-amber-400 drop-shadow">
          ★
        </span>
      )}

      <div className="min-w-0 border-t border-line px-2 py-1.5">
        {renaming ? (
          <input
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commitRename}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitRename()
              if (e.key === 'Escape') {
                setDraft(asset.title || '')
                setRenaming(false)
              }
            }}
            aria-label="Image name"
            className="input h-7 w-full px-1.5 py-0 text-xs"
          />
        ) : (
          <div className="truncate text-xs font-semibold" title={asset.title}>
            {asset.title || 'Untitled'}
          </div>
        )}
        <div className="truncate text-[10px] text-muted">
          {asset.width && asset.height ? `${asset.width}×${asset.height}` : asset.orientation}
          {asset.scope === SCOPE_DEFAULT ? ' · Stock' : ' · Mine'}
        </div>
      </div>
    </div>
  )
}

export default function MediaBrowser({
  selectedId,
  onSelect,
  onActivate,
  manage = false,
  // Who owns the scrolling. The modal gives this a fixed height and wants the
  // grid to scroll inside it; the page sits in <main>, which already scrolls —
  // nesting a second scroller there strands the controls above a short box.
  fill = true,
  className = '',
}) {
  const toast = useToast()
  const fileRef = useRef(null)
  const [assets, setAssets] = useState(null) // null = still loading
  const [scope, setScope] = useState('')
  const [search, setSearch] = useState('')
  const [facet, setFacet] = useState('category')
  const [filters, setFilters] = useState({})
  const [favoritesOnly, setFavoritesOnly] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    // Unfiltered on purpose — filtering happens below, against this array.
    mediaStore
      .list({})
      .then(setAssets)
      .catch(() => {
        toast.error('Could not open your media library')
        setAssets([])
      })
  }, [toast])

  useEffect(load, [load])

  const visible = useMemo(() => {
    if (!assets) return []
    return assets.filter(
      (a) =>
        (!scope || a.scope === scope) &&
        assetMatches(a, { search, favorites: favoritesOnly, ...filters }),
    )
  }, [assets, scope, search, favoritesOnly, filters])

  // "Nothing here yet" and "nothing matches" are different problems wanting
  // different buttons, and the difference is per scope: an untouched My Library
  // is empty however the filters are set, and clearing them would not help.
  const scopeEmpty = (assets || []).filter((a) => !scope || a.scope === scope).length === 0

  // Chips describe the scope being browsed, not the whole library: switching to
  // My Library should not offer to filter by a category only stock images have.
  const facets = useMemo(
    () => facetsOf((assets || []).filter((a) => !scope || a.scope === scope)),
    [assets, scope],
  )

  const chipValues =
    facet === 'orientation' ? ORIENTATIONS : facet === 'tag' ? facets.tags : facets.categories

  function setFilter(key, value) {
    setFilters((prev) => ({ ...prev, [key]: prev[key] === value ? undefined : value }))
  }

  function clearFilters() {
    setFilters({})
    setSearch('')
    setFavoritesOnly(false)
  }

  const activeCount = Object.values(filters).filter(Boolean).length + (favoritesOnly ? 1 : 0)

  async function upload(fileList) {
    const files = [...(fileList || [])].filter((f) => f.type?.startsWith('image/'))
    if (!files.length) {
      toast.error('Those files are not images')
      return
    }
    setBusy(true)
    let added = 0
    let duplicates = 0
    let failed = 0
    for (const file of files) {
      try {
        const { duplicate } = await mediaStore.add(file)
        if (duplicate) duplicates += 1
        else added += 1
      } catch {
        failed += 1
      }
    }
    setBusy(false)
    load()

    // Report what happened rather than a flat "uploaded": re-adding a photo you
    // already have is a no-op by design, and silently showing nothing new looks
    // like a bug.
    if (added) toast.success(`Added ${added} image${added > 1 ? 's' : ''} to My Library`)
    if (duplicates) toast.info(`${duplicates} already in your library`)
    if (failed) toast.error(`${failed} image${failed > 1 ? 's' : ''} could not be read`)
  }

  async function favorite(asset) {
    await mediaStore.update(asset.id, { isFavorite: !asset.isFavorite })
    load()
  }

  async function rename(asset, title) {
    await mediaStore.update(asset.id, { title })
    load()
  }

  async function remove(asset) {
    // Uploads live only in this browser — there is no server copy to restore
    // from, so deleting one is final and worth a confirmation.
    if (!window.confirm(`Delete "${asset.title || 'this image'}" from My Library? This cannot be undone.`)) {
      return
    }
    await mediaStore.remove(asset.id)
    toast.success('Image deleted')
    load()
  }

  return (
    <div className={`flex flex-col ${fill ? 'min-h-0 flex-1' : ''} ${className}`}>
      {/* ---- Controls ---- */}
      <div className="shrink-0 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-4 border-b border-line">
            {SCOPE_TABS.map((t) => (
              <button
                key={t.key || 'all'}
                type="button"
                onClick={() => setScope(t.key)}
                className={`-mb-px border-b-2 pb-2 text-sm font-semibold transition ${
                  scope === t.key
                    ? 'border-accent text-accent'
                    : 'border-transparent text-muted hover:text-body'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name, category or tag…"
            aria-label="Search images"
            className="input ml-auto w-full sm:w-64"
          />

          {/* Hidden rather than disabled when the library cannot take uploads:
              a provider without writes is a property of the deployment, not a
              temporary state the user can wait out. */}
          {mediaStore.canUpload && (
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={busy}
              className="btn btn-secondary btn-sm shrink-0"
            >
              {busy ? 'Adding…' : '⬆ Upload'}
            </button>
          )}
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={(e) => {
              const files = e.target.files
              e.target.value = '' // re-picking the same file must fire again
              upload(files)
            }}
          />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-3">
            {FACET_TABS.map((f) => (
              <button
                key={f.key}
                type="button"
                onClick={() => setFacet(f.key)}
                className={`text-xs font-semibold transition ${
                  facet === f.key ? 'text-accent' : 'text-muted hover:text-body'
                }`}
              >
                {f.label}
                {filters[f.key] && <span className="ml-1">•</span>}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={() => setFavoritesOnly((v) => !v)}
            aria-pressed={favoritesOnly}
            className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
              favoritesOnly
                ? 'border-accent bg-accent text-accent-contrast'
                : 'border-line text-muted hover:border-accent-line hover:text-body'
            }`}
          >
            ★ Favourites
          </button>

          {(activeCount > 0 || search) && (
            <button
              type="button"
              onClick={clearFilters}
              className="text-xs font-medium text-muted hover:text-body"
            >
              Clear filters
            </button>
          )}

          <span className="ml-auto text-xs text-muted">
            {assets === null ? 'Loading…' : `${visible.length} image${visible.length === 1 ? '' : 's'}`}
          </span>
        </div>

        {chipValues.length > 0 && (
          <div className="flex gap-2 overflow-x-auto pb-1">
            <Chip active={!filters[facet]} onClick={() => setFilter(facet, undefined)}>
              All
            </Chip>
            {chipValues.map((value) => (
              <Chip
                key={value}
                active={filters[facet] === value}
                onClick={() => setFilter(facet, value)}
              >
                {value}
              </Chip>
            ))}
          </div>
        )}
      </div>

      {/* ---- Grid ----
          Dropping anywhere over the results uploads, which is where a user
          aims when they drag a photo in. */}
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          upload(e.dataTransfer.files)
        }}
        className={`mt-3 rounded-xl transition ${
          fill ? 'min-h-0 flex-1 overflow-y-auto' : ''
        } ${dragging ? 'ring-2 ring-accent ring-offset-2 ring-offset-transparent' : ''}`}
      >
        {assets === null ? (
          <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(9rem,1fr))]">
            {Array.from({ length: 12 }).map((_, i) => (
              <div key={i} className="aspect-square animate-pulse rounded-xl bg-inset" />
            ))}
          </div>
        ) : visible.length === 0 ? (
          <div className="grid min-h-[18rem] place-items-center p-8 text-center">
            <div>
              <div className="text-3xl">🖼️</div>
              <div className="mt-3 font-medium">
                {scopeEmpty
                  ? scope === SCOPE_USER
                    ? 'My Library is empty.'
                    : 'No images here yet.'
                  : 'No images match those filters.'}
              </div>
              <p className="mx-auto mt-1 max-w-sm text-sm text-muted">
                {!scopeEmpty
                  ? 'Try a different category, or clear the filters.'
                  : mediaStore.canUpload
                    ? 'Upload your own images, or drop them anywhere in this panel. They stay in this browser.'
                    : 'Nothing has been added to this library yet.'}
              </p>
              {(!scopeEmpty || mediaStore.canUpload) && (
                <button
                  type="button"
                  onClick={scopeEmpty ? () => fileRef.current?.click() : clearFilters}
                  className="btn btn-secondary btn-sm mt-4"
                >
                  {scopeEmpty ? '⬆ Upload images' : 'Clear filters'}
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(9rem,1fr))]">
            {visible.map((asset) => (
              <AssetTile
                key={asset.id}
                asset={asset}
                selected={asset.id === selectedId}
                onSelect={onSelect}
                onActivate={onActivate}
                manage={manage}
                onFavorite={favorite}
                onRename={rename}
                onDelete={remove}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
