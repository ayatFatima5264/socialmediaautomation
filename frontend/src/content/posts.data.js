// ---------------------------------------------------------------------------
// Blog registry — the single source of truth for every article.
//
// Metadata lives here (eagerly bundled, ~4 kB) so the index page can render
// cards, filters, and SEO tags instantly. The article *bodies* live as
// Markdown in ./posts/<slug>.md and are loaded lazily, one chunk per post, so
// reading one article never downloads the other nineteen.
//
// To publish a new article: drop a Markdown file in ./posts/ and add an entry
// below. Nothing else needs touching — routes, sitemap, related posts, tag
// filters, and the covers all derive from this list.
// ---------------------------------------------------------------------------

export const CATEGORIES = [
  'AI & Automation',
  'Strategy',
  'Productivity',
  'Platform Guides',
  'Trends',
]

export const POSTS = [
  {
    slug: 'what-is-ai-social-media-automation',
    title: "What Is AI Social Media Automation? A Complete Beginner's Guide",
    metaTitle: "What Is AI Social Media Automation? Beginner's Guide",
    description:
      'AI social media automation explained in plain English: what it does, what it cannot do, how to start safely, and the mistakes that cost beginners their reach.',
    keyword: 'AI social media automation',
    category: 'AI & Automation',
    date: '2026-07-28',
    readMinutes: 11,
    featured: true,
    cover: { palette: 0, pattern: 0, icon: '✦' },
  },
  {
    slug: 'ways-ai-saves-time-social-media-management',
    title: '10 Ways AI Saves Time on Social Media Management',
    metaTitle: '10 Ways AI Saves Time on Social Media Management',
    description:
      'Ten specific, unglamorous places AI gives social media managers their hours back — with realistic time savings and the tasks you should never hand over.',
    keyword: 'AI social media management',
    category: 'Productivity',
    date: '2026-07-21',
    readMinutes: 10,
    cover: { palette: 1, pattern: 1, icon: '⚡' },
  },
  {
    slug: 'create-month-of-social-media-posts-in-one-hour',
    title: 'How to Create a Month of Social Media Posts in One Hour',
    metaTitle: 'Create a Month of Social Media Posts in One Hour',
    description:
      'A repeatable 60-minute batching workflow that turns one focused hour into a full month of on-brand social posts — broken down minute by minute.',
    keyword: 'batch create social media posts',
    category: 'Productivity',
    date: '2026-07-14',
    readMinutes: 11,
    featured: true,
    cover: { palette: 2, pattern: 2, icon: '◷' },
  },
]
