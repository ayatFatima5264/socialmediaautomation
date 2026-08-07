import { CAMPAIGN_TYPES } from '../../lib/ads/campaignTypes'

// ---------------------------------------------------------------------------
// What is this campaign advertising?
//
// A radio group rather than the pill selector used for Objective, for two
// reasons: the choice carries a sentence of explanation each — "Sell a physical
// or digital product" is what stops someone promoting a blog picking Product
// Promotion — and unlike a pill, a radio cannot be deselected. Every tool
// downstream reads this value, so "none" is not a state any of them can render.
//
// It sits ABOVE Objective in the form because it is the more consequential of
// the two: the objective changes the words, the type changes which tools exist.
// ---------------------------------------------------------------------------

export default function CampaignTypeSelect({ value, onChange, name = 'campaign-type' }) {
  return (
    <div role="radiogroup" aria-label="Campaign type" className="grid gap-2 sm:grid-cols-2">
      {CAMPAIGN_TYPES.map((type) => {
        const on = value === type.label
        return (
          <label
            key={type.key}
            className={`flex cursor-pointer items-start gap-2.5 rounded-xl border p-3 transition ${
              on
                ? 'border-accent bg-accent-soft'
                : 'border-line bg-surface hover:border-accent-line'
            }`}
          >
            <input
              type="radio"
              name={name}
              value={type.label}
              checked={on}
              onChange={() => onChange(type.label)}
              style={{ accentColor: 'var(--accent)' }}
              className="mt-0.5 h-4 w-4 shrink-0"
            />
            <span className="min-w-0">
              <span
                className={`block text-sm font-semibold ${on ? 'text-accent' : 'text-body'}`}
              >
                {type.label}
              </span>
              <span className="mt-0.5 block text-xs leading-snug text-muted">
                {type.description}
              </span>
            </span>
          </label>
        )
      })}
    </div>
  )
}
