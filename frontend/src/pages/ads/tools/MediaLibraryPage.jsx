import { useState } from 'react'
import AdsPageHeader from '../../../components/ads/AdsPageHeader.jsx'
import CampaignContextBar from '../../../components/ads/CampaignContextBar.jsx'
import useCampaignContext from '../../../hooks/useCampaignContext'
import MediaBrowser from '../../../components/media/MediaBrowser.jsx'

// ---------------------------------------------------------------------------
// Media Library — a real page, not a placeholder.
//
// The library already ships: a curated stock set plus the user's own uploads,
// searchable by category, industry, colour and orientation. Until now it was
// only reachable as a picker from inside the editor, which is right when you
// are choosing an image for something — and wrong when you just want to see
// what you have or add to it before starting a campaign.
//
// So this renders the SAME MediaBrowser the picker uses, in manage mode. No
// second implementation, no drift: a fix to the browser lands in both surfaces.
//
// `fill={false}` because this page sits in the app shell's <main>, which
// already scrolls. The browser's own comment says as much — passing true here
// would strand the search controls above a short scrolling box.
// ---------------------------------------------------------------------------

export default function MediaLibraryPage() {
  const [selectedId, setSelectedId] = useState(null)
  // Opened from a campaign, this page returns to it. The library itself is
  // account-wide, not campaign-scoped — the campaign only decides where Back
  // goes and what the bar above says.
  const { campaign, backTo, backLabel } = useCampaignContext()

  return (
    <div className="space-y-5 pb-2">
      <AdsPageHeader
        title="Media Library"
        description="Your uploads and the curated stock set, in one place. Anything here can be dropped into an ad from inside any tool."
        backLabel={backLabel}
        backTo={backTo}
      />

      {campaign && <CampaignContextBar campaign={campaign} />}

      <div className="card p-4">
        <MediaBrowser
          manage
          fill={false}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
      </div>
    </div>
  )
}
