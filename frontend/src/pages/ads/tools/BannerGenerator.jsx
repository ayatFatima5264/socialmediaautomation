import { useState } from 'react'
import AdsWorkspace, { Field, RailSection } from '../../../components/ads/workspace/AdsWorkspace.jsx'
import GenerateButton from '../../../components/ads/workspace/GenerateButton.jsx'
import PreviewStage from '../../../components/ads/workspace/PreviewStage.jsx'
import CreativeResults from '../../../components/ads/workspace/CreativeResults.jsx'
import useAdGeneration from '../../../hooks/useAdGeneration'
import { useToast } from '../../../context/ToastContext.jsx'
import { api } from '../../../lib/api'
import { BANNER_EXPORT_SETS, BANNER_SIZES, CTA_OPTIONS } from '../../../lib/ads/constants'

// ---------------------------------------------------------------------------
// Banner Generator — the workspace.
//
// One layout on the left, the chosen size in the centre, and every OTHER size
// it re-flows into on the right. That right column is the point of the tool:
// the value is not one banner, it is the set.
// ---------------------------------------------------------------------------

const TOOL = 'Banner Generator'
const PHASE = 2

// Drawn from the Brand Kit once it is wired; fixed here so the control reads
// as a real swatch row rather than an empty box.
const BRAND_COLORS = ['#1F8A5B', '#2F4A32', '#B4762E', '#F6F1E7', '#16281F']

// The banner ratio the image model is asked for. Display sizes are far wider
// than any generation ratio, so each maps to the nearest one the model handles
// — the layout re-flow that produces the exact pixel sizes is a compositing
// step, not a generation one.
const RATIO_FOR_SIZE = {
  '1200x628': '16:9',
  '1080x1080': '1:1',
  '1080x1920': '9:16',
  '728x90': '16:9',
  '300x250': '1:1',
  '160x600': '9:16',
}

export default function BannerGenerator() {
  const [size, setSize] = useState(BANNER_SIZES[0])
  const [headline, setHeadline] = useState('')
  const [offer, setOffer] = useState('')
  const [cta, setCta] = useState(CTA_OPTIONS[0])
  const [color, setColor] = useState(BRAND_COLORS[0])
  const [subject, setSubject] = useState('')

  const toast = useToast()
  const { data, loading, run } = useAdGeneration(api.adCreative)
  const images = data?.images || null

  function generate() {
    if (subject.trim().length < 2) {
      toast.error('Describe what the banner should show first.')
      return
    }
    run({
      subject: subject.trim(),
      // The headline steers composition (it asks for empty space to place text
      // in) without asking the model to render the words, which it does badly.
      headline: headline.trim() || null,
      aspect_ratio: RATIO_FOR_SIZE[size.value] || '16:9',
      count: 2,
    })
  }

  return (
    <AdsWorkspace
      title={TOOL}
      description="Build one banner layout and re-flow it into every standard display size — never a stretched crop."
      controls={
        <>
          <Field label="Banner size" hint={size.hint}>
            <select
              className="select"
              value={size.value}
              onChange={(e) =>
                setSize(BANNER_SIZES.find((s) => s.value === e.target.value) || BANNER_SIZES[0])
              }
              aria-label="Banner size"
            >
              {BANNER_SIZES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label} — {s.hint}
                </option>
              ))}
            </select>
          </Field>

          <Field label="What the banner shows">
            <input
              className="input"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="Amber serum bottle on a sunlit surface"
            />
          </Field>

          <Field label="Headline">
            <input
              className="input"
              value={headline}
              onChange={(e) => setHeadline(e.target.value)}
              placeholder="Summer Sale"
            />
          </Field>

          <Field label="Offer" hint="Optional">
            <input
              className="input"
              value={offer}
              onChange={(e) => setOffer(e.target.value)}
              placeholder="Up to 50% off"
            />
          </Field>

          <Field label="Call to action">
            <select
              className="select"
              value={cta}
              onChange={(e) => setCta(e.target.value)}
              aria-label="Call to action"
            >
              {CTA_OPTIONS.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Brand colour" hint="From your Brand Kit">
            <div className="flex flex-wrap gap-2">
              {BRAND_COLORS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setColor(c)}
                  aria-label={`Brand colour ${c}`}
                  aria-pressed={color === c}
                  style={{ background: c }}
                  className={`h-8 w-8 rounded-full border-2 transition ${
                    color === c ? 'border-accent ring-2 ring-accent-soft' : 'border-line'
                  }`}
                />
              ))}
            </div>
          </Field>

        </>
      }
      action={
        <GenerateButton
          label="Generate Banners"
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
              <h2 className="text-sm font-semibold text-body">Generated banners</h2>
              <span className="text-xs text-muted">{size.label} · {size.hint}</span>
            </div>
            <CreativeResults images={images} sources={data?.sources} />
            <p className="mt-3 text-xs leading-relaxed text-muted">
              Generated at the nearest ratio the model supports. Re-flowing these into the
              exact display pixel sizes on the right is a compositing step, still to come.
            </p>
          </div>
        ) : (
          <PreviewStage
            hint={'An example banner. Describe what yours should show, pick a size, and press Generate.'}
            art="bannerAd"
            ratio="wide"
            toolName={TOOL}
            caption={`${size.label} · ${size.hint}`}
          />
        )
      }
      output={
        <RailSection title="Export sizes">
          <div className="space-y-3">
            {BANNER_EXPORT_SETS.map((set) => (
              <div key={set.network} className="panel p-3">
                <div className="text-xs font-semibold text-body">{set.network}</div>
                <ul className="mt-1.5 space-y-1">
                  {set.sizes.map((s) => (
                    <li key={s} className="flex items-center justify-between gap-2 text-xs">
                      <span className="text-muted">{s}</span>
                      <span className="text-muted opacity-60">—</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          <button
            type="button"
            disabled
            className="btn btn-secondary btn-sm mt-3 w-full"
            title="Available once banners have been generated"
          >
            Download all sizes
          </button>
        </RailSection>
      }
    />
  )
}
