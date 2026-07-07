import { ACCOUNT_STATUS } from '../lib/constants'

// Status pill for a connected social account. Colors + label come from the
// shared ACCOUNT_STATUS map so they stay consistent across the app.
export default function AccountStatusBadge({ status }) {
  const meta = ACCOUNT_STATUS[status] || ACCOUNT_STATUS.not_connected
  return (
    <span className={`badge ${meta.badge}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
      {meta.label}
    </span>
  )
}
