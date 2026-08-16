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
    slug: 'ultimate-guide-to-ai-content-creation',
    title: 'The Ultimate Guide to AI Content Creation',
    metaTitle: 'The Ultimate Guide to AI Content Creation',
    description:
      'A complete, practical guide to AI content creation: prompting, brand voice, editing, fact-checking, and the workflow that keeps quality high at volume.',
    keyword: 'AI content creation',
    category: 'AI & Automation',
    date: '2026-08-15',
    readMinutes: 13,
    cover: { palette: 9, pattern: 4, icon: '❋' },
  },
  {
    slug: 'social-media-marketing-trends-2026',
    title: 'Top Social Media Marketing Trends for 2026',
    metaTitle: 'Top Social Media Marketing Trends for 2026',
    description:
      'The social media trends that actually matter in 2026 — from AI-assisted search and creator partnerships to the quiet return of owned audiences.',
    keyword: 'social media marketing trends 2026',
    category: 'Trends',
    date: '2026-08-16',
    readMinutes: 12,
    featured: true,
    cover: { palette: 7, pattern: 2, icon: '➔' },
  },
  {
    slug: 'instagram-content-ideas-for-small-businesses',
    title: 'Instagram Content Ideas for Small Businesses',
    metaTitle: '30 Instagram Content Ideas for Small Businesses',
    description:
      'Thirty Instagram content ideas built for real small businesses — organised by goal, with formats, caption angles, and a simple weekly posting rhythm.',
    keyword: 'Instagram content ideas for small business',
    category: 'Platform Guides',
    date: '2026-08-10',
    readMinutes: 12,
    cover: { palette: 13, pattern: 3, icon: '◎' },
  },
  {
    slug: 'high-engagement-linkedin-posts-with-ai',
    title: 'How to Write High-Engagement LinkedIn Posts Using AI',
    metaTitle: 'Write High-Engagement LinkedIn Posts Using AI',
    description:
      'The hook, structure, and formatting patterns that make LinkedIn posts perform — and exactly how to use AI for each without sounding like everyone else.',
    keyword: 'LinkedIn posts with AI',
    category: 'Platform Guides',
    date: '2026-08-12',
    readMinutes: 11,
    cover: { palette: 8, pattern: 3, icon: '✧' },
  },
  {
    slug: 'ai-vs-manual-social-media-management',
    title: 'AI vs Manual Social Media Management: Which Is Better?',
    metaTitle: 'AI vs Manual Social Media Management: Which Wins?',
    description:
      'A fair, side-by-side comparison of AI and manual social media management across speed, cost, quality, and risk — plus the hybrid model most teams land on.',
    keyword: 'AI vs manual social media management',
    category: 'Strategy',
    date: '2026-08-07',
    readMinutes: 11,
    cover: { palette: 5, pattern: 0, icon: '◐' },
  },
  {
    slug: 'best-ai-tools-for-social-media-managers',
    title: 'Best AI Tools for Social Media Managers in 2026',
    metaTitle: 'Best AI Tools for Social Media Managers in 2026',
    description:
      'An honest category-by-category look at the AI tools social media managers actually use in 2026, what each one is good at, and how to avoid a bloated stack.',
    keyword: 'AI tools for social media managers',
    category: 'AI & Automation',
    date: '2026-08-05',
    readMinutes: 12,
    cover: { palette: 3, pattern: 3, icon: '◈' },
  },
  {
    slug: 'how-small-businesses-grow-faster-with-ai',
    title: 'How Small Businesses Can Grow Faster Using AI',
    metaTitle: 'How Small Businesses Can Grow Faster Using AI',
    description:
      'Practical ways small businesses use AI to compete with bigger marketing teams — where it genuinely moves the needle, and where it quietly wastes your money.',
    keyword: 'AI for small business marketing',
    category: 'Strategy',
    date: '2026-08-05',
    readMinutes: 11,
    cover: { palette: 4, pattern: 4, icon: '▲' },
  },
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
  {
    slug: 'how-to-schedule-social-media-posts',
    title: 'How to Schedule Social Media Posts Like a Pro',
    metaTitle: 'How to Schedule Social Media Posts Like a Pro',
    description:
      'Scheduling is more than picking a time. Learn the queue structure, buffer rules, and approval habits that separate professional social teams from the rest.',
    keyword: 'schedule social media posts',
    category: 'Productivity',
    date: '2026-06-16',
    readMinutes: 10,
    cover: { palette: 6, pattern: 1, icon: '▣' },
  },
]
