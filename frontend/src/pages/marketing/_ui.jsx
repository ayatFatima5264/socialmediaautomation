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
    <section className="pt-16 pb-10 text-center md:pt-24">
      <Container>
        {eyebrow && (
          <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-indigo-500/20 bg-indigo-500/10 px-3 py-1 text-xs font-semibold text-indigo-500 dark:text-indigo-300">
            {eyebrow}
          </div>
        )}
        <h1 className="mx-auto max-w-3xl text-4xl font-black tracking-tight md:text-5xl">
          {title}
        </h1>
        {subtitle && (
          <p className="mx-auto mt-4 max-w-2xl text-lg text-slate-500 dark:text-slate-400">
            {subtitle}
          </p>
        )}
      </Container>
    </section>
  )
}

// Reusable "convert now" band shown near the bottom of most pages.
export function CTASection({
  title = 'Ready to create better content, faster?',
  subtitle = 'Start free — no credit card required.',
}) {
  return (
    <section className="py-20">
      <Container>
        <div className="card overflow-hidden p-10 text-center md:p-14">
          <h2 className="mx-auto max-w-2xl text-3xl font-bold md:text-4xl">
            {title}
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-slate-500 dark:text-slate-400">
            {subtitle}
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link to="/register" className="btn btn-primary px-6 py-2.5">
              Get Started Free
            </Link>
            <Link to="/login" className="btn btn-ghost px-6 py-2.5">
              Sign in
            </Link>
          </div>
        </div>
      </Container>
    </section>
  )
}

// A titled feature/benefit card.
export function FeatureCard({ icon, title, children }) {
  return (
    <div className="card p-6">
      <div className="mb-4 grid h-11 w-11 place-items-center rounded-xl bg-gradient-to-br from-indigo-500/15 to-violet-500/15 text-xl">
        {icon}
      </div>
      <h3 className="text-lg font-bold">{title}</h3>
      <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{children}</p>
    </div>
  )
}
