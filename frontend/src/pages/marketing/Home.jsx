import { Link } from 'react-router-dom'
import {
  Container,
  CtaPanel,
  FaqItem,
  PointList,
  Section,
  SectionHead,
  Split,
} from './_ui.jsx'
import Seo from '../../components/Seo.jsx'
import Icon from '../../components/marketing/Icon.jsx'
import ProductFrame from '../../components/marketing/ProductFrame.jsx'
import PlatformIcon from '../../components/PlatformIcon.jsx'
import { PLATFORMS, PLATFORM_KEYS } from '../../lib/constants'
import { PLANS } from '../../config/pricing'
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

// Every claim below is checked against a screen that exists in the app. Nothing
// here describes analytics, team workflows or billing, none of which are built.

const STEPS = [
  {
    icon: 'link',
    title: 'Connect',
    body: 'Link each network once. Status and token health stay visible on one screen.',
    shot: { src: '/product/social-accounts.webp', w: 1600, h: 1003, alt: 'The Social Accounts screen with five networks connected' },
  },
  {
    icon: 'pencil',
    title: 'Create',
    body: 'Write it yourself or start from an idea, a link or a file, then edit the draft.',
    shot: { src: '/product/ai-generator.webp', w: 1600, h: 960, alt: 'The AI Generator showing a draft per platform' },
  },
  {
    icon: 'calendar',
    title: 'Plan',
    body: 'Put posts on the calendar, or let the planner lay out a whole fortnight.',
    shot: { src: '/product/scheduler.webp', w: 1600, h: 1003, alt: 'The Scheduler month calendar with scheduled posts' },
  },
  {
    icon: 'send',
    title: 'Publish',
    body: 'Publish now or leave it scheduled. Everything that went out stays in Post History.',
    shot: { src: '/product/post-history.webp', w: 1600, h: 1003, alt: 'The Post History table showing published and scheduled posts' },
  },
]

const REASONS = [
  {
    icon: 'library',
    title: 'One workspace',
    body: 'Caption, image, preview, calendar and the connection to each network are the same screen — not four subscriptions and a downloads folder.',
  },
  {
    icon: 'pencil',
    title: 'Less retyping',
    body: 'One idea becomes a draft for every network you selected, each already inside that network\'s character limit.',
  },
  {
    icon: 'palette',
    title: 'Consistent branding',
    body: 'Your business profile and Brand Kit are applied to every generation, so drafts arrive sounding and looking like you.',
  },
  {
    icon: 'calendar',
    title: 'Easier planning',
    body: 'See the month rather than the next post. Nothing is scheduled until you have read it and approved it.',
  },
  {
    icon: 'send',
    title: 'Publishing in one place',
    body: 'Six networks from one screen, with per-platform previews and warnings before anything goes out.',
  },
]

const FAQ = [
  {
    q: 'Which platforms can I publish to?',
    a: 'Instagram, Facebook, LinkedIn, X, Threads and Pinterest. You connect one account per network, and you can publish to any combination of them from a single screen.',
  },
  {
    q: 'What do I need to connect an Instagram account?',
    a: 'Instagram publishing goes through the Meta Graph API, so your Instagram account needs to be a Professional account (Business or Creator) linked to a Facebook Page you manage. The Social Accounts screen walks you through it if a connection fails.',
  },
  {
    q: 'Will the writing sound like my brand?',
    a: 'You fill in a business profile once — what you do, who you are talking to, how you sound, what you are trying to achieve. Every generation is written with that context, so drafts start closer to publishable. You can still edit every word.',
  },
  {
    q: 'Can I edit anything before it publishes?',
    a: 'Yes, and nothing publishes on its own. Generated drafts are fully editable, and posts created by the Content Planner sit in a review step until you approve them.',
  },
  {
    q: 'Can I see how a post will look on each network?',
    a: 'The composer shows a live preview per platform as you type, along with a character counter set to the tightest limit among the networks you selected, and warnings when something will not work on a given network.',
  },
  {
    q: 'Where do the images come from?',
    a: 'Three places: AI image generation, the built-in media library of curated stock photography, or your own uploads. Images can be edited on a layer canvas, and your Brand Kit can be applied over them.',
  },
  {
    q: 'Is there a free plan?',
    a: 'Yes. You can create an account and start without a card.',
  },
  {
    q: 'What is not built yet?',
    a: 'Analytics and team collaboration. There is no performance reporting inside AutoSocial AI today, and no shared workspaces, roles or approval routing between teammates. Both are in development, and we would rather say so here than let you find out after signing up.',
  },
]

export default function Home() {
  return (
    <>
      <Seo jsonLd={JSON_LD} />

      {/* ---- Hero ------------------------------------------------------- */}
      <section className="border-b border-line bg-surface pb-16 pt-16 md:pb-20 md:pt-24">
        <Container>
          <div className="mx-auto max-w-3xl text-center">
            <h1 className="text-balance text-4xl font-bold leading-[1.06] tracking-tight md:text-6xl">
              Create, plan and publish your social content from one place
            </h1>
            <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-muted md:text-xl">
              AutoSocial AI is a workspace for social media. Write the post or
              have AI draft it, generate or choose the image, see exactly how it
              will look on each network, then put it on the calendar and publish.
            </p>

            <div className="mt-8 flex flex-wrap justify-center gap-3">
              <Link to="/register" className="btn btn-primary px-7 py-3 text-base">
                Start free
              </Link>
              <Link to="/features" className="btn btn-secondary px-7 py-3 text-base">
                See how it works
              </Link>
            </div>
            <p className="mt-4 text-sm text-muted">
              Free plan available. No credit card required.
            </p>

            <ul className="mt-8 flex flex-wrap items-center justify-center gap-x-5 gap-y-3">
              {PLATFORM_KEYS.map((key) => (
                <li key={key} className="flex items-center gap-2 text-sm text-muted">
                  <PlatformIcon platform={key} size={22} />
                  {PLATFORMS[key].label}
                </li>
              ))}
            </ul>
          </div>

          {/* The product itself, as the largest thing on the page. */}
          <div className="mt-14">
            <ProductFrame
              priority
              src="/product/create-post.webp"
              width={1600}
              height={960}
              mobileSrc="/product/m-create-post.webp"
              mobileWidth={860}
              mobileHeight={1720}
              label="autosocial.ai/create"
              alt="The Create Post screen: platform selection, a written caption with an attached image, and a live Instagram preview of the finished post beside it"
            />
          </div>
        </Container>
      </section>

      {/* ---- Problem ---------------------------------------------------- */}
      <Section>
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-16">
          <SectionHead
            eyebrow="The problem"
            title="Most social posts pass through four tools before they go live"
          />
          <div className="max-w-xl space-y-5 text-lg leading-relaxed text-muted">
            <p>
              A doc for the caption. A design app for the image. A downloads
              folder for the assets. A scheduler that wants all of it again,
              formatted its way. Every handoff is somewhere the work can stall —
              which is why the posts you planned on Monday are still unpublished
              on Friday.
            </p>
            <p className="text-body">
              AutoSocial AI keeps those steps together: the writing, the image,
              the preview, the calendar, and the connection to each network.
            </p>
          </div>
        </div>
      </Section>

      {/* ---- Create ----------------------------------------------------- */}
      <Section tone="surface">
        <Split
          media={
            <ProductFrame
              src="/product/ai-generator.webp"
              width={1600}
              height={960}
              label="autosocial.ai/generate"
              alt="The AI Generator with an idea typed on the left and finished Instagram and Facebook drafts on the right, each with its own character count and hashtags"
            />
          }
        >
          <SectionHead
            eyebrow="Create"
            title="Start from an idea — or a link, a document, or a post you have already written"
            subtitle="Describe what you want and get a draft written for each network you selected. Adjust the tone, translate it, shorten it, or write the whole thing yourself."
          />
          <PointList
            items={[
              'Sources: a prompt, a blog or product URL, pasted text, a PDF, DOCX or TXT file, an image, or an existing post to rewrite',
              'AI Assist rewrites, shortens, expands, changes tone, or translates into eight languages',
              'A character counter tracks the tightest limit among the platforms you picked',
            ]}
          />
        </Split>
      </Section>

      {/* ---- Brand ------------------------------------------------------ */}
      <Section>
        <Split
          reverse
          media={
            <ProductFrame
              src="/product/brand-kit.webp"
              width={1600}
              height={1003}
              label="autosocial.ai/business-profile"
              alt="The Brand Kit section of the business profile: logo upload, three brand colours, contact details, and a live preview of how the branding is laid over an image"
            />
          }
        >
          <SectionHead
            eyebrow="Brand"
            title="Set your brand once. Every draft starts there"
            subtitle="Your business profile — what you do, who you are talking to, how you sound, what you are trying to achieve — is applied to every generation, so drafts arrive closer to publishable."
          />
          <PointList
            items={[
              'Industry, description, audience, brand voice and goals feed every generation',
              'Brand Kit holds your logo, colours and contact details',
              'Branding is laid over generated images as layers you can still move and edit',
            ]}
          />
        </Split>
      </Section>

      {/* ---- Plan ------------------------------------------------------- */}
      <Section tone="surface">
        <Split
          media={
            <ProductFrame
              src="/product/content-planner.webp"
              width={1600}
              height={960}
              label="autosocial.ai/planner"
              alt="The Content Planner review step: posts grouped by day, each with its platform, content type, a pending badge, a scheduled time and edit, regenerate and delete actions"
            />
          }
        >
          <SectionHead
            eyebrow="Plan"
            title="See the whole fortnight, not just the next post"
            subtitle="Choose how far ahead to plan and how often to post. AutoSocial AI proposes a theme and a topic for each day, writes the posts, and lays them out on a calendar."
          />
          <PointList
            items={[
              'Plan 7, 14 or 30 days, at a posting frequency you choose',
              'Every post can be edited, regenerated or removed before it is scheduled',
              'Nothing publishes until you approve it',
            ]}
          />
        </Split>

        {/* The calendar is the other half of planning, and it earns its own
            full-width row rather than being stacked under the prose. */}
        <div className="mt-14">
          <ProductFrame
            src="/product/scheduler.webp"
            width={1600}
            height={1003}
            mobileSrc="/product/m-scheduler.webp"
            mobileWidth={860}
            mobileHeight={1720}
            label="autosocial.ai/scheduler"
            alt="The Scheduler: a month calendar with scheduled posts on their days beside a pending queue with publish and cancel actions"
            caption="Everything queued sits on one calendar, with a pending list you can publish early or cancel from."
          />
        </div>
      </Section>

      {/* ---- Connect ---------------------------------------------------- */}
      <Section>
        <Split
          reverse
          media={
            <ProductFrame
              src="/product/social-accounts.webp"
              width={1600}
              height={1003}
              label="autosocial.ai/accounts"
              alt="The Social Accounts screen showing five of six networks connected, with per-account status, last sync times and reconnect actions"
            />
          }
        >
          <SectionHead
            eyebrow="Connect"
            title="Connect each account once"
            subtitle="Six networks, one connection each, all on one screen with their current status. When a token expires you refresh it from the same card — you do not find out because a post failed."
          />
          <PointList
            items={[
              'Instagram, Facebook, LinkedIn, X, Threads and Pinterest',
              'Per-account status: connected, token expired, syncing or error',
              'Pinterest posts to a board you choose; Instagram needs a Professional account linked to a Page',
            ]}
          />
        </Split>
      </Section>

      {/* ---- Media ------------------------------------------------------ */}
      <Section tone="surface">
        <SectionHead
          eyebrow="Media"
          title="Your images and a stock library, in one search box"
          subtitle="Everything you have uploaded plus a curated stock set, filtered by category, tag and shape, and droppable straight onto the canvas."
        />
        <div className="mt-10">
          <ProductFrame
            src="/product/media-library.webp"
            width={1600}
            height={1003}
            label="autosocial.ai/ads/media-library"
            alt="The Media Library: All, My Library and Stock tabs above a search box, category filter chips, and a grid of stock photographs"
          />
        </div>
      </Section>

      {/* ---- Ads Studio ------------------------------------------------- */}
      <Section>
        <Split
          media={
            <ProductFrame
              src="/product/ads-studio.webp"
              width={1600}
              height={960}
              label="autosocial.ai/ads"
              alt="A campaign inside AI Ads Studio, listing the creative tools it can run: product ads, banner generator, carousel ads, four video tools, ad copy, headlines and CTAs"
            />
          }
        >
          <SectionHead
            eyebrow="Ads Studio"
            title="Ad creative lives in the same workspace"
            subtitle="Brief a campaign once — what you are advertising, to whom, on which platforms — and every tool inside it works from that brief instead of asking again."
          />
          <PointList
            items={[
              'Product ads, banner sets, carousel ads and website promotion creative',
              'Video tools: image to video, text to video, product showcase and slideshow',
              'Copy tools: ad copy, headlines, calls to action and A/B variants',
              'Everything a tool generates is saved into the campaign automatically',
            ]}
          />
          <p className="mt-6 text-sm text-muted">
            Ad performance reporting is not part of AutoSocial AI — campaigns are
            where the creative is made, not where results are measured.
          </p>
        </Split>
      </Section>

      {/* ---- How it works ----------------------------------------------- */}
      <Section tone="surface">
        <SectionHead
          eyebrow="How it works"
          title="Four steps, and you have seen all of them already"
          subtitle="No illustrations here — each step is the screen you will actually use."
        />
        <ol className="mt-12 grid gap-10 md:grid-cols-2 lg:grid-cols-4 lg:gap-6">
          {STEPS.map((step, i) => (
            <li key={step.title}>
              <div className="mb-4 flex items-center gap-3">
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full border border-accent-line bg-accent-soft text-sm font-bold text-accent">
                  {i + 1}
                </span>
                <h3 className="flex items-center gap-2 text-lg font-bold">
                  <Icon name={step.icon} size={18} className="text-accent" />
                  {step.title}
                </h3>
              </div>
              <ProductFrame
                src={step.shot.src}
                width={step.shot.w}
                height={step.shot.h}
                alt={step.shot.alt}
              />
              <p className="mt-4 text-[15px] leading-relaxed text-muted">{step.body}</p>
            </li>
          ))}
        </ol>
      </Section>

      {/* ---- Product tour ----------------------------------------------- */}
      <Section>
        <SectionHead
          eyebrow="Product tour"
          title="A closer look at the workspace"
        />
        <div className="mt-10 grid gap-8 lg:grid-cols-2">
          <ProductFrame
            className="lg:col-span-2"
            src="/product/dashboard.webp"
            width={1600}
            height={621}
            mobileSrc="/product/m-dashboard.webp"
            mobileWidth={860}
            mobileHeight={1720}
            label="autosocial.ai/dashboard"
            alt="The Dashboard: counts of total, scheduled, published and failed posts above an upcoming schedule list and recent activity"
            caption="Dashboard — what is queued, what went out, and what failed."
          />
          <ProductFrame
            src="/product/planner-setup.webp"
            width={1600}
            height={960}
            label="autosocial.ai/planner"
            alt="The Content Planner setup step: planning period, posting frequency, platform selection and content goals, with a plan summary beside it"
            caption="Content Planner — set the period, cadence, platforms and goals before AI proposes anything."
          />
          <ProductFrame
            src="/product/ai-generator-sources.webp"
            width={1600}
            height={960}
            label="autosocial.ai/generate"
            alt="The AI Generator input panel: a create-from source selector, tone, platform toggles, content types and an image template"
            caption="AI Generator — start from a prompt, a URL, a document, an image, or a post you already published."
          />
        </div>
      </Section>

      {/* ---- Why -------------------------------------------------------- */}
      <Section tone="surface">
        <SectionHead
          eyebrow="Why AutoSocial AI"
          title="What actually changes about your week"
        />
        <div className="mt-12 grid gap-x-10 gap-y-10 md:grid-cols-2 lg:grid-cols-3">
          {REASONS.map((r) => (
            <div key={r.title}>
              <Icon name={r.icon} size={22} className="text-accent" />
              <h3 className="mt-3 text-lg font-bold">{r.title}</h3>
              <p className="mt-2 text-[15px] leading-relaxed text-muted">{r.body}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* ---- Pricing preview -------------------------------------------- */}
      <Section>
        <SectionHead
          eyebrow="Pricing"
          title="Start free, move up when you need more"
          subtitle="Every plan starts by creating an account."
        />
        <div className="mt-10 grid gap-5 md:grid-cols-3">
          {PLANS.map((plan) => (
            <div
              key={plan.id}
              className={`card flex flex-col p-6 ${plan.highlight ? 'border-accent' : ''}`}
            >
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-muted">{plan.name}</span>
                {plan.highlight && (
                  <span className="badge badge-accent">Most popular</span>
                )}
              </div>
              <div className="mt-3 flex items-baseline gap-1">
                <span className="text-3xl font-bold tracking-tight">{plan.price}</span>
                <span className="text-sm text-muted">{plan.cadence}</span>
              </div>
              <p className="mt-1 text-sm text-muted">{plan.tagline}</p>
              <ul className="mt-5 flex-1 space-y-2.5 text-sm">
                {plan.features.slice(0, 4).map((f) => (
                  <li key={f} className="flex gap-2.5">
                    <Icon name="check" size={16} className="mt-0.5 shrink-0 text-accent" />
                    <span className="text-body">{f}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="mt-8">
          <Link to="/pricing" className="inline-flex items-center gap-2 font-semibold link-accent">
            Compare all plans
            <Icon name="arrowRight" size={18} />
          </Link>
        </div>
      </Section>

      {/* ---- FAQ -------------------------------------------------------- */}
      <Section tone="surface">
        <div className="grid gap-10 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)] lg:gap-16">
          <SectionHead
            eyebrow="FAQ"
            title="Questions worth asking before you sign up"
          />
          <div>
            {FAQ.map((item) => (
              <FaqItem key={item.q} q={item.q} a={item.a} />
            ))}
          </div>
        </div>
      </Section>

      <CtaPanel />
    </>
  )
}
