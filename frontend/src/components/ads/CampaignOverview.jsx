import CampaignStatTile from './CampaignStatTile.jsx'

// ---------------------------------------------------------------------------
// What this campaign contains, in one row.
//
// Every number here is derived from the asset array the library below is
// rendering — never fetched separately. Two requests for the same truth is how
// a page ends up claiming eight creatives above a grid showing seven.
//
// ---- Published and Scheduled ---------------------------------------------
// These count ASSETS that have gone out, and today that is always zero: an
// asset gets a `publishedAt` / `scheduledAt` when it is used in a post, and
// that round trip does not exist yet — "Use in Post" hands the asset to the
// composer and the composer never reports back.
//
// They are deliberately NOT derived from the campaign's own status. An Active
// campaign would then show "Published 1", which sitting in a row of asset
// counts reads as "one creative is live" — false, and the same mistake as
// showing 0% CTR for a campaign that never ran (see the note on `ctr` in
// app/models/ad_campaign.py). A zero that is true beats a one that is not.
// ---------------------------------------------------------------------------

const TILES = [
  { key: 'total', label: 'Creatives', accent: 'bg-accent' },
  { key: 'image', label: 'Images', accent: 'bg-sky-400' },
  { key: 'banner', label: 'Banners', accent: 'bg-violet-400' },
  { key: 'video', label: 'Videos', accent: 'bg-amber-400' },
  { key: 'copy', label: 'AI Copy', accent: 'bg-rose-400' },
  { key: 'carousel', label: 'Carousel', accent: 'bg-emerald-400' },
]

/** Assets carrying a timestamp for one of the two delivery states. */
function delivered(assets, field) {
  return assets.filter((a) => a.meta?.[field]).length
}

export default function CampaignOverview({ counts, assets = [], loading }) {
  return (
    <>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8">
        {TILES.map((tile) => (
          <CampaignStatTile
            key={tile.key}
            compact
            label={tile.label}
            accent={tile.accent}
            value={counts?.[tile.key] ?? 0}
            loading={loading}
          />
        ))}
        <CampaignStatTile
          compact
          label="Published"
          accent="bg-emerald-500"
          value={delivered(assets, 'publishedAt')}
          loading={loading}
        />
        <CampaignStatTile
          compact
          label="Scheduled"
          accent="bg-amber-500"
          value={delivered(assets, 'scheduledAt')}
          loading={loading}
        />
      </div>

      <p className="mt-2 text-xs text-muted">
        Published and Scheduled count creatives that have gone out. An asset is marked
        when it is used in a post — the campaign&apos;s own status is shown in its details
        above.
      </p>
    </>
  )
}
