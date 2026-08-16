// ---------------------------------------------------------------------------
// Plans, limits and the comparison matrix — the single source of truth for
// both the Pricing page and the homepage's pricing preview.
//
// Previously this lived inside Pricing.jsx alone, and the homepage described
// plans in prose, which is how a marketing site ends up quoting a price it no
// longer charges. One list, two surfaces.
//
// HONESTY RULES FOR THIS FILE — the marketing site must not out-run the
// product:
//   • Nothing here may claim a capability the application does not have. Items
//     that are not built carry `soon: true` and are rendered as unavailable.
//   • There is no billing integration yet (no payment provider, no plan model,
//     no metering). Every plan therefore creates an account, and the CTA labels
//     below say so rather than implying a checkout.
// ---------------------------------------------------------------------------

export const PLANS = [
  {
    id: 'free',
    name: 'Free',
    price: '$0',
    cadence: '/mo',
    tagline: 'For trying things out',
    cta: 'Create your account',
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
    id: 'pro',
    name: 'Pro',
    price: '$29',
    cadence: '/mo',
    tagline: 'For creators & solo marketers',
    cta: 'Create your account',
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
    id: 'business',
    name: 'Business',
    price: '$79',
    cadence: '/mo',
    tagline: 'For teams & agencies',
    cta: 'Create your account',
    to: '/register',
    highlight: false,
    features: [
      'Everything in Pro',
      'Up to 20 connected accounts',
      'Team collaboration (in development)',
      'Approval workflows (in development)',
      'Analytics dashboard (in development)',
      'Priority support',
    ],
  },
]

// Enterprise sits apart from the three-card row: it is agreed in a conversation
// rather than compared line by line.
export const ENTERPRISE = {
  name: 'Enterprise',
  price: 'Custom',
  tagline: 'For large organizations',
  cta: 'Talk to us',
  to: '/contact',
  features: [
    'Everything in Business',
    'Unlimited accounts & seats',
    'Dedicated onboarding',
    'Custom integrations',
    'SSO & advanced security',
    'SLA & dedicated support',
  ],
}

// Feature comparison matrix. Values: true / false / string.
// `soon: true` marks a row whose paid-plan values are not built yet, so the
// table can render them as unavailable rather than as a feature you can use.
export const COMPARISON = [
  { label: 'AI generations', free: '30 / mo', pro: 'Unlimited', business: 'Unlimited', enterprise: 'Unlimited' },
  { label: 'AI Planner (7 / 15 / 30-day)', free: '7-day', pro: true, business: true, enterprise: true },
  { label: 'Connected accounts', free: '1', pro: '5', business: '20', enterprise: 'Unlimited' },
  { label: 'AI captions & hashtags', free: true, pro: true, business: true, enterprise: true },
  { label: 'AI images & carousels', free: false, pro: true, business: true, enterprise: true },
  { label: 'Smart scheduler & calendar', free: 'Basic', pro: true, business: true, enterprise: true },
  { label: 'Business profile personalization', free: false, pro: true, business: true, enterprise: true },
  { label: 'Team collaboration', free: false, pro: false, business: 'In development', enterprise: 'In development', soon: true },
  { label: 'Analytics dashboard', free: false, pro: false, business: 'In development', enterprise: 'In development', soon: true },
  { label: 'SSO & advanced security', free: false, pro: false, business: false, enterprise: true },
  { label: 'Support', free: 'Community', pro: 'Priority', business: 'Priority', enterprise: 'Dedicated' },
]
