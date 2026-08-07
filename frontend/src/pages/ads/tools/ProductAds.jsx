import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import AdsWorkspace, { Field, RailSection } from '../../../components/ads/workspace/AdsWorkspace.jsx'
import AssetEditBar from '../../../components/ads/AssetEditBar.jsx'
import CreativeResults from '../../../components/ads/workspace/CreativeResults.jsx'
import GenerateButton from '../../../components/ads/workspace/GenerateButton.jsx'
import PreviewStage from '../../../components/ads/workspace/PreviewStage.jsx'
import UploadField from '../../../components/ads/workspace/UploadField.jsx'
import useAdGeneration from '../../../hooks/useAdGeneration'
import useCampaignContext from '../../../hooks/useCampaignContext'
import { useToast } from '../../../context/ToastContext.jsx'
import { api } from '../../../lib/api'
import { ASPECT_RATIOS } from '../../../lib/constants'
import { campaignSubject, campaignType, stylePrompt, stylesFor } from '../../../lib/ads/campaignTypes'
import { campaignToolPath } from '../../../lib/ads/tools'

// ---------------------------------------------------------------------------
// Product Ads — wired to /api/ads/creative.
//
// ---- Who this tool is for -------------------------------------------------
// Product campaigns, and only product campaigns. A campaign promoting a blog
// has no product to photograph, no background to place it on and no scene to
// stage — so the Campaign page does not offer this tool to one, and a Website
// campaign that reaches it by URL is pointed at Website Promotion instead of
// being asked for a product it does not have.
//
// ---- On the uploaded photo ------------------------------------------------
// The image model behind this endpoint is text-to-image: it cannot take your
// product photo as input. So the upload is NOT sent to it, and the field says
// so. It is still worth having — the photo is what you keep for reference and
// what an editing pass will use once one exists — but the generated creative is
// built from the written brief, and pretending otherwise would have users
// uploading a bottle and wondering why a different bottle came back.
//
// Inside a campaign that brief comes from the campaign; outside one the field
// appears, because there is nothing else for the model to read.
// ---------------------------------------------------------------------------

const TOOL = 'Product Ads'
const PHASE = 2
const VERSIONS = 3

export default function ProductAds() {
  const { campaign, editingAsset, saveAssets } = useCampaignContext()

  const type = campaignType(campaign?.campaignType)
  const styles = stylesFor(campaign?.campaignType)

  const [product, setProduct] = useState('')
  const [scene, setScene] = useState('')
  const [style, setStyle] = useState(styles[0].label)
  const [ratio, setRatio] = useState('1:1')
  const [chosen, setChosen] = useState(null)
  const [saveAsNew, setSaveAsNew] = useState(false)

  // Opened from an asset: bring back the settings it was made with. Applied
  // once, when the asset arrives — see the note in BannerGenerator.
  const prefilled = useRef(false)
  useEffect(() => {
    if (!editingAsset || prefilled.current) return
    prefilled.current = true
    const m = editingAsset.meta || {}
    if (m.ratio) setRatio(m.ratio)
    if (m.style) setStyle(m.style)
    if (m.scene) setScene(m.scene)
  }, [editingAsset])

  const activeStyle = styles.some((s) => s.label === style) ? style : styles[0].label

  const toast = useToast()
  const { data, loading, run } = useAdGeneration(api.adCreative)
  const images = data?.images || null

  // A campaign whose type has its own creative tool, and it is not this one.
  const wrongTool = campaign && type.creativeTool && type.creativeTool !== 'product-ads'

  async function generate() {
    const base = campaign ? campaignSubject(campaign) : product.trim()
    if (base.length < 2) {
      toast.error('Describe the product — that is what the image model reads.')
      return
    }

    setChosen(null)
    const result = await run({
      subject: [base, scene.trim(), stylePrompt(campaign?.campaignType, activeStyle)]
        .filter(Boolean)
        .join(' '),
      background: activeStyle,
      aspect_ratio: ratio,
      // Re-doing one asset returns one version; three would leave the user
      // choosing which replaces it.
      count: editingAsset && !saveAsNew ? 1 : VERSIONS,
    })

    if (result?.images?.length) {
      await saveAssets(
        result.images.map((url, i) => ({
          kind: 'image',
          title: editingAsset && !saveAsNew
            ? editingAsset.title
            : `${campaign ? campaign.name : product.trim()} — version ${i + 1}`,
          url,
          tool: TOOL,
          meta: { ratio, style: activeStyle, scene: scene.trim() },
        })),
        { saveAsNew },
      )
    }
  }

  return (
    <AdsWorkspace
      title={TOOL}
      campaign={campaign}
      description="Turn a product brief into a finished ad — background, composition and framing, sized for every placement."
      controls={
        <>
          <AssetEditBar
            asset={editingAsset}
            campaign={campaign}
            saveAsNew={saveAsNew}
            onSaveAsNewChange={setSaveAsNew}
          />

          {wrongTool && (
            <p className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs leading-relaxed text-amber-700">
              This is a {type.label} campaign, which has no product to shoot.{' '}
              <Link
                to={campaignToolPath(type.creativeTool, campaign.id)}
                className="font-semibold underline"
              >
                Website Promotion
              </Link>{' '}
              is the tool built for it.
            </p>
          )}

          {/* Inside a campaign the brief IS the product description, already
              written and shown in the bar above. */}
          {!campaign && (
            <Field label="Product">
              <input
                className="input"
                value={product}
                onChange={(e) => setProduct(e.target.value)}
                placeholder="Amber glass skincare serum bottle"
              />
            </Field>
          )}

          <Field label="Scene" hint="Optional — adds to the brief">
            <textarea
              rows={3}
              className="input resize-none"
              value={scene}
              onChange={(e) => setScene(e.target.value)}
              placeholder="On a marble slab, soft morning light, eucalyptus leaves"
            />
          </Field>

          <Field label="Presentation" hint={activeStyle}>
            <div className="grid gap-1.5 sm:grid-cols-2">
              {styles.map((s) => (
                <button
                  key={s.label}
                  type="button"
                  onClick={() => setStyle(s.label)}
                  aria-pressed={activeStyle === s.label}
                  className={`rounded-lg border px-2.5 py-2 text-left text-xs font-medium transition ${
                    activeStyle === s.label
                      ? 'border-accent bg-accent-soft text-accent'
                      : 'border-line text-muted hover:border-accent'
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </Field>

          <Field label="Aspect ratio">
            <select
              className="select"
              value={ratio}
              onChange={(e) => setRatio(e.target.value)}
              aria-label="Aspect ratio"
            >
              {ASPECT_RATIOS.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Reference photo" hint="Kept, not generated from">
            <UploadField hint="Your own product shot, for reference" />
            <p className="mt-1.5 text-[11px] leading-relaxed text-muted">
              The image model is text-to-image and does not read this upload. The creative
              is generated from the brief and the settings above.
            </p>
          </Field>
        </>
      }
      action={
        <GenerateButton
          label={editingAsset && !saveAsNew ? 'Replace This Creative' : `Generate ${VERSIONS} Versions`}
          toolName={TOOL}
          phase={PHASE}
          onClick={generate}
          loading={loading}
        />
      }
      stage={
        images ? (
          <div className="card flex min-h-[320px] flex-col p-4 lg:min-h-full">
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-sm font-semibold text-body">Generated versions</h2>
              <span className="text-xs text-muted">{ratio} · pick one</span>
            </div>
            <CreativeResults images={images} sources={data?.sources} selected={chosen} onSelect={setChosen} />
          </div>
        ) : (
          <PreviewStage
            hint={
              campaign
                ? `An example of what this produces. ${campaign.name}'s brief is already loaded — choose a presentation and press Generate.`
                : 'An example of the kind of ad this produces. Describe your product on the left and press Generate for three of your own.'
            }
            art="productAd"
            ratio="square"
            toolName={TOOL}
            caption={ratio}
          />
        )
      }
      output={
        <>
          <RailSection title="Versions">
            {images ? (
              <p className="text-xs leading-relaxed text-muted">
                {images.length} versions of the same brief
                {campaign ? `, all saved to ${campaign.name}` : ''}. Pick one in the centre,
                then open it full size.
              </p>
            ) : (
              <p className="panel px-3 py-6 text-center text-xs text-muted">
                Generated versions appear here — keep several to test against each other.
              </p>
            )}
          </RailSection>

          <RailSection title="Actions">
            <div className="space-y-2">
              <a
                href={chosen || undefined}
                target="_blank"
                rel="noreferrer"
                className={`btn btn-secondary btn-sm w-full ${chosen ? '' : 'pointer-events-none opacity-50'}`}
                title={chosen ? 'Open the selected creative' : 'Select a version first'}
              >
                Open full size
              </a>
              <button
                type="button"
                onClick={generate}
                disabled={loading || !images}
                className="btn btn-secondary btn-sm w-full"
              >
                Regenerate
              </button>
            </div>
          </RailSection>
        </>
      }
    />
  )
}
