import { Link } from 'react-router-dom'
import Icon from '../../components/marketing/Icon.jsx'

// Small, shared building blocks so every marketing page stays consistent and
// modular. These intentionally reuse the app's existing design-system classes
// (card / btn / app-bg) rather than introducing a parallel styling system.
//
// Two of these — Container and CTASection — are also used by the blog and the
// legal pages. Those pages are deliberately out of scope for the marketing
// redesign, so both keep their original behaviour and appearance; the
// redesigned pages use Section / CtaPanel below instead.

// Constrained, centered page container.
export function Container({ className = '', children }) {
  return (
    <div className={`mx-auto max-w-6xl px-4 md:px-6 ${className}`}>{children}</div>
  )
}

// Standard hero used at the top of secondary pages.
//
// Left-aligned rather than centred: every secondary page opened with the same
// centred wall of black type, which is the layout that made the site read as a
// template. Centring is now reserved for the homepage hero alone, so it means
// something when it appears.
// No eyebrow label. Every page passed one that simply repeated its own name —
// "Contact" above "Talk to us" — which the active nav item and the heading
// already say. It cost a line of type and ~36px of vertical space at the very
// top of the page, pushing the actual heading below the fold on short screens.
//
// The top padding is deliberately smaller than the bottom rhythm elsewhere: this
// section sits directly beneath the header, so it inherits that separation and
// does not need to restate it.
export function PageHero({ title, subtitle, children }) {
  return (
    <section className="border-b border-line bg-surface pb-10 pt-10 md:pb-14 md:pt-16">
      <Container>
        {/* No max-width: a 768px column broke every heading here onto a second
            line, which at 48px is most of the visible page before the content
            starts. The container's own 1104px is the limit instead. */}
        <h1 className="text-balance text-4xl font-bold leading-[1.08] tracking-tight md:text-5xl">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-5 max-w-2xl text-lg leading-relaxed text-muted">
            {subtitle}
          </p>
        )}
        {children && <div className="mt-8">{children}</div>}
      </Container>
    </section>
  )
}

// A page section with a consistent vertical rhythm. `tone="surface"` alternates
// the background so a long page has a readable cadence without gradients.
export function Section({ tone = 'page', className = '', children, ...rest }) {
  return (
    <section
      className={`py-16 md:py-24 ${
        tone === 'surface' ? 'border-y border-line bg-surface' : ''
      } ${className}`}
      {...rest}
    >
      <Container>{children}</Container>
    </section>
  )
}

// Section heading. Left-aligned by default; `align="center"` for the few places
// a centred heading genuinely helps (FAQ, final CTA).
export function SectionHead({ eyebrow, title, subtitle, align = 'left', className = '' }) {
  const centred = align === 'center'
  return (
    <div className={`${centred ? 'mx-auto text-center' : ''} max-w-2xl ${className}`}>
      {eyebrow && (
        <p className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-accent">
          {eyebrow}
        </p>
      )}
      <h2 className="text-balance text-3xl font-bold leading-tight tracking-tight md:text-4xl">
        {title}
      </h2>
      {subtitle && (
        <p className={`mt-4 text-lg leading-relaxed text-muted ${centred ? 'mx-auto' : ''}`}>
          {subtitle}
        </p>
      )}
    </div>
  )
}

// Prose + screenshot, side by side. `reverse` puts the screenshot on the left,
// which is what gives the homepage its alternating rhythm.
// `min-w-0` on both columns: a grid item's automatic minimum size is its
// min-content width, so a wide child — a screenshot that pans sideways on a
// phone, a long unbroken URL — would otherwise widen the whole column past the
// screen instead of scrolling or wrapping inside it.
export function Split({ reverse = false, children, media }) {
  return (
    <div className="grid items-center gap-10 lg:grid-cols-2 lg:gap-14">
      <div className={`min-w-0 ${reverse ? 'lg:order-2' : ''}`}>{children}</div>
      <div className={`min-w-0 ${reverse ? 'lg:order-1' : ''}`}>{media}</div>
    </div>
  )
}

// A tight list of specifics under a Split's prose. Deliberately not cards.
export function PointList({ items, className = '' }) {
  return (
    <ul className={`mt-6 space-y-3 ${className}`}>
      {items.map((item) => (
        <li key={item} className="flex gap-3 text-[15px] leading-relaxed">
          <Icon name="check" size={18} className="mt-0.5 shrink-0 text-accent" />
          <span className="text-body">{item}</span>
        </li>
      ))}
    </ul>
  )
}

// Closing call to action for the redesigned pages.
//
// The old CTASection (kept below, still used by the blog) was a full-bleed
// solid-accent slab repeated identically at the bottom of all five pages. This
// is a bordered panel instead: the accent lives in the button, where it marks
// the one action worth taking, rather than shouting across the whole width.
export function CtaPanel({
  title = 'Create your first post today',
  subtitle = 'Free plan, no credit card. Connect an account whenever you are ready to publish.',
  primary = { to: '/register', label: 'Start free' },
  secondary = { to: '/features', label: 'See how it works' },
}) {
  return (
    <Section>
      <div className="rounded-2xl border border-line bg-surface px-6 py-12 text-center md:px-14 md:py-16">
        <h2 className="mx-auto max-w-2xl text-balance text-3xl font-bold tracking-tight md:text-4xl">
          {title}
        </h2>
        {subtitle && (
          <p className="mx-auto mt-4 max-w-xl text-lg text-muted">{subtitle}</p>
        )}
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Link to={primary.to} className="btn btn-primary px-6 py-2.5 text-base">
            {primary.label}
          </Link>
          {secondary && (
            <Link to={secondary.to} className="btn btn-secondary px-6 py-2.5 text-base">
              {secondary.label}
            </Link>
          )}
        </div>
      </div>
    </Section>
  )
}

// Disclosure row used by the FAQ blocks.
export function FaqItem({ q, a }) {
  return (
    <details className="group border-b border-line py-5 [&_summary::-webkit-details-marker]:hidden">
      <summary className="flex cursor-pointer list-none items-start justify-between gap-6 text-left text-[17px] font-semibold">
        {q}
        <Icon
          name="plus"
          size={20}
          className="mt-0.5 shrink-0 text-accent transition-transform duration-150 group-open:rotate-45"
        />
      </summary>
      <div className="mt-3 max-w-3xl text-[15px] leading-relaxed text-muted">{a}</div>
    </details>
  )
}

// ---------------------------------------------------------------------------
// Kept as-is for the blog, which is out of scope for the redesign.
// ---------------------------------------------------------------------------

// Reusable "convert now" band shown near the bottom of most pages — a bold,
// full accent block for maximum conversion pull.
export function CTASection({
  title = 'Ready to create better content, faster?',
  subtitle = 'Start free — no credit card required.',
}) {
  return (
    <section className="py-16 md:py-24">
      <Container>
        <div className="rounded-3xl bg-accent px-6 py-14 text-center text-accent-contrast md:px-14 md:py-20">
          <h2 className="mx-auto max-w-2xl text-3xl font-black tracking-tight md:text-5xl">
            {title}
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-base opacity-90 md:text-lg">
            {subtitle}
          </p>
          <div className="mt-9 flex flex-wrap justify-center gap-3">
            <Link
              to="/register"
              className="btn bg-surface px-7 py-3 text-base font-bold text-accent hover:bg-inset"
            >
              Get Started Free
            </Link>
            <Link
              to="/login"
              className="btn border-2 border-current px-7 py-3 text-base font-semibold text-accent-contrast hover:opacity-80"
            >
              Sign in
            </Link>
          </div>
        </div>
      </Container>
    </section>
  )
}
