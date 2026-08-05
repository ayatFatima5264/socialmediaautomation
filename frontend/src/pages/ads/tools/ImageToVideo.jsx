import { useState } from 'react'
import AdsWorkspace, { Field, RailSection } from '../../../components/ads/workspace/AdsWorkspace.jsx'
import GenerateButton from '../../../components/ads/workspace/GenerateButton.jsx'
import PreviewStage from '../../../components/ads/workspace/PreviewStage.jsx'
import UploadField from '../../../components/ads/workspace/UploadField.jsx'
import ChipSelect from '../../../components/ChipSelect.jsx'
import {
  ANIMATION_STYLES,
  CAMERA_MOTIONS,
  VIDEO_DURATIONS,
} from '../../../lib/ads/constants'
import { ASPECT_RATIOS } from '../../../lib/constants'

// ---------------------------------------------------------------------------
// Image to Video — the workspace.
//
// One still in, one short motion ad out. The controls are the shot decisions —
// how long, how the camera moves, how hard the cut lands — because those are
// what separate an animated image from something that holds a scroll.
// ---------------------------------------------------------------------------

const TOOL = 'Image to Video'
const PHASE = 2

export default function ImageToVideo() {
  const [duration, setDuration] = useState(10)
  const [motion, setMotion] = useState('Slow zoom in')
  const [style, setStyle] = useState('Smooth')
  const [ratio, setRatio] = useState('9:16')

  return (
    <AdsWorkspace
      title={TOOL}
      description="Animate a still creative into a short video ad — camera movement, text reveals and a soundtrack."
      controls={
        <>
          <Field label="Source image">
            <UploadField hint="The still you want to animate" />
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

          <Field label="Camera motion">
            <ChipSelect options={CAMERA_MOTIONS} value={motion} onChange={setMotion} />
          </Field>

          <Field label="Animation style">
            <ChipSelect options={ANIMATION_STYLES} value={style} onChange={setStyle} />
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
        </>
      }
      action={<GenerateButton label="Generate Video" toolName={TOOL} phase={PHASE} />}
      stage={
        <PreviewStage
          art="imageVideo"
          ratio={ratio === '9:16' ? 'story' : ratio === '16:9' ? 'landscape' : 'square'}
          toolName={TOOL}
          phase={PHASE}
          caption={`${duration}s · ${motion}`}
        />
      }
      output={
        <>
          <RailSection title="Renders">
            <p className="panel px-3 py-6 text-center text-xs text-muted">
              Each render appears here with its settings, so you can compare two camera
              moves rather than replacing one with the other.
            </p>
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
