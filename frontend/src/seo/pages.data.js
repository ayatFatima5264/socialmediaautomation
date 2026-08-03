// ---------------------------------------------------------------------------
// Per-route SEO metadata — the single source of truth for titles, descriptions,
// and sitemap weighting on every public page.
//
// This module is deliberately dependency-free and free of Vite-specific syntax
// (no import.meta, no ?raw globs) so it can be imported BOTH by the React app
// and by the Node-side build plugin that generates sitemap.xml and prerenders
// static meta tags. That is what guarantees the HTML a non-JavaScript crawler
// sees is identical to what the app renders at runtime.
// ---------------------------------------------------------------------------

// Brand facts needed at build time. Kept here (rather than in config/site.js)
// because that module reads import.meta.env and cannot be loaded by Node.
export const BRAND = {
  name: 'AutoSocial AI',
  tagline: 'AI Social Media Management Platform',
  defaultDescription:
    'AutoSocial AI is an AI-powered social media platform. Generate and auto-schedule an entire 7, 15, or 30-day content plan, create images, and publish across every network — all from one dashboard.',
  locale: 'en_US',
  twitter: '@autosocialai',
  ogImage: '/og-image.png',
}

// Every indexable marketing route. `title` is the page title WITHOUT the brand
// suffix — `fullTitle()` below applies the same rule the <Seo> component uses.
export const MARKETING_PAGES = [
  {
    path: '/',
    title: null, // Home uses the brand + tagline as its title
    description:
      'AutoSocial AI helps businesses, agencies, and creators create content, generate AI images, schedule posts, and publish across every platform from one dashboard. Start free.',
    priority: '1.0',
    changefreq: 'weekly',
  },
  {
    path: '/features',
    title: 'Features',
    description:
      'Explore AutoSocial AI: AI post, image, carousel, caption, and hashtag generation, brand personalization, multi-platform publishing, smart scheduling, and account management.',
    priority: '0.8',
    changefreq: 'monthly',
  },
  {
    path: '/pricing',
    title: 'Pricing',
    description:
      'Simple, scalable pricing for AutoSocial AI. Start free, upgrade to Pro or Business for unlimited AI generations and images, or contact us for Enterprise.',
    priority: '0.8',
    changefreq: 'monthly',
  },
  {
    path: '/blog',
    // Kept short: the brand suffix is appended, and Google truncates page
    // titles past roughly 60 characters in search results.
    title: 'AI Social Media Marketing Blog',
    description:
      'Practical, no-fluff guides on AI social media automation, content strategy, scheduling, and platform marketing — written for busy teams and small businesses.',
    priority: '0.9',
    changefreq: 'weekly',
  },
  {
    path: '/about',
    title: 'About',
    description:
      "AutoSocial AI helps businesses, agencies, and creators stay consistently visible online. Learn about our mission, our values, and where we're headed.",
    priority: '0.5',
    changefreq: 'monthly',
  },
  {
    path: '/contact',
    title: 'Contact',
    description:
      'Questions, feedback, or partnership ideas? Get in touch with the AutoSocial AI team — we respond within one business day.',
    priority: '0.5',
    changefreq: 'monthly',
  },
  {
    path: '/privacy',
    title: 'Privacy Policy',
    description:
      'How AutoSocial AI collects, uses, and protects your account, business profile, AI prompts, and connected social accounts.',
    priority: '0.3',
    changefreq: 'yearly',
  },
  {
    path: '/terms',
    title: 'Terms of Service',
    description:
      'The terms governing your use of AutoSocial AI, including acceptable use, connected accounts, AI-generated content, and account terms.',
    priority: '0.3',
    changefreq: 'yearly',
  },
  {
    path: '/cookies',
    title: 'Cookie Policy',
    description:
      'Which cookies AutoSocial AI sets, why we set them, how advertising and analytics cookies are used, and how you can change your choices at any time.',
    priority: '0.3',
    changefreq: 'yearly',
  },
]

// Look up a page's metadata by path. Pages call this so the tags they render at
// runtime can never drift from the tags baked into the prerendered HTML.
export function pageSeo(path) {
  return MARKETING_PAGES.find((p) => p.path === path) || null
}

// The exact title rule used by <Seo>: "Page — Brand", or "Brand — Tagline".
export function fullTitle(title) {
  return title ? `${title} — ${BRAND.name}` : `${BRAND.name} — ${BRAND.tagline}`
}

// Routes behind authentication — excluded from the sitemap and disallowed in
// robots.txt. Keeping the list here means adding a private route updates both.
export const PRIVATE_ROUTES = [
  '/dashboard',
  '/planner',
  '/generate',
  '/create',
  '/scheduler',
  '/history',
  '/accounts',
  '/settings',
  '/business-profile',
  '/onboarding',
  '/login',
  '/register',
  '/forgot-password',
  '/reset-password',
]
