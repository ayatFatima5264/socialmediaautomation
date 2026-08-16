import { Container, CtaPanel, PageHero, PointList, Section, SectionHead, Split } from './_ui.jsx'
import Seo from '../../components/Seo.jsx'
import Icon from '../../components/marketing/Icon.jsx'
import ProductFrame from '../../components/marketing/ProductFrame.jsx'

// ---------------------------------------------------------------------------
// A product tour, not a card grid.
//
// Every block below is one screen that exists in the application, shown as a
// screenshot taken from it. Nothing is described that the product cannot do:
// features still in development are listed separately at the bottom, visually
// quieter, and clearly labelled as unavailable.
// ---------------------------------------------------------------------------

const FEATURES = [
  {
    id: 'create-post',
    eyebrow: 'Create Post',
    title: 'Write it, see it, then publish it',
    body: 'The composer holds everything one post needs: the caption, the media, the link, the hashtags, the first comment, and the schedule. A live preview beside it renders the post the way each network will, so you are not guessing at line breaks or where the caption gets truncated.',
    points: [
      'A live preview per platform, updating as you type',
      'Character counter set to the tightest limit among the platforms you selected',
      'Warnings before publishing when something will not work on a given network',
      'Publish now, or schedule it for a time in your own timezone',
    ],
    shot: {
      src: '/product/create-post.webp',
      w: 1600,
      h: 960,
      mobile: '/product/m-create-post.webp',
      label: 'autosocial.ai/create',
      alt: 'The Create Post composer with platform toggles, a written caption, an attached image and a live Instagram preview',
    },
  },
  {
    id: 'ai-generator',
    eyebrow: 'AI Generator',
    title: 'Start from whatever you already have',
    body: 'A blank prompt is only one of the ways in. Paste a blog post, drop in a PDF, point it at a product page, upload an image, or hand it something you published last year and ask for a rewrite. You get a separate draft for each network, written for that network.',
    points: [
      'Sources: prompt, blog URL, website URL, product URL, pasted article, plain text, PDF, DOCX, TXT, image, or an existing post',
      'Tone and audience controls, with optional hashtag suggestions',
      'Per-platform image overrides — different aspect ratio or style per network',
      'A LinkedIn article writer with an editable title, cover, body and tags',
    ],
    shot: {
      src: '/product/ai-generator.webp',
      w: 1600,
      h: 960,
      label: 'autosocial.ai/generate',
      alt: 'Generated Instagram and Facebook drafts side by side, each with hashtags, a character count and per-draft actions',
    },
  },
  {
    id: 'images',
    eyebrow: 'Visuals',
    title: 'Make the picture where you write the caption',
    body: 'Images are generated from the post you are working on, sized for the platform it is going to. Aspect ratio, visual style and quality are all set in the same panel as the copy, and carousels are generated as a set rather than slide by slide.',
    points: [
      'Aspect ratios for square, portrait, story, landscape and Pin',
      'Fifteen visual styles, including industry presets',
      'Multi-slide carousels, sized correctly per network',
      'Negative prompts and an optional prompt enhancer',
    ],
    shot: {
      src: '/product/ai-generator-sources.webp',
      w: 1600,
      h: 960,
      label: 'autosocial.ai/generate',
      alt: 'The generator input panel showing the create-from source selector, tone, platform toggles, content types and the image template picker',
    },
  },
  {
    id: 'brand-kit',
    eyebrow: 'Brand Kit',
    title: 'Your brand, applied without you asking',
    body: 'Fill in the business profile once and every generation is written with it. The Brand Kit adds the visual half — logo, colours, contact details — laid over generated images as real layers you can still move, restyle or remove.',
    points: [
      'Industry, description, audience, brand voice and goals steer the copy',
      'Logo, brand colours and contact details steer the visuals',
      'A profile-strength meter shows what is still worth filling in',
      'The preview renders with the same layer engine the generator uses',
    ],
    shot: {
      src: '/product/brand-kit.webp',
      w: 1600,
      h: 1003,
      label: 'autosocial.ai/business-profile',
      alt: 'The Brand Kit editor with logo upload, three brand colours, contact fields and a live preview of the branding overlay',
    },
  },
  {
    id: 'planner',
    eyebrow: 'Content Planner',
    title: 'Plan a fortnight instead of a post',
    body: 'Tell the planner how far ahead to plan, how often to post and what mix of content you want. It proposes a theme and a topic per day, writes the posts, then hands them back grouped by day for review. Nothing reaches the calendar until you approve it.',
    points: [
      'Plans of 7, 14 or 30 days at daily, five-a-week, three-a-week or a custom cadence',
      'A strategy step you can edit before a single post is written',
      'Every post editable, regenerable or removable in review',
      'Quick Generate repeats the whole thing from your saved defaults',
    ],
    shot: {
      src: '/product/content-planner.webp',
      w: 1600,
      h: 960,
      label: 'autosocial.ai/planner',
      alt: 'The planner review step with posts grouped by day, each showing platform, content type, pending status and a scheduled time',
    },
  },
  {
    id: 'scheduler',
    eyebrow: 'Scheduler',
    title: 'One calendar for everything queued',
    body: 'A month view of what is going out and when, with a pending queue beside it. Publish something early, cancel it, or move it — the calendar and the queue are the same data, so they can never disagree.',
    points: [
      'Month calendar with each post on its day, marked by network',
      'Pending queue with publish-now and cancel on every item',
      'Scheduling respects the timezone on your account',
    ],
    shot: {
      src: '/product/scheduler.webp',
      w: 1600,
      h: 1003,
      mobile: '/product/m-scheduler.webp',
      label: 'autosocial.ai/scheduler',
      alt: 'The Scheduler month calendar with scheduled posts and a pending list showing publish and cancel actions',
    },
  },
  {
    id: 'accounts',
    eyebrow: 'Social Accounts',
    title: 'Six networks, connected once',
    body: 'Connect an account per network and see the health of all of them on one screen. When a token expires or a permission is missing, the card says so and tells you what to do about it, rather than letting a scheduled post fail quietly.',
    points: [
      'Instagram, Facebook, LinkedIn, X, Threads and Pinterest',
      'Status per account: connected, token expired, syncing or error',
      'Reconnect and disconnect without leaving the page',
      'Pinterest board selection, and Instagram setup guidance when a connection fails',
    ],
    shot: {
      src: '/product/social-accounts.webp',
      w: 1600,
      h: 1003,
      label: 'autosocial.ai/accounts',
      alt: 'Six platform cards showing five connected accounts, one not connected, and one needing reconnection',
    },
  },
  {
    id: 'media',
    eyebrow: 'Media Library',
    title: 'Uploads and stock in the same search box',
    body: 'Everything you have uploaded sits alongside a curated stock set. Filter by category, tag or shape, and drop an image straight into whatever you are working on — it is the same library whether you open it from the editor or browse it on its own.',
    points: [
      'All, My Library and Stock views over one search',
      'Filter by category, tag or image shape',
      'Drag an image straight onto the editor canvas',
    ],
    shot: {
      src: '/product/media-library.webp',
      w: 1600,
      h: 1003,
      label: 'autosocial.ai/ads/media-library',
      alt: 'The media library grid with tabs, a search field, category chips and rows of stock photographs',
    },
  },
  {
    id: 'ads',
    eyebrow: 'AI Ads Studio',
    title: 'Ad creative, briefed once',
    body: 'A campaign records what you are advertising, to whom, on which platforms and in what tone. Every tool inside the campaign inherits that brief, and everything they produce is saved back into it automatically.',
    points: [
      'Creative tools: product ads, banner sets, carousel ads, website promotion',
      'Video tools: image to video, text to video, product showcase, slideshow',
      'Copy tools: ad copy, headlines, calls to action, A/B variants',
      'Starting layouts sized per placement and wired to your Brand Kit',
    ],
    shot: {
      src: '/product/ads-studio.webp',
      w: 1600,
      h: 960,
      label: 'autosocial.ai/ads',
      alt: 'A campaign page listing the creative tools available inside it, from product ads through to CTA generation',
    },
  },
]

// Real, shipped, and not worth a full screenshot each.
const ALSO = [
  'Import from a PDF, DOCX or TXT file',
  'Rewrite, shorten or expand any draft in place',
  'Change tone, or translate into eight languages',
  'Hashtag suggestions per platform',
  'First comment for Instagram and LinkedIn',
  'Pinterest board selection and board creation',
  'LinkedIn article writing with cover art',
  'Carousels generated as a set',
  'Formatting toolbar with lists, links and emoji',
  'Drag-and-drop media upload with reordering',
  'Draft management and full post history',
  'Layer-based image editor with an AI edit panel',
]

// Not built. Listed so the page is honest about the edges of the product.
const IN_DEVELOPMENT = [
  {
    icon: 'chart',
    title: 'Analytics',
    body: 'There is no performance reporting inside AutoSocial AI today. Reach, engagement and growth are not collected or displayed anywhere in the product.',
  },
  {
    icon: 'users',
    title: 'Team collaboration',
    body: 'No shared workspaces, roles, or approval routing between teammates. The approval step in the Content Planner is your own review of your own posts.',
  },
]

export default function Features() {
  return (
    <>
      <Seo />
      <PageHero title="Every screen you will actually use" />

      {FEATURES.map((f, i) => (
        <Section
          key={f.id}
          id={f.id}
          tone={i % 2 === 0 ? 'page' : 'surface'}
          // Only the first section tucks up under the hero; the rest keep the
          // standard rhythm, which is what separates one feature from the next.
          className={i === 0 ? 'pt-8 md:pt-10' : ''}
        >
          <Split
            reverse={i % 2 === 1}
            media={
              <ProductFrame
                src={f.shot.src}
                width={f.shot.w}
                height={f.shot.h}
                mobileSrc={f.shot.mobile}
                mobileWidth={f.shot.mobile ? 860 : undefined}
                mobileHeight={f.shot.mobile ? 1720 : undefined}
                label={f.shot.label}
                alt={f.shot.alt}
                priority={i === 0}
              />
            }
          >
            <SectionHead eyebrow={f.eyebrow} title={f.title} subtitle={f.body} />
            <PointList items={f.points} />
          </Split>
        </Section>
      ))}

      {/* ---- Also included ---------------------------------------------- */}
      <Section>
        <SectionHead
          eyebrow="Also included"
          title="The smaller things you would otherwise switch tools for"
        />
        <ul className="mt-10 grid gap-x-10 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
          {ALSO.map((item) => (
            <li key={item} className="flex gap-2.5 text-[15px]">
              <Icon name="check" size={18} className="mt-1 shrink-0 text-accent" />
              <span className="text-body">{item}</span>
            </li>
          ))}
        </ul>
      </Section>

      {/* ---- Not built yet ---------------------------------------------- */}
      <section className="border-t border-line py-16">
        <Container>
          <div className="rounded-2xl border border-line bg-inset p-8 md:p-10">
            <p className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-muted">
              In development — not available today
            </p>
            <div className="grid gap-8 md:grid-cols-2">
              {IN_DEVELOPMENT.map((item) => (
                <div key={item.title}>
                  <h3 className="flex items-center gap-2 text-lg font-bold text-muted">
                    <Icon name={item.icon} size={20} />
                    {item.title}
                  </h3>
                  <p className="mt-2 text-[15px] leading-relaxed text-muted">{item.body}</p>
                </div>
              ))}
            </div>
          </div>
        </Container>
      </section>

      <CtaPanel
        title="See it with your own brand in it"
        subtitle="Create an account, fill in the business profile, and generate your first set of posts."
        secondary={{ to: '/pricing', label: 'View pricing' }}
      />
    </>
  )
}
