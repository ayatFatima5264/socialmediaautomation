import { useEffect, useRef, useState } from 'react'
import AdsWorkspace, { Field, RailSection } from '../../../components/ads/workspace/AdsWorkspace.jsx'
import AssetEditBar from '../../../components/ads/AssetEditBar.jsx'
import GenerateButton from '../../../components/ads/workspace/GenerateButton.jsx'
import PreviewStage from '../../../components/ads/workspace/PreviewStage.jsx'
import ChipSelect from '../../../components/ChipSelect.jsx'
import useAdGeneration from '../../../hooks/useAdGeneration'
import useCampaignContext from '../../../hooks/useCampaignContext'
import { useToast } from '../../../context/ToastContext.jsx'
import { api } from '../../../lib/api'
import { VIDEO_DURATIONS, VIDEO_STYLES } from '../../../lib/ads/constants'
import {
  campaignSubject,
  campaignType,
  videoConceptPrompt,
  videoConcepts,
} from '../../../lib/ads/campaignTypes'
import { planToText } from '../../../lib/ads/videoPlan'
import { PLATFORMS } from '../../../lib/constants'

// ---------------------------------------------------------------------------
// Text to Video — the workspace.
//
// ---- Concepts instead of a blank prompt ----------------------------------
// The prompt used to be an empty box, which is the hardest possible starting
// point and the reason most people write one flat sentence and get a flat
// script back. It is now a list of concepts drawn from the campaign type: a
// Website campaign is offered Website Promo, Animated Browser, Scrolling
// Website, Feature Highlight, Typing Animation, Blog Intro; a Product campaign
// is offered Product Rotation, Lifestyle Ad, Unboxing Style and the rest.
//
// Picking one is a complete brief, because the campaign supplies the subject
// and the concept supplies the treatment. The prompt box is still there,
// prefilled and editable — the concept is a starting point, not a cage.
//
// ---- What is real ---------------------------------------------------------
// No video model is configured, so this returns a SHOT PLAN: scenes, timings,
// on-screen copy, voiceover. The endpoint's `renderable` flag says so and the
// rail repeats it. The plan is saved to the campaign as a video record with no
// file attached, which is exactly what it is.
// ---------------------------------------------------------------------------

const TOOL = 'Text to Video'
const PHASE = 3
const PROMPT_LIMIT = 900

export default function TextToVideo() {
  const { campaign, editingAsset, saveAssets } = useCampaignContext()

  const type = campaignType(campaign?.campaignType)
  const concepts = videoConcepts(campaign?.campaignType)

  const [concept, setConcept] = useState(concepts[0].label)
  const [prompt, setPrompt] = useState('')
  const [duration, setDuration] = useState(15)
  const [style, setStyle] = useState('Modern & Clean')
  const [saveAsNew, setSaveAsNew] = useState(false)

  // Re-opening a saved plan brings back the concept, length and style it was
  // written with, so "make that again but 30 seconds" is one control away.
  const prefilled = useRef(false)
  useEffect(() => {
    if (!editingAsset || prefilled.current) return
    prefilled.current = true
    const m = editingAsset.meta || {}
    if (m.concept) setConcept(m.concept)
    if (m.duration) setDuration(m.duration)
    if (m.style) setStyle(m.style)
  }, [editingAsset])

  const activeConcept = concepts.some((c) => c.label === concept)
    ? concept
    : concepts[0].label

  // The campaign decides the platform. With several, the first is the one the
  // plan is paced for — the others differ in length, not in story.
  const platform = campaign?.platforms?.[0] || 'instagram'

  const toast = useToast()
  const { data: plan, loading, run } = useAdGeneration(api.adVideoPlan)

  async function generatePlan() {
    // Concept + campaign is a complete brief on its own; the prompt box only
    // adds to it. Outside a campaign the box is the whole brief, so it matters.
    const written = prompt.trim()
    const base = campaign ? campaignSubject(campaign) : written

    if (!campaign && written.length < 4) {
      toast.error('Describe the ad you want first.')
      return
    }

    const result = await run({
      concept: [
        base,
        videoConceptPrompt(campaign?.campaignType, activeConcept),
        campaign ? written : '',
      ]
        .filter(Boolean)
        .join(' ')
        .slice(0, PROMPT_LIMIT),
      duration,
      platform,
      style,
    })

    if (result?.scenes?.length) {
      await saveAssets({
        kind: 'video',
        title: editingAsset && !saveAsNew
          ? editingAsset.title
          : `${activeConcept} — ${duration}s shot plan`,
        // No url: this is a plan, not a file. Saving a placeholder link would
        // put a card in the library that plays nothing.
        body: planToText(result),
        tool: TOOL,
        meta: {
          concept: activeConcept,
          duration,
          platform,
          style,
          renderable: false,
          scenes: result.scenes.length,
        },
      }, { saveAsNew })
    }
  }

  return (
    <AdsWorkspace
      title={TOOL}
      campaign={campaign}
      description="Pick a concept and get a scripted, storyboarded video back — scene by scene, with timings and on-screen copy."
      controls={
        <>
          <AssetEditBar
            asset={editingAsset}
            campaign={campaign}
            saveAsNew={saveAsNew}
            onSaveAsNewChange={setSaveAsNew}
          />

          <Field label="Concept" hint={type.label}>
            <div className="space-y-1.5">
              {concepts.map((c) => (
                <button
                  key={c.label}
                  type="button"
                  onClick={() => setConcept(c.label)}
                  aria-pressed={activeConcept === c.label}
                  className={`block w-full rounded-lg border px-2.5 py-2 text-left text-xs font-medium transition ${
                    activeConcept === c.label
                      ? 'border-accent bg-accent-soft text-accent'
                      : 'border-line text-muted hover:border-accent'
                  }`}
                >
                  {c.label}
                </button>
              ))}
            </div>
          </Field>

          <Field
            label={campaign ? 'Anything to add' : 'Describe your idea'}
            hint={`${prompt.length} / ${PROMPT_LIMIT}`}
          >
            <textarea
              rows={campaign ? 4 : 7}
              className="input resize-none"
              maxLength={PROMPT_LIMIT}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder={
                campaign
                  ? 'Optional. The campaign brief and the concept above are already being used.'
                  : 'A skincare serum on a marble surface, soft natural light, slow camera push in.'
              }
            />
          </Field>

          <Field label="Duration" hint={`${duration}s`}>
            <select
              className="select"
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              aria-label="Duration"
            >
              {VIDEO_DURATIONS.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Video style">
            <ChipSelect options={VIDEO_STYLES} value={style} onChange={setStyle} />
          </Field>

          <Field label="Paced for" hint={campaign ? 'From the campaign' : 'Default'}>
            <p className="text-xs text-body">{PLATFORMS[platform]?.label || platform}</p>
          </Field>
        </>
      }
      action={
        <GenerateButton
          label={editingAsset && !saveAsNew ? 'Replace This Shot Plan' : 'Generate Shot Plan'}
          toolName={TOOL}
          phase={PHASE}
          onClick={generatePlan}
          loading={loading}
        />
      }
      stage={
        plan ? (
          <div className="card flex min-h-[320px] flex-col p-4 lg:min-h-full">
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-sm font-semibold text-body">{activeConcept} — shot plan</h2>
              <span className="badge badge-accent">
                {plan.total_seconds}s · {plan.scenes.length} scenes
              </span>
            </div>

            {plan.hook && <p className="mb-3 text-sm font-semibold text-body">“{plan.hook}”</p>}

            <ol className="space-y-2">
              {plan.scenes.map((s, i) => (
                <li key={i} className="panel flex gap-3 p-3">
                  <span className="shrink-0 text-xs font-bold text-accent">{s.start}s</span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-body">{s.shot}</p>
                    {s.on_screen && (
                      <p className="mt-1 text-xs font-semibold text-body">
                        On screen: {s.on_screen}
                      </p>
                    )}
                    {s.voiceover && <p className="mt-0.5 text-xs italic text-muted">{s.voiceover}</p>}
                  </div>
                  <span className="shrink-0 text-[11px] text-muted">{s.seconds}s</span>
                </li>
              ))}
            </ol>

            {plan.cta && (
              <p className="mt-3 text-sm text-body">
                <span className="font-semibold">CTA:</span> {plan.cta}
              </p>
            )}

            {/* The endpoint's own honesty flag, surfaced rather than hidden. */}
            {!plan.renderable && (
              <p className="mt-4 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs leading-relaxed text-amber-700">
                {plan.note}
              </p>
            )}
          </div>
        ) : (
          <PreviewStage
            hint={
              campaign
                ? `An example of the kind of ad this plans. ${campaign.name}'s brief is loaded — pick a concept and press Generate.`
                : 'An example of the kind of ad this plans. Describe your idea on the left and press Generate for a shot-by-shot plan.'
            }
            art="textVideo"
            ratio="story"
            toolName={TOOL}
            caption={`${duration}s · ${activeConcept}`}
          />
        )
      }
      output={
        <>
          <RailSection title="What runs today">
            <p className="text-xs leading-relaxed text-muted">
              The shot plan — scenes, timings, on-screen copy and voiceover — is generated
              for real. Rendering the file needs a video provider, which is not configured,
              so there is no download to offer yet.
              {campaign && ' The plan is saved to the campaign as a video record with no file attached.'}
            </p>
          </RailSection>

          <RailSection title="Actions">
            <button
              type="button"
              disabled={!plan}
              onClick={() => {
                navigator.clipboard
                  ?.writeText(planToText(plan))
                  .then(() => toast.success('Shot plan copied.'))
                  .catch(() => toast.error('Could not copy.'))
              }}
              className="btn btn-secondary btn-sm w-full"
              title={plan ? 'Copy the shot plan' : 'Generate a plan first'}
            >
              Copy shot plan
            </button>
          </RailSection>
        </>
      }
    />
  )
}
