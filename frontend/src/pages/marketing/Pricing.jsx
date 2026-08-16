import { Link } from 'react-router-dom'
import { CtaPanel, FaqItem, PageHero, Section, SectionHead } from './_ui.jsx'
import Seo from '../../components/Seo.jsx'
import Icon from '../../components/marketing/Icon.jsx'
import { COMPARISON, ENTERPRISE, PLANS } from '../../config/pricing'

// ---------------------------------------------------------------------------
// Plans, limits and features all come from config/pricing.js so this page and
// the homepage's preview cannot drift apart.
//
// Three claims that used to live here have been removed rather than reworded,
// because the product does not support them: a PCI-compliant payment provider
// (there is no payment processing), a definition of what "counts as" a metered
// generation (nothing meters them), and a footnote admitting the prices were
// placeholders. What replaces them is below, in the FAQ, stated plainly.
// ---------------------------------------------------------------------------

const FAQ = [
  {
    q: 'Can I start without a credit card?',
    a: 'Yes. Creating an account puts you on the Free plan, and no card is asked for at any point in signing up.',
  },
  {
    q: 'How do I move onto a paid plan?',
    a: 'Get in touch. Upgrading is not self-serve yet — there is no checkout inside the product — so paid plans are arranged with us directly. Start on Free in the meantime; nothing you create is locked to a plan.',
  },
  {
    q: 'Are the usage limits enforced today?',
    a: 'No. The generation counts and account limits above describe the plan structure, not a meter running inside the application. We would rather say that here than have you discover it later.',
  },
  {
    q: 'What is not included on any plan?',
    a: 'Analytics and team collaboration. Neither is built yet, on any plan, which is why they are marked as in development rather than as a Business feature.',
  },
  {
    q: 'Do you work with agencies?',
    a: 'Yes. The Business plan is aimed at teams handling several brands, and Enterprise covers larger deployments with dedicated onboarding. Both start with a conversation — use the contact form and tell us roughly how many accounts and people are involved.',
  },
]

function Cell({ value, soon }) {
  if (value === true) return <Icon name="check" size={18} className="mx-auto text-accent" />
  if (value === false) return <span className="text-muted">—</span>
  return (
    <span className={soon ? 'text-xs font-medium text-muted' : 'text-body'}>{value}</span>
  )
}

export default function Pricing() {
  return (
    <>
      <Seo />
      <PageHero
        eyebrow="Pricing"
        title="Start free, and talk to us when you outgrow it"
        subtitle="Every plan begins by creating an account. Paid plans are arranged directly with us — there is no checkout in the product yet."
      />

      {/* ---- Plan cards -------------------------------------------------- */}
      <Section>
        <div className="grid items-stretch gap-6 lg:grid-cols-3">
          {PLANS.map((plan) => (
            <div
              key={plan.id}
              className={`card relative flex flex-col p-7 ${
                plan.highlight ? 'border-accent shadow-[0_18px_40px_-28px_rgba(22,40,31,0.5)]' : ''
              }`}
            >
              {plan.highlight && (
                <span className="absolute -top-3 left-7 rounded-full bg-accent px-3 py-1 text-[11px] font-bold uppercase tracking-wide text-accent-contrast">
                  Most popular
                </span>
              )}
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">
                {plan.name}
              </h2>
              <div className="mt-3 flex items-baseline gap-1.5">
                <span className="text-4xl font-bold tracking-tight">{plan.price}</span>
                <span className="text-muted">{plan.cadence}</span>
              </div>
              <p className="mt-2 text-sm text-muted">{plan.tagline}</p>

              <Link
                to={plan.to}
                className={`btn mt-7 w-full py-2.5 ${
                  plan.highlight ? 'btn-primary' : 'btn-secondary'
                }`}
              >
                {plan.cta}
              </Link>

              <ul className="mt-7 space-y-3 border-t border-line pt-6 text-sm">
                {plan.features.map((f) => {
                  const soon = f.includes('(in development)')
                  return (
                    <li key={f} className="flex gap-2.5">
                      <Icon
                        name={soon ? 'clock' : 'check'}
                        size={17}
                        className={`mt-0.5 shrink-0 ${soon ? 'text-muted' : 'text-accent'}`}
                      />
                      <span className={soon ? 'text-muted' : 'text-body'}>{f}</span>
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </div>

        {/* Enterprise sits apart: it is agreed in a conversation, not compared
            line by line against a monthly price. */}
        <div className="mt-6 rounded-2xl border border-line bg-surface p-7 md:p-9">
          <div className="grid gap-8 md:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] md:items-center">
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">
                {ENTERPRISE.name}
              </h2>
              <div className="mt-2 text-3xl font-bold tracking-tight">{ENTERPRISE.price}</div>
              <p className="mt-2 text-muted">{ENTERPRISE.tagline}</p>
              <Link to={ENTERPRISE.to} className="btn btn-secondary mt-6 px-6 py-2.5">
                {ENTERPRISE.cta}
              </Link>
            </div>
            <ul className="grid gap-3 text-sm sm:grid-cols-2">
              {ENTERPRISE.features.map((f) => (
                <li key={f} className="flex gap-2.5">
                  <Icon name="check" size={17} className="mt-0.5 shrink-0 text-accent" />
                  <span className="text-body">{f}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Section>

      {/* ---- Comparison -------------------------------------------------- */}
      <Section tone="surface">
        <SectionHead title="Compare plans" />
        <div className="mt-8 overflow-x-auto rounded-xl border border-line bg-surface">
          <table className="w-full min-w-[720px] border-collapse text-left text-sm">
            <thead>
              {/* Sticky header and first column so plan names and feature names
                  stay readable while the table is scrolled sideways on a phone. */}
              <tr className="border-b border-line">
                <th className="sticky left-0 z-10 bg-surface p-4 font-semibold">Feature</th>
                {['Free', 'Pro', 'Business', 'Enterprise'].map((name) => (
                  <th key={name} className="p-4 text-center font-semibold">
                    {name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {COMPARISON.map((row) => (
                <tr key={row.label} className="border-b border-line last:border-0">
                  <td className="sticky left-0 z-10 bg-surface p-4 text-body">
                    {row.label}
                  </td>
                  <td className="p-4 text-center"><Cell value={row.free} soon={row.soon} /></td>
                  <td className="p-4 text-center"><Cell value={row.pro} soon={row.soon} /></td>
                  <td className="p-4 text-center"><Cell value={row.business} soon={row.soon} /></td>
                  <td className="p-4 text-center"><Cell value={row.enterprise} soon={row.soon} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-4 flex items-start gap-2 text-sm text-muted">
          <Icon name="alert" size={17} className="mt-0.5 shrink-0" />
          Rows marked “In development” are not available on any plan yet.
        </p>
      </Section>

      {/* ---- FAQ --------------------------------------------------------- */}
      <Section>
        <div className="grid gap-10 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)] lg:gap-16">
          <SectionHead eyebrow="Pricing FAQ" title="Before you pick a plan" />
          <div>
            {FAQ.map((item) => (
              <FaqItem key={item.q} q={item.q} a={item.a} />
            ))}
          </div>
        </div>
      </Section>

      <CtaPanel
        title="Start on Free today"
        subtitle="Create an account, connect a network, and publish your first post."
        secondary={{ to: '/contact', label: 'Talk to us' }}
      />
    </>
  )
}
