import { useState } from 'react'
import AdsWorkspace, { Field, RailSection } from '../../../components/ads/workspace/AdsWorkspace.jsx'
import CreativeResults from '../../../components/ads/workspace/CreativeResults.jsx'
import GenerateButton from '../../../components/ads/workspace/GenerateButton.jsx'
import PreviewStage from '../../../components/ads/workspace/PreviewStage.jsx'
import UploadField from '../../../components/ads/workspace/UploadField.jsx'
import ChipSelect from '../../../components/ChipSelect.jsx'
import useAdGeneration from '../../../hooks/useAdGeneration'
import { useToast } from '../../../context/ToastContext.jsx'
import { api } from '../../../lib/api'
import { ASPECT_RATIOS } from '../../../lib/constants'
import { BACKGROUND_PRESETS } from '../../../lib/ads/constants'

// ---------------------------------------------------------------------------
// Product Ads — wired to /api/ads/creative.
//
// ---- On the uploaded photo ------------------------------------------------
// The image model behind this endpoint is text-to-image: it cannot take your
// product photo as input. So the upload is NOT sent to it, and the field says
// so. It is still worth having — the photo is what you keep for reference and
// what an editing pass will use once one exists — but the generated creative
// is built from the written description, and pretending otherwise would have
// users uploading a bottle and wondering why a different bottle came back.
//
// That is why "Product" is a required text field rather than optional: it is
// the only thing the model actually sees.
// ---------------------------------------------------------------------------

const TOOL = 'Product Ads'
const PHASE = 2
const VERSIONS = 3

export default function ProductAds() {
  const [product, setProduct] = useState('')
  const [scene, setScene] = useState('')
  const [background, setBackground] = useState('Studio white')
  const [ratio, setRatio] = useState('1:1')
  const [chosen, setChosen] = useState(null)

  const toast = useToast()
  const { data, loading, run } = useAdGeneration(api.adCreative)
  const images = data?.images || null

  function generate() {
    if (product.trim().length < 2) {
      toast.error('Describe the product — that is what the image model reads.')
      return
    }
    setChosen(null)
    run({
      subject: [product.trim(), scene.trim()].filter(Boolean).join(', '),
      background,
      aspect_ratio: ratio,
      count: VERSIONS,
    })
  }

  return (
    <AdsWorkspace
      title={TOOL}
      description="Turn a product brief into a finished ad — background, composition and framing, sized for every placement."
      controls={
        <>
          <Field label="Product">
            <input
              className="input"
              value={product}
              onChange={(e) => setProduct(e.target.value)}
              placeholder="Amber glass skincare serum bottle"
            />
          </Field>

          <Field label="Scene" hint="Optional">
            <textarea
              rows={3}
              className="input resize-none"
              value={scene}
              onChange={(e) => setScene(e.target.value)}
              placeholder="On a marble slab, soft morning light, eucalyptus leaves"
            />
          </Field>

          <Field label="Background" hint={background}>
            <ChipSelect
              options={BACKGROUND_PRESETS}
              value={background}
              onChange={setBackground}
            />
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

          <Field label="Reference photo" hint="Kept, not generated from">
            <UploadField hint="Your own product shot, for reference" />
            <p className="mt-1.5 text-[11px] leading-relaxed text-muted">
              The image model is text-to-image and does not read this upload. The creative
              is generated from the Product and Scene fields above.
            </p>
          </Field>
        </>
      }
      action={
        <GenerateButton
          label={`Generate ${VERSIONS} Versions`}
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
              <h2 className="text-sm font-semibold text-body">Generated versions</h2>
              <span className="text-xs text-muted">{ratio} · pick one</span>
            </div>
            <CreativeResults images={images} sources={data?.sources} selected={chosen} onSelect={setChosen} />
          </div>
        ) : (
          <PreviewStage
            hint={'An example of the kind of ad this produces. Describe your product on the left and press Generate for three of your own.'}
            art="productAd"
            ratio="square"
            toolName={TOOL}
            caption={ratio}
          />
        )
      }
      output={
        <>
          <RailSection title="Versions">
            {images ? (
              <p className="text-xs leading-relaxed text-muted">
                {images.length} versions of the same brief. Pick one in the centre, then
                download it.
              </p>
            ) : (
              <p className="panel px-3 py-6 text-center text-xs text-muted">
                Generated versions appear here — keep several to test against each other.
              </p>
            )}
          </RailSection>

          <RailSection title="Actions">
            <div className="space-y-2">
              <a
                href={chosen || undefined}
                target="_blank"
                rel="noreferrer"
                className={`btn btn-secondary btn-sm w-full ${chosen ? '' : 'pointer-events-none opacity-50'}`}
                title={chosen ? 'Open the selected creative' : 'Select a version first'}
              >
                Open full size
              </a>
              <button
                type="button"
                onClick={generate}
                disabled={loading || !images}
                className="btn btn-secondary btn-sm w-full"
              >
                Regenerate
              </button>
            </div>
          </RailSection>
        </>
      }
    />
  )
}
