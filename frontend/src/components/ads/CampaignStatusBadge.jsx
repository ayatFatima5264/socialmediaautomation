import { CAMPAIGN_STATUS } from '../../lib/ads/constants'

// Campaign lifecycle pill. Same construction as StatusBadge (posts) and
// AccountStatusBadge (connections) so the three read as one component family
// without sharing a vocabulary none of them fully owns.
export default function CampaignStatusBadge({ status }) {
  const meta = CAMPAIGN_STATUS[status] || CAMPAIGN_STATUS.draft
  return (
    <span className={`badge ${meta.badge}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
      {meta.label}
    </span>
  )
}
