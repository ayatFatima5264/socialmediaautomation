import { useState } from 'react'
import AdsWorkspace, { Field, RailSection } from '../../../components/ads/workspace/AdsWorkspace.jsx'
import GenerateButton from '../../../components/ads/workspace/GenerateButton.jsx'
import PlatformIcon from '../../../components/PlatformIcon.jsx'
import ChipSelect from '../../../components/ChipSelect.jsx'
import useAdGeneration from '../../../hooks/useAdGeneration'
import { useToast } from '../../../context/ToastContext.jsx'
import { api } from '../../../lib/api'
import { AD_PLATFORM_KEYS, COPY_TONES, CTA_OPTIONS } from '../../../lib/ads/constants'
import { PLATFORMS } from '../../../lib/constants'

// ---------------------------------------------------------------------------
// AI Ad Copy — wired to /api/ads/copy, which runs on the configured text
// provider (groq).
//
// The centre column shows either a worked EXAMPLE (before anything is
// generated, so the panel says what the tool returns) or the real variants.
// The two are never mixed and the heading says which is on screen — an example
// that could be mistaken for your own output is worse than an empty panel.
//
// The character counter is measured against PLATFORMS[platform].limit, the same
// source the organic composer counts against, so a variant that will not fit is
// visible before it is copied anywhere.
// ---------------------------------------------------------------------------

const TOOL = 'AI Ad Copy'
const PHASE = 2

const EXAMPLE = [
  {
    angle: 'Benefit',
    headline: 'Skin that looks after itself',
    body: 'Our organic serum gives your skin the care it deserves. Naturally made, clinically tested, and kind to every skin type.',
    cta: 'Shop Now',
  },
]

export default function AdCopy() {
  const [product, setProduct] = useState('')
  const [audience, setAudience] = useState('')
  const [offer, setOffer] = useState('')
  const [platform, setPlatform] = useState('instagram')
  const [tone, setTone] = useState('Professional')
  const [cta, setCta] = useState(CTA_OPTIONS[0])

  const toast = useToast()
  const { data, loading, run } = useAdGeneration(api.adCopy)

  const limit = PLATFORMS[platform]?.limit ?? 2200
  const variants = data?.variants || null
  const shown = variants || EXAMPLE

  function generate() {
    if (product.trim().length < 2) {
      toast.error('Tell the model what you are advertising first.')
      return
    }
    run({
      product: product.trim(),
      audience: audience.trim() || null,
      offer: offer.trim() || null,
      platform,
      tone,
      cta,
      variants: 3,
    })
  }

  return (
    <AdsWorkspace
      title={TOOL}
      description="Write headlines, primary text and calls to action tuned to each platform's limits and conventions."
      controls={
        <>
          <Field label="Product or service">
            <input
              className="input"
              value={product}
              onChange={(e) => setProduct(e.target.value)}
              placeholder="Organic skincare serum"
            />
          </Field>

          <Field label="Audience" hint="Optional">
            <input
              className="input"
              value={audience}
              onChange={(e) => setAudience(e.target.value)}
              placeholder="Women 25–40 who buy natural skincare"
            />
          </Field>

          <Field label="Offer" hint="Optional">
            <input
              className="input"
              value={offer}
              onChange={(e) => setOffer(e.target.value)}
              placeholder="20% off the first order"
            />
          </Field>

          <Field label="Platform" hint={`${limit.toLocaleString()} char limit`}>
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

          <Field label="Tone">
            <ChipSelect options={COPY_TONES} value={tone} onChange={setTone} />
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
        </>
      }
      action={
        <GenerateButton
          label="Generate Copy"
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
              {variants ? 'Generated Copy' : 'Example output'}
            </h2>
            <span className="badge badge-accent">
              {variants ? `${variants.length} variants` : 'Not generated yet'}
            </span>
          </div>

          {!variants && (
            <p className="mb-4 text-xs leading-relaxed text-muted">
              This is the shape {TOOL} returns — a headline, primary text and a CTA per
              variant. Fill in the brief and press Generate for your own.
            </p>
          )}

          <div className="space-y-4">
            {shown.map((v, i) => {
              const used = v.body.length
              return (
                <article key={i} className="panel p-3.5">
                  <div className="mb-2.5 flex items-center justify-between gap-2">
                    <span className="text-[11px] font-semibold uppercase tracking-wide text-accent">
                      {v.angle}
                    </span>
                    <PlatformIcon platform={platform} size={22} />
                  </div>

                  <p className="text-base font-bold leading-snug text-body">{v.headline}</p>

                  <p className="mt-2 text-sm leading-relaxed text-body">{v.body}</p>

                  <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                    <span className="btn btn-primary btn-sm pointer-events-none">{v.cta}</span>
                    <span
                      className={`text-[11px] font-medium ${
                        used > limit ? 'text-rose-600' : 'text-muted'
                      }`}
                    >
                      {used} / {limit.toLocaleString()}
                    </span>
                  </div>
                </article>
              )
            })}
          </div>
        </div>
      }
      output={
        <>
          <RailSection title="Angles">
            <p className="text-xs leading-relaxed text-muted">
              Each generation returns several angles — benefit, curiosity, objection,
              proof, urgency — so there is something real to test against rather than one
              safe option.
            </p>
          </RailSection>

          <RailSection title="Actions">
            <div className="space-y-2">
              <button
                type="button"
                disabled={!variants}
                onClick={() => {
                  const text = variants
                    .map((v) => `${v.headline}\n\n${v.body}\n\n${v.cta}`)
                    .join('\n\n---\n\n')
                  navigator.clipboard
                    ?.writeText(text)
                    .then(() => toast.success('Copied all variants.'))
                    .catch(() => toast.error('Could not copy.'))
                }}
                className="btn btn-secondary btn-sm w-full"
                title={variants ? 'Copy every variant' : 'Generate copy first'}
              >
                Copy all
              </button>
            </div>
          </RailSection>
        </>
      }
    />
  )
}
