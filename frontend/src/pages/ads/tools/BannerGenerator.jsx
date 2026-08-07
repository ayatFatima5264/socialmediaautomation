import { useEffect, useRef, useState } from 'react'
import AdsWorkspace, { Field, RailSection } from '../../../components/ads/workspace/AdsWorkspace.jsx'
import AssetEditBar from '../../../components/ads/AssetEditBar.jsx'
import GenerateButton from '../../../components/ads/workspace/GenerateButton.jsx'
import PreviewStage from '../../../components/ads/workspace/PreviewStage.jsx'
import CreativeResults from '../../../components/ads/workspace/CreativeResults.jsx'
import UploadField from '../../../components/ads/workspace/UploadField.jsx'
import useAdGeneration from '../../../hooks/useAdGeneration'
import useBrandKit from '../../../hooks/useBrandKit'
import useCampaignContext from '../../../hooks/useCampaignContext'
import { useToast } from '../../../context/ToastContext.jsx'
import { api } from '../../../lib/api'
import { BANNER_EXPORT_SETS, BANNER_SIZES, CTA_OPTIONS } from '../../../lib/ads/constants'
import { campaignSubject, campaignType, stylePrompt, stylesFor } from '../../../lib/ads/campaignTypes'

// ---------------------------------------------------------------------------
// Banner Generator — the workspace.
//
// One layout on the left, the chosen size in the centre, and every OTHER size
// it re-flows into on the right. That right column is the point of the tool:
// the value is not one banner, it is the set.
//
// ---- What this page no longer asks ---------------------------------------
// It used to ask what the banner shows, what the offer is, and which brand
// colour to use — questions the campaign had already answered, in a page the
// user reached FROM that campaign. All six now come from the campaign and the
// Brand Kit, and are shown in the bar above rather than re-collected.
//
// What is left is the six decisions that are genuinely about this banner and
// nothing else: size, headline, subheadline, CTA, background style, image.
//
// ---- Background styles ----------------------------------------------------
// The options come from the campaign TYPE. A Website campaign is offered a
// browser window, a laptop mockup, a blog thumbnail; a Product campaign is
// offered a surface, a shadow, a reflection — and only a Product campaign gets
// the upload and cut-out controls, because only it has a product to shoot.
// That mapping lives in lib/ads/campaignTypes.js, not here.
// ---------------------------------------------------------------------------

const TOOL = 'Banner Generator'
const PHASE = 2

// The banner ratio the image model is asked for. Display sizes are far wider
// than any generation ratio, so each maps to the nearest one the model handles
// — the layout re-flow that produces the exact pixel sizes is a compositing
// step, not a generation one.
const RATIO_FOR_SIZE = {
  '1200x628': '16:9',
  '1080x1080': '1:1',
  '1080x1920': '9:16',
  '728x90': '16:9',
  '300x250': '1:1',
  '160x600': '9:16',
}

export default function BannerGenerator() {
  const { campaign, editingAsset, saveAssets } = useCampaignContext()
  const { brandKit } = useBrandKit()

  const type = campaignType(campaign?.campaignType)
  const styles = stylesFor(campaign?.campaignType)

  const [size, setSize] = useState(BANNER_SIZES[0])
  const [headline, setHeadline] = useState('')
  const [subheadline, setSubheadline] = useState('')
  const [cta, setCta] = useState(CTA_OPTIONS[0])
  const [style, setStyle] = useState(styles[0].label)
  const [cutout, setCutout] = useState(true)
  // The campaign arrives a moment after the first render, and with it a
  // different set of styles. Deriving the active one — rather than resetting it
  // in an effect — means the control is never briefly showing a style that does
  // not exist for this campaign type, and `stylePrompt` can never be handed a
  // label from the previous type and return an empty prompt.
  const activeStyle = styles.some((s) => s.label === style) ? style : styles[0].label
  // Only asked for when there is no campaign to read it from — see below.
  const [subject, setSubject] = useState('')
  const [saveAsNew, setSaveAsNew] = useState(false)

  // ---- Edit mode ---------------------------------------------------------
  // Opened from an asset, the controls come back up as they were when it was
  // made — everything the tool recorded in `meta`. Applied ONCE, when the asset
  // arrives: re-running on every render would fight the user's own edits, and
  // the asset loads a moment after the first paint.
  const prefilled = useRef(false)
  useEffect(() => {
    if (!editingAsset || prefilled.current) return
    prefilled.current = true
    const m = editingAsset.meta || {}
    const size = BANNER_SIZES.find((s) => s.value === m.size)
    if (size) setSize(size)
    if (m.headline) setHeadline(m.headline)
    if (m.subheadline) setSubheadline(m.subheadline)
    if (m.cta) setCta(m.cta)
    if (m.style) setStyle(m.style)
  }, [editingAsset])

  const toast = useToast()
  const { data, loading, run } = useAdGeneration(api.adCreative)
  const images = data?.images || null

  // The Brand Kit's own colours, falling back to the app accent so the swatch
  // row is never an empty box. A user with no Brand Kit sees the palette the
  // rest of the app uses, which is the truth rather than a placeholder.
  const brandColors = (brandKit?.brand_colors || []).filter(Boolean)
  const palette = brandColors.length ? brandColors : ['#1F8A5B']

  async function generate() {
    // The brief IS the subject inside a campaign. Outside one there is nothing
    // to fall back on, so the field appears and is required — the image model
    // is text-to-image and cannot generate from an empty string.
    const base = campaign ? campaignSubject(campaign) : subject.trim()
    if (base.length < 2) {
      toast.error('Describe what the banner should show first.')
      return
    }

    const result = await run({
      subject: [base, stylePrompt(campaign?.campaignType, activeStyle)].filter(Boolean).join(' '),
      // The headline steers composition (it asks for empty space to place text
      // in) without asking the model to render the words, which it does badly.
      headline: headline.trim() || null,
      aspect_ratio: RATIO_FOR_SIZE[size.value] || '16:9',
      // Re-doing ONE asset returns one banner. Two would leave the user picking
      // which of them replaces it, a choice edit mode exists to avoid.
      count: editingAsset && !saveAsNew ? 1 : 2,
    })

    // Saved the moment it exists, not when the user remembers to. Everything
    // that identifies the banner rides along in `meta` so the library can say
    // what size it was made at without re-deriving it from the image.
    if (result?.images?.length) {
      await saveAssets(
        result.images.map((url, i) => ({
          kind: 'banner',
          // In edit mode the asset keeps whatever the user called it; only a
          // brand-new banner gets a generated name.
          title: editingAsset && !saveAsNew
            ? editingAsset.title
            : `${headline.trim() || size.label} — ${i + 1}`,
          url,
          tool: TOOL,
          meta: {
            size: size.value,
            sizeLabel: size.label,
            style: activeStyle,
            headline: headline.trim(),
            subheadline: subheadline.trim(),
            cta,
          },
        })),
        { saveAsNew },
      )
    }
  }

  return (
    <AdsWorkspace
      title={TOOL}
      campaign={campaign}
      description="Build one banner layout and re-flow it into every standard display size — never a stretched crop."
      controls={
        <>
          <AssetEditBar
            asset={editingAsset}
            campaign={campaign}
            saveAsNew={saveAsNew}
            onSaveAsNewChange={setSaveAsNew}
          />

          <Field label="Banner size" hint={size.hint}>
            <select
              className="select"
              value={size.value}
              onChange={(e) =>
                setSize(BANNER_SIZES.find((s) => s.value === e.target.value) || BANNER_SIZES[0])
              }
              aria-label="Banner size"
            >
              {BANNER_SIZES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label} — {s.hint}
                </option>
              ))}
            </select>
          </Field>

          {/* Only outside a campaign. Inside one this is the brief, already
              written, already shown in the bar above. */}
          {!campaign && (
            <Field label="What the banner shows" hint="Or open this from a campaign">
              <input
                className="input"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder={type.subjectPlaceholder}
              />
            </Field>
          )}

          <Field label="Headline">
            <input
              className="input"
              value={headline}
              onChange={(e) => setHeadline(e.target.value)}
              placeholder="Summer Sale"
            />
          </Field>

          <Field label="Subheadline" hint="Optional">
            <input
              className="input"
              value={subheadline}
              onChange={(e) => setSubheadline(e.target.value)}
              placeholder="Up to 50% off, this week only"
            />
          </Field>

          <Field label="Call to action">
            <select
              className="select"
              value={cta}
              onChange={(e) => setCta(e.target.value)}
              aria-label="Call to action"
            >
              {CTA_OPTIONS.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Background style" hint={type.label}>
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

          {/* Product campaigns, and only product campaigns, have something to
              photograph and cut out. A website campaign shown these controls
              would be asked for a product it does not have. */}
          {type.productControls && (
            <Field label="Product image" hint="Kept, not generated from">
              <UploadField hint="Your own product shot, for reference" />
              <label className="mt-2 flex items-center gap-2 text-xs text-muted">
                <input
                  type="checkbox"
                  checked={cutout}
                  onChange={(e) => setCutout(e.target.checked)}
                  style={{ accentColor: 'var(--accent)' }}
                  className="h-3.5 w-3.5"
                />
                Ask for a clean cut-out background
              </label>
              <p className="mt-1.5 text-[11px] leading-relaxed text-muted">
                The image model is text-to-image and does not read this upload. The banner
                is generated from the campaign brief and the style above.
              </p>
            </Field>
          )}

          <Field label="Brand colour" hint={brandColors.length ? 'From your Brand Kit' : 'No Brand Kit yet'}>
            <div className="flex flex-wrap gap-2">
              {palette.map((c) => (
                <span
                  key={c}
                  title={c}
                  style={{ background: c }}
                  className="h-8 w-8 rounded-full border-2 border-line"
                />
              ))}
            </div>
            <p className="mt-1.5 text-[11px] leading-relaxed text-muted">
              Applied when the banner is composited into its final sizes. Change these in
              your Brand Kit, not here — they belong to every campaign, not this one.
            </p>
          </Field>
        </>
      }
      action={
        <GenerateButton
          label={editingAsset && !saveAsNew ? 'Replace This Banner' : 'Generate Banners'}
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
              <h2 className="text-sm font-semibold text-body">Generated banners</h2>
              <span className="text-xs text-muted">{size.label} · {size.hint}</span>
            </div>
            <CreativeResults images={images} sources={data?.sources} />
            <p className="mt-3 text-xs leading-relaxed text-muted">
              {campaign
                ? `Saved to ${campaign.name}. `
                : 'Generated but not saved — open this tool from a campaign to keep what it makes. '}
              Generated at the nearest ratio the model supports; re-flowing these into the
              exact display pixel sizes is a compositing step, still to come.
            </p>
          </div>
        ) : (
          <PreviewStage
            hint={
              campaign
                ? `An example banner. This tool already has ${campaign.name}'s brief — set the size, headline and style, then press Generate.`
                : 'An example banner. Describe what yours should show, pick a size, and press Generate.'
            }
            art="bannerAd"
            ratio="wide"
            toolName={TOOL}
            caption={`${size.label} · ${size.hint}`}
          />
        )
      }
      output={
        <RailSection title="Export sizes">
          <div className="space-y-3">
            {BANNER_EXPORT_SETS.map((set) => (
              <div key={set.network} className="panel p-3">
                <div className="text-xs font-semibold text-body">{set.network}</div>
                <ul className="mt-1.5 space-y-1">
                  {set.sizes.map((s) => (
                    <li key={s} className="flex items-center justify-between gap-2 text-xs">
                      <span className="text-muted">{s}</span>
                      <span className="text-muted opacity-60">—</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          <button
            type="button"
            disabled
            className="btn btn-secondary btn-sm mt-3 w-full"
            title="Available once banners have been generated"
          >
            Download all sizes
          </button>
        </RailSection>
      }
    />
  )
}
