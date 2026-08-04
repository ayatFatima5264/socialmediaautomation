// ---------------------------------------------------------------------------
// The Media Library's storage layer.
//
// Two libraries, one interface:
//
//   default — the curated set shipped in /public/media-library. Read-only,
//             identical for every user, served as static files so it costs
//             nothing and survives every deploy.
//   user    — "My Library". Held in IndexedDB, so uploads persist across
//             sessions with no backend and no storage bill.
//
// Both implement the same `MediaProvider` shape, and `mediaStore` merges them.
// Everything above this file — the grid, the search, the AI's chooser, the
// editor's Replace panel — talks only to `mediaStore` and never knows which
// library an image came from beyond its `scope` field.
//
// That indirection is the point. Swapping IndexedDB for cloud storage later
// means writing one more provider with these five methods and handing it to
// `mediaStore`; no UI and no business logic changes. The asset shape is
// deliberately storage-agnostic for the same reason: consumers read
// `asset.url`, never a path or a blob key.
//
// The asset shape:
//   { id, scope, url, thumbUrl, title, categories[], industries[], tags[],
//     keywords[], width, height, orientation, colors[], isFavorite,
//     lastUsedAt, useCount, source, createdAt }
//
// ---------------------------------------------------------------------------
// Moving the images to external storage
// ---------------------------------------------------------------------------
//
// The files currently ship in /public, which is right while the library is a
// fixed application asset. Two seams exist so that stops being a decision the
// rest of the app is built on:
//
//   1. Where the shipped files live is `VITE_MEDIA_BASE_URL`. The manifest
//      stores relative keys ("full/ab12.webp"), never absolute paths, so
//      pointing that at an R2 / S3 / Vercel Blob / CDN origin moves all 512
//      images with a deploy-time setting and no re-import. A manifest entry
//      that is already an absolute URL is passed through untouched, so a
//      future export can also emit per-asset CDN URLs.
//
//   2. Who serves a scope is `setMediaProvider(scope, provider)`. Uploads move
//      off the device by registering a provider that talks to the bucket or
//      the backend; nothing above this file changes, because ids stay
//      "<scope>:<key>" and writes are routed by the provider's `writable`
//      flag rather than by any assumption about where the bytes are.
//
// A MediaProvider implements:
//   scope     string, matching the id prefix it issues
//   writable  boolean — false means update/remove/markUsed are refused here
//   list()    → Promise<asset[]>
//   add(file, opts)      → Promise<{ asset, duplicate }>   (writable only)
//   update(id, patch)    → Promise<asset|null>             (writable only)
//   remove(id)           → Promise<void>                   (writable only)
//
// One constraint a remote origin inherits: the editor rasterizes through a
// canvas and loads artwork with crossOrigin="anonymous", and `assetToFile`
// fetches the bytes back. Both need the bucket to send permissive CORS headers
// or images will load but fail to export.
// ---------------------------------------------------------------------------

const DB_NAME = 'autosocial-media'
const DB_VERSION = 1
const STORE = 'assets'

// Where the shipped library and its manifest live. Same shape as VITE_API_URL
// in lib/api: blank means "served from this origin", set means "somewhere
// else entirely". The trailing slash is stripped so both spellings work.
const DEFAULT_BASE = (import.meta.env.VITE_MEDIA_BASE_URL || '/media-library').replace(/\/+$/, '')
const DEFAULT_MANIFEST =
  import.meta.env.VITE_MEDIA_MANIFEST_URL || `${DEFAULT_BASE}/index.json`

/**
 * A manifest key resolved to something the browser can fetch.
 *
 * Keys are relative by design — that is what lets the whole library move
 * origins — but anything already absolute (a signed CDN URL, a blob or data
 * URL) is left exactly as it is.
 */
export function mediaUrl(key) {
  if (!key) return ''
  return /^(https?:|blob:|data:|\/\/)/i.test(key) ? key : `${DEFAULT_BASE}/${key}`
}

export const SCOPE_DEFAULT = 'default'
export const SCOPE_USER = 'user'

export const ORIENTATIONS = ['landscape', 'portrait', 'square']

/** Orientation from pixel dimensions. Square gets a tolerance — a 1000x1004 */
/*  photo is square to everyone except a strict equality check. */
export function orientationOf(width, height) {
  if (!width || !height) return 'landscape'
  const ratio = width / height
  if (ratio > 1.05) return 'landscape'
  if (ratio < 0.95) return 'portrait'
  return 'square'
}

// ---------------------------------------------------------------------------
// Default library — static files, read-only
// ---------------------------------------------------------------------------

class DefaultLibraryProvider {
  constructor() {
    this.scope = SCOPE_DEFAULT
    this.writable = false
    this._cache = null
  }

  // Fetched once per page load and held. The manifest is a static file behind
  // the CDN, so re-reading it per keystroke would be wasteful, not expensive.
  async _load() {
    if (this._cache) return this._cache
    try {
      const res = await fetch(DEFAULT_MANIFEST, { cache: 'force-cache' })
      if (!res.ok) throw new Error(String(res.status))
      const data = await res.json()
      this._cache = (data.assets || []).map((a) => ({
        ...a,
        id: `${SCOPE_DEFAULT}:${a.file}`,
        scope: SCOPE_DEFAULT,
        url: mediaUrl(a.file),
        // The grid must never reach for the full-size file. At ~170KB each,
        // rendering a few hundred tiles from `url` would pull tens of
        // megabytes to show thumbnails; the import writes a 400px version
        // for exactly this.
        thumbUrl: mediaUrl(a.thumb || a.file),
        orientation: a.orientation || orientationOf(a.width, a.height),
        isFavorite: false,
        source: 'default',
      }))
    } catch {
      // No manifest yet is the normal state before the first import, not an
      // error worth surfacing — My Library still works.
      this._cache = []
    }
    return this._cache
  }

  async list() {
    return this._load()
  }
}

// ---------------------------------------------------------------------------
// My Library — IndexedDB, read/write
// ---------------------------------------------------------------------------

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE)) {
        const os = db.createObjectStore(STORE, { keyPath: 'id' })
        // Duplicate detection: the same bytes are stored once.
        os.createIndex('hash', 'hash', { unique: true })
        os.createIndex('createdAt', 'createdAt')
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

const tx = async (mode, fn) => {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const t = db.transaction(STORE, mode)
    const store = t.objectStore(STORE)
    let out
    try {
      out = fn(store)
    } catch (err) {
      reject(err)
      return
    }
    t.oncomplete = () => resolve(out?.result ?? out)
    t.onerror = () => reject(t.error)
  })
}

const request = (req) =>
  new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })

/** SHA-256 of the file's bytes, so re-uploading a picture is a no-op. */
async function hashBlob(blob) {
  const buf = await blob.arrayBuffer()
  const digest = await crypto.subtle.digest('SHA-256', buf)
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

/** Natural dimensions and a small dominant-colour sample, read from the blob. */
async function inspect(blob) {
  const url = URL.createObjectURL(blob)
  try {
    const img = await new Promise((resolve, reject) => {
      const el = new Image()
      el.onload = () => resolve(el)
      el.onerror = reject
      el.src = url
    })
    const { naturalWidth: width, naturalHeight: height } = img

    // Colours are sampled from a tiny downscale — enough to rank the palette,
    // cheap enough to run on upload without blocking.
    let colors = []
    try {
      const c = document.createElement('canvas')
      c.width = 16
      c.height = 16
      const ctx = c.getContext('2d', { willReadFrequently: true })
      ctx.drawImage(img, 0, 0, 16, 16)
      const { data } = ctx.getImageData(0, 0, 16, 16)
      const buckets = new Map()
      for (let i = 0; i < data.length; i += 4) {
        if (data[i + 3] < 128) continue
        // Quantised to 32 levels: exact pixel values would give 256 unique
        // "colours" for what the eye reads as one.
        const key = [data[i], data[i + 1], data[i + 2]]
          .map((v) => Math.round(v / 32) * 32)
          .join(',')
        buckets.set(key, (buckets.get(key) || 0) + 1)
      }
      colors = [...buckets.entries()]
        .sort((a, b) => b[1] - a[1])
        .slice(0, 4)
        .map(([k]) => {
          const [r, g, b] = k.split(',').map(Number)
          return `#${[r, g, b].map((v) => Math.min(255, v).toString(16).padStart(2, '0')).join('')}`
        })
    } catch {
      /* canvas unavailable — colours are a nicety, not a requirement */
    }

    return { width, height, orientation: orientationOf(width, height), colors }
  } finally {
    URL.revokeObjectURL(url)
  }
}

class IndexedDbProvider {
  constructor() {
    this.scope = SCOPE_USER
    this.writable = true
    // Object URLs are minted per record and revoked on replace/delete, so a
    // long session does not leak one blob URL per scroll.
    this._urls = new Map()
  }

  _decorate(row) {
    let url = this._urls.get(row.id)
    if (!url) {
      url = URL.createObjectURL(row.blob)
      this._urls.set(row.id, url)
    }
    const { blob, ...rest } = row
    // An upload has no separate thumbnail — the object URL is already local,
    // so there is nothing to save by generating one. The field exists so
    // consumers can read `thumbUrl` without caring which library they are in.
    return { ...rest, scope: SCOPE_USER, url, thumbUrl: url }
  }

  _release(id) {
    const url = this._urls.get(id)
    if (url) {
      URL.revokeObjectURL(url)
      this._urls.delete(id)
    }
  }

  async list() {
    const rows = await tx('readonly', (s) => s.getAll())
    return (rows || []).map((r) => this._decorate(r))
  }

  /**
   * Store a file. Returns the existing asset when the same bytes are already
   * held, so "upload" is safely idempotent — the user re-picking a photo they
   * already have gets their original back rather than a second copy.
   */
  async add(file, { title, source = 'upload', tags, categories } = {}) {
    const hash = await hashBlob(file)

    const existing = await tx('readonly', (s) => s.index('hash').get(hash))
    if (existing) return { asset: this._decorate(existing), duplicate: true }

    const meta = await inspect(file)
    const row = {
      id: `user:${hash.slice(0, 16)}`,
      hash,
      blob: file,
      title: title || file.name?.replace(/\.[^.]+$/, '') || 'Untitled',
      categories: categories || [],
      industries: [],
      tags: tags || [],
      keywords: [],
      ...meta,
      byteSize: file.size,
      mimeType: file.type || 'image/jpeg',
      isFavorite: false,
      lastUsedAt: null,
      useCount: 0,
      source,
      createdAt: new Date().toISOString(),
    }
    await tx('readwrite', (s) => s.put(row))
    return { asset: this._decorate(row), duplicate: false }
  }

  async update(id, patch) {
    const row = await tx('readonly', (s) => s.get(id))
    if (!row) return null
    // `blob`, `hash` and `id` are identity — a rename must not be able to
    // rewrite which bytes a record points at.
    const { blob, hash, id: _id, ...safe } = patch || {}
    const next = { ...row, ...safe }
    await tx('readwrite', (s) => s.put(next))
    return this._decorate(next)
  }

  async remove(id) {
    await tx('readwrite', (s) => s.delete(id))
    this._release(id)
  }
}

// ---------------------------------------------------------------------------
// The facade every consumer uses
// ---------------------------------------------------------------------------

const providers = {
  [SCOPE_DEFAULT]: new DefaultLibraryProvider(),
  [SCOPE_USER]: new IndexedDbProvider(),
}

/**
 * Replace the implementation backing a scope.
 *
 * The migration path off this device: write a provider that talks to the
 * bucket or the backend, register it here at startup, and every consumer keeps
 * working — they only ever asked `mediaStore` for assets. Swapping the default
 * scope is how a hosted, per-tenant stock library would arrive; swapping the
 * user scope is how uploads stop being browser-local.
 */
export function setMediaProvider(scope, provider) {
  if (!provider || typeof provider.list !== 'function') {
    throw new Error('A media provider must implement list()')
  }
  providers[scope] = provider
}

/**
 * The provider that issued an id.
 *
 * Ids are "<scope>:<key>", so routing is a lookup rather than a guess about
 * storage. The previous check — does the id start with "user:" — hardcoded
 * both the scope and the assumption that only IndexedDB is ever writable.
 */
function providerFor(id) {
  const scope = String(id || '').split(':')[0]
  return providers[scope] || null
}

/** The provider for a write, or null when the target refuses writes. */
function writableFor(id) {
  const provider = providerFor(id)
  return provider?.writable ? provider : null
}

const norm = (v) => String(v || '').toLowerCase()

/**
 * Does an asset satisfy the active filters?
 *
 * Exported because the browser holds its assets in memory and re-filters as
 * the user types. Going back to `list()` per keystroke would re-read IndexedDB
 * for a result that cannot have changed — and a second implementation of this
 * in the UI is exactly how a search box drifts from what the store considers a
 * match.
 */
export function assetMatches(asset, { search, category, industry, tag, orientation, favorites } = {}) {
  if (orientation && asset.orientation !== orientation) return false
  if (favorites && !asset.isFavorite) return false
  if (category && !(asset.categories || []).some((c) => norm(c) === norm(category))) return false
  if (industry && !(asset.industries || []).some((c) => norm(c) === norm(industry))) return false
  if (tag && !(asset.tags || []).some((c) => norm(c) === norm(tag))) return false

  const q = norm(search).trim()
  if (!q) return true
  const haystack = [
    asset.title,
    ...(asset.categories || []),
    ...(asset.industries || []),
    ...(asset.tags || []),
    ...(asset.keywords || []),
  ]
    .filter(Boolean)
    .map(norm)
  return q.split(/\s+/).every((word) => haystack.some((h) => h.includes(word)))
}

export const mediaStore = {
  /**
   * Assets from one or both libraries, filtered and sorted.
   *
   * My Library is returned before the default set: a picture the user chose to
   * keep is a stronger signal than one that shipped with the app, and the same
   * ordering is what the AI chooser wants.
   */
  async list({ scope, sort = 'recent', ...filters } = {}) {
    const scopes = scope ? [scope] : [SCOPE_USER, SCOPE_DEFAULT]
    const groups = await Promise.all(scopes.map((s) => providers[s].list()))

    const out = []
    groups.forEach((assets) => {
      out.push(...assets.filter((a) => assetMatches(a, filters)))
    })

    if (sort === 'used') {
      out.sort((a, b) => (b.lastUsedAt || '').localeCompare(a.lastUsedAt || ''))
    } else if (sort === 'recent') {
      // Scope order is already the primary ranking; keep it and sort within.
      out.sort((a, b) => {
        if (a.scope !== b.scope) return a.scope === SCOPE_USER ? -1 : 1
        return (b.createdAt || '').localeCompare(a.createdAt || '')
      })
    }
    return out
  },

  /**
   * Save a file to My Library. Idempotent on content.
   *
   * Uploads go to whichever provider owns the user scope, so moving them to a
   * bucket is a `setMediaProvider` call and not an edit here.
   */
  add(file, opts) {
    const provider = providers[SCOPE_USER]
    if (!provider?.writable) throw new Error('This library does not accept uploads')
    return provider.add(file, opts)
  },

  /** Rename / favourite / re-tag. Read-only libraries refuse, returning null. */
  async update(id, patch) {
    const provider = writableFor(id)
    if (!provider) return null
    return provider.update(id, patch)
  },

  async remove(id) {
    const provider = writableFor(id)
    if (!provider) return
    return provider.remove(id)
  },

  /**
   * Record that an asset was placed in a design — powers "Recently used" and
   * lets the chooser prefer what this user actually reaches for.
   *
   * Only a writable library can keep counters: the shipped set is shared and
   * read-only, so per-user usage there has nowhere to live until a provider
   * with a backend behind it owns that scope.
   */
  async markUsed(id) {
    const provider = writableFor(id)
    if (!provider) return null
    const row = await provider.update(id, {})
    if (!row) return null
    return provider.update(id, {
      lastUsedAt: new Date().toISOString(),
      useCount: (row.useCount || 0) + 1,
    })
  },

  /**
   * Can anything be added right now?
   *
   * Asked by the UI so the Upload affordances disappear on their own if the
   * user scope is ever served by a read-only provider — rather than offering a
   * button that fails once pressed.
   */
  get canUpload() {
    return !!providers[SCOPE_USER]?.writable
  },

  /** Every category present across both libraries, for the filter chips. */
  async facets() {
    return facetsOf(await this.list({}))
  },
}

/**
 * The filter values actually present in a set of assets.
 *
 * Derived rather than declared: a chip for a category no image carries is a
 * dead end, and one missing for a category several carry hides them. Callers
 * that already hold the assets pass them straight in.
 */
export function facetsOf(assets) {
  // Keyed by the normalised value so "SaaS" and "saas" collapse, but the
  // first-seen spelling is what gets shown.
  const collect = (key) => {
    const found = new Map()
    assets.forEach((a) => (a[key] || []).forEach((v) => found.set(norm(v), v)))
    return [...found.values()].sort((a, b) => a.localeCompare(b))
  }
  return {
    categories: collect('categories'),
    industries: collect('industries'),
    tags: collect('tags'),
  }
}

/**
 * An asset's bytes, as a File.
 *
 * Every surface that already accepts an image takes a File from an <input
 * type="file">: the editor's Replace, the planner's swap, the generator's
 * upload. Handing one back means the library becomes another source for those
 * paths instead of a second code route beside them — and it resolves the
 * scope difference that would otherwise leak upward, since a user asset's
 * `url` is an object URL that cannot be persisted and a default asset's is a
 * static path that can.
 */
export async function assetToFile(asset) {
  if (!asset?.url) throw new Error('That image has no source file')
  const res = await fetch(asset.url)
  if (!res.ok) throw new Error(`Could not read ${asset.title || 'that image'}`)
  const blob = await res.blob()
  const type = blob.type || 'image/webp'
  const ext = (type.split('/')[1] || 'webp').replace('jpeg', 'jpg')
  const stem =
    String(asset.title || 'image')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '') || 'image'
  return new File([blob], `${stem}.${ext}`, { type })
}

export default mediaStore
