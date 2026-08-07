import { useState } from 'react'
import AdsWorkspace, { Field, RailSection } from '../../../components/ads/workspace/AdsWorkspace.jsx'
import GenerateButton from '../../../components/ads/workspace/GenerateButton.jsx'
import ChipSelect from '../../../components/ChipSelect.jsx'
import useAdGeneration from '../../../hooks/useAdGeneration'
import useCampaignContext from '../../../hooks/useCampaignContext'
import { useToast } from '../../../context/ToastContext.jsx'
import { api } from '../../../lib/api'
import { AD_PLATFORM_KEYS } from '../../../lib/ads/constants'
import { campaignSubject } from '../../../lib/ads/campaignTypes'
import { PLATFORMS } from '../../../lib/constants'

// ---------------------------------------------------------------------------
// Headline Generator — wired to /api/ads/headlines (groq).
//
// The output is a ranked list, not one answer, so the centre column is the
// list. Each row carries its angle, its length against the 40-character ad
// ceiling, and the model's reasoning for the position — so the ranking can be
// disagreed with rather than taken on trust.
// ---------------------------------------------------------------------------

const TOOL = 'Headline Generator'
const PHASE = 2

const ANGLES = ['Curiosity', 'Benefit', 'Objection', 'Proof', 'Urgency', 'Question']

const EXAMPLE = [
  { angle: 'Benefit', text: 'Skin that looks after itself', why: '' },
  { angle: 'Curiosity', text: 'The step most routines skip', why: '' },
  { angle: 'Proof', text: '9 in 10 saw softer skin', why: '' },
]

export default function HeadlineGenerator() {
  const { campaign, saveAssets } = useCampaignContext()

  const [product, setProduct] = useState('')
  const [offer, setOffer] = useState('')
  const [platform, setPlatform] = useState('facebook')
  const [angles, setAngles] = useState(['Benefit', 'Curiosity', 'Proof'])

  // Inside a campaign the platform is the campaign's, not a fifth thing to
  // choose — a headline written to LinkedIn's conventions for a campaign that
  // does not run on LinkedIn is a wasted generation.
  const activePlatform = campaign?.platforms?.[0] || platform

  const toast = useToast()
  const { data, loading, run } = useAdGeneration(api.adHeadlines)

  const headlines = data?.headlines || null
  const limit = data?.limit ?? 40
  const shown = headlines || EXAMPLE

  async function generate() {
    const base = campaign ? campaignSubject(campaign) : product.trim()
    if (base.length < 2) {
      toast.error('Tell the model what you are advertising first.')
      return
    }

    const result = await run({
      product: base,
      offer: offer.trim() || null,
      angles,
      platform: activePlatform,
      count: 6,
    })

    // Saved as they arrive — a ranked list you have to re-generate because you
    // navigated away is not a library.
    if (result?.headlines?.length) {
      await saveAssets(
        result.headlines.map((h) => ({
          kind: 'headline',
          title: `${h.angle} — ${PLATFORMS[activePlatform]?.label || activePlatform}`,
          body: h.text,
          tool: TOOL,
          meta: { angle: h.angle, why: h.why, platform: activePlatform },
        })),
      )
    }
  }

  return (
    <AdsWorkspace
      title={TOOL}
      campaign={campaign}
      description="Produce a spread of headlines for one offer — different angles and lengths, ranked so you know what to test first."
      controls={
        <>
          {/* Inside a campaign the brief is the subject, already written and
              shown above. Outside one it has to be asked for. */}
          {!campaign && (
            <Field label="Product or service">
              <input
                className="input"
                value={product}
                onChange={(e) => setProduct(e.target.value)}
                placeholder="Organic skincare serum"
              />
            </Field>
          )}

          <Field label="Offer" hint="Optional">
            <input
              className="input"
              value={offer}
              onChange={(e) => setOffer(e.target.value)}
              placeholder="20% off the first order"
            />
          </Field>

          <Field label="Angles" hint={`${angles.length} selected`}>
            <ChipSelect options={ANGLES} value={angles} onChange={setAngles} multi />
          </Field>

          <Field label="Platform" hint={campaign ? 'From the campaign' : undefined}>
            {campaign ? (
              <p className="text-xs text-body">
                {PLATFORMS[activePlatform]?.label || activePlatform}
              </p>
            ) : (
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
            )}
          </Field>
        </>
      }
      action={
        <GenerateButton
          label="Generate Headlines"
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
              {headlines ? 'Headlines' : 'Example output'}
            </h2>
            <span className="badge badge-accent">
              {headlines ? `${headlines.length} ranked` : 'Not generated yet'}
            </span>
          </div>

          <p className="mb-4 text-xs leading-relaxed text-muted">
            {headlines
              ? `Ranked strongest first, measured against the ${limit}-character ad headline ceiling.`
              : `This is the shape ${TOOL} returns. Fill in the brief and press Generate for your own.`}
          </p>

          <ol className="space-y-2">
            {shown.map((h, i) => {
              const over = h.over_limit ?? h.text.length > limit
              return (
                <li key={`${h.text}-${i}`} className="panel flex items-start gap-3 p-3">
                  <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-accent-soft text-xs font-bold text-accent">
                    {i + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-body">{h.text}</p>

                    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
                      <span className="text-[11px] font-medium text-muted">{h.angle}</span>
                      <span
                        className={`text-[11px] font-medium ${
                          over ? 'text-rose-600' : 'text-muted'
                        }`}
                      >
                        {h.text.length} / {limit}
                      </span>
                    </div>

                    {h.why && (
                      <p className="mt-1.5 text-[11px] leading-relaxed text-muted">{h.why}</p>
                    )}
                  </div>
                </li>
              )
            })}
          </ol>
        </div>
      }
      output={
        <>
          <RailSection title="Why ranked">
            <p className="text-xs leading-relaxed text-muted">
              Each headline arrives with the reasoning behind its position, so you can
              disagree with the order rather than take it on trust.
            </p>
          </RailSection>

          <RailSection title="Actions">
            <button
              type="button"
              disabled={!headlines}
              onClick={() => {
                navigator.clipboard
                  ?.writeText(headlines.map((h) => h.text).join('\n'))
                  .then(() => toast.success('Copied all headlines.'))
                  .catch(() => toast.error('Could not copy.'))
              }}
              className="btn btn-secondary btn-sm w-full"
              title={headlines ? 'Copy every headline' : 'Generate headlines first'}
            >
              Copy all
            </button>
          </RailSection>
        </>
      }
    />
  )
}
