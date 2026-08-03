// ---------------------------------------------------------------------------
// Business profile completeness.
//
// Both the Settings card and the Business Profile page show a "how complete is
// this" figure. They previously would have computed it independently, which is
// exactly how two counters end up disagreeing — the Settings card saying 4/6
// while the page it links to says 5/6. One function, one answer.
//
// `website` is deliberately NOT counted: it is marked optional in the UI and
// does not change what the AI writes, so including it would mean the profile
// could never read as complete for a business without a site.
// ---------------------------------------------------------------------------

export const PROFILE_FIELDS = [
  { key: 'business_name', label: 'Business name' },
  { key: 'industry', label: 'Industry' },
  { key: 'business_description', label: 'Description' },
  { key: 'target_audience', label: 'Target audience' },
  { key: 'brand_voice', label: 'Brand voice' },
  { key: 'business_goals', label: 'Business goals' },
]

function isFilled(value) {
  if (Array.isArray(value)) return value.length > 0
  return typeof value === 'string' ? value.trim().length > 0 : Boolean(value)
}

/**
 * @param {object|null} profile  canonical API shape (BusinessProfileRead)
 * @returns {{filled:number,total:number,complete:boolean,missing:string[]}}
 */
export function profileCompletion(profile) {
  const missing = []
  let filled = 0

  for (const field of PROFILE_FIELDS) {
    if (isFilled(profile?.[field.key])) filled += 1
    else missing.push(field.label)
  }

  return {
    filled,
    total: PROFILE_FIELDS.length,
    complete: filled === PROFILE_FIELDS.length,
    missing,
  }
}
