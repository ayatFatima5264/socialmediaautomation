import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import Seo from '../../components/Seo.jsx'
import BlogCover from '../../components/marketing/BlogCover.jsx'
import { Container, CTASection } from './_ui.jsx'
import { SITE, SITE_URL } from '../../config/site'
import { ACTIVE_CATEGORIES, POSTS_BY_DATE, formatPostDate } from '../../content/posts'

// ---------------------------------------------------------------------------
// Blog index — the hub page for every article. Renders a featured lead story,
// a category filter, and a responsive card grid. All content comes from the
// registry in content/posts.js, so this page never needs editing to publish.
// ---------------------------------------------------------------------------

const ALL = 'All'

function CategoryPill({ label, active, onClick, count }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full border px-4 py-1.5 text-sm font-semibold transition ${
        active
          ? 'border-accent bg-accent text-accent-contrast'
          : 'border-line text-muted hover:border-accent-line hover:text-accent'
      }`}
    >
      {label}
      <span className={`ml-1.5 text-xs ${active ? 'opacity-80' : 'opacity-60'}`}>{count}</span>
    </button>
  )
}

function PostMeta({ post, className = '' }) {
  return (
    <div className={`flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted ${className}`}>
      <span className="font-semibold text-accent">{post.category}</span>
      <span aria-hidden="true">·</span>
      <time dateTime={post.date}>{formatPostDate(post.date)}</time>
      <span aria-hidden="true">·</span>
      <span>{post.readMinutes} min read</span>
    </div>
  )
}

// The lead story — wide layout, larger art, on its own above the grid.
function FeaturedCard({ post }) {
  return (
    <Link
      to={`/blog/${post.slug}`}
      className="card group grid gap-0 overflow-hidden transition duration-150 hover:-translate-y-0.5 hover:border-accent md:grid-cols-2"
    >
      <div className="aspect-[16/10] md:aspect-auto md:h-full">
        <BlogCover
          slug={post.slug}
          palette={post.cover.palette}
          pattern={post.cover.pattern}
          icon={post.cover.icon}
          label={post.category}
          rounded=""
          className="h-full object-cover"
        />
      </div>
      <div className="flex flex-col justify-center p-6 md:p-9">
        <span className="mb-3 inline-flex w-fit items-center gap-1.5 rounded-full border border-accent-line bg-accent-soft px-3 py-1 text-[11px] font-bold uppercase tracking-wide text-accent">
          Featured
        </span>
        <h2 className="text-2xl font-black leading-tight tracking-tight transition group-hover:text-accent md:text-3xl">
          {post.title}
        </h2>
        <p className="mt-3 line-clamp-3 text-sm leading-relaxed text-muted">{post.description}</p>
        <PostMeta post={post} className="mt-5" />
      </div>
    </Link>
  )
}

function PostCard({ post }) {
  return (
    <Link
      to={`/blog/${post.slug}`}
      className="card group flex flex-col overflow-hidden transition duration-150 hover:-translate-y-0.5 hover:border-accent"
    >
      <div className="aspect-[16/9]">
        <BlogCover
          slug={post.slug}
          palette={post.cover.palette}
          pattern={post.cover.pattern}
          icon={post.cover.icon}
          label={post.category}
          rounded=""
          className="h-full"
        />
      </div>
      <div className="flex flex-1 flex-col p-5">
        <h3 className="text-lg font-bold leading-snug transition group-hover:text-accent">
          {post.title}
        </h3>
        <p className="mt-2 line-clamp-3 flex-1 text-sm leading-relaxed text-muted">
          {post.description}
        </p>
        <PostMeta post={post} className="mt-4 border-t border-line pt-4" />
      </div>
    </Link>
  )
}

export default function Blog() {
  const [active, setActive] = useState(ALL)

  const counts = useMemo(() => {
    const map = { [ALL]: POSTS_BY_DATE.length }
    ACTIVE_CATEGORIES.forEach((c) => {
      map[c] = POSTS_BY_DATE.filter((p) => p.category === c).length
    })
    return map
  }, [])

  const visible = useMemo(
    () => (active === ALL ? POSTS_BY_DATE : POSTS_BY_DATE.filter((p) => p.category === active)),
    [active],
  )

  // Only lead with a featured story on the unfiltered view — a filtered list
  // reads better as a plain, even grid.
  const showcase = active === ALL ? visible.find((p) => p.featured) : null
  const grid = showcase ? visible.filter((p) => p.slug !== showcase.slug) : visible

  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'Blog',
    name: `${SITE.name} Blog`,
    description:
      'Practical guides on AI social media automation, content strategy, scheduling, and platform-specific marketing.',
    url: `${SITE_URL}/blog`,
    publisher: { '@type': 'Organization', name: SITE.name, url: SITE_URL },
    blogPost: POSTS_BY_DATE.slice(0, 10).map((p) => ({
      '@type': 'BlogPosting',
      headline: p.title,
      description: p.description,
      datePublished: p.date,
      url: `${SITE_URL}/blog/${p.slug}`,
    })),
  }

  return (
    <>
      <Seo jsonLd={jsonLd} />

      {/* Hero */}
      <section className="pt-20 pb-10 text-center md:pt-28">
        <Container>
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-accent-line bg-accent-soft px-3.5 py-1 text-xs font-semibold uppercase tracking-wide text-accent">
            The {SITE.name} Blog
          </div>
          <h1 className="mx-auto max-w-3xl text-4xl font-black leading-[1.1] tracking-tight md:text-6xl">
            Social media, without the busywork
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-lg text-muted md:text-xl">
            Practical guides on AI content creation, scheduling, and platform strategy — written
            for people who have to actually ship the posts.
          </p>
        </Container>
      </section>

      {/* Category filter */}
      <Container>
        <div className="flex flex-wrap justify-center gap-2 pb-10">
          <CategoryPill
            label={ALL}
            count={counts[ALL]}
            active={active === ALL}
            onClick={() => setActive(ALL)}
          />
          {ACTIVE_CATEGORIES.map((c) => (
            <CategoryPill
              key={c}
              label={c}
              count={counts[c]}
              active={active === c}
              onClick={() => setActive(c)}
            />
          ))}
        </div>
      </Container>

      {/* Featured + grid */}
      <Container className="pb-16">
        {showcase && (
          <div className="mb-10">
            <FeaturedCard post={showcase} />
          </div>
        )}

        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {grid.map((post) => (
            <PostCard key={post.slug} post={post} />
          ))}
        </div>

        {grid.length === 0 && !showcase && (
          <p className="py-12 text-center text-muted">No articles in this category yet.</p>
        )}
      </Container>

      <CTASection
        title="Stop writing posts one at a time"
        subtitle="Generate, schedule, and publish a full content plan with AI. Start free — no credit card required."
      />
    </>
  )
}
