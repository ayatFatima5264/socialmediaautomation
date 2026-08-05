import { useState } from 'react'
import AdsWorkspace, { Field, RailSection } from '../../../components/ads/workspace/AdsWorkspace.jsx'
import AdCreativeArt from '../../../components/ads/AdCreativeArt.jsx'
import GenerateButton from '../../../components/ads/workspace/GenerateButton.jsx'
import UploadField from '../../../components/ads/workspace/UploadField.jsx'
import ChipSelect from '../../../components/ChipSelect.jsx'
import CreativeResults from '../../../components/ads/workspace/CreativeResults.jsx'
import { useToast } from '../../../context/ToastContext.jsx'
import { api } from '../../../lib/api'

// ---------------------------------------------------------------------------
// Multiple Variations — the workspace.
//
// The rule that makes a variant set readable is one variable at a time. Change
// the headline AND the colour AND the layout and a winner tells you nothing
// about why it won. So the axis is a single-select, and the centre column
// labels every tile with what was changed in it.
// ---------------------------------------------------------------------------

const TOOL = 'Multiple Variations'
const PHASE = 3

const AXES = ['Headline', 'Colour', 'Layout', 'Imagery', 'Call to action']
const COUNTS = [2, 3, 4, 6, 8]

// What each tile in the grid is varying. Generated from the axis so the labels
// and the chosen variable can never drift apart.
const AXIS_LABELS = {
  Headline: ['Benefit-led', 'Curiosity-led', 'Proof-led', 'Urgency-led', 'Question', 'Objection', 'Direct', 'Playful'],
  Colour: ['Brand green', 'Warm sand', 'High contrast', 'Dark mode', 'Pastel', 'Mono', 'Accent pop', 'Muted'],
  Layout: ['Product left', 'Product right', 'Centred', 'Full bleed', 'Split', 'Stacked', 'Cropped', 'Framed'],
  Imagery: ['Studio', 'Lifestyle', 'Flat lay', 'In hand', 'On surface', 'Outdoors', 'Close crop', 'Group shot'],
  'Call to action': ['Shop Now', 'Learn More', 'Get Offer', 'Sign Up', 'Book Now', 'Try Free', 'See Range', 'Order Today'],
}

export default function Variations() {
  const [axis, setAxis] = useState('Headline')
  const [count, setCount] = useState(4)
  const [subject, setSubject] = useState('')
  const [images, setImages] = useState(null)
  const [sources, setSources] = useState([])
  const [loading, setLoading] = useState(false)

  const toast = useToast()
  const labels = AXIS_LABELS[axis] || []
  const used = labels.slice(0, count)

  // One request PER variant, not one request for `count` images.
  //
  // The endpoint's own `count` only varies the seed, which would give the same
  // brief rendered several ways — not what this tool promises. Folding the axis
  // label into each subject is what makes "varying colour" actually vary the
  // colour, and keeps the tile labels honest about what changed.
  async function generate() {
    if (subject.trim().length < 2) {
      toast.error('Describe the creative you want to vary first.')
      return
    }
    setLoading(true)
    setImages(null)
    try {
      const results = await Promise.all(
        used.map((label) =>
          api
            .adCreative({
              subject: `${subject.trim()}, ${axis.toLowerCase()}: ${label}`,
              aspect_ratio: '1:1',
              count: 1,
            })
            .then((r) => ({ url: r.images?.[0] || null, source: r.sources?.[0] }))
            .catch(() => ({ url: null, source: null })),
        ),
      )
      const ok = results.filter((r) => r.url)
      if (!ok.length) {
        toast.error('No variant could be generated. Try again.')
      } else {
        setImages(ok.map((r) => r.url))
        setSources(ok.map((r) => r.source))
        if (ok.length < used.length) {
          toast.info(`${ok.length} of ${used.length} variants generated.`)
        }
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <AdsWorkspace
      title={TOOL}
      description="Take a creative that works and generate a set around it — one variable changed at a time, so the results are readable."
      controls={
        <>
          <Field label="What the creative shows">
            <input
              className="input"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="Amber serum bottle on a marble slab"
            />
          </Field>

          <Field label="Reference creative" hint="Kept, not generated from">
            <UploadField hint="The ad you want to vary" />
          </Field>

          <Field label="Variable to change" hint="One at a time">
            <ChipSelect options={AXES} value={axis} onChange={setAxis} />
          </Field>

          <Field label="How many variants" hint={`${count} variants`}>
            <select
              className="select"
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
              aria-label="Number of variants"
            >
              {COUNTS.map((n) => (
                <option key={n} value={n}>
                  {n} variants
                </option>
              ))}
            </select>
          </Field>

          <p className="panel p-3 text-xs leading-relaxed text-muted">
            Only <span className="font-semibold text-body">{axis.toLowerCase()}</span> changes
            between these. Everything else is held constant, so a winner tells you which{' '}
            {axis.toLowerCase()} won — not which combination did.
          </p>
        </>
      }
      action={
        <GenerateButton
          label={`Generate ${count} Variants`}
          toolName={TOOL}
          phase={PHASE}
          onClick={generate}
          loading={loading}
        />
      }
      stage={
        <div className="card flex min-h-[320px] flex-col p-4 lg:min-h-full">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-semibold text-body">
              Variants — varying {axis.toLowerCase()}
            </h2>
            <span className="badge badge-accent">{images ? `${images.length} variants` : 'Not generated yet'}</span>
          </div>

          {images ? (
            <CreativeResults images={images} sources={sources} labels={used} columns={3} />
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3 xl:grid-cols-3">
                {used.map((label, i) => (
                  <div key={i} className="overflow-hidden rounded-xl border border-line">
                    <AdCreativeArt name="productAd" className="aspect-square w-full opacity-45" />
                    <div className="border-t border-line px-2.5 py-2">
                      <div className="text-[11px] font-semibold text-body">
                        Variant {String.fromCharCode(65 + i)}
                      </div>
                      <div className="truncate text-[11px] text-muted">{label}</div>
                    </div>
                  </div>
                ))}
              </div>

              <p className="mt-4 text-xs leading-relaxed text-muted">
                This is the set&apos;s shape and labelling. Describe the creative and press
                Generate for your own.
              </p>
            </>
          )}
        </div>
      }
      output={
        <>
          <RailSection title="Next step">
            <p className="text-xs leading-relaxed text-muted">
              A finished set goes straight into A/B Testing, which splits delivery evenly and
              reports which variant won.
            </p>
          </RailSection>

          <RailSection title="Actions">
            <div className="space-y-2">
              {['Download set', 'Send to A/B Testing'].map((action) => (
                <button
                  key={action}
                  type="button"
                  disabled
                  className="btn btn-secondary btn-sm w-full"
                  title="Available once variants have been generated"
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
