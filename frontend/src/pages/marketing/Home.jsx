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
  { icon: '✍️', title: 'AI Post Generator', body: 'Describe an idea and get ready-to-publish posts tailored to each platform — hooks, body, and call to action included.' },
  { icon: '🎨', title: 'AI Image & Carousels', body: 'Turn a topic into scroll-stopping visuals and multi-slide carousels, sized correctly for every network.' },
  { icon: '#️⃣', title: 'Captions & Hashtags', body: 'Get platform-aware captions and relevant hashtag sets that match your topic and audience — no guessing.' },
  { icon: '🗓️', title: 'Smart Scheduler', body: 'Plan a week or a month on a visual calendar and let AutoSocial publish at the times your audience is active.' },
  { icon: '📤', title: 'Multi-Platform Publishing', body: 'Connect your accounts once and push finished content everywhere from a single screen.' },
  { icon: '🎯', title: 'Brand Personalization', body: 'Your business profile shapes every draft, so the output already sounds like you before you edit a word.' },
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
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-indigo-500/20 bg-indigo-500/10 px-3 py-1 text-xs font-semibold text-indigo-500 dark:text-indigo-300">
            ✦ {SITE.slogan}
          </div>
          <h1 className="mx-auto max-w-4xl text-4xl font-black leading-[1.1] tracking-tight md:text-6xl">
            Create, design, and schedule{' '}
            <span className="bg-gradient-to-r from-indigo-500 to-violet-500 bg-clip-text text-transparent">
              social content in minutes
            </span>
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-lg text-slate-500 dark:text-slate-400">
            AutoSocial AI writes your captions, designs your visuals, and publishes
            to every platform — so you stay consistent without living in six
            different apps.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link to="/register" className="btn btn-primary px-6 py-2.5 text-base">
              Start for free
            </Link>
            <Link to="/features" className="btn btn-ghost px-6 py-2.5 text-base">
              See how it works
            </Link>
          </div>
          <p className="mt-4 text-xs text-slate-400">
            No credit card required · Free plan available
          </p>

          {/* Supported platforms */}
          <div className="mt-12">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              Publish everywhere you post
            </p>
            <div className="mt-4 flex flex-wrap items-center justify-center gap-3">
              {Object.entries(PLATFORMS).map(([key, p]) => (
                <span
                  key={key}
                  className="badge border border-slate-200 bg-white/60 px-3 py-1 dark:border-white/10 dark:bg-white/5"
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
      <section className="border-y border-slate-200 bg-white/40 py-8 dark:border-white/10 dark:bg-slate-900/20">
        <Container>
          <p className="text-center text-sm text-slate-500 dark:text-slate-400">
            Built for marketers, agencies, recruiters, startups, and creators —
            trusted by fast-moving teams to stay visible every day.
          </p>
          <div className="mt-5 flex flex-wrap items-center justify-center gap-x-10 gap-y-3 text-sm font-semibold text-slate-400">
            <span>NorthPeak</span>
            <span>Loomly Studio</span>
            <span>BrightHire</span>
            <span>Onda Labs</span>
            <span>Fieldwork</span>
            <span>Ketchup&nbsp;Media</span>
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
              <FeatureCard key={f.title} icon={f.icon} title={f.title}>
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
              <div key={w.title} className="card p-6">
                <div className="mb-3 text-2xl">{w.icon}</div>
                <h3 className="font-bold">{w.title}</h3>
                <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{w.body}</p>
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
              <p className="mt-3 text-slate-500 dark:text-slate-400">
                Give AutoSocial AI a topic and it produces a full set of posts,
                visuals, and hashtags — each adapted to the platform it's meant for.
                Edit anything, or accept the draft and schedule it.
              </p>
              <ul className="mt-6 space-y-3">
                {CAPABILITIES.map((c) => (
                  <li key={c} className="flex items-start gap-2 text-sm">
                    <span className="mt-0.5 text-indigo-500 dark:text-indigo-400">✓</span>
                    <span className="text-slate-600 dark:text-slate-300">{c}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="card p-8">
              <div className="text-sm font-semibold text-indigo-500 dark:text-indigo-300">
                Personalized onboarding
              </div>
              <h3 className="mt-2 text-2xl font-bold">Content that sounds like you from day one</h3>
              <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">
                A short setup captures your business name, industry, audience, brand
                voice, and goals. AutoSocial AI uses that profile on every
                generation — so you spend time refining, not rewriting from scratch.
              </p>
              <div className="mt-6 grid grid-cols-2 gap-3 text-sm">
                {['Your industry', 'Your audience', 'Your brand voice', 'Your goals'].map((t) => (
                  <div
                    key={t}
                    className="rounded-xl border border-slate-200 bg-white/60 px-3 py-2 font-medium dark:border-white/10 dark:bg-white/5"
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
                <p className="mt-3 text-slate-500 dark:text-slate-400">
                  Connect your social accounts once and manage them all from a
                  single dashboard. See connection status at a glance, refresh
                  access, and publish without logging in and out of each network.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {Object.entries(PLATFORMS).map(([key, p]) => (
                  <span
                    key={key}
                    className="badge border border-slate-200 bg-white/60 px-3 py-1.5 dark:border-white/10 dark:bg-white/5"
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
                <blockquote className="flex-1 text-sm text-slate-600 dark:text-slate-300">
                  "{t.quote}"
                </blockquote>
                <figcaption className="mt-5 flex items-center gap-3">
                  <span className="grid h-9 w-9 place-items-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 text-sm font-bold text-white">
                    {t.initial}
                  </span>
                  <span>
                    <span className="block text-sm font-semibold">{t.name}</span>
                    <span className="block text-xs text-slate-400">{t.role}</span>
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

function SectionHeading({ title, subtitle }) {
  return (
    <div className="mb-10 text-center">
      <h2 className="text-3xl font-bold md:text-4xl">{title}</h2>
      {subtitle && (
        <p className="mx-auto mt-3 max-w-2xl text-slate-500 dark:text-slate-400">{subtitle}</p>
      )}
    </div>
  )
}

function FaqItem({ q, a }) {
  return (
    <details className="card group p-5 [&_summary::-webkit-details-marker]:hidden">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold">
        {q}
        <span className="text-indigo-500 transition group-open:rotate-45 dark:text-indigo-300">+</span>
      </summary>
      <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">{a}</p>
    </details>
  )
}
