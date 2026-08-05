import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import AdsPageHeader from '../../components/ads/AdsPageHeader.jsx'
import CampaignStatusBadge from '../../components/ads/CampaignStatusBadge.jsx'
import ChipSelect from '../../components/ChipSelect.jsx'
import PlatformIcon from '../../components/PlatformIcon.jsx'
import { useToast } from '../../context/ToastContext.jsx'
import { campaignStore } from '../../lib/ads/store'
import {
  AD_PLATFORM_KEYS,
  CAMPAIGN_OBJECTIVES,
  CAMPAIGN_STATUS,
  CAMPAIGN_STATUS_KEYS,
} from '../../lib/ads/constants'
import { ADS_BASE_PATH, toolHref, toolsInCategory } from '../../lib/ads/tools'
import { formatDateTime } from '../../lib/datetime'
import { PLATFORMS } from '../../lib/constants'

// ---------------------------------------------------------------------------
// One campaign — editable, and the launch point for the tools that fill it.
//
// Edits save on demand rather than on every keystroke: a campaign is shared,
// billable state, and autosaving a half-typed name into it is the wrong
// default. The Save button enables only once something actually differs from
// what was loaded, so it never invites a no-op write.
//
// Deleting asks first, because there is no undo behind it.
// ---------------------------------------------------------------------------

export default function CampaignDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const toast = useToast()

  const [campaign, setCampaign] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const [form, setForm] = useState(null)

  useEffect(() => {
    let cancelled = false
    campaignStore
      .get(id)
      .then((row) => {
        if (cancelled) return
        setCampaign(row)
        if (row) {
          setForm({
            name: row.name,
            objective: row.objective,
            platforms: row.platforms,
            status: row.status,
            brief: row.brief || '',
          })
        }
      })
      .catch((e) => !cancelled && toast.error(e?.message || 'Could not load the campaign.'))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [id]) // eslint-disable-line react-hooks/exhaustive-deps

  const dirty =
    form &&
    campaign &&
    (form.name !== campaign.name ||
      form.objective !== campaign.objective ||
      form.status !== campaign.status ||
      form.brief !== (campaign.brief || '') ||
      form.platforms.join(',') !== campaign.platforms.join(','))

  async function save() {
    setSaving(true)
    try {
      const next = await campaignStore.update(id, form)
      setCampaign(next)
      toast.success('Campaign saved.')
    } catch (err) {
      toast.error(err?.message || 'Could not save.')
    } finally {
      setSaving(false)
    }
  }

  async function remove() {
    try {
      await campaignStore.remove(id)
      toast.success('Campaign deleted.')
      navigate(ADS_BASE_PATH, { replace: true })
    } catch (err) {
      toast.error(err?.message || 'Could not delete.')
    }
  }

  if (loading) {
    return (
      <div className="space-y-4 pb-4">
        <div className="skeleton h-8 w-64" />
        <div className="skeleton h-40 w-full" />
      </div>
    )
  }

  if (!campaign || !form) {
    return (
      <div className="space-y-6 pb-4">
        <AdsPageHeader
          title="Campaign not found"
          description="It may have been deleted."
          backLabel="AI Ads Studio"
        />
        <Link to={ADS_BASE_PATH} className="btn btn-primary">
          Go to AI Ads Studio
        </Link>
      </div>
    )
  }

  const creationTools = [...toolsInCategory('create'), ...toolsInCategory('video')]

  return (
    <div className="mx-auto max-w-3xl space-y-6 pb-4">
      <AdsPageHeader
        title={campaign.name}
        description={`Created ${formatDateTime(campaign.createdAt)} · ${campaign.creatives} creatives`}
        backLabel="AI Ads Studio"
        actions={<CampaignStatusBadge status={campaign.status} />}
      />

      {/* ---- Editable detail -------------------------------------------- */}
      <div className="card space-y-5 p-5">
        <div>
          <label htmlFor="cmp-name" className="label">
            Campaign name
          </label>
          <input
            id="cmp-name"
            className="input"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </div>

        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <span className="label">Objective</span>
            <select
              className="select"
              value={form.objective}
              onChange={(e) => setForm({ ...form, objective: e.target.value })}
              aria-label="Objective"
            >
              {CAMPAIGN_OBJECTIVES.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </div>

          <div>
            <span className="label">Status</span>
            <select
              className="select"
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value })}
              aria-label="Status"
            >
              {CAMPAIGN_STATUS_KEYS.map((k) => (
                <option key={k} value={k}>
                  {CAMPAIGN_STATUS[k].label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <span className="label">Platforms</span>
          <div className="flex flex-wrap gap-2">
            {AD_PLATFORM_KEYS.map((key) => {
              const on = form.platforms.includes(key)
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() =>
                    setForm({
                      ...form,
                      platforms: on
                        ? form.platforms.filter((p) => p !== key)
                        : [...form.platforms, key],
                    })
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
            value={form.brief}
            onChange={(e) => setForm({ ...form, brief: e.target.value })}
            placeholder="What are you selling, to whom, and what should the ads say?"
          />
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-line pt-4">
          <button
            type="button"
            onClick={save}
            disabled={!dirty || saving}
            className="btn btn-primary"
            title={dirty ? 'Save your changes' : 'Nothing has changed'}
          >
            {saving ? 'Saving…' : 'Save changes'}
          </button>

          {confirmDelete ? (
            <>
              <button type="button" onClick={remove} className="btn btn-danger">
                Delete permanently
              </button>
              <button
                type="button"
                onClick={() => setConfirmDelete(false)}
                className="btn btn-secondary"
              >
                Keep it
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmDelete(true)}
              className="btn btn-ghost ml-auto"
            >
              Delete
            </button>
          )}
        </div>
      </div>

      {/* ---- Performance ------------------------------------------------- */}
      <div className="card p-5">
        <h2 className="text-sm font-semibold text-body">Performance</h2>
        {campaign.ctr == null ? (
          <p className="mt-2 text-sm text-muted">
            Not started. Performance appears once the campaign runs on a connected ad
            account.
          </p>
        ) : (
          <dl className="mt-3 grid gap-4 sm:grid-cols-2">
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted">CTR</dt>
              <dd className="mt-1 text-2xl font-extrabold text-body">{campaign.ctr}%</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted">Impressions</dt>
              <dd className="mt-1 text-2xl font-extrabold text-body">
                {campaign.impressions.toLocaleString()}
              </dd>
            </div>
          </dl>
        )}
      </div>

      {/* ---- Fill it ----------------------------------------------------- */}
      <div className="card p-5">
        <h2 className="text-sm font-semibold text-body">Make creatives for this campaign</h2>
        <p className="mt-1.5 text-xs leading-relaxed text-muted">
          Each tool opens on its own. Attaching what they produce back to this campaign
          arrives with the creative library.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {creationTools.map((tool) => (
            <Link key={tool.slug} to={toolHref(tool)} className="btn btn-secondary btn-sm">
              {tool.name}
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}
