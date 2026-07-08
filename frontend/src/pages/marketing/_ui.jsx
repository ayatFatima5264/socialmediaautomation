import { Link } from 'react-router-dom'

// Small, shared building blocks so every marketing page stays consistent and
// modular. These intentionally reuse the app's existing design-system classes
// (card / btn / app-bg) rather than introducing a parallel styling system.

// Constrained, centered page container.
export function Container({ className = '', children }) {
  return (
    <div className={`mx-auto max-w-6xl px-4 md:px-6 ${className}`}>{children}</div>
  )
}

// Standard hero used at the top of secondary pages.
export function PageHero({ eyebrow, title, subtitle }) {
  return (
    <section className="pt-20 pb-12 text-center md:pt-28">
      <Container>
        {eyebrow && (
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-accent-line bg-accent-soft px-3.5 py-1 text-xs font-semibold uppercase tracking-wide text-accent">
            {eyebrow}
          </div>
        )}
        <h1 className="mx-auto max-w-3xl text-4xl font-black leading-[1.1] tracking-tight md:text-6xl">
          {title}
        </h1>
        {subtitle && (
          <p className="mx-auto mt-5 max-w-2xl text-lg text-muted md:text-xl">
            {subtitle}
          </p>
        )}
      </Container>
    </section>
  )
}

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

// A titled feature/benefit card with an accent-highlighted icon and hover lift.
// An optional `tag` renders a small accent pill (e.g. "New") beside the title.
export function FeatureCard({ icon, title, children, tag }) {
  return (
    <div className="card p-6 transition duration-150 hover:-translate-y-0.5 hover:border-accent">
      <div className="mb-4 grid h-12 w-12 place-items-center rounded-xl border border-accent-line bg-accent-soft text-2xl">
        {icon}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-lg font-bold">{title}</h3>
        {tag && (
          <span className="rounded-full bg-accent px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-accent-contrast">
            {tag}
          </span>
        )}
      </div>
      <p className="mt-2 text-sm text-muted">{children}</p>
    </div>
  )
}
