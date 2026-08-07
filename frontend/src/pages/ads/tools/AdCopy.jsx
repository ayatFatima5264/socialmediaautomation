import { useState } from 'react'
import { Link } from 'react-router-dom'
import AdsWorkspace, { Field, RailSection } from '../../../components/ads/workspace/AdsWorkspace.jsx'
import GenerateButton from '../../../components/ads/workspace/GenerateButton.jsx'
import PlatformIcon from '../../../components/PlatformIcon.jsx'
import useCampaignContext from '../../../hooks/useCampaignContext'
import { useToast } from '../../../context/ToastContext.jsx'
import { api } from '../../../lib/api'
import { AD_PLATFORM_KEYS, CTA_OPTIONS } from '../../../lib/ads/constants'
import { campaignSubject } from '../../../lib/ads/campaignTypes'
import { CAMPAIGN_NEW_PATH } from '../../../lib/ads/tools'
import { PLATFORMS } from '../../../lib/constants'

// ---------------------------------------------------------------------------
// AI Ad Copy — wired to /api/ads/copy, which runs on the configured text
// provider (groq).
//
// ---- What it no longer asks ----------------------------------------------
// Product, audience, offer and tone used to be four fields here. All four are
// campaign memory: they were answered once when the campaign was briefed, and
// re-typing them into this page — every visit, for every platform — was the
// duplication this workflow exists to remove. The bar above shows what is being
// used; the controls are down to the two decisions that belong to this
// generation alone: which CTA button, and how many angles.
//
// ---- Platform versions ----------------------------------------------------
// One request PER PLATFORM rather than one request re-labelled. Each platform
// has a different character ceiling and different conventions, and the endpoint
// already enforces the ceiling it is told about — so asking once and captioning
// the result "works everywhere" would be the lie. The tabs in the centre are
// genuinely different copy.
//
// Everything generated is saved into the campaign as it arrives: headlines,
// primary text and CTAs each land in their own section of the library.
// ---------------------------------------------------------------------------

const TOOL = 'AI Ad Copy'
const PHASE = 2

const EXAMPLE = {
  angle: 'Benefit',
  headline: 'Skin that looks after itself',
  description: 'Naturally made, clinically tested, kind to every skin type.',
  body: 'Our organic serum gives your skin the care it deserves. Two weeks is all it takes to see the difference.',
  cta: 'Shop Now',
  hashtags: ['organicskincare', 'cleanbeauty', 'serum'],
}

function Variant({ variant, platform, limit }) {
  const used = variant.body.length

  return (
    <article className="panel p-3.5">
      <div className="mb-2.5 flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-accent">
          {variant.angle}
        </span>
        <PlatformIcon platform={platform} size={22} />
      </div>

      <dl className="space-y-2.5">
        <div>
          <dt className="text-[10px] font-semibold uppercase tracking-wide text-muted">
            Headline
          </dt>
          <dd className="text-base font-bold leading-snug text-body">{variant.headline}</dd>
        </div>

        {variant.description && (
          <div>
            <dt className="text-[10px] font-semibold uppercase tracking-wide text-muted">
              Description
            </dt>
            <dd className="text-sm leading-snug text-body">{variant.description}</dd>
          </div>
        )}

        <div>
          <dt className="text-[10px] font-semibold uppercase tracking-wide text-muted">
            Primary text
          </dt>
          <dd className="text-sm leading-relaxed text-body">{variant.body}</dd>
        </div>

        {variant.hashtags?.length > 0 && (
          <div>
            <dt className="text-[10px] font-semibold uppercase tracking-wide text-muted">
              Hashtags
            </dt>
            <dd className="flex flex-wrap gap-1.5 pt-0.5">
              {variant.hashtags.map((tag) => (
                <span key={tag} className="badge badge-accent">
                  #{tag}
                </span>
              ))}
            </dd>
          </div>
        )}
      </dl>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <span className="btn btn-primary btn-sm pointer-events-none">{variant.cta}</span>
        <span
          className={`text-[11px] font-medium ${used > limit ? 'text-rose-600' : 'text-muted'}`}
        >
          {used} / {limit.toLocaleString()}
        </span>
      </div>
    </article>
  )
}

export default function AdCopy() {
  const { campaign, saveAssets } = useCampaignContext()
  const toast = useToast()

  const [cta, setCta] = useState(CTA_OPTIONS[0])
  const [count, setCount] = useState(3)
  const [subject, setSubject] = useState('')
  const [running, setRunning] = useState(false)
  // { [platformKey]: variants[] }
  const [byPlatform, setByPlatform] = useState(null)
  const [tab, setTab] = useState(null)

  // The campaign decides which platforms to write for. Outside a campaign there
  // is nothing to read, so it falls back to the full ad-platform list.
  const platforms = campaign?.platforms?.length ? campaign.platforms : AD_PLATFORM_KEYS.slice(0, 1)

  const activeTab = tab && platforms.includes(tab) ? tab : platforms[0]
  const variants = byPlatform?.[activeTab] || null
  const limit = PLATFORMS[activeTab]?.limit ?? 2200
  const shown = variants || [EXAMPLE]

  async function generate() {
    const base = campaign ? campaignSubject(campaign) : subject.trim()
    if (base.length < 2) {
      toast.error('Tell the model what you are advertising first.')
      return
    }

    setRunning(true)
    try {
      // allSettled: one platform being rate-limited must not throw away the
      // copy already written for the others.
      const settled = await Promise.allSettled(
        platforms.map((platform) =>
          api.adCopy({
            product: base,
            audience: campaign?.audience?.trim() || null,
            offer: null,
            platform,
            tone: campaign?.tone || 'Professional',
            cta,
            variants: count,
          }),
        ),
      )

      const next = {}
      settled.forEach((outcome, i) => {
        if (outcome.status === 'fulfilled' && outcome.value?.variants?.length) {
          next[platforms[i]] = outcome.value.variants
        }
      })

      if (!Object.keys(next).length) {
        toast.error('The model returned no usable copy. Try again.')
        return
      }

      const missed = platforms.length - Object.keys(next).length
      if (missed > 0) {
        toast.info(`Copy written for ${Object.keys(next).length} of ${platforms.length} platforms.`)
      }

      setByPlatform(next)
      setTab(Object.keys(next)[0])

      // Each piece is saved into the section of the library it belongs to —
      // headlines with headlines, primary text with captions, CTAs with CTAs —
      // rather than as one blob nothing can be reused from.
      const assets = []
      Object.entries(next).forEach(([platform, list]) => {
        const label = PLATFORMS[platform]?.label || platform
        list.forEach((v) => {
          assets.push({
            kind: 'headline',
            title: `${label} · ${v.angle}`,
            body: v.headline,
            tool: TOOL,
            meta: { platform, angle: v.angle, description: v.description },
          })
          assets.push({
            kind: 'caption',
            title: `${label} · ${v.angle} — primary text`,
            body: v.body,
            tool: TOOL,
            meta: { platform, angle: v.angle, hashtags: v.hashtags },
          })
          assets.push({
            kind: 'cta',
            title: `${label} · ${v.cta}`,
            body: v.cta,
            tool: TOOL,
            meta: { platform, angle: v.angle },
          })
        })
      })
      await saveAssets(assets)
    } catch (err) {
      toast.error(err?.message || 'Generation failed. Try again.')
    } finally {
      setRunning(false)
    }
  }

  function copyAll() {
    if (!variants) return
    const text = variants
      .map((v) =>
        [
          v.headline,
          v.description,
          v.body,
          v.cta,
          v.hashtags?.length ? v.hashtags.map((t) => `#${t}`).join(' ') : '',
        ]
          .filter(Boolean)
          .join('\n\n'),
      )
      .join('\n\n---\n\n')

    navigator.clipboard
      ?.writeText(text)
      .then(() => toast.success('Copied all variants.'))
      .catch(() => toast.error('Could not copy.'))
  }

  return (
    <AdsWorkspace
      title={TOOL}
      campaign={campaign}
      description="Headlines, descriptions, primary text, CTAs and hashtags — written once per platform, to each one's limits."
      controls={
        <>
          {!campaign && (
            <>
              <Field label="What you are advertising" hint="Or open this from a campaign">
                <textarea
                  rows={3}
                  className="input resize-none"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder="Organic skincare serum for sensitive skin"
                />
              </Field>
              <p className="text-[11px] leading-relaxed text-muted">
                <Link to={CAMPAIGN_NEW_PATH} className="text-accent underline">
                  Start a campaign
                </Link>{' '}
                and the audience, tone and platforms come with it — this page stops asking
                entirely.
              </p>
            </>
          )}

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

          <Field label="Angles per platform" hint={`${count} variants`}>
            <select
              className="select"
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
              aria-label="Angles per platform"
            >
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>
                  {n} {n === 1 ? 'angle' : 'angles'}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Writing for" hint={campaign ? "The campaign's platforms" : 'Default'}>
            <div className="flex flex-wrap gap-2">
              {platforms.map((key) => (
                <span
                  key={key}
                  className="flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-xs font-medium text-body"
                >
                  <PlatformIcon platform={key} size={16} />
                  {PLATFORMS[key]?.label || key}
                </span>
              ))}
            </div>
            <p className="mt-1.5 text-[11px] leading-relaxed text-muted">
              {campaign
                ? 'Set on the campaign, not here — changing them for one tool would put the campaign and its copy out of step.'
                : 'Open this from a campaign to write for all of its platforms at once.'}
            </p>
          </Field>
        </>
      }
      action={
        <GenerateButton
          label={`Generate Copy · ${platforms.length} platform${platforms.length === 1 ? '' : 's'}`}
          toolName={TOOL}
          phase={PHASE}
          onClick={generate}
          loading={running}
        />
      }
      stage={
        <div className="card flex min-h-[320px] flex-col p-4 lg:min-h-full">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-semibold text-body">
              {variants ? 'Generated copy' : 'Example output'}
            </h2>
            <span className="badge badge-accent">
              {variants ? `${variants.length} variants` : 'Not generated yet'}
            </span>
          </div>

          {/* Platform tabs. Shown whenever the campaign has more than one, even
              before generating — so it is clear up front that this produces a
              version per platform rather than one shared block. */}
          {platforms.length > 1 && (
            <div className="mb-3 flex flex-wrap gap-1.5">
              {platforms.map((key) => {
                const on = key === activeTab
                const ready = Boolean(byPlatform?.[key])
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setTab(key)}
                    aria-pressed={on}
                    className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                      on
                        ? 'border-accent bg-accent-soft text-accent'
                        : 'border-line text-muted hover:border-accent'
                    }`}
                  >
                    <PlatformIcon platform={key} size={16} />
                    {PLATFORMS[key]?.label || key}
                    {byPlatform && !ready && (
                      <span className="text-[10px] opacity-70">—</span>
                    )}
                  </button>
                )
              })}
            </div>
          )}

          {!variants && (
            <p className="mb-4 text-xs leading-relaxed text-muted">
              This is the shape {TOOL} returns — a headline, a description, the primary
              text, a CTA and hashtags per angle.{' '}
              {campaign
                ? 'Everything it needs is already loaded from the campaign; press Generate.'
                : 'Fill in the brief and press Generate for your own.'}
            </p>
          )}

          <div className="space-y-4">
            {shown.map((v, i) => (
              <Variant key={i} variant={v} platform={activeTab} limit={limit} />
            ))}
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
                onClick={copyAll}
                className="btn btn-secondary btn-sm w-full"
                title={variants ? 'Copy every variant on this tab' : 'Generate copy first'}
              >
                Copy this platform
              </button>
              <button
                type="button"
                onClick={generate}
                disabled={running}
                className="btn btn-secondary btn-sm w-full"
              >
                Regenerate
              </button>
            </div>
            {campaign && variants && (
              <p className="mt-2 text-[11px] leading-relaxed text-muted">
                Saved to {campaign.name} — headlines, primary text and CTAs each in their
                own section of the library.
              </p>
            )}
          </RailSection>
        </>
      }
    />
  )
}
