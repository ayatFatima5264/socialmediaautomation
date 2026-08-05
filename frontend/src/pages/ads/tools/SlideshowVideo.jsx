import { useState } from 'react'
import AdsWorkspace, { Field, RailSection } from '../../../components/ads/workspace/AdsWorkspace.jsx'
import GenerateButton from '../../../components/ads/workspace/GenerateButton.jsx'
import PreviewStage from '../../../components/ads/workspace/PreviewStage.jsx'
import UploadField from '../../../components/ads/workspace/UploadField.jsx'
import ChipSelect from '../../../components/ChipSelect.jsx'
import useVideoRender from '../../../hooks/useVideoRender'
import { useToast } from '../../../context/ToastContext.jsx'
import { ASPECT_RATIOS } from '../../../lib/constants'

// ---------------------------------------------------------------------------
// Slideshow Video — rendered in the browser (see lib/ads/videoRender.js).
//
// Ordering, pacing and captioning a set of images is compositing, so this
// produces a real file for free with nothing leaving the machine.
//
// Captions are per slide and editable here rather than generated: the images
// are the user's, and only they know what each one is meant to say. A model
// could guess, but a wrong caption burned into a video is worse than none.
// ---------------------------------------------------------------------------

const TOOL = 'Slideshow Video'
const PHASE = 3

const TRANSITIONS = ['Cut', 'Crossfade']
const PER_SLIDE = [1.5, 2, 2.5, 3, 4]

export default function SlideshowVideo() {
  const [files, setFiles] = useState([])
  const [perSlide, setPerSlide] = useState(2.5)
  const [transition, setTransition] = useState('Crossfade')
  const [captions, setCaptions] = useState({})
  const [ratio, setRatio] = useState('9:16')

  const toast = useToast()
  const { render, save, rendering, progress, result, supported } = useVideoRender()

  const slideCount = files.length
  const total = slideCount ? (slideCount * perSlide).toFixed(1) : null

  function generate() {
    if (!slideCount) {
      toast.error('Add at least one image first.')
      return
    }
    render({
      slides: files.map((f, i) => ({
        source: f,
        seconds: perSlide,
        caption: (captions[i] || '').trim(),
      })),
      aspect: ratio,
      transition,
    })
  }

  return (
    <AdsWorkspace
      title={TOOL}
      description="Turn several images into one paced, captioned video — ordering, transitions and timing handled for you."
      controls={
        <>
          <Field label="Images" hint={slideCount ? `${slideCount} selected` : 'None yet'}>
            <UploadField multiple hint="Add the shots in any order" onChange={setFiles} />
          </Field>

          <Field label="Seconds per image" hint={total ? `${total}s total` : `${perSlide}s`}>
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

          {slideCount > 0 && (
            <Field label="Captions" hint="Optional, per slide">
              <div className="space-y-2">
                {files.map((f, i) => (
                  <input
                    key={i}
                    className="input"
                    value={captions[i] || ''}
                    onChange={(e) => setCaptions({ ...captions, [i]: e.target.value })}
                    placeholder={`Slide ${i + 1}`}
                  />
                ))}
              </div>
            </Field>
          )}
        </>
      }
      action={
        <>
          <GenerateButton
            label={total ? `Render ${total}s Video` : 'Render Video'}
            toolName={TOOL}
            phase={PHASE}
            onClick={generate}
            loading={rendering}
            disabled={!supported}
          />
          {rendering && (
            <div className="mt-2">
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-inset">
                <div
                  className="h-full rounded-full bg-accent transition-[width] duration-150"
                  style={{ width: `${Math.round(progress * 100)}%` }}
                />
              </div>
              <p className="mt-1.5 text-center text-[11px] text-muted">
                Recording in real time — {Math.round(progress * 100)}%
              </p>
            </div>
          )}
        </>
      }
      stage={
        result ? (
          <div className="card flex min-h-[320px] flex-col p-4 lg:min-h-full">
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-sm font-semibold text-body">Your video</h2>
              <span className="text-xs text-muted">
                {slideCount} slides · {total}s · .{result.extension}
              </span>
            </div>

            <div className="flex flex-1 items-center justify-center">
              <video
                key={result.url}
                src={result.url}
                controls
                loop
                playsInline
                className="max-h-[420px] rounded-xl border border-line"
              />
            </div>
          </div>
        ) : (
          <PreviewStage
            hint={'An example of the result. Add your images, set the pace, and press Render — your browser makes the video.'}
            art="imageVideo"
            ratio={ratio === '9:16' ? 'story' : ratio === '16:9' ? 'landscape' : 'square'}
            toolName={TOOL}
            caption={total ? `${slideCount} slides · ${total}s` : 'Add images to begin'}
          />
        )
      }
      output={
        <>
          <RailSection title="Timeline">
            {slideCount ? (
              <div className="space-y-1.5 text-xs">
                {files.map((file, i) => (
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

          <RailSection title="How this renders">
            <p className="text-xs leading-relaxed text-muted">
              Rendered by your browser — free, offline, nothing uploaded. Recording takes as
              long as the video is, and there is no audio track.
            </p>
          </RailSection>

          <RailSection title="Actions">
            <div className="space-y-2">
              <button
                type="button"
                onClick={() => save('slideshow')}
                disabled={!result}
                className="btn btn-primary btn-sm w-full"
              >
                Download {result ? `.${result.extension}` : 'video'}
              </button>
              <button
                type="button"
                onClick={generate}
                disabled={rendering || !slideCount}
                className="btn btn-secondary btn-sm w-full"
              >
                Re-render
              </button>
            </div>
          </RailSection>
        </>
      }
    />
  )
}
