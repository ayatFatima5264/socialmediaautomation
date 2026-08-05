import { Link } from 'react-router-dom'
import PlatformIcon from '../PlatformIcon.jsx'
import CampaignStatusBadge from './CampaignStatusBadge.jsx'
import { campaignPath } from '../../lib/ads/tools'
import { formatRelative } from '../../lib/datetime'

// ---------------------------------------------------------------------------
// Recent campaigns.
//
// Two renderings of one dataset, not two components: a real <table> from `md`
// up, and stacked cards below it. A table forced onto a phone either scrolls
// sideways — which the app forbids globally (see index.css) — or squeezes the
// campaign name down to a few characters, and the name is the one column a
// user scans by.
//
// The row shape is shared by `Row` and `MobileCard` through the same props, so
// a new column is added once in each of two adjacent places rather than being
// reverse-engineered from a grid of divs pretending to be a table.
// ---------------------------------------------------------------------------

function Platforms({ platforms = [] }) {
  if (!platforms.length) {
    return <span className="text-xs text-muted">—</span>
  }
  return (
    <div className="flex items-center gap-1.5">
      {platforms.map((p) => (
        <PlatformIcon key={p} platform={p} size={22} />
      ))}
    </div>
  )
}

function EditLink({ id, className = '' }) {
  return (
    <Link to={campaignPath(id)} className={`btn btn-secondary btn-sm ${className}`}>
      Edit
    </Link>
  )
}

function Row({ campaign }) {
  return (
    <tr className="border-t border-line transition-colors hover:bg-inset">
      <td className="px-4 py-3">
        <Link
          to={campaignPath(campaign.id)}
          className="font-semibold text-body hover:text-accent"
        >
          {campaign.name}
        </Link>
        <div className="mt-0.5 text-xs text-muted">{campaign.objective}</div>
      </td>
      <td className="px-4 py-3">
        <Platforms platforms={campaign.platforms} />
      </td>
      <td className="px-4 py-3">
        <CampaignStatusBadge status={campaign.status} />
      </td>
      <td className="whitespace-nowrap px-4 py-3 text-sm text-muted">
        {formatRelative(campaign.updatedAt) || '—'}
      </td>
      <td className="px-4 py-3 text-right">
        <EditLink id={campaign.id} />
      </td>
    </tr>
  )
}

function MobileCard({ campaign }) {
  return (
    <li className="panel p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Link
            to={campaignPath(campaign.id)}
            className="block truncate font-semibold text-body hover:text-accent"
          >
            {campaign.name}
          </Link>
          <div className="mt-0.5 text-xs text-muted">{campaign.objective}</div>
        </div>
        <CampaignStatusBadge status={campaign.status} />
      </div>

      <div className="mt-3 flex items-center justify-between gap-3">
        <Platforms platforms={campaign.platforms} />
        <span className="text-xs text-muted">{formatRelative(campaign.updatedAt)}</span>
      </div>

      <EditLink id={campaign.id} className="mt-3 w-full" />
    </li>
  )
}

export default function CampaignTable({ campaigns }) {
  return (
    <>
      {/* Desktop */}
      <div className="hidden md:block">
        <table className="w-full text-left">
          <thead>
            <tr className="text-xs font-semibold uppercase tracking-wide text-muted">
              <th scope="col" className="px-4 pb-2 font-semibold">
                Campaign
              </th>
              <th scope="col" className="px-4 pb-2 font-semibold">
                Platforms
              </th>
              <th scope="col" className="px-4 pb-2 font-semibold">
                Status
              </th>
              <th scope="col" className="px-4 pb-2 font-semibold">
                Last Updated
              </th>
              <th scope="col" className="px-4 pb-2 text-right font-semibold">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {campaigns.map((c) => (
              <Row key={c.id} campaign={c} />
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile */}
      <ul className="space-y-2 md:hidden">
        {campaigns.map((c) => (
          <MobileCard key={c.id} campaign={c} />
        ))}
      </ul>
    </>
  )
}
