import { useState } from 'react'
import AdsWorkspace, { Field, RailSection } from '../../../components/ads/workspace/AdsWorkspace.jsx'
import GenerateButton from '../../../components/ads/workspace/GenerateButton.jsx'
import PreviewStage from '../../../components/ads/workspace/PreviewStage.jsx'
import ChipSelect from '../../../components/ChipSelect.jsx'
import useAdGeneration from '../../../hooks/useAdGeneration'
import { useToast } from '../../../context/ToastContext.jsx'
import { api } from '../../../lib/api'
import { VIDEO_DURATIONS, VIDEO_STYLES } from '../../../lib/ads/constants'
import { AD_PLATFORM_KEYS } from '../../../lib/ads/constants'
import { PLATFORMS } from '../../../lib/constants'

// ---------------------------------------------------------------------------
// Text to Video — the workspace.
//
// The prompt is the whole input here, so it gets the room: a large field with a
// character count, and the shot decisions underneath it rather than above.
// ---------------------------------------------------------------------------

const TOOL = 'Text to Video'
const PHASE = 3
const PROMPT_LIMIT = 900

export default function TextToVideo() {
  const [prompt, setPrompt] = useState('')
  const [duration, setDuration] = useState(15)
  const [style, setStyle] = useState('Modern & Clean')
  const [platform, setPlatform] = useState('instagram')

  const toast = useToast()
  // What CAN be generated today: the shot plan. No video model is configured,
  // so the endpoint returns scenes, timings and copy — never a file. Its
  // `renderable` flag is false, and the rail says so rather than offering a
  // download that cannot exist.
  const { data: plan, loading, run } = useAdGeneration(api.adVideoPlan)

  function generatePlan() {
    if (prompt.trim().length < 4) {
      toast.error('Describe the ad you want first.')
      return
    }
    run({ concept: prompt.trim(), duration, platform, style })
  }

  return (
    <AdsWorkspace
      title={TOOL}
      description="Describe the ad you want and get a scripted, storyboarded video concept back."
      controls={
        <>
          <Field
            label="Describe your idea"
            hint={`${prompt.length} / ${PROMPT_LIMIT}`}
          >
            <textarea
              rows={7}
              className="input resize-none"
              maxLength={PROMPT_LIMIT}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="A skincare serum on a marble surface, soft natural light, slow camera push in, calm music."
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

          <Field label="Platform">
            <select
              className="select"
              value={platform}
              onChange={(e) => setPlatform(e.target.value)}
              aria-label="Platform"
            >
              {AD_PLATFORM_KEYS.map((key) => (
                <option key={key} value={key}>
                  {PLATFORMS[key]?.label || key}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Video style">
            <ChipSelect options={VIDEO_STYLES} value={style} onChange={setStyle} />
          </Field>
        </>
      }
      action={
        <GenerateButton
          label="Generate Shot Plan"
          toolName={TOOL}
          phase={PHASE}
          onClick={generatePlan}
          loading={loading}
        />
      }
      stage={
        // Before a plan exists the panel shows what a finished video looks
        // like; once one exists, the plan replaces it. The plan is the real
        // output — showing sample artwork beside it would only muddle which
        // of the two came from the user's brief.
        plan ? (
          <div className="card flex min-h-[320px] flex-col p-4 lg:min-h-full">
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-sm font-semibold text-body">Shot plan</h2>
              <span className="badge badge-accent">{plan.total_seconds}s · {plan.scenes.length} scenes</span>
            </div>

            {plan.hook && (
              <p className="mb-3 text-sm font-semibold text-body">“{plan.hook}”</p>
            )}

            <ol className="space-y-2">
              {plan.scenes.map((s, i) => (
                <li key={i} className="panel flex gap-3 p-3">
                  <span className="shrink-0 text-xs font-bold text-accent">
                    {s.start}s
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-body">{s.shot}</p>
                    {s.on_screen && (
                      <p className="mt-1 text-xs font-semibold text-body">
                        On screen: {s.on_screen}
                      </p>
                    )}
                    {s.voiceover && (
                      <p className="mt-0.5 text-xs italic text-muted">{s.voiceover}</p>
                    )}
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
            hint={'An example of the kind of ad this plans. Describe your idea on the left and press Generate for a shot-by-shot plan.'}
            art="textVideo"
            ratio="story"
            toolName={TOOL}
            caption={`${duration}s · ${style}`}
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
            </p>
          </RailSection>

          <RailSection title="Actions">
            <button
              type="button"
              disabled={!plan}
              onClick={() => {
                const text = [
                  plan.hook && `HOOK: ${plan.hook}`,
                  ...plan.scenes.map(
                    (s) =>
                      `${s.start}s (${s.seconds}s) — ${s.shot}` +
                      (s.on_screen ? `\n  On screen: ${s.on_screen}` : '') +
                      (s.voiceover ? `\n  VO: ${s.voiceover}` : ''),
                  ),
                  plan.cta && `CTA: ${plan.cta}`,
                ]
                  .filter(Boolean)
                  .join('\n')
                navigator.clipboard
                  ?.writeText(text)
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
