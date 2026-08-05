import { useState } from 'react'
import AdsWorkspace, { Field, RailSection } from '../../../components/ads/workspace/AdsWorkspace.jsx'
import GenerateButton from '../../../components/ads/workspace/GenerateButton.jsx'
import PreviewStage from '../../../components/ads/workspace/PreviewStage.jsx'
import UploadField from '../../../components/ads/workspace/UploadField.jsx'
import CreativeResults from '../../../components/ads/workspace/CreativeResults.jsx'
import useAdGeneration from '../../../hooks/useAdGeneration'
import { useToast } from '../../../context/ToastContext.jsx'
import { api } from '../../../lib/api'
import { CAROUSEL_SLIDE_COUNTS } from '../../../lib/ads/constants'

// ---------------------------------------------------------------------------
// Carousel Ads — the workspace.
//
// A carousel is a sequence, not a pile of images, so the centre column is a
// slide strip with one selected rather than a single preview. Selecting a slide
// is live — the roles below are what the generator will fill, and being able to
// step through them is how you check the story holds before generating it.
// ---------------------------------------------------------------------------

const TOOL = 'Carousel Ads'
const PHASE = 2

// What each position in the sequence is FOR. The first card earns the stop, the
// last one asks for the click, and everything between carries the argument.
function slideRoles(count) {
  const roles = ['Cover — the hook', 'Benefit', 'Ingredients', 'Proof', 'Comparison', 'How it works', 'Offer', 'Testimonial']
  return Array.from({ length: count }, (_, i) =>
    i === count - 1 ? 'CTA — ask for the click' : roles[i] || `Slide ${i + 1}`,
  )
}

export default function CarouselAds() {
  const [slides, setSlides] = useState(4)
  const [active, setActive] = useState(0)
  const [subject, setSubject] = useState('')

  const toast = useToast()
  const { data, loading, run } = useAdGeneration(api.adCreative)
  const images = data?.images || null

  const roles = slideRoles(slides)

  function generate() {
    if (subject.trim().length < 2) {
      toast.error('Describe the product or story first.')
      return
    }
    setActive(0)
    // One image per slide. The endpoint varies the seed per image, so the set
    // is a sequence of related frames rather than the same picture repeated.
    run({ subject: subject.trim(), aspect_ratio: '4:5', count: slides })
  }

  function changeCount(next) {
    setSlides(next)
    setActive((a) => Math.min(a, next - 1))
  }

  return (
    <AdsWorkspace
      title={TOOL}
      description="Build a multi-card ad that tells one story across the swipe — a hook, the argument, and a close."
      controls={
        <>
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
          </Field>

          <Field label="Product images" hint="Optional">
            <UploadField multiple hint="Add one or more product shots" />
          </Field>

          <Field label="What the carousel shows">
            <textarea
              rows={4}
              className="input resize-none"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="An organic skincare serum: the bottle, its texture, and it in use"
            />
          </Field>
        </>
      }
      action={
        <GenerateButton
          label={`Generate ${slides} Slides`}
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
            <CreativeResults images={images} sources={data?.sources}
              labels={roles}
              columns={3}
              selected={images[active]}
              onSelect={(src) => setActive(images.indexOf(src))}
            />
          </div>
        ) : (
          <PreviewStage
            hint={'An example carousel slide. Describe the story on the left and press Generate to make one image per slide.'}
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
          <RailSection title="Slide plan">
            <ol className="space-y-1.5">
              {roles.map((role, i) => (
                <li key={i} className="flex gap-2 text-xs">
                  <span className="font-semibold text-body">{i + 1}.</span>
                  <span className="text-muted">{role}</span>
                </li>
              ))}
            </ol>
          </RailSection>

          <RailSection title="Actions">
            <div className="space-y-2">
              {['Regenerate slide', 'Download all', 'Publish'].map((action) => (
                <button
                  key={action}
                  type="button"
                  disabled
                  className="btn btn-secondary btn-sm w-full"
                  title="Available once the carousel has been generated"
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
