import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { SITE } from '../config/site'
import { isPrivatePath, pageSeo, privatePageTitle } from '../seo/pages.data.js'

// ---------------------------------------------------------------------------
// Dependency-free SEO head manager for our Vite SPA. Renders no DOM of its own;
// on mount / prop change it upserts <title>, meta, canonical, and JSON-LD tags
// into <head>, then restores the previous state on unmount so pages don't leak
// each other's metadata. Add <Seo .../> at the top of every public page.
// ---------------------------------------------------------------------------

// Upsert <meta name=".."> or <meta property=".."> and return a cleanup fn.
function upsertMeta(attr, key, content) {
  if (content == null) return () => {}
  let el = document.head.querySelector(`meta[${attr}="${key}"]`)
  const created = !el
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute(attr, key)
    document.head.appendChild(el)
  }
  const prev = el.getAttribute('content')
  el.setAttribute('content', content)
  return () => {
    if (created) el.remove()
    else if (prev != null) el.setAttribute('content', prev)
  }
}

function upsertLink(rel, href) {
  if (!href) return () => {}
  let el = document.head.querySelector(`link[rel="${rel}"]`)
  const created = !el
  if (!el) {
    el = document.createElement('link')
    el.setAttribute('rel', rel)
    document.head.appendChild(el)
  }
  const prev = el.getAttribute('href')
  el.setAttribute('href', href)
  return () => {
    if (created) el.remove()
    else if (prev != null) el.setAttribute('href', prev)
  }
}

export default function Seo({
  title,
  description,
  image = SITE.ogImage,
  type = 'website',
  noindex = false,
  jsonLd,
}) {
  const { pathname } = useLocation()

  // Marketing routes take their title and description from the shared registry
  // in seo/pages.data.js — the same module the build-time prerenderer reads.
  // That is what guarantees the tags a JS-capable crawler sees at runtime are
  // identical to the ones baked into the static HTML. Explicit props still win,
  // which is how dynamic pages (blog articles) supply their own.
  const registry = pageSeo(pathname)
  // Private routes are never prerendered, so the host answers them with the
  // noindex 404 shell and its "Page Not Found" title. Naming them here is what
  // stops that title surviving into a page that rendered perfectly well. They
  // are also forced noindex, matching the robots.txt Disallow they already
  // carry — a private page should never be indexable by accident.
  // Asked per rendered path rather than matched against a flat list, so nested
  // module routes (/ads/carousel-ads, /ads/campaigns/42) are covered too.
  const privateTitle = privatePageTitle(pathname)
  const isPrivate = isPrivatePath(pathname)

  const resolvedTitle =
    title !== undefined ? title : registry?.title ?? privateTitle ?? null
  const resolvedDescription = description ?? registry?.description ?? SITE.description
  const resolvedNoindex = noindex || isPrivate

  const fullTitle = resolvedTitle
    ? `${resolvedTitle} — ${SITE.name}`
    : `${SITE.name} — ${SITE.tagline}`

  // Canonical must never include query strings or hashes — those create
  // duplicate-content variants that dilute the page in search results.
  const canonical = `${SITE.url}${pathname === '/' ? '/' : pathname.replace(/\/$/, '')}`

  useEffect(() => {
    const prevTitle = document.title
    document.title = fullTitle

    const cleanups = [
      upsertMeta('name', 'description', resolvedDescription),
      upsertMeta('name', 'robots', resolvedNoindex ? 'noindex, nofollow' : 'index, follow'),
      upsertLink('canonical', canonical),
      // Open Graph
      upsertMeta('property', 'og:type', type),
      upsertMeta('property', 'og:site_name', SITE.name),
      upsertMeta('property', 'og:title', fullTitle),
      upsertMeta('property', 'og:description', resolvedDescription),
      upsertMeta('property', 'og:url', canonical),
      upsertMeta('property', 'og:image', image),
      upsertMeta('property', 'og:locale', SITE.locale),
      // Twitter
      upsertMeta('name', 'twitter:card', 'summary_large_image'),
      upsertMeta('name', 'twitter:site', SITE.twitter),
      upsertMeta('name', 'twitter:title', fullTitle),
      upsertMeta('name', 'twitter:description', resolvedDescription),
      upsertMeta('name', 'twitter:image', image),
    ]

    // Structured data (JSON-LD).
    let scriptEl
    if (jsonLd) {
      scriptEl = document.createElement('script')
      scriptEl.type = 'application/ld+json'
      scriptEl.textContent = JSON.stringify(jsonLd)
      document.head.appendChild(scriptEl)
    }

    return () => {
      document.title = prevTitle
      cleanups.forEach((fn) => fn())
      if (scriptEl) scriptEl.remove()
    }
  }, [fullTitle, resolvedDescription, image, type, resolvedNoindex, canonical, jsonLd])

  return null
}
