import { useState } from 'react'
import AdsWorkspace, { Field, RailSection } from '../../../components/ads/workspace/AdsWorkspace.jsx'
import GenerateButton from '../../../components/ads/workspace/GenerateButton.jsx'
import ChipSelect from '../../../components/ChipSelect.jsx'
import PlatformIcon from '../../../components/PlatformIcon.jsx'
import useAdGeneration from '../../../hooks/useAdGeneration'
import useCampaignContext from '../../../hooks/useCampaignContext'
import { useToast } from '../../../context/ToastContext.jsx'
import { api } from '../../../lib/api'
import { AD_PLATFORM_KEYS, COPY_TONES } from '../../../lib/ads/constants'
import { campaignSubject } from '../../../lib/ads/campaignTypes'
import { PLATFORMS } from '../../../lib/constants'

// ---------------------------------------------------------------------------
// CTA Generator — wired to /api/ads/ctas (groq).
//
// A call to action is two decisions: the button, which the platform constrains
// to a fixed list, and the line above it, which is free text. The server owns
// the button list and rejects anything the model invents outside it, so a
// generated CTA is always one the platform will actually accept.
//
// Funnel stages are ASCII here on purpose. An em dash in the request body has
// tripped encoding on the way out before; the label is cosmetic, so there is no
// reason to risk it on a value that crosses the wire.
// ---------------------------------------------------------------------------

const TOOL = 'CTA Generator'
const PHASE = 2

const FUNNEL_STAGES = [
  'Cold - first touch',
  'Warm - considering',
  'Hot - ready to buy',
  'Retargeting',
]

const EXAMPLE = [
  { line: 'Start your routine tonight', button: 'Shop Now' },
  { line: 'See what two weeks changes', button: 'Learn More' },
]

export default function CtaGenerator() {
  const { campaign, saveAssets } = useCampaignContext()

  const [offer, setOffer] = useState('')
  const [stage, setStage] = useState('Warm - considering')
  const [platform, setPlatform] = useState('facebook')
  const [tone, setTone] = useState('Friendly')

  // Platform and tone belong to the campaign when there is one. Both change
  // what comes back, and both were already answered when it was briefed.
  const activePlatform = campaign?.platforms?.[0] || platform
  const activeTone = campaign?.tone || tone

  const toast = useToast()
  const { data, loading, run } = useAdGeneration(api.adCtas)

  const ctas = data?.ctas || null
  const buttons = data?.buttons || null
  const shown = ctas || EXAMPLE

  async function generate() {
    // A CTA needs the specific offer; the campaign brief is the fallback when
    // no separate offer has been typed.
    const base = offer.trim() || (campaign ? campaignSubject(campaign) : '')
    if (base.length < 2) {
      toast.error('Describe the offer first.')
      return
    }

    const result = await run({
      offer: base,
      stage,
      platform: activePlatform,
      tone: activeTone,
      count: 5,
    })

    if (result?.ctas?.length) {
      await saveAssets(
        result.ctas.map((c) => ({
          kind: 'cta',
          title: `${c.button} — ${stage}`,
          body: c.line,
          tool: TOOL,
          meta: { button: c.button, stage, platform: activePlatform, tone: activeTone },
        })),
      )
    }
  }

  return (
    <AdsWorkspace
      title={TOOL}
      campaign={campaign}
      description="Calls to action matched to the offer, the funnel stage, and the button set the platform actually gives you."
      controls={
        <>
          <Field label="Offer" hint={campaign ? 'Optional — the brief is used otherwise' : undefined}>
            <input
              className="input"
              value={offer}
              onChange={(e) => setOffer(e.target.value)}
              placeholder="20% off the first order"
            />
          </Field>

          <Field label="Funnel stage">
            <ChipSelect options={FUNNEL_STAGES} value={stage} onChange={setStage} />
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

          {!campaign?.tone && (
            <Field label="Tone">
              <ChipSelect options={COPY_TONES} value={tone} onChange={setTone} />
            </Field>
          )}
        </>
      }
      action={
        <GenerateButton
          label="Generate CTAs"
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
              {ctas ? 'Calls to action' : 'Example output'}
            </h2>
            <span className="badge badge-accent">
              {ctas ? `${ctas.length} options` : 'Not generated yet'}
            </span>
          </div>

          <p className="mb-4 text-xs leading-relaxed text-muted">
            The supporting line is generated; the button comes from{' '}
            {PLATFORMS[activePlatform]?.label || activePlatform}&apos;s own set, so it is always one the
            platform will accept.
          </p>

          <div className="space-y-2.5">
            {shown.map((c, i) => (
              <div key={`${c.line}-${i}`} className="panel flex flex-wrap items-center gap-3 p-3.5">
                <PlatformIcon platform={activePlatform} size={26} />
                <p className="min-w-0 flex-1 text-sm text-body">{c.line}</p>
                <span className="btn btn-primary btn-sm pointer-events-none">{c.button}</span>
              </div>
            ))}
          </div>

          {buttons && (
            <div className="mt-5">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
                Buttons {PLATFORMS[activePlatform]?.label || activePlatform} supports
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {buttons.map((b) => (
                  <span
                    key={b}
                    className="rounded-md border border-line bg-inset px-2 py-1 text-xs text-muted"
                  >
                    {b}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      }
      output={
        <>
          <RailSection title="Matched to stage">
            <p className="text-xs leading-relaxed text-muted">
              A cold audience is asked to learn, not to buy. The stage you pick changes the
              ask, not just the wording.
            </p>
          </RailSection>

          <RailSection title="Actions">
            <button
              type="button"
              disabled={!ctas}
              onClick={() => {
                navigator.clipboard
                  ?.writeText(ctas.map((c) => `${c.line} — [${c.button}]`).join('\n'))
                  .then(() => toast.success('Copied all CTAs.'))
                  .catch(() => toast.error('Could not copy.'))
              }}
              className="btn btn-secondary btn-sm w-full"
              title={ctas ? 'Copy every CTA' : 'Generate CTAs first'}
            >
              Copy all
            </button>
          </RailSection>
        </>
      }
    />
  )
}
