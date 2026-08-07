import { useEffect, useRef, useState } from 'react'
import AdsWorkspace, { Field, RailSection } from '../../../components/ads/workspace/AdsWorkspace.jsx'
import AssetEditBar from '../../../components/ads/AssetEditBar.jsx'
import GenerateButton from '../../../components/ads/workspace/GenerateButton.jsx'
import PreviewStage from '../../../components/ads/workspace/PreviewStage.jsx'
import UploadField from '../../../components/ads/workspace/UploadField.jsx'
import CreativeResults from '../../../components/ads/workspace/CreativeResults.jsx'
import useAdGeneration from '../../../hooks/useAdGeneration'
import useCampaignContext from '../../../hooks/useCampaignContext'
import { useToast } from '../../../context/ToastContext.jsx'
import { api } from '../../../lib/api'
import { CAROUSEL_SLIDE_COUNTS } from '../../../lib/ads/constants'
import {
  campaignSubject,
  campaignType,
  carouselRoles,
  stylePrompt,
  stylesFor,
} from '../../../lib/ads/campaignTypes'

// ---------------------------------------------------------------------------
// Carousel Ads — the workspace.
//
// A carousel is a sequence, not a pile of images, so the centre column is a
// slide strip with one selected rather than a single preview.
//
// ---- Where the structure comes from --------------------------------------
// The role of each slide is decided by the CAMPAIGN TYPE, not by this file. A
// product carousel runs Feature → Benefit → Close-up → Comparison → CTA; a
// website carousel runs Problem → Solution → Tips → Features → Visit the
// website. Those are different arguments, and generating the second with the
// first's structure produces a deck that never makes its point.
//
// Lengthening a carousel adds argument in the MIDDLE — the closing ask is
// always the last slide, whether there are five or ten. See carouselRoles().
//
// Each slide is generated with its own role folded into the prompt, so slide
// three is a close-up because it was asked to be, not because the seed varied.
// ---------------------------------------------------------------------------

const TOOL = 'Carousel Ads'
const PHASE = 2

export default function CarouselAds() {
  const { campaign, editingAsset, saveAssets } = useCampaignContext()

  const type = campaignType(campaign?.campaignType)
  const styles = stylesFor(campaign?.campaignType)

  const [slides, setSlides] = useState(5)
  const [active, setActive] = useState(0)
  const [style, setStyle] = useState(styles[0].label)
  const [subject, setSubject] = useState('')
  const [saveAsNew, setSaveAsNew] = useState(false)

  // Editing a carousel asset edits ONE SLIDE — that is what a card in the
  // library is. The slide's own role and position come back from its meta, so
  // re-generating slide 3 asks for a slide 3 rather than a fresh cover.
  const prefilled = useRef(false)
  useEffect(() => {
    if (!editingAsset || prefilled.current) return
    prefilled.current = true
    const m = editingAsset.meta || {}
    if (m.of) setSlides(m.of)
    if (m.slide) setActive(m.slide - 1)
    if (m.style) setStyle(m.style)
  }, [editingAsset])

  const activeStyle = styles.some((s) => s.label === style) ? style : styles[0].label

  const toast = useToast()
  const { data, loading, run } = useAdGeneration(api.adCreative)
  const images = data?.images || null

  const roles = carouselRoles(campaign?.campaignType, slides)

  async function generate() {
    const base = campaign ? campaignSubject(campaign) : subject.trim()
    if (base.length < 2) {
      toast.error('Describe the story the carousel should tell first.')
      return
    }

    // ---- Editing one slide, or generating the whole deck ------------------
    // A card in the library is ONE slide, so editing re-generates that slide in
    // its own position — asking for the whole carousel again would replace one
    // asset and orphan the other four.
    const editingSlide = editingAsset && !saveAsNew
    const slideIndex = editingSlide ? (editingAsset.meta?.slide || 1) - 1 : 0

    if (!editingSlide) setActive(0)

    const result = await run({
      subject: [
        base,
        stylePrompt(campaign?.campaignType, activeStyle),
        editingSlide
          ? `Slide ${slideIndex + 1} of a ${slides}-slide carousel — its job is: ${roles[slideIndex]}.`
          : `A ${slides}-slide carousel running: ${roles.join(' → ')}.`,
      ]
        .filter(Boolean)
        .join(' '),
      aspect_ratio: '4:5',
      // One image per slide. The endpoint varies the seed per image, and the
      // roles are named in the prompt so the set reads as a sequence rather
      // than the same picture repeated with different noise.
      count: editingSlide ? 1 : slides,
    })

    if (result?.images?.length) {
      await saveAssets(
        result.images.map((url, i) => {
          const position = editingSlide ? slideIndex : i
          return {
            kind: 'carousel',
            title: editingSlide
              ? editingAsset.title
              : `Slide ${position + 1} — ${roles[position] || ''}`.trim(),
            url,
            tool: TOOL,
            meta: {
              slide: position + 1,
              of: slides,
              role: roles[position],
              style: activeStyle,
            },
          }
        }),
        { saveAsNew },
      )
    }
  }

  function changeCount(next) {
    setSlides(next)
    setActive((a) => Math.min(a, next - 1))
  }

  return (
    <AdsWorkspace
      title={TOOL}
      campaign={campaign}
      description="Build a multi-card ad that tells one story across the swipe — a hook, the argument, and a close."
      controls={
        <>
          <AssetEditBar
            asset={editingAsset}
            campaign={campaign}
            saveAsNew={saveAsNew}
            onSaveAsNewChange={setSaveAsNew}
          />

          <Field label="Number of slides" hint={`${slides} slides`}>
            <select
              className="select"
              value={slides}
              onChange={(e) => changeCount(Number(e.target.value))}
              aria-label="Number of slides"
            >
              {CAROUSEL_SLIDE_COUNTS.map((n) => (
                <option key={n} value={n}>
                  {n} slides
                </option>
              ))}
            </select>
            <p className="mt-1.5 text-[11px] leading-relaxed text-muted">
              The closing ask stays last however many you pick — extra slides add argument
              in the middle.
            </p>
          </Field>

          {!campaign && (
            <Field label="What the carousel shows" hint="Or open this from a campaign">
              <textarea
                rows={4}
                className="input resize-none"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder={type.subjectPlaceholder}
              />
            </Field>
          )}

          <Field label="Visual treatment" hint={type.label}>
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

          {type.productControls && (
            <Field label="Product images" hint="Kept, not generated from">
              <UploadField multiple hint="Add one or more product shots" />
            </Field>
          )}
        </>
      }
      action={
        <GenerateButton
          label={
            editingAsset && !saveAsNew
              ? `Replace Slide ${editingAsset.meta?.slide || 1}`
              : `Generate ${slides} Slides`
          }
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
              <h2 className="text-sm font-semibold text-body">Slides</h2>
              <span className="text-xs text-muted">{images.length} generated</span>
            </div>
            <CreativeResults
              images={images}
              sources={data?.sources}
              labels={roles}
              columns={3}
              selected={images[active]}
              onSelect={(src) => setActive(images.indexOf(src))}
            />
            {campaign && (
              <p className="mt-3 text-xs leading-relaxed text-muted">
                Saved to {campaign.name}, each slide labelled with its role in the sequence.
              </p>
            )}
          </div>
        ) : (
          <PreviewStage
            hint={
              campaign
                ? `An example slide. The sequence below is built for a ${type.label} campaign — press Generate to make one image per slide.`
                : 'An example carousel slide. Describe the story on the left and press Generate to make one image per slide.'
            }
            art="carouselAd"
            ratio="portrait"
            toolName={TOOL}
            caption={`Slide ${active + 1} of ${slides}`}
          >
            <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
              {roles.map((role, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => setActive(i)}
                  aria-pressed={i === active}
                  className={`w-24 shrink-0 rounded-lg border p-2 text-left transition ${
                    i === active
                      ? 'border-accent bg-accent-soft'
                      : 'border-line bg-surface hover:border-accent-line'
                  }`}
                >
                  <span className="block text-[11px] font-bold text-body">Slide {i + 1}</span>
                  <span className="mt-0.5 block text-[10px] leading-snug text-muted">{role}</span>
                </button>
              ))}
            </div>
          </PreviewStage>
        )
      }
      output={
        <>
          <RailSection title="Slide plan" action={<span className="text-xs text-muted">{type.label}</span>}>
            <ol className="space-y-1.5">
              {roles.map((role, i) => (
                <li key={i} className="flex gap-2 text-xs">
                  <span className="font-semibold text-body">{i + 1}.</span>
                  <span className={i === active ? 'font-medium text-accent' : 'text-muted'}>
                    {role}
                  </span>
                </li>
              ))}
            </ol>
            <p className="mt-2 text-[11px] leading-relaxed text-muted">
              This sequence comes from the campaign type. A website carousel argues
              differently from a product one, so it is not the same list with different
              pictures.
            </p>
          </RailSection>

          <RailSection title="Actions">
            <div className="space-y-2">
              <a
                href={images?.[active] || undefined}
                target="_blank"
                rel="noreferrer"
                className={`btn btn-secondary btn-sm w-full ${images ? '' : 'pointer-events-none opacity-50'}`}
                title={images ? 'Open the selected slide' : 'Generate the carousel first'}
              >
                Open slide {active + 1}
              </a>
              <button
                type="button"
                onClick={generate}
                disabled={loading}
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
