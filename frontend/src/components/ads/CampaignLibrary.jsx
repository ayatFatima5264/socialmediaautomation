import { useNavigate } from 'react-router-dom'
import CampaignAssetCard from './CampaignAssetCard.jsx'
import { ASSET_KINDS, assetsOfKind, isMediaKind } from '../../lib/ads/assets'
import { assetEditPath, editorForAsset } from '../../lib/ads/tools'

// ---------------------------------------------------------------------------
// Everything this campaign has produced, grouped by kind.
//
// Sections come from the ASSET_KINDS registry, and a section with nothing in it
// is not rendered — an empty "Videos" heading above blank space says the
// feature is broken, when the truth is simply that no video has been made yet.
// The one empty state that IS worth showing is the whole library being empty,
// because that is the moment to point at the tools.
//
// Copy sits in a wider grid than media: a headline is a line of text and reads
// badly in a square, while an image needs to be square to be judged.
// ---------------------------------------------------------------------------

function Section({ kind, assets, actions, campaignId }) {
  if (!assets.length) return null

  const media = isMediaKind(kind.key)

  return (
    <section aria-labelledby={`assets-${kind.key}`}>
      <div className="mb-2 flex items-baseline gap-2">
        <h3 id={`assets-${kind.key}`} className="text-sm font-semibold text-body">
          {kind.label}
        </h3>
        <span className="text-xs text-muted">{assets.length}</span>
      </div>

      <div
        className={`grid gap-3 ${
          media
            ? 'grid-cols-2 lg:grid-cols-3 xl:grid-cols-4'
            : 'grid-cols-1 sm:grid-cols-2 xl:grid-cols-3'
        }`}
      >
        {assets.map((asset) => {
          // Only offer Edit when a workspace can actually reopen this asset —
          // see editorForAsset. A card whose tool cannot prefill itself would
          // open blank and then overwrite the asset with something unrelated.
          const editor = editorForAsset(asset)
          return (
            <CampaignAssetCard
              key={asset.id}
              asset={asset}
              {...actions}
              editHref={
                editor && campaignId ? assetEditPath(editor, campaignId, asset.id) : null
              }
            />
          )
        })}
      </div>
    </section>
  )
}

export default function CampaignLibrary({
  assets,
  campaignId,
  loading,
  error,
  onRename,
  onEditBody,
  onDuplicate,
  onDelete,
}) {
  const navigate = useNavigate()

  /**
   * Send an asset to the composer.
   *
   * Media becomes an attachment, copy becomes the post body — the asset decides
   * which, so the button does the obvious thing for the card it is on rather
   * than the user having to pick a mode first.
   */
  function attach(asset) {
    navigate('/create', {
      state: {
        prefill: isMediaKind(asset.kind)
          ? {
              url: asset.url,
              type: asset.kind === 'video' ? 'video' : 'image',
              name: asset.title,
            }
          : { content: asset.body },
      },
    })
  }

  const actions = { onRename, onEditBody, onDuplicate, onDelete, onAttach: attach }

  if (loading) {
    return (
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="skeleton h-44 w-full" />
        ))}
      </div>
    )
  }

  if (error) {
    return <p className="py-8 text-center text-sm text-rose-600">{error}</p>
  }

  if (!assets.length) {
    return (
      <p className="panel px-4 py-8 text-center text-sm leading-relaxed text-muted">
        Nothing here yet. Everything you generate from the tools below is saved
        into this campaign automatically — there is no Save button to forget.
      </p>
    )
  }

  return (
    <div className="space-y-6">
      {ASSET_KINDS.map((kind) => (
        <Section
          key={kind.key}
          kind={kind}
          assets={assetsOfKind(assets, kind.key)}
          actions={actions}
          campaignId={campaignId}
        />
      ))}
    </div>
  )
}
