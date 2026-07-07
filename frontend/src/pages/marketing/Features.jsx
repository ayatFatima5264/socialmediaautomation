import { Container, CTASection, PageHero } from './_ui.jsx'
import Seo from '../../components/Seo.jsx'

const FEATURES = [
  {
    icon: '✍️',
    title: 'AI Post Generator',
    body: 'Start from a single idea and get complete posts written for each platform — a strong hook, a clear message, and a call to action. Instead of staring at a blank page, you start from a solid draft and edit from there.',
    benefit: 'Turns a blank page into a finished post in seconds.',
  },
  {
    icon: '🎨',
    title: 'AI Image Generator',
    body: 'Create original visuals from a short description, with control over style, aspect ratio, and quality. No stock photos, no design software — just images that match your post and your brand.',
    benefit: 'Professional visuals without a designer or a stock subscription.',
  },
  {
    icon: '🖼️',
    title: 'AI Carousel Generator',
    body: 'Generate multi-slide carousels that tell a story or break down a topic step by step, each slide sized correctly for the platform. Perfect for tips, how-tos, and product highlights.',
    benefit: 'Build swipe-worthy carousels in one pass, not slide by slide.',
  },
  {
    icon: '💬',
    title: 'AI Caption Generator',
    body: 'Get captions written for the platform you\'re posting to — punchy for X, professional for LinkedIn, warm for Instagram. Adjust the tone and length until it feels right.',
    benefit: 'Platform-perfect captions without rewriting the same idea five times.',
  },
  {
    icon: '#️⃣',
    title: 'AI Hashtag Suggestions',
    body: 'Receive relevant hashtag sets based on your topic and audience, balancing reach and relevance. Add them with a click instead of researching tags for every post.',
    benefit: 'Reach the right audience without manual hashtag research.',
  },
  {
    icon: '🎯',
    title: 'Business Profile Personalization',
    body: 'Set your industry, audience, brand voice, and goals once. AutoSocial AI applies that context to every generation, so drafts already sound like your brand before you touch them.',
    benefit: 'Less editing — content starts on-brand, not generic.',
  },
  {
    icon: '📤',
    title: 'Multi-Platform Publishing',
    body: 'Connect Instagram, Facebook, LinkedIn, X, Threads, and Pinterest, then publish to any of them from one screen. Adapt a single idea to every network without copying and pasting.',
    benefit: 'Publish everywhere from one place — no app-switching.',
  },
  {
    icon: '🗓️',
    title: 'Smart Scheduler',
    body: 'Plan your week or month on a visual calendar, set your posting times, and let AutoSocial publish automatically. Keep a steady cadence even during your busiest weeks.',
    benefit: 'Stay consistent on autopilot — set it and move on.',
  },
  {
    icon: '📝',
    title: 'Draft Management',
    body: 'Keep every draft and published post organized, searchable, and reusable. Revisit what worked, repurpose past content, and never lose an idea in a notes app again.',
    benefit: 'One tidy home for every idea, draft, and published post.',
  },
  {
    icon: '🔗',
    title: 'Social Account Management',
    body: 'Connect and manage all your accounts from a single dashboard. See connection status at a glance, refresh access when needed, and control everything without logging in and out.',
    benefit: 'Every account, one dashboard, always in view.',
  },
  {
    icon: '📊',
    title: 'Analytics',
    comingSoon: true,
    body: 'Track how your content performs across platforms — reach, engagement, and growth — in one report. Spot what works and do more of it, without exporting spreadsheets from six dashboards.',
    benefit: 'Understand what performs and refine what you post next.',
  },
  {
    icon: '👥',
    title: 'Team Collaboration',
    comingSoon: true,
    body: 'Invite teammates, assign roles, and move drafts through review and approval before they go live. Built for agencies and teams that manage multiple brands together.',
    benefit: 'Draft, review, and approve as a team — no messy handoffs.',
  },
]

export default function Features() {
  return (
    <>
      <Seo
        title="Features"
        description="Explore AutoSocial AI: AI post, image, carousel, caption, and hashtag generation, brand personalization, multi-platform publishing, smart scheduling, and account management."
      />
      <PageHero
        eyebrow="Features"
        title="One studio for your entire social workflow"
        subtitle="From the first idea to the published post, AutoSocial AI replaces a stack of tools with a single, AI-native workspace built to save you time."
      />
      <section className="pb-8">
        <Container>
          <div className="grid gap-5 md:grid-cols-2">
            {FEATURES.map((f) => (
              <div key={f.title} className="card p-6">
                <div className="flex items-start gap-4">
                  <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-indigo-500/15 to-violet-500/15 text-xl">
                    {f.icon}
                  </div>
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-lg font-bold">{f.title}</h3>
                      {f.comingSoon && (
                        <span className="rounded-full bg-indigo-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-indigo-500 dark:text-indigo-300">
                          Coming Soon
                        </span>
                      )}
                    </div>
                    <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{f.body}</p>
                    <p className="mt-3 flex items-start gap-2 text-sm font-medium text-slate-700 dark:text-slate-200">
                      <span className="text-indigo-500 dark:text-indigo-400">→</span>
                      {f.benefit}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Container>
      </section>
      <CTASection
        title="See what AutoSocial AI can create for you"
        subtitle="Start free and generate your first week of content in minutes."
      />
    </>
  )
}
