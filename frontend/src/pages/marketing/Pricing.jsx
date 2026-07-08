import { Link } from 'react-router-dom'
import { Container, CTASection, PageHero } from './_ui.jsx'
import Seo from '../../components/Seo.jsx'

const PLANS = [
  {
    name: 'Free',
    price: '$0',
    cadence: '/mo',
    tagline: 'For trying things out',
    cta: 'Start free',
    to: '/register',
    highlight: false,
    features: [
      '30 AI generations / month',
      'AI Planner — 7-day plans',
      '1 connected account',
      'AI captions & hashtags',
      'Basic scheduling',
      'Draft management',
    ],
  },
  {
    name: 'Pro',
    price: '$29',
    cadence: '/mo',
    tagline: 'For creators & solo marketers',
    cta: 'Start Pro',
    to: '/register',
    highlight: true,
    features: [
      'Unlimited AI generations',
      'AI Planner — 7, 15 & 30-day plans',
      'Up to 5 connected accounts',
      'AI images & carousels',
      'Calendar & smart scheduling',
      'Business profile personalization',
      'Priority support',
    ],
  },
  {
    name: 'Business',
    price: '$79',
    cadence: '/mo',
    tagline: 'For teams & agencies',
    cta: 'Start Business',
    to: '/register',
    highlight: false,
    features: [
      'Everything in Pro',
      'Up to 20 connected accounts',
      'Team collaboration (coming soon)',
      'Approval workflows (coming soon)',
      'Analytics dashboard (coming soon)',
      'Priority support',
    ],
  },
  {
    name: 'Enterprise',
    price: 'Custom',
    cadence: '',
    tagline: 'For large organizations',
    cta: 'Contact sales',
    to: '/contact',
    highlight: false,
    features: [
      'Everything in Business',
      'Unlimited accounts & seats',
      'Dedicated onboarding',
      'Custom integrations',
      'SSO & advanced security',
      'SLA & dedicated support',
    ],
  },
]

// Feature comparison matrix. Values: true / false / string.
const COMPARISON = [
  { label: 'AI generations', free: '30 / mo', pro: 'Unlimited', business: 'Unlimited', enterprise: 'Unlimited' },
  { label: 'AI Planner (7 / 15 / 30-day)', free: '7-day', pro: true, business: true, enterprise: true },
  { label: 'Connected accounts', free: '1', pro: '5', business: '20', enterprise: 'Unlimited' },
  { label: 'AI captions & hashtags', free: true, pro: true, business: true, enterprise: true },
  { label: 'AI images & carousels', free: false, pro: true, business: true, enterprise: true },
  { label: 'Smart scheduler & calendar', free: 'Basic', pro: true, business: true, enterprise: true },
  { label: 'Business profile personalization', free: false, pro: true, business: true, enterprise: true },
  { label: 'Team collaboration', free: false, pro: false, business: 'Coming soon', enterprise: 'Coming soon' },
  { label: 'Analytics dashboard', free: false, pro: false, business: 'Coming soon', enterprise: 'Coming soon' },
  { label: 'SSO & advanced security', free: false, pro: false, business: false, enterprise: true },
  { label: 'Support', free: 'Community', pro: 'Priority', business: 'Priority', enterprise: 'Dedicated' },
]

const FAQ = [
  { q: 'Can I start without a credit card?', a: 'Yes. The Free plan is genuinely free and needs no card. Upgrade only when you\'re ready for more generations, accounts, or team features.' },
  { q: 'Can I change plans later?', a: 'Anytime. Upgrade or downgrade from your settings — changes take effect immediately, and downgrades apply at the end of your billing period.' },
  { q: 'What counts as an AI generation?', a: 'Each post, image, carousel, or caption you generate counts as one generation. Paid plans include unlimited generations.' },
  { q: 'Do you offer plans for agencies?', a: 'Yes. The Business plan is built for teams managing multiple brands, and Enterprise adds unlimited seats, security, and dedicated support.' },
  { q: 'Is my payment information secure?', a: 'Payments are processed by a PCI-compliant provider. We never store your full card details on our servers.' },
]

function Cell({ value }) {
  if (value === true) return <span className="text-accent">✓</span>
  if (value === false) return <span className="text-muted">—</span>
  return <span className="text-body">{value}</span>
}

export default function Pricing() {
  return (
    <>
      <Seo
        title="Pricing"
        description="Simple, scalable pricing for AutoSocial AI. Start free, upgrade to Pro or Business for unlimited AI generations and images, or contact us for Enterprise."
      />
      <PageHero
        eyebrow="Pricing"
        title="Pricing that grows with you"
        subtitle="Start free and upgrade when you're ready. No hidden fees, cancel anytime."
      />

      {/* Plan cards */}
      <section className="pb-8">
        <Container>
          <div className="grid items-start gap-6 md:grid-cols-2 lg:grid-cols-4">
            {PLANS.map((plan) => (
              <div
                key={plan.name}
                className={`card relative flex flex-col p-7 ${
                  plan.highlight
                    ? 'border-2 border-accent ring-4 ring-accent-soft lg:-translate-y-2'
                    : ''
                }`}
              >
                {plan.highlight && (
                  <span className="absolute -top-3.5 left-1/2 -translate-x-1/2 rounded-full bg-accent px-4 py-1.5 text-xs font-bold uppercase tracking-wide text-accent-contrast">
                    Most Popular
                  </span>
                )}
                <div className={`text-sm font-semibold ${plan.highlight ? 'text-accent' : 'text-muted'}`}>
                  {plan.name}
                </div>
                <div className="mt-2 flex items-baseline gap-1">
                  <span className="text-4xl font-black">{plan.price}</span>
                  <span className="text-muted">{plan.cadence}</span>
                </div>
                <p className="mt-1 text-sm text-muted">{plan.tagline}</p>
                <Link
                  to={plan.to}
                  className={`btn mt-6 w-full ${plan.highlight ? 'btn-primary' : 'btn-secondary'}`}
                >
                  {plan.cta}
                </Link>
                <ul className="mt-6 space-y-3 text-sm">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-2">
                      <span className="mt-0.5 text-accent">✓</span>
                      <span className="text-body">{f}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <p className="mt-4 text-center text-xs text-muted">
            Prices shown are placeholders and billed monthly. Annual billing coming soon.
          </p>
        </Container>
      </section>

      {/* Comparison table */}
      <section className="py-12">
        <Container>
          <h2 className="mb-6 text-center text-2xl font-bold md:text-3xl">Compare plans</h2>
          <div className="card overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead>
                <tr className="border-b border-line">
                  <th className="p-4 font-semibold">Features</th>
                  <th className="p-4 text-center font-semibold">Free</th>
                  <th className="p-4 text-center font-semibold">Pro</th>
                  <th className="p-4 text-center font-semibold">Business</th>
                  <th className="p-4 text-center font-semibold">Enterprise</th>
                </tr>
              </thead>
              <tbody>
                {COMPARISON.map((row) => (
                  <tr key={row.label} className="border-b border-line last:border-0">
                    <td className="p-4 text-body">{row.label}</td>
                    <td className="p-4 text-center"><Cell value={row.free} /></td>
                    <td className="p-4 text-center"><Cell value={row.pro} /></td>
                    <td className="p-4 text-center"><Cell value={row.business} /></td>
                    <td className="p-4 text-center"><Cell value={row.enterprise} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Container>
      </section>

      {/* FAQ */}
      <section className="py-12">
        <Container className="max-w-3xl">
          <h2 className="mb-8 text-center text-2xl font-bold md:text-3xl">Pricing FAQs</h2>
          <div className="space-y-3">
            {FAQ.map((item) => (
              <details key={item.q} className="card group p-5 [&_summary::-webkit-details-marker]:hidden">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold">
                  {item.q}
                  <span className="text-accent transition group-open:rotate-45">+</span>
                </summary>
                <p className="mt-3 text-sm text-muted">{item.a}</p>
              </details>
            ))}
          </div>
        </Container>
      </section>

      <CTASection
        title="Ready to upgrade your content workflow?"
        subtitle="Start on Free today — move up the moment you need more."
      />
    </>
  )
}
