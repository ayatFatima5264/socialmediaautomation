// ---------------------------------------------------------------------------
// Build-time SEO plugin.
//
// A Vite SPA ships one empty index.html. Google can execute JavaScript and will
// eventually see the tags <Seo> injects at runtime, but three important
// consumers cannot:
//
//   • Facebook / LinkedIn / X link scrapers  — no JS, so shared links show no
//     title, description, or preview image at all.
//   • The AdSense review crawler             — sees a page that looks empty.
//   • Search engines on first discovery      — render budget is deferred and
//     unreliable for new sites.
//
// So at build time we emit a real static HTML file per public route with the
// correct <title>, description, canonical, Open Graph, Twitter, and JSON-LD
// tags baked in. Vercel serves static files before applying SPA rewrites, so
// /features returns prerendered HTML while React still hydrates and takes over
// client-side navigation exactly as before.
//
// It also generates robots.txt, sitemap.xml, and ads.txt from the SAME route
// data the app uses, so they cannot drift when pages or articles are added.
// ---------------------------------------------------------------------------

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))

// Node's ESM loader rejects bare Windows paths ("C:\...") — dynamic imports
// must be file:// URLs. pathToFileURL handles both platforms correctly.
const importFile = (relative) => import(pathToFileURL(join(HERE, relative)).href)

// Resolve the canonical origin. On Vercel, VERCEL_PROJECT_PRODUCTION_URL is the
// stable production domain (preview deploys get their own VERCEL_URL, which we
// deliberately ignore — previews must not advertise themselves as canonical).
function resolveSiteUrl(env = process.env) {
  const explicit = env.VITE_SITE_URL
  if (explicit) return explicit.replace(/\/$/, '')
  if (env.VERCEL_PROJECT_PRODUCTION_URL) {
    return `https://${env.VERCEL_PROJECT_PRODUCTION_URL}`.replace(/\/$/, '')
  }
  return 'https://autosocial.zaions.com'
}

const esc = (s) =>
  String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')

// Strip the placeholder SEO tags out of the built index.html so the per-page
// block we inject is the only one present. Leaving both in place would give
// every page two conflicting descriptions.
function stripSeoTags(html) {
  return html
    .replace(/<title>[\s\S]*?<\/title>/i, '')
    .replace(/<meta\s+name="description"[^>]*>/gi, '')
    .replace(/<meta\s+property="og:[^"]*"[^>]*>/gi, '')
    .replace(/<meta\s+name="twitter:[^"]*"[^>]*>/gi, '')
    .replace(/<link\s+rel="canonical"[^>]*>/gi, '')
    .replace(/<!--\s*Primary SEO[\s\S]*?-->/gi, '')
    .replace(/<!--\s*Open Graph defaults\s*-->/gi, '')
    .replace(/<!--\s*Twitter defaults\s*-->/gi, '')
}

function seoBlock({ url, title, description, image, type, noindex, jsonLd, brand }) {
  const tags = [
    `<title>${esc(title)}</title>`,
    `<meta name="description" content="${esc(description)}" />`,
    `<link rel="canonical" href="${esc(url)}" />`,
    `<meta name="robots" content="${noindex ? 'noindex, nofollow' : 'index, follow'}" />`,
    `<meta property="og:type" content="${type}" />`,
    `<meta property="og:site_name" content="${esc(brand.name)}" />`,
    `<meta property="og:title" content="${esc(title)}" />`,
    `<meta property="og:description" content="${esc(description)}" />`,
    `<meta property="og:url" content="${esc(url)}" />`,
    `<meta property="og:image" content="${esc(image)}" />`,
    `<meta property="og:locale" content="${brand.locale}" />`,
    `<meta name="twitter:card" content="summary_large_image" />`,
    `<meta name="twitter:site" content="${esc(brand.twitter)}" />`,
    `<meta name="twitter:title" content="${esc(title)}" />`,
    `<meta name="twitter:description" content="${esc(description)}" />`,
    `<meta name="twitter:image" content="${esc(image)}" />`,
  ]
  if (jsonLd) {
    tags.push(
      `<script type="application/ld+json">${JSON.stringify(jsonLd).replace(/</g, '\\u003c')}</script>`,
    )
  }
  return tags.join('\n    ')
}

export default function seoPlugin() {
  let outDir = 'dist'
  let siteUrl = resolveSiteUrl()

  return {
    name: 'autosocial-seo',
    apply: 'build',

    configResolved(config) {
      outDir = config.build.outDir
      // Vite loads .env files itself; prefer whatever it resolved.
      siteUrl = resolveSiteUrl({ ...process.env, ...config.env })
    },

    async closeBundle() {
      // Import the same route data the app uses. These modules are plain ESM
      // with no Vite syntax, which is exactly why they were split out.
      const { AUTHOR, BRAND, MARKETING_PAGES, PRIVATE_ROUTES, fullTitle } =
        await importFile('../src/seo/pages.data.js')
      // posts.data.js holds ONLY published articles — it is what the client
      // bundle imports. drafts.data.js is read here and nowhere else, purely so
      // the guards below can validate against it without shipping it.
      const { POSTS } = await importFile('../src/content/posts.data.js')
      const { DRAFT_POSTS: DRAFTS } = await importFile('../src/content/drafts.data.js')

      // ---- Draft integrity guards ---------------------------------------
      // Two independent failure modes, both silent without these checks.
      const draftSlugs = new Set(DRAFTS.map((p) => p.slug))
      const publishedSlugs = new Set(POSTS.map((p) => p.slug))
      const problems = []

      // (1) File location must match the registry flag. Article bodies are
      // loaded by `import.meta.glob('./posts/*.md')`, which cannot filter on a
      // runtime flag — so a draft left in posts/ would still be COMPILED INTO
      // THE BUNDLE and served from the CDN, unlisted but publicly fetchable.
      // Drafts therefore live in content/drafts/, outside the glob, and this
      // check is what stops the flag and the file location from desyncing.
      for (const post of DRAFTS) {
        if (existsSync(join(HERE, `../src/content/posts/${post.slug}.md`))) {
          problems.push(
            `${post.slug}: listed in drafts.data.js but its body is still in ` +
              `content/posts/ — move it to content/drafts/ or it will ship in the bundle`,
          )
        }
        if (publishedSlugs.has(post.slug)) {
          problems.push(`${post.slug}: appears in BOTH posts.data.js and drafts.data.js`)
        }
      }
      for (const post of POSTS) {
        if (!existsSync(join(HERE, `../src/content/posts/${post.slug}.md`))) {
          problems.push(
            `${post.slug}: published but no body at content/posts/${post.slug}.md ` +
              `(is it still in content/drafts/?)`,
          )
        }
      }

      // (2) A published article must never link to a draft or a missing post.
      // Unpublishing otherwise leaves dead links inside the articles that did
      // ship — the kind of thing nobody notices until Googlebot hits the 404.
      for (const post of POSTS) {
        const path = join(HERE, `../src/content/posts/${post.slug}.md`)
        if (!existsSync(path)) continue // already reported above
        const body = readFileSync(path, 'utf8')
        for (const m of body.matchAll(/\]\(\/blog\/([a-z0-9-]+)\)/g)) {
          const target = m[1]
          if (draftSlugs.has(target)) {
            problems.push(`${post.slug} → /blog/${target} (target is a draft)`)
          } else if (!publishedSlugs.has(target)) {
            problems.push(`${post.slug} → /blog/${target} (no such article)`)
          }
        }
      }

      if (problems.length) {
        this.error(`SEO: draft/publish integrity check failed:\n  - ${problems.join('\n  - ')}`)
      }

      const root = join(process.cwd(), outDir)
      const template = readFileSync(join(root, 'index.html'), 'utf8')
      const base = stripSeoTags(template)
      const ogImage = `${siteUrl}${BRAND.ogImage}`

      // ---- Write one prerendered HTML file per route --------------------
      const write = (routePath, html) => {
        const dir = routePath === '/' ? root : join(root, routePath)
        mkdirSync(dir, { recursive: true })
        writeFileSync(join(dir, 'index.html'), html, 'utf8')
      }

      const inject = (html, block) =>
        html.replace(/<head>/i, `<head>\n    ${block}`)

      // Organization + WebSite structured data, emitted on the homepage only.
      const orgJsonLd = {
        '@context': 'https://schema.org',
        '@graph': [
          {
            '@type': 'Organization',
            '@id': `${siteUrl}/#organization`,
            name: BRAND.name,
            url: siteUrl,
            logo: `${siteUrl}/logo.png`,
            description: BRAND.defaultDescription,
          },
          {
            '@type': 'WebSite',
            '@id': `${siteUrl}/#website`,
            url: siteUrl,
            name: BRAND.name,
            publisher: { '@id': `${siteUrl}/#organization` },
          },
        ],
      }

      let count = 0

      for (const page of MARKETING_PAGES) {
        const url = page.path === '/' ? `${siteUrl}/` : `${siteUrl}${page.path}`
        write(
          page.path,
          inject(
            base,
            seoBlock({
              url,
              title: fullTitle(page.title),
              description: page.description,
              image: ogImage,
              type: 'website',
              noindex: false,
              jsonLd: page.path === '/' ? orgJsonLd : null,
              brand: BRAND,
            }),
          ),
        )
        count++
      }

      for (const post of POSTS) {
        const url = `${siteUrl}/blog/${post.slug}`
        write(
          `/blog/${post.slug}`,
          inject(
            base,
            seoBlock({
              url,
              title: fullTitle(post.metaTitle),
              description: post.description,
              image: ogImage,
              type: 'article',
              noindex: false,
              jsonLd: {
                '@context': 'https://schema.org',
                '@type': 'BlogPosting',
                headline: post.title,
                description: post.description,
                datePublished: post.date,
                dateModified: post.date,
                keywords: post.keyword,
                articleSection: post.category,
                mainEntityOfPage: { '@type': 'WebPage', '@id': url },
                author: { '@type': 'Person', name: AUTHOR.name },
                publisher: {
                  '@type': 'Organization',
                  name: BRAND.name,
                  url: siteUrl,
                  logo: { '@type': 'ImageObject', url: `${siteUrl}/logo.png` },
                },
              },
              brand: BRAND,
            }),
          ),
        )
        count++
      }

      // ---- SPA fallback shell --------------------------------------------
      // Vercel serves static files first and falls back to a rewrite for
      // anything with no matching file. That fallback MUST NOT be the
      // prerendered homepage: it would answer every unknown URL — including
      // draft article URLs — with the homepage's HTML and its "index, follow",
      // telling crawlers that arbitrary paths are real, indexable pages.
      //
      // This shell is the rewrite target instead. It carries noindex and no
      // canonical, while still loading the app, so React renders the branded
      // 404 for unknown routes and the real app for private routes (which
      // should be noindex anyway).
      writeFileSync(
        join(root, '404.html'),
        inject(
          base,
          [
            `<title>Page Not Found — ${esc(BRAND.name)}</title>`,
            `<meta name="description" content="The page you are looking for could not be found." />`,
            `<meta name="robots" content="noindex, nofollow" />`,
          ].join('\n    '),
        ),
        'utf8',
      )

      // ---- robots.txt ----------------------------------------------------
      const robots = [
        `# ${BRAND.name} — robots.txt (generated at build time)`,
        'User-agent: *',
        'Allow: /',
        '',
        '# Keep the authenticated application out of search indexes.',
        ...PRIVATE_ROUTES.map((r) => `Disallow: ${r}`),
        '',
        '# Google AdSense crawler needs access to render pages for ad targeting.',
        'User-agent: Mediapartners-Google',
        'Allow: /',
        '',
        `Sitemap: ${siteUrl}/sitemap.xml`,
        '',
      ].join('\n')
      writeFileSync(join(root, 'robots.txt'), robots, 'utf8')

      // ---- sitemap.xml ---------------------------------------------------
      const today = new Date().toISOString().slice(0, 10)
      const entries = [
        ...MARKETING_PAGES.map((p) => ({
          loc: p.path === '/' ? `${siteUrl}/` : `${siteUrl}${p.path}`,
          lastmod: today,
          changefreq: p.changefreq,
          priority: p.priority,
        })),
        ...POSTS.map((p) => ({
          loc: `${siteUrl}/blog/${p.slug}`,
          lastmod: p.date,
          changefreq: 'monthly',
          priority: '0.7',
        })),
      ]
      const sitemap = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        ...entries.map(
          (e) =>
            `  <url>\n    <loc>${e.loc}</loc>\n    <lastmod>${e.lastmod}</lastmod>\n` +
            `    <changefreq>${e.changefreq}</changefreq>\n    <priority>${e.priority}</priority>\n  </url>`,
        ),
        '</urlset>',
        '',
      ].join('\n')
      writeFileSync(join(root, 'sitemap.xml'), sitemap, 'utf8')

      // ---- ads.txt (only once an AdSense publisher ID is configured) ------
      const pub = process.env.VITE_ADSENSE_ID
      if (pub && /^ca-pub-\d+$/.test(pub)) {
        writeFileSync(
          join(root, 'ads.txt'),
          `google.com, ${pub.replace('ca-', '')}, DIRECT, f08c47fec0942fa0\n`,
          'utf8',
        )
      }

      this.info?.(
        `SEO: ${count} pages prerendered, sitemap (${entries.length} urls) + robots.txt written for ${siteUrl}` +
          (pub ? ' + ads.txt' : ''),
      )
    },
  }
}
