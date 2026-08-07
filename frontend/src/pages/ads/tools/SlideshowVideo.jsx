import { useEffect, useRef, useState } from 'react'
import AdsWorkspace, { Field, RailSection } from '../../../components/ads/workspace/AdsWorkspace.jsx'
import AssetEditBar from '../../../components/ads/AssetEditBar.jsx'
import GenerateButton from '../../../components/ads/workspace/GenerateButton.jsx'
import PreviewStage from '../../../components/ads/workspace/PreviewStage.jsx'
import UploadField from '../../../components/ads/workspace/UploadField.jsx'
import ChipSelect from '../../../components/ChipSelect.jsx'
import useCampaignContext from '../../../hooks/useCampaignContext'
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
  const { campaign, editingAsset, saveAssets } = useCampaignContext()

  const [files, setFiles] = useState([])
  const [perSlide, setPerSlide] = useState(2.5)
  const [transition, setTransition] = useState('Crossfade')
  const [captions, setCaptions] = useState({})
  const [ratio, setRatio] = useState('9:16')
  const [saveAsNew, setSaveAsNew] = useState(false)
  // Source URLs a restored recipe came with — see the long note in
  // ImageToVideo on when a browser render can be reproduced and when it cannot.
  const [replaySources, setReplaySources] = useState([])

  const prefilled = useRef(false)
  useEffect(() => {
    if (!editingAsset || prefilled.current) return
    prefilled.current = true
    const m = editingAsset.meta || {}
    if (m.perSlide) setPerSlide(m.perSlide)
    if (m.transition) setTransition(m.transition)
    if (m.ratio) setRatio(m.ratio)
    if (m.captions) setCaptions(m.captions)
    if (m.sourceUrls?.length) setReplaySources(m.sourceUrls)
  }, [editingAsset])

  const toast = useToast()
  const { render, save, rendering, progress, result, supported } = useVideoRender()

  // A picked file's durable URL when it has one, the file itself otherwise —
  // renderVideo takes either. With nothing picked, a restored recipe's URLs
  // stand in, which is what makes re-rendering possible at all.
  const sources = files.length
    ? files.map((f) => f.sourceUrl || f)
    : replaySources

  // Only URLs can be written back into the recipe. A set that is partly
  // uploads is not reproducible, so none of it is claimed to be.
  const durableUrls = files.length
    ? files.every((f) => f.sourceUrl)
      ? files.map((f) => f.sourceUrl)
      : null
    : replaySources.length
      ? replaySources
      : null

  const slideCount = sources.length
  const total = slideCount ? (slideCount * perSlide).toFixed(1) : null

  async function generate() {
    if (!slideCount) {
      toast.error('Add at least one image first.')
      return
    }
    const rendered = await render({
      slides: sources.map((source, i) => ({
        source,
        seconds: perSlide,
        caption: (captions[i] || '').trim(),
      })),
      aspect: ratio,
      transition,
    })

    // MediaRecorder's blob URL dies with this page and the app has no file
    // store, so the campaign keeps the recipe and says so — see the note in
    // ImageToVideo.
    if (rendered) {
      await saveAssets(
        {
          kind: 'video',
          title: editingAsset && !saveAsNew
            ? editingAsset.title
            : `Slideshow — ${slideCount} images, ${total}s`,
          body: `${total}s ${ratio} slideshow · ${slideCount} images · ${perSlide}s each · ${transition}. ${
            durableUrls
              ? 'Rendered in the browser — reopen this asset to render it again.'
              : 'Rendered in the browser from uploaded files — download it here to keep it.'
          }`,
          tool: TOOL,
          meta: {
            slides: slideCount,
            perSlide,
            transition,
            ratio,
            captions,
            seconds: Number(total),
            local: true,
            ...(durableUrls ? { sourceUrls: durableUrls } : {}),
          },
        },
        { saveAsNew },
      )
    }
  }

  return (
    <AdsWorkspace
      title={TOOL}
      campaign={campaign}
      description="Turn several images into one paced, captioned video — ordering, transitions and timing handled for you."
      controls={
        <>
          <AssetEditBar
            asset={editingAsset}
            campaign={campaign}
            saveAsNew={saveAsNew}
            onSaveAsNewChange={setSaveAsNew}
          />

          <Field label="Images" hint={slideCount ? `${slideCount} selected` : 'None yet'}>
            <UploadField multiple hint="Add the shots in any order" onChange={setFiles} />
            {replaySources.length > 0 && !files.length && (
              <p className="mt-1.5 rounded-lg border border-accent-line bg-accent-soft p-2 text-[11px] leading-relaxed text-muted">
                This recipe kept its {replaySources.length} source images, so it can be
                rendered again as it is. Adding images here replaces the set.
              </p>
            )}
            {editingAsset && !replaySources.length && !files.length && (
              <p className="mt-1.5 rounded-lg border border-amber-500/40 bg-amber-500/10 p-2 text-[11px] leading-relaxed text-amber-700">
                The settings came back, but this render used uploaded files — those bytes
                only existed in the page that made it. Add the images again to re-render.
              </p>
            )}
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
              {/* Driven by `sources`, not `files` — a restored recipe has
                  slides but no File objects, and captioning has to work for it
                  too. */}
              <div className="space-y-2">
                {sources.map((_, i) => (
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
                {sources.map((source, i) => (
                  <div key={i} className="flex items-baseline justify-between gap-2">
                    {/* A File knows its name; a restored recipe is a bare URL,
                        so the slide number is the only honest label. */}
                    <span className="min-w-0 truncate text-muted">
                      {source?.name || `Slide ${i + 1}`}
                    </span>
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
