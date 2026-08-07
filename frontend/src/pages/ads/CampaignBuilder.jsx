import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import AdsPageHeader from '../../components/ads/AdsPageHeader.jsx'
import CampaignTypeSelect from '../../components/ads/CampaignTypeSelect.jsx'
import ChipSelect from '../../components/ChipSelect.jsx'
import PlatformIcon from '../../components/PlatformIcon.jsx'
import { useToast } from '../../context/ToastContext.jsx'
import { campaignStore } from '../../lib/ads/store'
import { AD_PLATFORM_KEYS, CAMPAIGN_OBJECTIVES, COPY_TONES } from '../../lib/ads/constants'
import { campaignType, CAMPAIGN_TYPE_LABELS, DEFAULT_CAMPAIGN_TYPE } from '../../lib/ads/campaignTypes'
import { campaignPath } from '../../lib/ads/tools'
import { PLATFORMS } from '../../lib/constants'

// ---------------------------------------------------------------------------
// New Campaign — the brief that creates a campaign record.
//
// One screen, not a multi-step wizard. Every answer here is editable afterwards
// on the campaign itself, so splitting them across steps would add clicks and a
// progress bar without adding certainty.
//
// ---- Why this form is longer than it was ---------------------------------
// It is the ONLY place these questions get asked. Type, objective, platforms,
// tone, audience and brief used to be re-asked by each of the six generators,
// once per visit; now they are answered once here and every tool inherits them.
// Six fields on one screen is a shorter path than four fields re-typed six
// times, and it is the trade this whole workflow rests on.
//
// Campaign Type comes FIRST after the name because it is the most consequential
// answer: it decides which creative tools exist, what the fields are called,
// and what the image model is asked for. Objective only changes the words.
//
// The campaign is created as a DRAFT. Nothing is scheduled or spent by pressing
// Create — that only happens later, deliberately, from the campaign itself.
// ---------------------------------------------------------------------------

export default function CampaignBuilder() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()

  // The Studio home's quick-start cards pick the type before the form opens, so
  // "Promote a Website" lands on a form that already knows that much. An
  // unrecognised value falls back to the default rather than blanking the field.
  const requested = params.get('type')
  const initialType = CAMPAIGN_TYPE_LABELS.includes(requested)
    ? requested
    : DEFAULT_CAMPAIGN_TYPE.label

  const [name, setName] = useState('')
  const [type, setType] = useState(initialType)
  const [objective, setObjective] = useState(CAMPAIGN_OBJECTIVES[0])
  const [platforms, setPlatforms] = useState(['instagram'])
  const [brief, setBrief] = useState('')
  const [audience, setAudience] = useState('')
  const [tone, setTone] = useState('Professional')
  const [saving, setSaving] = useState(false)

  // Templates hand their slug over in the URL. It is recorded in the brief
  // rather than silently applied: the template library does not exist yet, so
  // claiming a template was applied would be a lie.
  const template = params.get('template')

  const selectedType = campaignType(type)

  async function create() {
    if (name.trim().length < 1) {
      toast.error('Give the campaign a name.')
      return
    }
    if (!platforms.length) {
      toast.error('Pick at least one platform.')
      return
    }

    setSaving(true)
    try {
      const campaign = await campaignStore.create({
        name: name.trim(),
        campaignType: type,
        objective,
        platforms,
        status: 'draft',
        tone,
        audience: audience.trim(),
        brief: [brief.trim(), template ? `Started from template: ${template}` : '']
          .filter(Boolean)
          .join('\n\n'),
      })
      toast.success('Campaign created as a draft.')
      navigate(campaignPath(campaign.id), { replace: true })
    } catch (err) {
      toast.error(err?.message || 'Could not create the campaign.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6 pb-4">
      <AdsPageHeader
        title="New Campaign"
        description="A campaign is the project every tool works inside. Answer these once and the Banner Generator, AI Copy, Carousel and video tools all inherit them — none of them will ask again."
        backLabel="AI Ads Studio"
      />

      <div className="card space-y-5 p-5">
        <div>
          <label htmlFor="cmp-name" className="label">
            Campaign name
          </label>
          <input
            id="cmp-name"
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Spring Product Launch"
          />
        </div>

        {/* Type before objective — it decides which tools the campaign gets. */}
        <div>
          <span className="label">Campaign type</span>
          <p className="-mt-1 mb-2 text-xs text-muted">
            What you are advertising. Not every campaign sells a product, and this is
            what stops the tools asking for one.
          </p>
          <CampaignTypeSelect value={type} onChange={setType} />
        </div>

        <div>
          <span className="label">Objective</span>
          <p className="-mt-1 mb-2 text-xs text-muted">What the campaign should achieve.</p>
          <ChipSelect
            options={CAMPAIGN_OBJECTIVES}
            value={objective}
            onChange={setObjective}
          />
        </div>

        <div>
          <span className="label">Platforms</span>
          <div className="flex flex-wrap gap-2">
            {AD_PLATFORM_KEYS.map((key) => {
              const on = platforms.includes(key)
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() =>
                    setPlatforms(
                      on ? platforms.filter((p) => p !== key) : [...platforms, key],
                    )
                  }
                  aria-pressed={on}
                  className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-medium transition ${
                    on
                      ? 'border-accent bg-accent-soft text-accent'
                      : 'border-line text-muted hover:border-accent'
                  }`}
                >
                  <PlatformIcon platform={key} size={18} />
                  {PLATFORMS[key]?.label || key}
                </button>
              )
            })}
          </div>
        </div>

        <div>
          <label htmlFor="cmp-brief" className="label">
            Brief
          </label>
          <textarea
            id="cmp-brief"
            rows={5}
            className="input resize-none"
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            placeholder={`What is this campaign about? e.g. ${selectedType.subjectPlaceholder}`}
          />
          <p className="mt-1.5 text-xs text-muted">
            This is what the generators read. Written once here, it is the brief every
            tool starts from.
          </p>
        </div>

        {/* Audience and tone complete the campaign memory. Optional, because a
            brief on its own is enough to generate from — but supplied here they
            never have to be typed into a tool. */}
        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <label htmlFor="cmp-audience" className="label">
              Audience <span className="font-normal text-muted">— optional</span>
            </label>
            <input
              id="cmp-audience"
              className="input"
              value={audience}
              onChange={(e) => setAudience(e.target.value)}
              placeholder="Women 25–40 who buy natural skincare"
            />
          </div>

          <div>
            <span className="label">
              Tone <span className="font-normal text-muted">— optional</span>
            </span>
            <select
              className="select"
              value={tone}
              onChange={(e) => setTone(e.target.value)}
              aria-label="Tone"
            >
              {COPY_TONES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
        </div>

        {template && (
          <p className="panel p-3 text-xs leading-relaxed text-muted">
            Starting from the <span className="font-semibold text-body">{template}</span>{' '}
            template. Template layouts arrive in a later phase — for now the choice is
            recorded in the brief.
          </p>
        )}

        <div className="flex flex-wrap items-center gap-2 border-t border-line pt-4">
          <button
            type="button"
            onClick={create}
            disabled={saving}
            className="btn btn-primary"
          >
            {saving ? 'Creating…' : '✦ Create Campaign'}
          </button>
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="btn btn-secondary"
          >
            Cancel
          </button>
          <span className="ml-auto text-xs text-muted">Created as a draft</span>
        </div>
      </div>
    </div>
  )
}
