import { useState } from 'react'
import AdsWorkspace, { Field, RailSection } from '../../../components/ads/workspace/AdsWorkspace.jsx'
import GenerateButton from '../../../components/ads/workspace/GenerateButton.jsx'
import PreviewStage from '../../../components/ads/workspace/PreviewStage.jsx'
import UploadField from '../../../components/ads/workspace/UploadField.jsx'
import ChipSelect from '../../../components/ChipSelect.jsx'
import { ASPECT_RATIOS } from '../../../lib/constants'

// ---------------------------------------------------------------------------
// Slideshow Video — the workspace.
//
// The fastest route from a folder of images to something that runs. The only
// decisions that matter are pace, transition and whether it is captioned, so
// those are the only controls — and the total length is computed from them
// rather than asked for, because it is a consequence, not a choice.
// ---------------------------------------------------------------------------

const TOOL = 'Slideshow Video'
const PHASE = 3

const TRANSITIONS = ['Cut', 'Crossfade', 'Slide', 'Zoom blur']
const MUSIC = ['Upbeat', 'Calm', 'Cinematic', 'None']
const PER_SLIDE = [1.5, 2, 2.5, 3, 4]

export default function SlideshowVideo() {
  const [images, setImages] = useState([])
  const [perSlide, setPerSlide] = useState(2.5)
  const [transition, setTransition] = useState('Crossfade')
  const [music, setMusic] = useState('Upbeat')
  const [captions, setCaptions] = useState(true)
  const [ratio, setRatio] = useState('9:16')

  const slideCount = images.length
  const total = slideCount ? (slideCount * perSlide).toFixed(1) : null

  return (
    <AdsWorkspace
      title={TOOL}
      description="Turn several images into one paced, captioned video — order, transitions and music handled for you."
      controls={
        <>
          <Field label="Images" hint={slideCount ? `${slideCount} selected` : 'None yet'}>
            <UploadField multiple hint="Add the shots in any order" onChange={setImages} />
          </Field>

          <Field label="Seconds per image" hint={`${perSlide}s`}>
            <select
              className="select"
              value={perSlide}
              onChange={(e) => setPerSlide(Number(e.target.value))}
              aria-label="Seconds per image"
            >
              {PER_SLIDE.map((s) => (
                <option key={s} value={s}>
                  {s} seconds
                </option>
              ))}
            </select>
          </Field>

          <Field label="Transition">
            <ChipSelect options={TRANSITIONS} value={transition} onChange={setTransition} />
          </Field>

          <Field label="Music">
            <ChipSelect options={MUSIC} value={music} onChange={setMusic} />
          </Field>

          <Field label="Captions">
            <label className="panel flex cursor-pointer items-center justify-between gap-3 p-3">
              <span className="text-sm text-body">Generate a caption per slide</span>
              <input
                type="checkbox"
                checked={captions}
                onChange={(e) => setCaptions(e.target.checked)}
                className="h-4 w-4 accent-[var(--accent)]"
              />
            </label>
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
      action={<GenerateButton label="Generate Slideshow" toolName={TOOL} phase={PHASE} />}
      stage={
        <PreviewStage
          art="imageVideo"
          ratio={ratio === '9:16' ? 'story' : ratio === '16:9' ? 'landscape' : 'square'}
          toolName={TOOL}
          phase={PHASE}
          caption={total ? `${slideCount} slides · ${total}s` : 'Add images to begin'}
        />
      }
      output={
        <>
          <RailSection title="Timeline">
            {/* Real arithmetic on a real selection — the one thing here that
                does not need a model, so it is not deferred to one. */}
            {slideCount ? (
              <div className="space-y-1.5 text-xs">
                {images.map((file, i) => (
                  <div key={i} className="flex items-baseline justify-between gap-2">
                    <span className="min-w-0 truncate text-muted">{file.name}</span>
                    <span className="shrink-0 font-semibold text-body">
                      {(i * perSlide).toFixed(1)}s
                    </span>
                  </div>
                ))}
                <div className="mt-2 border-t border-line pt-2 text-right font-semibold text-body">
                  {total}s total
                </div>
              </div>
            ) : (
              <p className="panel px-3 py-6 text-center text-xs text-muted">
                Add images and the running order appears here with its timings.
              </p>
            )}
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
