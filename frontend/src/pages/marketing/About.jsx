import { Link } from 'react-router-dom'
import { CtaPanel, PageHero, Section, SectionHead, Split } from './_ui.jsx'
import Seo from '../../components/Seo.jsx'
import Icon from '../../components/marketing/Icon.jsx'
import ProductFrame from '../../components/marketing/ProductFrame.jsx'

// ---------------------------------------------------------------------------
// About, written from the product outward.
//
// Deliberately contains no company history, founding date, team size, customer
// count, award or certification — none of that is established, and inventing it
// is exactly what made the previous version of this page read as generated. The
// credibility here comes from being specific about what is built and blunt
// about what is not.
// ---------------------------------------------------------------------------

const BUILT = [
  'A composer with a live per-platform preview and character limits',
  'AI drafting from a prompt, a URL, a document, an image or an old post',
  'AI image generation, carousels, and a layer-based image editor',
  'A business profile and Brand Kit that steer every generation',
  'A content planner that proposes, writes and schedules a fortnight at a time',
  'A scheduler, a pending queue and a full post history',
  'Publishing to Instagram, Facebook, LinkedIn, X, Threads and Pinterest',
  'A media library of uploads plus curated stock',
  'An ads studio for campaign creative: static, video and copy',
]

const PRINCIPLES = [
  {
    icon: 'shield',
    title: 'Nothing publishes without you',
    body: 'Every draft is editable, and planner posts sit in a review step until you approve them. There is no mode where the software posts something you have not read.',
  },
  {
    icon: 'target',
    title: 'Context beats prompting',
    body: 'The business profile exists so you are not re-explaining your company in every prompt. The more it knows, the less you edit — which is the only measure of an AI feature that matters here.',
  },
  {
    icon: 'alert',
    title: 'Say what is not built',
    body: 'Analytics and team collaboration are not in the product. You will find that written on the features page and the pricing table too, because finding out after signing up is worse for everyone.',
  },
]

export default function About() {
  return (
    <>
      <Seo />
      <PageHero
        title="Why AutoSocial AI exists"
        subtitle="Posting consistently across six networks is not hard because writing is hard. It is hard because the work is scattered across four tools that do not know about each other."
      />

      {/* ---- The problem -------------------------------------------------- */}
      <Section>
        <div className="grid gap-10 lg:grid-cols-2 lg:gap-16">
          <div className="space-y-5 text-lg leading-relaxed text-muted">
            <p>
              The caption gets written in a doc. The image gets made in a design
              app. The finished assets pile up in a downloads folder. Then a
              scheduler asks for all of it again, formatted its own way, one
              network at a time.
            </p>
            <p>
              None of those steps is difficult on its own. The cost is in the
              handoffs — and in the fact that skipping a week is always easier
              than doing the round trip again.
            </p>
          </div>
          <div className="space-y-5 text-lg leading-relaxed">
            <p className="text-body">
              AutoSocial AI puts those steps in one place. You describe an idea
              or bring something you have already written, the draft is written
              for each network you selected, the image is made or picked in the
              same screen, and you see the post the way each network will render
              it before it goes anywhere.
            </p>
            <p className="text-body">
              Then it goes on a calendar, and the calendar publishes it.
            </p>
          </div>
        </div>
      </Section>

      {/* ---- What is built ------------------------------------------------ */}
      <Section tone="surface">
        <Split
          media={
            <ProductFrame
              src="/product/content-planner.webp"
              width={1600}
              height={960}
              label="autosocial.ai/planner"
              alt="The Content Planner review step, with generated posts grouped by day awaiting approval"
            />
          }
        >
          <SectionHead
            eyebrow="What is built"
            title="The whole loop works today"
            subtitle="Not a waiting list, and not a demo. Every item below is a screen you can open once you have an account."
          />
          <ul className="mt-6 space-y-2.5">
            {BUILT.map((item) => (
              <li key={item} className="flex gap-2.5 text-[15px] leading-relaxed">
                <Icon name="check" size={18} className="mt-0.5 shrink-0 text-accent" />
                <span className="text-body">{item}</span>
              </li>
            ))}
          </ul>
          <p className="mt-6 text-[15px] text-muted">
            The{' '}
            <Link to="/features" className="link-accent font-medium">
              features page
            </Link>{' '}
            shows each of these as a screenshot from the running application.
          </p>
        </Split>
      </Section>

      {/* ---- What is not built -------------------------------------------- */}
      <Section>
        <div className="grid gap-10 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] lg:gap-16">
          <SectionHead eyebrow="What is not built" title="The honest gaps" />
          <div className="grid gap-8 sm:grid-cols-2">
            <div>
              <h3 className="flex items-center gap-2 text-lg font-bold">
                <Icon name="chart" size={20} className="text-muted" />
                Analytics
              </h3>
              <p className="mt-2 text-[15px] leading-relaxed text-muted">
                AutoSocial AI does not collect or report on how your posts
                perform. If unified reporting across networks is the reason you
                are shopping, this is not that tool yet.
              </p>
            </div>
            <div>
              <h3 className="flex items-center gap-2 text-lg font-bold">
                <Icon name="users" size={20} className="text-muted" />
                Team collaboration
              </h3>
              <p className="mt-2 text-[15px] leading-relaxed text-muted">
                There are no shared workspaces, roles or approval routing between
                people. An account is one person&rsquo;s workspace, and the
                approval step is your own review of your own posts.
              </p>
            </div>
          </div>
        </div>
      </Section>

      {/* ---- Principles ---------------------------------------------------- */}
      <Section tone="surface">
        <SectionHead
          eyebrow="How we build it"
          title="Three things that decide what ships"
        />
        <div className="mt-12 grid gap-10 md:grid-cols-3">
          {PRINCIPLES.map((p) => (
            <div key={p.title}>
              <Icon name={p.icon} size={22} className="text-accent" />
              <h3 className="mt-3 text-lg font-bold">{p.title}</h3>
              <p className="mt-2 text-[15px] leading-relaxed text-muted">{p.body}</p>
            </div>
          ))}
        </div>
      </Section>

      <CtaPanel
        title="Try it against your own brand"
        subtitle="Create an account, fill in the business profile, and see what the first set of drafts looks like."
        secondary={{ to: '/contact', label: 'Ask us something' }}
      />
    </>
  )
}
