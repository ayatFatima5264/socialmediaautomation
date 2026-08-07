import { useState } from 'react'
import { Link } from 'react-router-dom'
import PlatformIcon from '../PlatformIcon.jsx'
import CampaignStatusBadge from './CampaignStatusBadge.jsx'
import { campaignPath } from '../../lib/ads/tools'
import { formatRelative } from '../../lib/datetime'

// ---------------------------------------------------------------------------
// A list of campaigns.
//
// Two renderings of one dataset, not two components: a real <table> from `md`
// up, and stacked cards below it. A table forced onto a phone either scrolls
// sideways — which the app forbids globally (see index.css) — or squeezes the
// campaign name down to a few characters, and the name is the one column a
// user scans by.
//
// ---- Two modes ------------------------------------------------------------
// Without `actions` this is the read-mostly table the Studio home shows: name,
// platforms, status, when it changed, and a way in. With `actions` it becomes
// the management table on the campaign list — rename in place, duplicate,
// archive, delete.
//
// Both share every row through the same props, so a new column is added once in
// each of two adjacent places rather than being reverse-engineered from a grid
// of divs pretending to be a table.
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

/**
 * The campaign's name, editable in place.
 *
 * Renaming is the most common edit and the least consequential, so it does not
 * deserve a trip to the campaign page and back. Commits on blur or Enter,
 * abandons on Escape.
 */
function Name({ campaign, onRename }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(campaign.name)

  if (!onRename) {
    return (
      <Link
        to={campaignPath(campaign.id)}
        className="font-semibold text-body hover:text-accent"
      >
        {campaign.name}
      </Link>
    )
  }

  if (editing) {
    return (
      <input
        autoFocus
        className="input h-8 py-1 text-sm"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => {
          setEditing(false)
          onRename(campaign, draft)
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') e.currentTarget.blur()
          if (e.key === 'Escape') {
            setDraft(campaign.name)
            setEditing(false)
          }
        }}
        aria-label="Campaign name"
      />
    )
  }

  return (
    <span className="flex items-center gap-2">
      <Link
        to={campaignPath(campaign.id)}
        className="font-semibold text-body hover:text-accent"
      >
        {campaign.name}
      </Link>
      <button
        type="button"
        onClick={() => {
          setDraft(campaign.name)
          setEditing(true)
        }}
        title="Rename"
        aria-label={`Rename ${campaign.name}`}
        className="text-xs text-muted transition-colors hover:text-accent"
      >
        ✎
      </button>
    </span>
  )
}

/**
 * Duplicate / archive / delete.
 *
 * Delete asks first — there is no undo behind it, and it takes the campaign's
 * whole asset library with it. Archive does not ask, because it is reversible
 * and the Archived filter is where it goes.
 */
function RowActions({ campaign, actions, className = '' }) {
  const [confirming, setConfirming] = useState(false)
  const archived = campaign.status === 'archived'

  return (
    <div className={`flex flex-wrap items-center justify-end gap-1.5 ${className}`}>
      <Link to={campaignPath(campaign.id)} className="btn btn-secondary btn-sm">
        Open
      </Link>

      <button
        type="button"
        onClick={() => actions.duplicate(campaign)}
        disabled={actions.busy}
        className="btn btn-secondary btn-sm"
        title="Copy this campaign and everything it has made"
      >
        Duplicate
      </button>

      <button
        type="button"
        onClick={() => actions.setStatus(campaign, archived ? 'draft' : 'archived')}
        disabled={actions.busy}
        className="btn btn-secondary btn-sm"
        title={
          archived
            ? 'Bring this campaign back as a draft'
            : 'Put this campaign away — its assets are kept'
        }
      >
        {archived ? 'Restore' : 'Archive'}
      </button>

      {confirming ? (
        <>
          <button
            type="button"
            onClick={() => actions.remove(campaign)}
            disabled={actions.busy}
            className="btn btn-danger btn-sm"
            title={`Permanently delete ${campaign.name} and its ${campaign.creatives} assets`}
          >
            Delete {campaign.creatives > 0 ? `+ ${campaign.creatives} assets` : ''}
          </button>
          <button
            type="button"
            onClick={() => setConfirming(false)}
            className="btn btn-ghost btn-sm"
          >
            Keep
          </button>
        </>
      ) : (
        <button
          type="button"
          onClick={() => setConfirming(true)}
          className="btn btn-ghost btn-sm"
        >
          Delete
        </button>
      )}
    </div>
  )
}

function Row({ campaign, actions }) {
  return (
    <tr className="border-t border-line transition-colors hover:bg-inset">
      <td className="px-4 py-3">
        <Name campaign={campaign} onRename={actions?.rename} />
        <div className="mt-0.5 text-xs text-muted">
          {campaign.campaignType} · {campaign.objective}
        </div>
      </td>
      {actions && (
        <td className="whitespace-nowrap px-4 py-3 text-sm text-muted">
          {campaign.creatives}
        </td>
      )}
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
        {actions ? (
          <RowActions campaign={campaign} actions={actions} />
        ) : (
          <Link to={campaignPath(campaign.id)} className="btn btn-secondary btn-sm">
            Open
          </Link>
        )}
      </td>
    </tr>
  )
}

function MobileCard({ campaign, actions }) {
  return (
    <li className="panel p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Name campaign={campaign} onRename={actions?.rename} />
          <div className="mt-0.5 text-xs text-muted">
            {campaign.campaignType} · {campaign.objective}
          </div>
        </div>
        <CampaignStatusBadge status={campaign.status} />
      </div>

      <div className="mt-3 flex items-center justify-between gap-3">
        <Platforms platforms={campaign.platforms} />
        <span className="text-xs text-muted">
          {campaign.creatives} creatives · {formatRelative(campaign.updatedAt)}
        </span>
      </div>

      {actions ? (
        <RowActions campaign={campaign} actions={actions} className="mt-3 justify-start" />
      ) : (
        <Link
          to={campaignPath(campaign.id)}
          className="btn btn-secondary btn-sm mt-3 w-full"
        >
          Open
        </Link>
      )}
    </li>
  )
}

export default function CampaignTable({ campaigns, actions }) {
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
              {actions && (
                <th scope="col" className="px-4 pb-2 font-semibold">
                  Creatives
                </th>
              )}
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
              <Row key={c.id} campaign={c} actions={actions} />
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile */}
      <ul className="space-y-2 md:hidden">
        {campaigns.map((c) => (
          <MobileCard key={c.id} campaign={c} actions={actions} />
        ))}
      </ul>
    </>
  )
}
