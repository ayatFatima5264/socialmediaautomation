import { useState } from 'react'
import AdsWorkspace, { Field, RailSection } from '../../../components/ads/workspace/AdsWorkspace.jsx'
import GenerateButton from '../../../components/ads/workspace/GenerateButton.jsx'
import PreviewStage from '../../../components/ads/workspace/PreviewStage.jsx'
import UploadField from '../../../components/ads/workspace/UploadField.jsx'
import ChipSelect from '../../../components/ChipSelect.jsx'
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
      action={<GenerateButton label="Generate Showcase" toolName={TOOL} phase={PHASE} />}
      stage={
        <PreviewStage
          art="showcase"
          ratio="square"
          toolName={TOOL}
          phase={PHASE}
          caption={`${duration}s · ${move}`}
        />
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

          <RailSection title="Actions">
            <div className="space-y-2">
              {['Download MP4', 'Regenerate'].map((action) => (
                <button
                  key={action}
                  type="button"
                  disabled
                  className="btn btn-secondary btn-sm w-full"
                  title="Available once a video has been rendered"
                >
                  {action}
                </button>
              ))}
            </div>
          </RailSection>
        </>
      }
    />
  )
}
