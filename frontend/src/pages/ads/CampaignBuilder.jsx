import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import AdsPageHeader from '../../components/ads/AdsPageHeader.jsx'
import ChipSelect from '../../components/ChipSelect.jsx'
import PlatformIcon from '../../components/PlatformIcon.jsx'
import { useToast } from '../../context/ToastContext.jsx'
import { campaignStore } from '../../lib/ads/store'
import { AD_PLATFORM_KEYS, CAMPAIGN_OBJECTIVES } from '../../lib/ads/constants'
import { campaignPath } from '../../lib/ads/tools'
import { PLATFORMS } from '../../lib/constants'

// ---------------------------------------------------------------------------
// New Campaign — the brief that creates a campaign record.
//
// One screen, not a multi-step wizard. A campaign here is four decisions
// (name, objective, platforms, brief) and every one of them is editable
// afterwards, so splitting them across steps would add clicks and a progress
// bar without adding certainty.
//
// The campaign is created as a DRAFT. Nothing is scheduled or spent by
// pressing Create — that only happens later, deliberately, from the campaign
// itself. A "Create" that quietly went live would be the wrong default for the
// one object in this module that can cost money.
// ---------------------------------------------------------------------------

export default function CampaignBuilder() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()

  const [name, setName] = useState('')
  const [objective, setObjective] = useState(CAMPAIGN_OBJECTIVES[0])
  const [platforms, setPlatforms] = useState(['instagram'])
  const [brief, setBrief] = useState('')
  const [saving, setSaving] = useState(false)

  // Templates hand their slug over in the URL. It is recorded in the brief
  // rather than silently applied: the template library does not exist yet, so
  // claiming a template was applied would be a lie.
  const template = params.get('template')

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
        objective,
        platforms,
        status: 'draft',
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
        description="A campaign groups the creatives, copy and platforms of one advertising effort so you can schedule and measure them together."
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

        <div>
          <span className="label">Objective</span>
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
            Brief <span className="font-normal text-muted">— optional</span>
          </label>
          <textarea
            id="cmp-brief"
            rows={5}
            className="input resize-none"
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            placeholder="What are you selling, to whom, and what should the ads say?"
          />
          <p className="mt-1.5 text-xs text-muted">
            Kept with the campaign so every tool you open from it starts from the same
            brief.
          </p>
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
