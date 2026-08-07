import { Link } from 'react-router-dom'
import PlatformIcon from '../PlatformIcon.jsx'
import { campaignPath } from '../../lib/ads/tools'
import { PLATFORMS } from '../../lib/constants'

// ---------------------------------------------------------------------------
// The campaign a tool is working inside, shown at the top of every workspace.
//
// This strip is the answer to "why is this tool not asking me anything?". The
// generators now inherit the campaign's name, type, objective, platforms, tone,
// audience and brief — and inheriting silently is indistinguishable from
// ignoring. Showing the values, with one link to go and change them, is what
// makes the inheritance trustworthy rather than mysterious.
//
// Deliberately read-only. Editing a campaign from inside a tool would mean two
// places that write the same record and a half-finished generation sitting on
// top of a brief that just changed underneath it.
// ---------------------------------------------------------------------------

function Fact({ label, children }) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] font-semibold uppercase tracking-wide text-muted">
        {label}
      </dt>
      <dd className="mt-0.5 truncate text-xs font-medium text-body">{children}</dd>
    </div>
  )
}

export default function CampaignContextBar({ campaign }) {
  if (!campaign) return null

  return (
    <section
      aria-label="Current campaign"
      className="rounded-xl border border-accent-line bg-accent-soft px-3.5 py-3"
    >
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-accent">
            Current campaign
          </span>
          <h2 className="truncate text-sm font-bold text-body">{campaign.name}</h2>
        </div>

        <Link
          to={campaignPath(campaign.id)}
          className="btn btn-secondary btn-sm shrink-0 bg-surface"
        >
          Campaign
        </Link>
      </div>

      <dl className="mt-2.5 grid gap-x-4 gap-y-2 sm:grid-cols-2 lg:grid-cols-4">
        <Fact label="Type">{campaign.campaignType}</Fact>
        <Fact label="Objective">{campaign.objective}</Fact>
        <Fact label="Platforms">
          {campaign.platforms?.length ? (
            <span className="flex items-center gap-1.5">
              {campaign.platforms.map((p) => (
                <PlatformIcon key={p} platform={p} size={18} />
              ))}
              <span className="sr-only">
                {campaign.platforms.map((p) => PLATFORMS[p]?.label || p).join(', ')}
              </span>
            </span>
          ) : (
            '—'
          )}
        </Fact>
        <Fact label="Tone">{campaign.tone || 'Not set'}</Fact>
      </dl>

      {campaign.brief && (
        <p className="mt-2 line-clamp-2 border-t border-accent-line/50 pt-2 text-xs leading-relaxed text-muted">
          <span className="font-semibold text-body">Brief: </span>
          {campaign.brief}
        </p>
      )}
    </section>
  )
}
