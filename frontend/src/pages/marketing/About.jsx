import { Container, CTASection, PageHero } from './_ui.jsx'
import Seo from '../../components/Seo.jsx'

const VALUES = [
  { icon: '🎯', title: 'Brand before AI', body: 'AI should sound like you, not like a robot. Everything we build starts from your voice, your audience, and your goals.' },
  { icon: '⏱️', title: 'Respect people\'s time', body: 'Every feature earns its place by removing work. If it doesn\'t save you time, it doesn\'t ship.' },
  { icon: '🧭', title: 'You stay in control', body: 'AutoSocial drafts and suggests — you review and decide. Nothing publishes without your approval.' },
  { icon: '🔒', title: 'Trust by default', body: 'Your content and connected accounts are handled with care, clear permissions, and straightforward privacy.' },
]

const ROADMAP = [
  { when: 'Now', title: 'Content, images & scheduling', body: 'AI post, image, caption, and carousel generation, multi-platform publishing, and a smart scheduler — live today.', done: true },
  { when: 'Next', title: 'Analytics', body: 'Unified performance reporting across every connected platform, so you can see what works in one place.' },
  { when: 'Next', title: 'Team collaboration', body: 'Shared workspaces, roles, and approval workflows for agencies and teams managing multiple brands.' },
  { when: 'Later', title: 'Public API & integrations', body: 'Connect AutoSocial AI to your own tools and automate content workflows end to end.' },
]

export default function About() {
  return (
    <>
      <Seo
        title="About"
        description="AutoSocial AI helps businesses, agencies, and creators stay consistently visible online. Learn about our mission, our values, and where we're headed."
      />
      <PageHero
        eyebrow="About"
        title="We help teams show up online — consistently"
        subtitle="AutoSocial AI is built for busy founders, marketers, agencies, and creators who know consistency wins, but never have enough hours to make it happen."
      />

      <section className="pb-8">
        <Container>
          {/* Mission & Vision */}
          <div className="grid gap-6 md:grid-cols-2">
            <div className="card p-8">
              <div className="text-sm font-semibold text-accent">Our mission</div>
              <h2 className="mt-2 text-2xl font-bold">Make consistent, on-brand content effortless</h2>
              <p className="mt-4 text-muted">
                Great social media rewards those who show up every day — but creating
                on-brand content across six platforms is exhausting. Our mission is to
                take that weight off your plate, turning a single idea into a full set
                of platform-ready posts, visuals, and a schedule you can actually keep.
              </p>
            </div>
            <div className="card p-8">
              <div className="text-sm font-semibold text-accent">Our vision</div>
              <h2 className="mt-2 text-2xl font-bold">A content team in every dashboard</h2>
              <p className="mt-4 text-muted">
                We picture a world where any business — from a solo recruiter to a
                growing agency — has the creative output of a full team, without the
                overhead. AutoSocial AI is how we get there: one place to create,
                design, schedule, and publish everything.
              </p>
            </div>
          </div>

          {/* Why we built it */}
          <div className="mt-6 card p-8 md:p-10">
            <h2 className="text-2xl font-bold">Why we built AutoSocial AI</h2>
            <p className="mt-4 text-muted">
              We kept seeing the same story: talented teams with real expertise going
              quiet online — not because they had nothing to say, but because posting
              consistently took too many tools, too much time, and too much
              second-guessing. Writing in one app, designing in another, scheduling in
              a third, and still missing days.
            </p>
            <p className="mt-4 text-muted">
              AutoSocial AI brings all of it into one workflow. You bring the ideas and
              the judgment; the platform handles the drafting, the design, and the
              logistics. The result is simple — you stay visible and on-brand, while
              the busywork disappears.
            </p>
          </div>

          {/* Values */}
          <div className="mt-10">
            <h2 className="mb-6 text-center text-2xl font-bold md:text-3xl">What we value</h2>
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              {VALUES.map((v) => (
                <div key={v.title} className="card p-6">
                  <div className="mb-3 text-2xl">{v.icon}</div>
                  <h3 className="font-bold">{v.title}</h3>
                  <p className="mt-2 text-sm text-muted">{v.body}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Roadmap */}
          <div className="mt-12">
            <h2 className="mb-6 text-center text-2xl font-bold md:text-3xl">Where we're headed</h2>
            <div className="grid gap-4 md:grid-cols-2">
              {ROADMAP.map((r) => (
                <div key={r.title} className="card flex gap-4 p-6">
                  <div className="shrink-0">
                    <span
                      className={`badge ${
                        r.done
                          ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-300'
                          : 'bg-accent-soft text-accent'
                      }`}
                    >
                      {r.when}
                    </span>
                  </div>
                  <div>
                    <h3 className="font-bold">{r.title}</h3>
                    <p className="mt-1 text-sm text-muted">{r.body}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Container>
      </section>

      <CTASection />
    </>
  )
}
