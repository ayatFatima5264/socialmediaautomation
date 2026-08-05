import { useState } from 'react'
import AdsWorkspace, { Field, RailSection } from '../../../components/ads/workspace/AdsWorkspace.jsx'
import GenerateButton from '../../../components/ads/workspace/GenerateButton.jsx'
import PreviewStage from '../../../components/ads/workspace/PreviewStage.jsx'
import UploadField from '../../../components/ads/workspace/UploadField.jsx'
import ChipSelect from '../../../components/ChipSelect.jsx'
import useAdGeneration from '../../../hooks/useAdGeneration'
import { useToast } from '../../../context/ToastContext.jsx'
import { api } from '../../../lib/api'
import { VIDEO_DURATIONS } from '../../../lib/ads/constants'

// ---------------------------------------------------------------------------
// Product Showcase Video — the workspace.
//
// Several stills of one product become a controlled shot: a camera move, a
// lighting set-up, and callouts timed to the reveal. The callout list is the
// part that separates this from Image to Video — it is a product film, so it
// has to say something about the product while it turns.
// ---------------------------------------------------------------------------

const TOOL = 'Product Showcase Video'
const PHASE = 3

const CAMERA_MOVES = ['Turntable', 'Slow dolly in', 'Orbit', 'Rise', 'Push and hold']
const LIGHTING = ['Soft studio', 'Hard key', 'Natural window', 'Dark luxury', 'Backlit glow']

export default function ProductShowcaseVideo() {
  const [duration, setDuration] = useState(15)
  const [move, setMove] = useState('Turntable')
  const [lighting, setLighting] = useState('Soft studio')
  const [callouts, setCallouts] = useState(['Naturally made', 'Clinically tested'])

  const toast = useToast()
  // Rendering a turntable needs a generative video model, which is not
  // configured. The shot plan is the part a language model genuinely produces,
  // so that is what this generates — and it says so rather than implying a file.
  const { data: plan, loading, run } = useAdGeneration(api.adVideoPlan)

  function generatePlan() {
    const concept = [
      'Product showcase film.',
      `Camera: ${move}. Lighting: ${lighting}.`,
      callouts.filter(Boolean).length
        ? `Feature callouts: ${callouts.filter(Boolean).join('; ')}.`
        : '',
    ]
      .filter(Boolean)
      .join(' ')
    run({ concept, duration, platform: 'instagram', style: lighting, motion: move })
  }

  function updateCallout(i, value) {
    setCallouts(callouts.map((c, j) => (j === i ? value : c)))
  }

  return (
    <AdsWorkspace
      title={TOOL}
      description="Turn product photos into a showcase film — camera moves, studio lighting and feature callouts timed to the reveal."
      controls={
        <>
          <Field label="Product images" hint="2–6 angles">
            <UploadField multiple hint="Front, side and detail shots work best" />
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

          <Field label="Camera move">
            <ChipSelect options={CAMERA_MOVES} value={move} onChange={setMove} />
          </Field>

          <Field label="Lighting">
            <ChipSelect options={LIGHTING} value={lighting} onChange={setLighting} />
          </Field>

          <Field label="Feature callouts" hint={`${callouts.length} / 4`}>
            <div className="space-y-2">
              {callouts.map((c, i) => (
                <div key={i} className="flex gap-2">
                  <input
                    className="input"
                    value={c}
                    onChange={(e) => updateCallout(i, e.target.value)}
                    placeholder={`Callout ${i + 1}`}
                  />
                  <button
                    type="button"
                    onClick={() => setCallouts(callouts.filter((_, j) => j !== i))}
                    className="btn btn-ghost btn-sm shrink-0"
                    aria-label={`Remove callout ${i + 1}`}
                  >
                    ✕
                  </button>
                </div>
              ))}

              {callouts.length < 4 && (
                <button
                  type="button"
                  onClick={() => setCallouts([...callouts, ''])}
                  className="btn btn-secondary btn-sm w-full"
                >
                  + Add callout
                </button>
              )}
            </div>
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
        plan ? (
          <div className="card flex min-h-[320px] flex-col p-4 lg:min-h-full">
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-sm font-semibold text-body">Shot plan</h2>
              <span className="badge badge-accent">
                {plan.total_seconds}s · {plan.scenes.length} scenes
              </span>
            </div>

            {plan.hook && <p className="mb-3 text-sm font-semibold text-body">“{plan.hook}”</p>}

            <ol className="space-y-2">
              {plan.scenes.map((sc, i) => (
                <li key={i} className="panel flex gap-3 p-3">
                  <span className="shrink-0 text-xs font-bold text-accent">{sc.start}s</span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-body">{sc.shot}</p>
                    {sc.on_screen && (
                      <p className="mt-1 text-xs font-semibold text-body">
                        On screen: {sc.on_screen}
                      </p>
                    )}
                    {sc.voiceover && (
                      <p className="mt-0.5 text-xs italic text-muted">{sc.voiceover}</p>
                    )}
                  </div>
                  <span className="shrink-0 text-[11px] text-muted">{sc.seconds}s</span>
                </li>
              ))}
            </ol>

            {!plan.renderable && (
              <p className="mt-4 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs leading-relaxed text-amber-700">
                {plan.note}
              </p>
            )}
          </div>
        ) : (
          <PreviewStage
            hint={'An example of the kind of film this plans. Set the camera and lighting, then press Generate for a shot-by-shot plan.'}
            art="showcase"
            ratio="square"
            toolName={TOOL}
            caption={`${duration}s · ${move}`}
          />
        )
      }
      output={
        <>
          <RailSection title="Shot list">
            <ol className="space-y-1.5 text-xs">
              <li className="text-muted">
                <span className="font-semibold text-body">0s</span> — establishing, product
                centred
              </li>
              {callouts.filter(Boolean).map((c, i) => (
                <li key={i} className="text-muted">
                  <span className="font-semibold text-body">
                    {Math.round(((i + 1) * duration) / (callouts.length + 1))}s
                  </span>{' '}
                  — {c}
                </li>
              ))}
              <li className="text-muted">
                <span className="font-semibold text-body">{duration}s</span> — hold on the
                pack shot
              </li>
            </ol>
          </RailSection>

          <RailSection title="What runs today">
            <p className="text-xs leading-relaxed text-muted">
              The shot plan is generated for real. Rendering a turntable needs a
              generative video provider, which is not configured — so there is no file to
              download yet. For motion you can make now, try Image to Video.
            </p>
          </RailSection>
        </>
      }
    />
  )
}
