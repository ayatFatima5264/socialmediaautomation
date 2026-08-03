// ---------------------------------------------------------------------------
// Blog module used by the app. The article metadata itself lives in
// ./posts.data.js — a dependency-free module with no Vite-specific syntax, so
// the build-time SEO plugin (sitemap, prerender) can import the exact same
// list Node-side. One source of truth for routes, sitemap, and UI.
// ---------------------------------------------------------------------------

import { CATEGORIES, POSTS } from './posts.data.js'

export { CATEGORIES, POSTS }

// ---- Draft handling -------------------------------------------------------
// Unpublished articles are NOT in this module's data at all — they live in
// ./drafts.data.js, which only the build-time guard imports. That means draft
// titles and descriptions never reach the client bundle, and there is no
// runtime filter that could be forgotten at a call site: POSTS *is* the
// published set.
export const POSTS_BY_DATE = [...POSTS].sort((a, b) => b.date.localeCompare(a.date))

// Only categories that actually have a published article, so the blog filter
// never renders a pill with a count of zero.
export const ACTIVE_CATEGORIES = CATEGORIES.filter((c) =>
  POSTS.some((p) => p.category === c),
)

// Unknown or unpublished slug → null, so the article route renders the 404
// page (which carries noindex) rather than an unlisted preview.
export function getPost(slug) {
  return POSTS.find((p) => p.slug === slug) || null
}

// Related posts: same category first, then fill from the newest remaining.
export function getRelated(slug, limit = 3) {
  const current = getPost(slug)
  if (!current) return []
  const others = POSTS_BY_DATE.filter((p) => p.slug !== slug)
  const sameCategory = others.filter((p) => p.category === current.category)
  const rest = others.filter((p) => p.category !== current.category)
  return [...sameCategory, ...rest].slice(0, limit)
}

// ---- Lazy body loading ----------------------------------------------------
// Vite turns each Markdown file into its own async chunk. `bodyLoaders` maps a
// slug to a promise for that article's raw Markdown.
//
// The glob only covers ./posts/ — unpublished article bodies live in
// ./drafts/, deliberately outside it. This is not cosmetic: the glob is
// resolved at build time and cannot filter on a runtime `draft` flag, so a
// draft left in posts/ would be bundled and served from the CDN even though
// nothing links to it. The build fails if a file is in the wrong directory
// (see plugins/seo.js), so the flag and the location cannot drift apart.
const modules = import.meta.glob('./posts/*.md', { query: '?raw', import: 'default' })

const bodyLoaders = Object.fromEntries(
  Object.entries(modules).map(([path, load]) => [
    path.replace('./posts/', '').replace('.md', ''),
    load,
  ]),
)

export function loadPostBody(slug) {
  const load = bodyLoaders[slug]
  return load ? load() : Promise.reject(new Error(`No article body for "${slug}"`))
}

// Human-readable date for cards and article headers.
export function formatPostDate(iso) {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    timeZone: 'UTC',
  })
}
