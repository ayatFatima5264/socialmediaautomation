import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import AdsPageHeader from '../../components/ads/AdsPageHeader.jsx'
import CampaignStatusBadge from '../../components/ads/CampaignStatusBadge.jsx'
import PlatformIcon from '../../components/PlatformIcon.jsx'
import { campaignStore } from '../../lib/ads/store'
import { ADS_BASE_PATH, toolHref, toolsInCategory } from '../../lib/ads/tools'
import { formatRelative } from '../../lib/datetime'

// ---------------------------------------------------------------------------
// The campaign editor's placeholder — the destination for "New Campaign" and
// for every Edit control in the campaigns table.
//
// It exists in phase 1 so those controls lead somewhere real instead of being
// dead buttons, and so the two routes the AI Campaign Builder will need are
// already reserved and titled. When a record is being opened, its stored
// summary is shown: enough to confirm the store round-trips, without inventing
// an editing UI that phase 3 will design properly.
// ---------------------------------------------------------------------------

export default function CampaignPlaceholder() {
  const { id } = useParams()
  const isNew = !id
  const [campaign, setCampaign] = useState(null)
  const [loading, setLoading] = useState(!isNew)

  useEffect(() => {
    if (isNew) return
    let cancelled = false
    campaignStore
      .get(id)
      .then((row) => {
        if (!cancelled) setCampaign(row)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [id, isNew])

  return (
    <div className="space-y-6 pb-4">
      <AdsPageHeader
        title={isNew ? 'New Campaign' : campaign?.name || 'Campaign'}
        description={
          isNew
            ? 'The AI Campaign Builder will take a short brief — product, audience, objective and platforms — and generate the creatives and copy for the whole campaign.'
            : 'Campaign editing arrives with the AI Campaign Builder. Until then this is a read-only summary of what is stored.'
        }
        backLabel="AI Ads Studio"
      />

      {/* Stored summary, for an existing campaign. */}
      {!isNew && (
        <div className="card p-5">
          {loading ? (
            <div className="space-y-3">
              <div className="skeleton h-5 w-48" />
              <div className="skeleton h-4 w-32" />
            </div>
          ) : campaign ? (
            <dl className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-muted">
                  Objective
                </dt>
                <dd className="mt-1.5 text-sm font-medium text-body">{campaign.objective}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-muted">
                  Platforms
                </dt>
                <dd className="mt-1.5 flex items-center gap-1.5">
                  {campaign.platforms?.length ? (
                    campaign.platforms.map((p) => (
                      <PlatformIcon key={p} platform={p} size={22} />
                    ))
                  ) : (
                    <span className="text-sm text-muted">—</span>
                  )}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-muted">
                  Status
                </dt>
                <dd className="mt-1.5">
                  <CampaignStatusBadge status={campaign.status} />
                </dd>
              </div>
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-muted">
                  Creatives
                </dt>
                <dd className="mt-1.5 text-sm font-medium text-body">
                  {campaign.creatives}
                  <span className="ml-2 font-normal text-muted">
                    updated {formatRelative(campaign.updatedAt)}
                  </span>
                </dd>
              </div>
            </dl>
          ) : (
            <p className="py-6 text-center text-sm text-muted">
              That campaign no longer exists.{' '}
              <Link to={ADS_BASE_PATH} className="link-accent">
                Back to AI Ads Studio
              </Link>
            </p>
          )}
        </div>
      )}

      {/* Somewhere useful to go in the meantime. */}
      <div className="card p-5">
        <h2 className="text-base font-bold text-body">Start with a single creative</h2>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
          Full campaign generation is coming with the AI Campaign Builder. Each tool below will
          produce one part of a campaign on its own.
        </p>

        {/* The creation tools only. Offering the whole registry here — every
            AI tool and every asset library — would be a list, not a shortcut. */}
        <div className="mt-4 flex flex-wrap gap-2">
          {[...toolsInCategory('create'), ...toolsInCategory('video')].map((tool) => (
            <Link key={tool.slug} to={toolHref(tool)} className="btn btn-secondary btn-sm">
              {tool.name}
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}
