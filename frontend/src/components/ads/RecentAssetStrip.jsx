import { useState } from 'react'
import { Link } from 'react-router-dom'
import { isMediaKind } from '../../lib/ads/assets'
import { campaignPath } from '../../lib/ads/tools'

// ---------------------------------------------------------------------------
// The last few things this account made, across every campaign.
//
// Each tile links to the CAMPAIGN, not to the asset. There is no single-asset
// page and there should not be one: an asset only means anything beside the
// rest of its set, and the campaign is where it can be renamed, reused or
// deleted. A tile that opened a lightbox would be a dead end.
//
// Copy tiles show their words rather than a placeholder graphic — a headline is
// legible at this size and an icon standing in for it would say nothing.
// ---------------------------------------------------------------------------

function Thumb({ asset }) {
  const [failed, setFailed] = useState(false)

  // No URL means there is no file behind it — a browser-rendered video or a
  // saved shot plan, both of which are text records. Same rendering as copy.
  if (!isMediaKind(asset.kind) || !asset.url) {
    return (
      <span className="line-clamp-4 p-2.5 text-xs leading-snug text-body">
        {asset.body}
      </span>
    )
  }

  if (asset.kind === 'video') {
    return (
      <video src={asset.url} muted playsInline preload="metadata" className="h-full w-full object-cover" />
    )
  }

  if (failed) {
    return (
      <span className="grid h-full place-items-center p-2 text-center text-[10px] leading-snug text-muted">
        Image host not responding
      </span>
    )
  }

  return (
    <img
      src={asset.url}
      alt={asset.title}
      loading="lazy"
      onError={() => setFailed(true)}
      className="h-full w-full object-cover"
    />
  )
}

export default function RecentAssetStrip({ assets, loading }) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4 xl:grid-cols-8">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="skeleton aspect-square w-full" />
        ))}
      </div>
    )
  }

  return (
    <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4 xl:grid-cols-8">
      {assets.map((asset) => (
        <Link
          key={asset.id}
          to={campaignPath(asset.campaignId)}
          title={`${asset.title} — ${asset.campaignName}`}
          className="panel overflow-hidden p-0 transition-colors hover:border-accent-line focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-page"
        >
          <div className="flex aspect-square w-full items-start overflow-hidden bg-inset">
            <Thumb asset={asset} />
          </div>
          <span className="block truncate border-t border-line px-2 py-1.5 text-[11px] font-medium text-body">
            {asset.title}
          </span>
        </Link>
      ))}
    </div>
  )
}
