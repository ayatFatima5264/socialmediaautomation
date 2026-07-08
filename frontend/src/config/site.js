// ---------------------------------------------------------------------------
// Central site configuration — the single source of truth shared by the
// Marketing Website (SEO, footer, structured data) and, where relevant, the
// Authenticated Application. Change brand facts here, not in individual pages.
// ---------------------------------------------------------------------------

// Canonical origin, e.g. "https://autosocial.ai". Overridable per environment.
export const SITE_URL = (
  import.meta.env.VITE_SITE_URL || 'https://autosocial.ai'
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
export const MARKETING_NAV = [
  { to: '/features', label: 'Features' },
  { to: '/pricing', label: 'Pricing' },
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
    ],
  },
]

// Every indexable public route — consumed by the SEO sitemap reference and
// kept here so adding a marketing page is a one-line change.
export const PUBLIC_ROUTES = [
  '/',
  '/features',
  '/pricing',
  '/about',
  '/contact',
  '/privacy',
  '/terms',
]
