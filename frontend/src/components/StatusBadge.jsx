import { STATUS_STYLES } from '../lib/constants'

const DOT = {
  draft: 'bg-slate-400',
  scheduled: 'bg-amber-400',
  publishing: 'bg-sky-400',
  published: 'bg-emerald-400',
  failed: 'bg-rose-400',
}

export default function StatusBadge({ status }) {
  return (
    <span className={`badge ${STATUS_STYLES[status] || STATUS_STYLES.draft}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${DOT[status] || DOT.draft}`} />
      {status}
    </span>
  )
}
