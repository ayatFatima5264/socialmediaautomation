// ---------------------------------------------------------------------------
// Central site configuration — the single source of truth shared by the
// Marketing Website (SEO, footer, structured data) and, where relevant, the
// Authenticated Application. Change brand facts here, not in individual pages.
// ---------------------------------------------------------------------------

import { POSTS } from '../content/posts.data.js'

// Only released articles are public routes — drafts are excluded from the
// sitemap reference below and from anything that enumerates the site.
const PUBLISHED_POSTS = POSTS.filter((p) => !p.draft)

// Canonical origin used for canonical links, Open Graph URLs, and JSON-LD.
//
// Resolution order matters: an explicit VITE_SITE_URL wins, but when it is
// unset we fall back to the origin the page is actually being served from —
// NOT a hardcoded domain. A hardcoded fallback is actively dangerous: if the
// site is deployed anywhere other than that domain, every canonical tag tells
// Google the real page lives somewhere else, which de-indexes the live site.
// The literal below is only ever used during SSR/prerender, where `window`
// does not exist; the build plugin rewrites those tags with the real origin.
export const SITE_URL = (
  import.meta.env.VITE_SITE_URL ||
  (typeof window !== 'undefined' ? window.location.origin : 'https://autosocial.zaions.com')
).replace(/\/$/, '')

export const SITE = {
  name: 'AutoSocial AI',
  // Concise tagline used as the SEO title suffix.
  tagline: 'AI Social Media Management Platform',
  // Punchy brand slogan for on-page display (hero, footer).
  slogan: 'Create. Design. Schedule. Publish. All Powered by AI.',
  // Default meta description used when a page doesn't provide its own.
  description:
    'AutoSocial AI is an AI-powered social media platform. Use AI Planner to generate and auto-schedule an entire 7, 15, or 30-day content plan, generate images, and publish across every network — all from one dashboard.',
  url: SITE_URL,
  // Social sharing image (Open Graph / Twitter). Lives in /public.
  ogImage: `${SITE_URL}/og-image.png`,
  twitter: '@autosocialai',
  supportEmail: 'hello@autosocial.ai',
  locale: 'en_US',
  // Social profiles (placeholder URLs until the real handles are live).
  socials: {
    facebook: 'https://facebook.com/autosocialai',
    instagram: 'https://instagram.com/autosocialai',
    linkedin: 'https://linkedin.com/company/autosocialai',
    x: 'https://x.com/autosocialai',
  },
}

// Marketing top-navigation (used by PublicLayout).
// `end: true` makes the link active only on an exact path match — needed for
// Home ("/") so it isn't flagged active on every marketing route.
export const MARKETING_NAV = [
  { to: '/', label: 'Home', end: true },
  { to: '/features', label: 'Features' },
  { to: '/pricing', label: 'Pricing' },
  { to: '/blog', label: 'Blog' },
  { to: '/about', label: 'About' },
  { to: '/contact', label: 'Contact' },
]

// Footer columns. External/coming-soon links carry flags so the footer can
// render them differently without special-casing.
export const FOOTER_COLUMNS = [
  {
    title: 'Product',
    links: [
      { to: '/features', label: 'AI Planner', badge: 'New' },
      { to: '/features', label: 'Features' },
      { to: '/pricing', label: 'Pricing' },
      { to: '/about', label: 'Roadmap' },
    ],
  },
  {
    title: 'Company',
    links: [
      { to: '/about', label: 'About' },
      { to: '/contact', label: 'Contact' },
      { href: '#', label: 'Careers', badge: 'Coming Soon' },
    ],
  },
  {
    title: 'Resources',
    links: [
      { to: '/blog', label: 'Blog' },
      { href: '#', label: 'Help Center', badge: 'Coming Soon' },
      { href: '#', label: 'Documentation', badge: 'Coming Soon' },
      { href: '#', label: 'API', badge: 'Coming Soon' },
    ],
  },
  {
    title: 'Legal',
    links: [
      { to: '/privacy', label: 'Privacy Policy' },
      { to: '/terms', label: 'Terms of Service' },
      { to: '/cookies', label: 'Cookie Policy' },
    ],
  },
]

// Every indexable public route — consumed by the SEO sitemap reference and
// kept here so adding a marketing page is a one-line change. Blog article
// routes are derived from the post registry, so publishing an article never
// requires editing this list.
export const MARKETING_ROUTES = [
  '/',
  '/features',
  '/pricing',
  '/blog',
  '/about',
  '/contact',
  '/privacy',
  '/terms',
  '/cookies',
]

export const PUBLIC_ROUTES = [
  ...MARKETING_ROUTES,
  ...PUBLISHED_POSTS.map((p) => `/blog/${p.slug}`),
]
