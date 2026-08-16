// ---------------------------------------------------------------------------
// Unpublished articles.
//
// Kept in a SEPARATE module from posts.data.js on purpose: the app only ever
// imports posts.data.js, so nothing in this file — not even a title — reaches
// the client bundle. Only the build-time guard in plugins/seo.js reads it, to
// verify that no published article links to something in here and that each
// entry's body sits in content/drafts/ rather than content/posts/.
//
// To publish: move the entry into posts.data.js AND move its .md file from
// content/drafts/ into content/posts/. The build fails if you do only one.
// ---------------------------------------------------------------------------

export const DRAFT_POSTS = [
  {
    slug: 'ultimate-guide-to-ai-content-creation',
    title: 'The Ultimate Guide to AI Content Creation',
    metaTitle: 'The Ultimate Guide to AI Content Creation',
    description:
      'A complete, practical guide to AI content creation: prompting, brand voice, editing, fact-checking, and the workflow that keeps quality high at volume.',
    keyword: 'AI content creation',
    category: 'AI & Automation',
    date: '2026-05-26',
    readMinutes: 13,
    cover: { palette: 9, pattern: 4, icon: '❋' },
  },
  {
    slug: 'repurpose-one-content-into-10-social-posts',
    title: 'How to Repurpose One Piece of Content into 10 Social Media Posts',
    metaTitle: 'Repurpose 1 Piece of Content Into 10 Social Posts',
    description:
      'A ten-format repurposing framework that turns a single blog post, webinar, or podcast into a fortnight of social content without repeating yourself.',
    keyword: 'repurpose content for social media',
    category: 'Productivity',
    date: '2026-05-19',
    readMinutes: 11,
    cover: { palette: 10, pattern: 0, icon: '⬢' },
  },
  {
    slug: 'common-social-media-mistakes-businesses-make',
    title: 'Common Social Media Mistakes Businesses Make',
    metaTitle: '12 Common Social Media Mistakes Businesses Make',
    description:
      'The twelve social media mistakes we see most often from businesses — why each one quietly suppresses reach, and the specific fix for every single one.',
    keyword: 'social media mistakes',
    category: 'Strategy',
    date: '2026-05-12',
    readMinutes: 11,
    cover: { palette: 11, pattern: 1, icon: '✚' },
  },
  {
    slug: 'how-ai-increases-social-media-engagement',
    title: 'How AI Helps Increase Engagement on Social Media',
    metaTitle: 'How AI Helps Increase Social Media Engagement',
    description:
      'Engagement is a system, not a lucky post. Here is how AI improves hooks, timing, formats, and replies — and the one thing it should never do for you.',
    keyword: 'increase social media engagement',
    category: 'AI & Automation',
    date: '2026-05-05',
    readMinutes: 11,
    cover: { palette: 12, pattern: 2, icon: '◉' },
  },
  {
    slug: 'instagram-content-ideas-for-small-businesses',
    title: 'Instagram Content Ideas for Small Businesses',
    metaTitle: '30 Instagram Content Ideas for Small Businesses',
    description:
      'Thirty Instagram content ideas built for real small businesses — organised by goal, with formats, caption angles, and a simple weekly posting rhythm.',
    keyword: 'Instagram content ideas for small business',
    category: 'Platform Guides',
    date: '2026-04-28',
    readMinutes: 12,
    cover: { palette: 13, pattern: 3, icon: '◎' },
  },
  {
    slug: 'linkedin-marketing-tips-for-b2b-companies',
    title: 'LinkedIn Marketing Tips for B2B Companies',
    metaTitle: 'LinkedIn Marketing Tips for B2B Companies (2026)',
    description:
      'How B2B companies actually generate pipeline on LinkedIn: company page vs employee reach, content pillars, comment strategy, and measuring what matters.',
    keyword: 'LinkedIn marketing for B2B',
    category: 'Platform Guides',
    date: '2026-04-21',
    readMinutes: 12,
    cover: { palette: 14, pattern: 4, icon: '■' },
  },
  {
    slug: 'facebook-marketing-strategies-that-work',
    title: 'Facebook Marketing Strategies That Still Work',
    metaTitle: 'Facebook Marketing Strategies That Still Work',
    description:
      'Facebook is not dead — it changed. Here are the organic and low-budget strategies that still reliably work for local businesses, communities, and B2C brands.',
    keyword: 'Facebook marketing strategies',
    category: 'Platform Guides',
    date: '2026-04-14',
    readMinutes: 11,
    cover: { palette: 15, pattern: 0, icon: '★' },
  },
  {
    slug: 'build-consistent-brand-voice-with-ai',
    title: 'How to Build a Consistent Brand Voice with AI',
    metaTitle: 'How to Build a Consistent Brand Voice With AI',
    description:
      'Build a brand voice guide AI can actually follow — with the four dimensions, a reusable voice prompt, and a scoring test for every generated draft.',
    keyword: 'brand voice with AI',
    category: 'Strategy',
    date: '2026-04-07',
    readMinutes: 11,
    cover: { palette: 16, pattern: 1, icon: '◆' },
  },
  {
    slug: 'best-time-to-post-on-social-media',
    title: 'Best Time to Post on Social Media in 2026',
    metaTitle: 'Best Time to Post on Social Media in 2026',
    description:
      'Why generic "best time to post" charts mislead you, how modern feeds really rank content, and a four-week test to find your own audience’s real peak times.',
    keyword: 'best time to post on social media',
    category: 'Trends',
    date: '2026-03-31',
    readMinutes: 11,
    cover: { palette: 17, pattern: 2, icon: '◷' },
  },
  {
    slug: 'automate-your-social-media-workflow',
    title: 'How to Automate Your Entire Social Media Workflow',
    metaTitle: 'How to Automate Your Entire Social Media Workflow',
    description:
      'Map, automate, and monitor the full social media workflow — from idea capture to publishing and reporting — with clear human checkpoints at every risky step.',
    keyword: 'automate social media workflow',
    category: 'AI & Automation',
    date: '2026-03-24',
    readMinutes: 12,
    cover: { palette: 18, pattern: 3, icon: '⟳' },
  },
  {
    slug: 'ai-viral-content-ideas',
    title: 'How AI Can Help You Generate Viral Content Ideas',
    metaTitle: 'How AI Helps You Generate Viral Content Ideas',
    description:
      'Virality is not random — it is a pattern you can study. Learn how to use AI to mine, remix, and stress-test content ideas before you spend time making them.',
    keyword: 'viral content ideas',
    category: 'Trends',
    date: '2026-03-17',
    readMinutes: 11,
    cover: { palette: 19, pattern: 4, icon: '✳' },
  },
]
