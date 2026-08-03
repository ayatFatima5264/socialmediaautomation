import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import Seo from '../../components/Seo.jsx'
import BlogCover from '../../components/marketing/BlogCover.jsx'
import Markdown, { extractHeadings, extractFaq } from '../../lib/markdown.jsx'
import { Container, CTASection } from './_ui.jsx'
import { SITE, SITE_URL } from '../../config/site'
import { getPost, getRelated, loadPostBody, formatPostDate } from '../../content/posts'
import NotFound from '../NotFound.jsx'

// ---------------------------------------------------------------------------
// Single article page. The body Markdown is fetched lazily per slug, so the
// blog index stays light and each article ships as its own chunk.
// ---------------------------------------------------------------------------

function ArticleSkeleton() {
  return (
    <Container className="max-w-3xl py-16">
      <div className="skeleton h-8 w-2/3" />
      <div className="mt-4 space-y-3">
        {Array.from({ length: 10 }, (_, i) => (
          <div key={i} className="skeleton h-4" style={{ width: `${72 + ((i * 13) % 26)}%` }} />
        ))}
      </div>
    </Container>
  )
}

// Sticky in-page navigation, built from the article's own H2s.
function TableOfContents({ headings }) {
  if (headings.length < 3) return null
  return (
    <nav aria-label="Table of contents" className="card p-5">
      <div className="text-sm font-bold">Table of contents</div>
      <ol className="mt-3 space-y-2 text-sm">
        {headings.map((h, i) => (
          <li key={h.id} className="flex gap-2.5">
            <span className="w-4 shrink-0 text-right text-xs font-semibold text-accent">
              {i + 1}
            </span>
            <a href={`#${h.id}`} className="text-muted transition hover:text-accent">
              {h.text}
            </a>
          </li>
        ))}
      </ol>
    </nav>
  )
}

function RelatedCard({ post }) {
  return (
    <Link
      to={`/blog/${post.slug}`}
      className="card group flex flex-col overflow-hidden transition duration-150 hover:-translate-y-0.5 hover:border-accent"
    >
      <div className="aspect-[16/9]">
        <BlogCover
          slug={`rel-${post.slug}`}
          palette={post.cover.palette}
          pattern={post.cover.pattern}
          icon={post.cover.icon}
          label={post.category}
          rounded=""
          className="h-full"
        />
      </div>
      <div className="p-4">
        <div className="text-xs font-semibold text-accent">{post.category}</div>
        <h3 className="mt-1.5 text-base font-bold leading-snug transition group-hover:text-accent">
          {post.title}
        </h3>
        <div className="mt-2 text-xs text-muted">{post.readMinutes} min read</div>
      </div>
    </Link>
  )
}

export default function BlogPost() {
  const { slug } = useParams()
  const post = getPost(slug)
  const [body, setBody] = useState(null)
  const [failed, setFailed] = useState(false)

  // Load this article's Markdown, and reset scroll when moving between posts.
  useEffect(() => {
    if (!post) return
    let cancelled = false
    setBody(null)
    setFailed(false)
    window.scrollTo({ top: 0 })

    loadPostBody(post.slug)
      .then((text) => {
        if (!cancelled) setBody(text)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })

    return () => {
      cancelled = true
    }
  }, [post])

  const headings = useMemo(() => (body ? extractHeadings(body) : []), [body])
  const faq = useMemo(() => (body ? extractFaq(body) : []), [body])

  const jsonLd = useMemo(() => {
    if (!post) return null
    const article = {
      '@context': 'https://schema.org',
      '@type': 'BlogPosting',
      headline: post.title,
      description: post.description,
      datePublished: post.date,
      dateModified: post.date,
      author: { '@type': 'Organization', name: SITE.name, url: SITE_URL },
      publisher: { '@type': 'Organization', name: SITE.name, url: SITE_URL },
      mainEntityOfPage: { '@type': 'WebPage', '@id': `${SITE_URL}/blog/${post.slug}` },
      keywords: post.keyword,
      articleSection: post.category,
      wordCount: body ? body.split(/\s+/).length : undefined,
    }
    if (!faq.length) return article
    return [
      article,
      {
        '@context': 'https://schema.org',
        '@type': 'FAQPage',
        mainEntity: faq.map((f) => ({
          '@type': 'Question',
          name: f.question,
          acceptedAnswer: { '@type': 'Answer', text: f.answer },
        })),
      },
    ]
  }, [post, faq, body])

  // Unknown slug — render the site's real 404 rather than an empty shell.
  if (!post) return <NotFound />

  const related = getRelated(post.slug)

  return (
    <>
      <Seo
        title={post.metaTitle}
        description={post.description}
        type="article"
        jsonLd={jsonLd}
      />

      {/* ---- Header ---------------------------------------------------- */}
      <article>
        <Container className="max-w-4xl pt-12 md:pt-16">
          <nav className="mb-6 flex flex-wrap items-center gap-1.5 text-sm text-muted">
            <Link to="/" className="transition hover:text-accent">
              Home
            </Link>
            <span aria-hidden="true">/</span>
            <Link to="/blog" className="transition hover:text-accent">
              Blog
            </Link>
            <span aria-hidden="true">/</span>
            <span className="text-accent">{post.category}</span>
          </nav>

          <h1 className="text-3xl font-black leading-[1.15] tracking-tight md:text-5xl">
            {post.title}
          </h1>

          <p className="mt-5 text-lg leading-relaxed text-muted">{post.description}</p>

          <div className="mt-6 flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-line pt-5 text-sm text-muted">
            <span className="grid h-8 w-8 place-items-center rounded-full bg-accent text-xs font-bold text-accent-contrast">
              {SITE.name.slice(0, 1)}
            </span>
            <span className="font-medium text-body">The {SITE.name} Team</span>
            <span aria-hidden="true">·</span>
            <time dateTime={post.date}>{formatPostDate(post.date)}</time>
            <span aria-hidden="true">·</span>
            <span>{post.readMinutes} min read</span>
          </div>
        </Container>

        {/* Header image */}
        <Container className="max-w-5xl py-8 md:py-10">
          <div className="aspect-[1200/500] overflow-hidden rounded-2xl border border-line md:aspect-[1200/430]">
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
        </Container>

        {/* ---- Body + sidebar -------------------------------------------- */}
        <Container className="max-w-6xl pb-16">
          <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_18rem]">
            <div className="min-w-0 text-[1.0625rem]">
              {failed && (
                <p className="rounded-xl border border-rose-400/40 bg-rose-500/10 p-4 text-sm text-rose-600">
                  This article could not be loaded. Please refresh the page or{' '}
                  <Link to="/blog" className="link-accent font-semibold">
                    return to the blog
                  </Link>
                  .
                </p>
              )}
              {!body && !failed && <ArticleSkeleton />}
              {body && <Markdown source={body} />}
            </div>

            <aside className="hidden lg:block">
              <div className="sticky top-24 space-y-5">
                <TableOfContents headings={headings} />

                <div className="card overflow-hidden">
                  <div className="aspect-[16/9]">
                    <BlogCover
                      slug={`aside-${post.slug}`}
                      palette={post.cover.palette}
                      pattern={(post.cover.pattern + 2) % 5}
                      icon="✦"
                      rounded=""
                      className="h-full"
                    />
                  </div>
                  <div className="p-5">
                    <div className="text-sm font-bold">Try {SITE.name} free</div>
                    <p className="mt-1.5 text-xs leading-relaxed text-muted">
                      Generate a full content plan, create the images, and auto-schedule every
                      post — from one dashboard.
                    </p>
                    <Link to="/register" className="btn btn-primary btn-sm mt-4 w-full">
                      Get started free
                    </Link>
                    <Link to="/features" className="btn btn-ghost btn-sm mt-2 w-full">
                      See features
                    </Link>
                  </div>
                </div>
              </div>
            </aside>
          </div>
        </Container>
      </article>

      {/* ---- Related --------------------------------------------------- */}
      {related.length > 0 && (
        <section className="border-t border-line py-16">
          <Container>
            <div className="mb-8 flex flex-wrap items-end justify-between gap-3">
              <h2 className="text-2xl font-black tracking-tight md:text-3xl">Keep reading</h2>
              <Link to="/blog" className="link-accent text-sm font-semibold">
                All articles →
              </Link>
            </div>
            <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {related.map((p) => (
                <RelatedCard key={p.slug} post={p} />
              ))}
            </div>
          </Container>
        </section>
      )}

      <CTASection
        title="Put this into practice today"
        subtitle="Plan, generate, and schedule a month of content with AI. Start free — no credit card required."
      />
    </>
  )
}
