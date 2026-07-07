import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { SITE } from '../config/site'

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
  description = SITE.description,
  image = SITE.ogImage,
  type = 'website',
  noindex = false,
  jsonLd,
}) {
  const { pathname } = useLocation()
  const fullTitle = title ? `${title} — ${SITE.name}` : `${SITE.name} — ${SITE.tagline}`
  const canonical = `${SITE.url}${pathname}`

  useEffect(() => {
    const prevTitle = document.title
    document.title = fullTitle

    const cleanups = [
      upsertMeta('name', 'description', description),
      upsertMeta('name', 'robots', noindex ? 'noindex, nofollow' : 'index, follow'),
      upsertLink('canonical', canonical),
      // Open Graph
      upsertMeta('property', 'og:type', type),
      upsertMeta('property', 'og:site_name', SITE.name),
      upsertMeta('property', 'og:title', fullTitle),
      upsertMeta('property', 'og:description', description),
      upsertMeta('property', 'og:url', canonical),
      upsertMeta('property', 'og:image', image),
      upsertMeta('property', 'og:locale', SITE.locale),
      // Twitter
      upsertMeta('name', 'twitter:card', 'summary_large_image'),
      upsertMeta('name', 'twitter:site', SITE.twitter),
      upsertMeta('name', 'twitter:title', fullTitle),
      upsertMeta('name', 'twitter:description', description),
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
  }, [fullTitle, description, image, type, noindex, canonical, jsonLd])

  return null
}
