import { Link } from 'react-router-dom'
import { Container, CTASection, FeatureCard } from './_ui.jsx'
import Seo from '../../components/Seo.jsx'
import { PLATFORMS } from '../../lib/constants'
import { SITE } from '../../config/site'

// Structured data — helps search engines understand the brand + product.
const JSON_LD = {
  '@context': 'https://schema.org',
  '@graph': [
    {
      '@type': 'Organization',
      name: SITE.name,
      url: SITE.url,
      logo: `${SITE.url}/favicon.svg`,
      description: SITE.description,
    },
    { '@type': 'WebSite', name: SITE.name, url: SITE.url },
    {
      '@type': 'SoftwareApplication',
      name: SITE.name,
      applicationCategory: 'BusinessApplication',
      operatingSystem: 'Web',
      offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
    },
  ],
}

const FEATURES = [
  { icon: '🤖', title: 'AI Planner', tag: 'New', body: 'Generate and auto-schedule a full 7, 15, or 30-day content plan across all six platforms — captions, content types, and posting times done for you.' },
  { icon: '✍️', title: 'AI Post Generator', body: 'Describe an idea and get ready-to-publish posts tailored to each platform — hooks, body, and call to action included.' },
  { icon: '🎨', title: 'AI Image & Carousels', body: 'Turn a topic into scroll-stopping visuals and multi-slide carousels, sized correctly for every network.' },
  { icon: '#️⃣', title: 'Captions & Hashtags', body: 'Get platform-aware captions and relevant hashtag sets that match your topic and audience — no guessing.' },
  { icon: '🗓️', title: 'Smart Scheduler', body: 'Plan a week or a month on a visual calendar and let AutoSocial publish at the times your audience is active.' },
  { icon: '📤', title: 'Multi-Platform Publishing', body: 'Connect your accounts once and push finished content everywhere from a single screen.' },
  { icon: '🎯', title: 'Brand Personalization', body: 'Your business profile shapes every draft, so the output already sounds like you before you edit a word.' },
]

// AI Planner spotlight data.
const PLANNER_HIGHLIGHTS = [
  'One-click AI content generation',
  '7-day, 15-day & 30-day plans',
  'Captions tailored to each platform',
  'Promotional, educational & engagement mix',
  'Automatic post scheduling',
  'Edit, regenerate or delete before publishing',
]

const PLANNER_WORKFLOW = [
  { icon: '💬', title: 'Describe your business', body: 'Tell AI your industry, audience, and goals — or reuse the business profile you set during onboarding.' },
  { icon: '📅', title: 'Choose 7, 15 or 30 days', body: 'Pick how far ahead you want to plan and AI maps out the whole content calendar for you.' },
  { icon: '🤖', title: 'AI generates & schedules', body: 'Platform-tailored captions across content types — created, organized, and auto-scheduled across all six platforms.' },
  { icon: '✏️', title: 'Review & publish', body: 'Edit, regenerate, or remove any post before it goes live. You stay in full control of the calendar.' },
]

const WHY = [
  { icon: '⏱️', title: 'Hours back every week', body: 'What used to take an afternoon of writing and designing now takes a few minutes — from idea to scheduled post.' },
  { icon: '🎯', title: 'Always on-brand', body: 'Your voice, audience, and goals are built into every generation, so content stays consistent across platforms.' },
  { icon: '🧩', title: 'One tool, not six', body: 'Writing, design, scheduling, and publishing live in one dashboard. No more juggling tabs and subscriptions.' },
  { icon: '🚀', title: 'No design skills needed', body: 'Generate images, carousels, and captions that look professionally made — without opening a design app.' },
]

const CAPABILITIES = [
  'Write posts, threads, and long-form captions',
  'Generate original images and carousels',
  'Suggest hashtags that fit your niche',
  'Rewrite, shorten, or restyle any draft',
  'Adapt one idea to every platform at once',
  'Import a link or document and turn it into posts',
]

const TESTIMONIALS = [
  { quote: 'We went from posting twice a week to daily on four platforms. AutoSocial does the heavy lifting and everything still sounds like us.', name: 'Sara Malik', role: 'Founder, Loomly Studio', initial: 'S' },
  { quote: 'As an agency, the scheduler and per-platform generation save us hours per client. Onboarding new accounts takes minutes.', name: 'David Chen', role: 'Creative Director, NorthPeak', initial: 'D' },
  { quote: 'I run recruitment marketing solo. This is like having a content team — captions, images, and a calendar I actually keep up with.', name: 'Amara Okoye', role: 'Talent Marketing Lead', initial: 'A' },
]

const FAQ = [
  { q: 'What is the AI Planner?', a: 'AI Planner generates and schedules a complete social media content plan from a single request. Choose a 7, 15, or 30-day duration and AI creates platform-tailored posts across content types, organizes them into a calendar, and automatically schedules them across all six connected platforms. You can review, edit, regenerate, or delete any post before it publishes.' },
  { q: 'Do I need any design or copywriting experience?', a: 'No. Describe what you want and AutoSocial AI drafts the copy and generates the visuals for you. You stay in control — review, tweak, and approve before anything goes out.' },
  { q: 'Which platforms can I publish to?', a: 'Instagram, Facebook, LinkedIn, X, Threads, and Pinterest. Connect your accounts once and publish to any of them from a single screen.' },
  { q: 'Will the content actually sound like my brand?', a: 'Yes. During onboarding you set your industry, audience, brand voice, and goals. Every generation is guided by that profile, so drafts start on-brand instead of generic.' },
  { q: 'Can I schedule posts in advance?', a: 'Absolutely. Plan a week or a month on the calendar, set your times, and AutoSocial publishes automatically. You can edit or reschedule anytime.' },
  { q: 'Is there a free plan?', a: 'Yes — you can start for free, no credit card required. Upgrade to Pro or Business when you need more generations, accounts, or team features.' },
]

export default function Home() {
  return (
    <>
      <Seo
        title={null}
        description="AutoSocial AI helps businesses, agencies, and creators create content, generate AI images, schedule posts, and publish across every platform from one dashboard. Start free."
        jsonLd={JSON_LD}
      />

      {/* Hero */}
      <section className="pt-20 pb-12 text-center md:pt-28">
        <Container>
          <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-accent-line bg-accent-soft px-3.5 py-1 text-xs font-semibold uppercase tracking-wide text-accent">
            ✦ New · AI Content Planner
          </div>
          <h1 className="mx-auto max-w-4xl text-4xl font-black leading-[1.08] tracking-tight md:text-6xl">
            Generate and schedule{' '}
            <span className="text-accent">30 days of social media content</span>{' '}
            with AI
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-muted md:text-xl">
            Create an entire week, 15 days, or a full month of content in minutes.
            AutoSocial AI generates engaging posts, organizes them into a content
            calendar, and automatically schedules them across six social platforms —
            all from a single dashboard.
          </p>
          <div className="mt-9 flex flex-wrap justify-center gap-3">
            <Link to="/register" className="btn btn-primary px-7 py-3 text-base">
              Start for free
            </Link>
            <Link to="/features" className="btn btn-secondary px-7 py-3 text-base">
              See how it works
            </Link>
          </div>
          <p className="mt-4 text-xs text-muted">
            No credit card required · Free plan available
          </p>

          {/* Product preview — decorative, fully fluid */}
          <div className="mx-auto mt-14 max-w-4xl">
            <div className="overflow-hidden rounded-2xl border-2 border-accent-line bg-surface text-left shadow-[0_1px_2px_rgba(22,40,31,0.06)]">
              <div className="flex items-center gap-2 border-b border-line bg-inset px-4 py-3">
                <span className="h-3 w-3 rounded-full bg-accent" />
                <span className="h-3 w-3 rounded-full border border-line" />
                <span className="h-3 w-3 rounded-full border border-line" />
                <span className="ml-3 text-xs font-medium text-muted">AutoSocial AI · New post</span>
              </div>
              <div className="grid gap-4 p-5 sm:grid-cols-3">
                <div className="space-y-3 sm:col-span-2">
                  <div className="h-3 w-1/3 rounded-full bg-accent" />
                  <div className="h-2.5 w-full rounded-full bg-inset" />
                  <div className="h-2.5 w-11/12 rounded-full bg-inset" />
                  <div className="h-2.5 w-4/5 rounded-full bg-inset" />
                  <div className="flex flex-wrap gap-2 pt-1">
                    {['#marketing', '#ai', '#socialmedia'].map((t) => (
                      <span key={t} className="badge bg-accent-soft text-accent">{t}</span>
                    ))}
                  </div>
                </div>
                <div className="grid place-items-center rounded-xl border border-accent-line bg-accent-soft p-6 text-3xl">
                  🎨
                </div>
              </div>
            </div>
          </div>

          {/* Supported platforms */}
          <div className="mt-14">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted">
              Publish everywhere you post
            </p>
            <div className="mt-4 flex flex-wrap items-center justify-center gap-3">
              {Object.entries(PLATFORMS).map(([key, p]) => (
                <span
                  key={key}
                  className="badge border border-line bg-inset px-3 py-1"
                >
                  <span
                    className="grid h-5 w-5 place-items-center rounded-full text-[10px] font-bold text-white"
                    style={{ background: p.color }}
                  >
                    {p.initial}
                  </span>
                  {p.label}
                </span>
              ))}
            </div>
          </div>
        </Container>
      </section>

      {/* Trusted by */}
      <section className="border-y border-line bg-surface py-8">
        <Container>
          <p className="text-center text-sm text-muted">
            Built for marketers, agencies, recruiters, startups, and creators —
            trusted by fast-moving teams to stay visible every day.
          </p>
          <div className="mt-5 flex flex-wrap items-center justify-center gap-x-10 gap-y-3 text-sm font-semibold text-muted">
            <span>NorthPeak</span>
            <span>Loomly Studio</span>
            <span>BrightHire</span>
            <span>Onda Labs</span>
            <span>Fieldwork</span>
            <span>Ketchup&nbsp;Media</span>
          </div>
        </Container>
      </section>

      {/* ★ AI Planner spotlight (flagship feature) */}
      <section className="py-16">
        <Container>
          <div className="grid items-center gap-10 lg:grid-cols-2">
            <div>
              <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-accent-line bg-accent-soft px-3.5 py-1 text-xs font-semibold uppercase tracking-wide text-accent">
                🤖 AI Planner
              </div>
              <h2 className="text-3xl font-black tracking-tight md:text-5xl">
                Plan an entire month of content in minutes
              </h2>
              <p className="mt-4 text-lg text-muted">
                Stop creating posts one at a time. Tell AI what your business is
                about, choose a 7, 15, or 30-day schedule, and AutoSocial AI
                generates the content, organizes it into a calendar, and
                automatically schedules every post across all six connected
                platforms.
              </p>
              <ul className="mt-6 grid gap-3 sm:grid-cols-2">
                {PLANNER_HIGHLIGHTS.map((h) => (
                  <li key={h} className="flex items-start gap-2 text-sm">
                    <span className="mt-0.5 text-accent">✓</span>
                    <span className="text-body">{h}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link to="/register" className="btn btn-primary px-6 py-2.5 text-base">
                  Try AI Planner free
                </Link>
                <Link to="/features" className="btn btn-secondary px-6 py-2.5 text-base">
                  See how it works
                </Link>
              </div>
            </div>
            <PlannerVisual />
          </div>
        </Container>
      </section>

      {/* How AI Planner works */}
      <section className="py-16">
        <Container>
          <SectionHeading
            title="From idea to a full content calendar — in four steps"
            subtitle="AI Planner does the planning, writing, and scheduling for you — you stay in control of every post."
          />
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {PLANNER_WORKFLOW.map((s, i) => (
              <div key={s.title} className="card p-6">
                <div className="mb-4 flex items-center gap-3">
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-accent text-sm font-bold text-accent-contrast">
                    {i + 1}
                  </span>
                  <span className="text-2xl">{s.icon}</span>
                </div>
                <h3 className="font-bold">{s.title}</h3>
                <p className="mt-2 text-sm text-muted">{s.body}</p>
              </div>
            ))}
          </div>
        </Container>
      </section>

      {/* Features overview */}
      <section className="py-16">
        <Container>
          <SectionHeading
            title="Everything you need to post consistently"
            subtitle="From the first idea to the published post, AutoSocial AI handles the parts that usually slow you down."
          />
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <FeatureCard key={f.title} icon={f.icon} title={f.title} tag={f.tag}>
                {f.body}
              </FeatureCard>
            ))}
          </div>
          <div className="mt-8 text-center">
            <Link to="/features" className="btn btn-ghost">
              Explore all features →
            </Link>
          </div>
        </Container>
      </section>

      {/* Why choose */}
      <section className="py-16">
        <Container>
          <SectionHeading
            title="Why teams choose AutoSocial AI"
            subtitle="Less busywork, more consistency — without hiring a full content team."
          />
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {WHY.map((w) => (
              <div
                key={w.title}
                className="card p-6 transition duration-150 hover:-translate-y-0.5 hover:border-accent"
              >
                <div className="mb-4 grid h-12 w-12 place-items-center rounded-xl border border-accent-line bg-accent-soft text-2xl">
                  {w.icon}
                </div>
                <h3 className="font-bold">{w.title}</h3>
                <p className="mt-2 text-sm text-muted">{w.body}</p>
              </div>
            ))}
          </div>
        </Container>
      </section>

      {/* AI capabilities + onboarding */}
      <section className="py-16">
        <Container>
          <div className="grid items-center gap-10 lg:grid-cols-2">
            <div>
              <h2 className="text-3xl font-bold md:text-4xl">One prompt, content for every platform</h2>
              <p className="mt-3 text-muted">
                Give AutoSocial AI a topic and it produces a full set of posts,
                visuals, and hashtags — each adapted to the platform it's meant for.
                Edit anything, or accept the draft and schedule it.
              </p>
              <ul className="mt-6 space-y-3">
                {CAPABILITIES.map((c) => (
                  <li key={c} className="flex items-start gap-2 text-sm">
                    <span className="mt-0.5 text-accent">✓</span>
                    <span className="text-body">{c}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="card p-8">
              <div className="text-sm font-semibold text-accent">
                Personalized onboarding
              </div>
              <h3 className="mt-2 text-2xl font-bold">Content that sounds like you from day one</h3>
              <p className="mt-3 text-sm text-muted">
                A short setup captures your business name, industry, audience, brand
                voice, and goals. AutoSocial AI uses that profile on every
                generation — so you spend time refining, not rewriting from scratch.
              </p>
              <div className="mt-6 grid grid-cols-2 gap-3 text-sm">
                {['Your industry', 'Your audience', 'Your brand voice', 'Your goals'].map((t) => (
                  <div
                    key={t}
                    className="rounded-xl border border-line bg-inset px-3 py-2 font-medium"
                  >
                    {t}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Container>
      </section>

      {/* Social account management */}
      <section className="py-16">
        <Container>
          <div className="card p-8 md:p-12">
            <div className="grid items-center gap-8 md:grid-cols-2">
              <div>
                <h2 className="text-3xl font-bold md:text-4xl">Manage every account in one place</h2>
                <p className="mt-3 text-muted">
                  Connect your social accounts once and manage them all from a
                  single dashboard. See connection status at a glance, refresh
                  access, and publish without logging in and out of each network.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {Object.entries(PLATFORMS).map(([key, p]) => (
                  <span
                    key={key}
                    className="badge border border-line bg-inset px-3 py-1.5"
                  >
                    <span
                      className="grid h-5 w-5 place-items-center rounded-full text-[10px] font-bold text-white"
                      style={{ background: p.color }}
                    >
                      {p.initial}
                    </span>
                    {p.label}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </Container>
      </section>

      {/* Testimonials */}
      <section className="py-16">
        <Container>
          <SectionHeading
            title="Loved by the people who post every day"
            subtitle="Teams use AutoSocial AI to stay consistent, save time, and keep their brand voice."
          />
          <div className="grid gap-5 md:grid-cols-3">
            {TESTIMONIALS.map((t) => (
              <figure key={t.name} className="card flex flex-col p-6">
                <div className="mb-3 text-amber-400">★★★★★</div>
                <blockquote className="flex-1 text-sm text-body">
                  "{t.quote}"
                </blockquote>
                <figcaption className="mt-5 flex items-center gap-3">
                  <span className="grid h-9 w-9 place-items-center rounded-full bg-accent text-sm font-bold text-accent-contrast">
                    {t.initial}
                  </span>
                  <span>
                    <span className="block text-sm font-semibold">{t.name}</span>
                    <span className="block text-xs text-muted">{t.role}</span>
                  </span>
                </figcaption>
              </figure>
            ))}
          </div>
        </Container>
      </section>

      {/* FAQ */}
      <section className="py-16">
        <Container className="max-w-3xl">
          <SectionHeading
            title="Frequently asked questions"
            subtitle="Everything you need to know before you start."
          />
          <div className="space-y-3">
            {FAQ.map((item) => (
              <FaqItem key={item.q} q={item.q} a={item.a} />
            ))}
          </div>
        </Container>
      </section>

      <CTASection
        title="Start creating with AutoSocial AI today"
        subtitle="Create, design, schedule, and publish — all from one dashboard. Free to start."
      />
    </>
  )
}

// Decorative content-calendar illustration for the AI Planner spotlight.
// Purely presentational; fully fluid and theme-aware.
function PlannerVisual() {
  const DURATIONS = ['7 days', '15 days', '30 days']
  // Days that carry a scheduled post in the mock calendar.
  const scheduled = new Set([0, 1, 2, 3, 4, 7, 8, 9, 11, 14, 15, 16, 18, 21, 22, 23, 25, 27])
  return (
    <div className="rounded-2xl border-2 border-accent-line bg-surface p-5 shadow-[0_1px_2px_rgba(22,40,31,0.06)]">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold text-muted">Plan for</span>
        {DURATIONS.map((d, i) => (
          <span
            key={d}
            className={`rounded-full px-3 py-1 text-xs font-semibold ${
              i === 2 ? 'bg-accent text-accent-contrast' : 'border border-line text-muted'
            }`}
          >
            {d}
          </span>
        ))}
      </div>
      <div className="mb-2 grid grid-cols-7 gap-1.5 text-center text-[10px] font-medium text-muted">
        {['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((d, i) => (
          <span key={i}>{d}</span>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1.5">
        {Array.from({ length: 28 }).map((_, i) => {
          const has = scheduled.has(i)
          return (
            <div
              key={i}
              className={`grid aspect-square place-items-center rounded-md border ${
                has ? 'border-accent-line bg-accent-soft' : 'border-line bg-inset'
              }`}
            >
              {has && <span className="h-1.5 w-1.5 rounded-full bg-accent" />}
            </div>
          )
        })}
      </div>
      <div className="mt-4 flex items-center justify-between rounded-xl bg-inset px-3 py-2 text-xs">
        <span className="text-muted">📅 {scheduled.size} posts scheduled</span>
        <span className="font-semibold text-accent">across 6 platforms</span>
      </div>
    </div>
  )
}

function SectionHeading({ title, subtitle }) {
  return (
    <div className="mb-10 text-center">
      <h2 className="text-3xl font-bold md:text-4xl">{title}</h2>
      {subtitle && (
        <p className="mx-auto mt-3 max-w-2xl text-muted">{subtitle}</p>
      )}
    </div>
  )
}

function FaqItem({ q, a }) {
  return (
    <details className="card group p-5 [&_summary::-webkit-details-marker]:hidden">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold">
        {q}
        <span className="text-accent transition group-open:rotate-45">+</span>
      </summary>
      <p className="mt-3 text-sm text-muted">{a}</p>
    </details>
  )
}
