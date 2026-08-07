import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import AdsPageHeader from '../../components/ads/AdsPageHeader.jsx'
import CampaignLibrary from '../../components/ads/CampaignLibrary.jsx'
import CampaignOverview from '../../components/ads/CampaignOverview.jsx'
import CampaignStatusBadge from '../../components/ads/CampaignStatusBadge.jsx'
import CampaignTypeSelect from '../../components/ads/CampaignTypeSelect.jsx'
import PlatformIcon from '../../components/PlatformIcon.jsx'
import useCampaignAssets from '../../hooks/useCampaignAssets'
import { forgetCampaign } from '../../hooks/useCampaignContext'
import { useToast } from '../../context/ToastContext.jsx'
import { campaignStore } from '../../lib/ads/store'
import {
  AD_PLATFORM_KEYS,
  CAMPAIGN_OBJECTIVES,
  CAMPAIGN_STATUS,
  CAMPAIGN_STATUS_KEYS,
  COPY_TONES,
} from '../../lib/ads/constants'
import { campaignType, toolAppliesTo } from '../../lib/ads/campaignTypes'
import { ADS_BASE_PATH, campaignToolPath, toolsInCategory } from '../../lib/ads/tools'
import { formatDateTime } from '../../lib/datetime'
import { PLATFORMS } from '../../lib/constants'

// ---------------------------------------------------------------------------
// One campaign — the Studio's actual workspace.
//
// Everything happens here. The Studio home lists campaigns; this page is where
// creative gets made, and it is the destination every tool returns to. Four
// bands, in the order the work happens:
//
//   1. What this campaign IS      — the answers, given once, shown back
//   2. What it CONTAINS           — counts derived from the library below
//   3. What it HAS PRODUCED       — the library itself
//   4. What to MAKE NEXT          — the tools, each carrying the campaign
//
// ---- Why the detail is a summary with an editor behind it ----------------
// The old page opened as a form. That is the wrong default for a page visited
// mostly to make something: the six answers are settled, they need to be
// VISIBLE (so a tool inheriting them is verifiable) but not editable-by-default
// (so a stray keystroke cannot change what six generators read). Edit is one
// click away and saves on demand.
//
// ---- Which tools appear ---------------------------------------------------
// Filtered by campaign type. A Website campaign is not offered Product Ads,
// because that tool opens by asking for a product photo it does not have; it
// gets Website Promotion instead. That filtering lives in campaignTypes.js so
// this page states the rule once rather than enumerating slugs.
// ---------------------------------------------------------------------------

function Fact({ label, children }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] font-semibold uppercase tracking-wide text-muted">
        {label}
      </dt>
      <dd className="mt-1 text-sm font-medium text-body">{children}</dd>
    </div>
  )
}

export default function CampaignDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const toast = useToast()

  const [campaign, setCampaign] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [editing, setEditing] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const [form, setForm] = useState(null)

  const library = useCampaignAssets(id)

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
            campaignType: row.campaignType,
            objective: row.objective,
            platforms: row.platforms,
            status: row.status,
            brief: row.brief || '',
            tone: row.tone || '',
            audience: row.audience || '',
          })
        }
      })
      .catch((e) => !cancelled && toast.error(e?.message || 'Could not load the campaign.'))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [id]) // eslint-disable-line react-hooks/exhaustive-deps

  // The campaign's own creative count lives on the row, but it was written by
  // the server when an asset was last saved. The library on this page is the
  // fresher truth, so the header counts what is actually loaded.
  const creativeCount = library.loading ? campaign?.creatives ?? 0 : library.counts.total

  const dirty =
    form &&
    campaign &&
    (form.name !== campaign.name ||
      form.campaignType !== campaign.campaignType ||
      form.objective !== campaign.objective ||
      form.status !== campaign.status ||
      form.brief !== (campaign.brief || '') ||
      form.tone !== (campaign.tone || '') ||
      form.audience !== (campaign.audience || '') ||
      form.platforms.join(',') !== campaign.platforms.join(','))

  async function save() {
    setSaving(true)
    try {
      const next = await campaignStore.update(id, form)
      setCampaign(next)
      // Tools cache the campaign so moving between them does not refetch it.
      // An edit here makes every cached copy stale, including the one a tool
      // may be about to generate from.
      forgetCampaign(id)
      setEditing(false)
      toast.success('Campaign saved.')
    } catch (err) {
      toast.error(err?.message || 'Could not save.')
    } finally {
      setSaving(false)
    }
  }

  function cancelEdit() {
    setForm({
      name: campaign.name,
      campaignType: campaign.campaignType,
      objective: campaign.objective,
      platforms: campaign.platforms,
      status: campaign.status,
      brief: campaign.brief || '',
      tone: campaign.tone || '',
      audience: campaign.audience || '',
    })
    setEditing(false)
  }

  async function remove() {
    try {
      await campaignStore.remove(id)
      forgetCampaign(id)
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

  const type = campaignType(campaign.campaignType)

  // Every tool that makes something, minus the ones this campaign type has no
  // use for and the ones blocked on an integration the user does not have.
  const creationTools = [
    ...toolsInCategory('create'),
    ...toolsInCategory('video'),
    ...toolsInCategory('tools'),
  ].filter((tool) => !tool.blocked && toolAppliesTo(tool.slug, campaign.campaignType))

  return (
    <div className="mx-auto max-w-5xl space-y-6 pb-4">
      <AdsPageHeader
        title={campaign.name}
        description={type.description}
        backLabel="AI Ads Studio"
        actions={<CampaignStatusBadge status={campaign.status} />}
      />

      {/* ---- 1. What this campaign is ----------------------------------- */}
      <div className="card p-5">
        {editing ? (
          <div className="space-y-5">
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

            <div>
              <span className="label">Campaign type</span>
              <p className="-mt-1 mb-2 text-xs text-muted">
                Changing this changes which tools this campaign offers and what they
                generate. Assets already made are kept.
              </p>
              <CampaignTypeSelect
                value={form.campaignType}
                onChange={(v) => setForm({ ...form, campaignType: v })}
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
                placeholder={`What is this campaign about? e.g. ${type.subjectPlaceholder}`}
              />
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
              <div>
                <label htmlFor="cmp-audience" className="label">
                  Audience
                </label>
                <input
                  id="cmp-audience"
                  className="input"
                  value={form.audience}
                  onChange={(e) => setForm({ ...form, audience: e.target.value })}
                  placeholder="Women 25–40 who buy natural skincare"
                />
              </div>
              <div>
                <span className="label">Tone</span>
                <select
                  className="select"
                  value={form.tone || ''}
                  onChange={(e) => setForm({ ...form, tone: e.target.value })}
                  aria-label="Tone"
                >
                  <option value="">Not set</option>
                  {COPY_TONES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </div>
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
              <button type="button" onClick={cancelEdit} className="btn btn-secondary">
                Cancel
              </button>

              {confirmDelete ? (
                <>
                  <button
                    type="button"
                    onClick={remove}
                    className="btn btn-danger ml-auto"
                  >
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
                  Delete campaign
                </button>
              )}
            </div>
          </div>
        ) : (
          <>
            <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-sm font-semibold text-body">Campaign details</h2>
              <button
                type="button"
                onClick={() => setEditing(true)}
                className="btn btn-secondary btn-sm"
              >
                Edit details
              </button>
            </div>

            <dl className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              <Fact label="Campaign type">{campaign.campaignType}</Fact>
              <Fact label="Objective">{campaign.objective}</Fact>
              <Fact label="Platforms">
                {campaign.platforms.length ? (
                  <span className="flex flex-wrap items-center gap-1.5">
                    {campaign.platforms.map((p) => (
                      <PlatformIcon key={p} platform={p} size={22} />
                    ))}
                    <span className="sr-only">
                      {campaign.platforms.map((p) => PLATFORMS[p]?.label || p).join(', ')}
                    </span>
                  </span>
                ) : (
                  '—'
                )}
              </Fact>
              <Fact label="Status">
                <CampaignStatusBadge status={campaign.status} />
              </Fact>
              <Fact label="Created">{formatDateTime(campaign.createdAt)}</Fact>
              <Fact label="Creatives">{creativeCount}</Fact>
              <Fact label="Audience">{campaign.audience || 'Not set'}</Fact>
              <Fact label="Tone">{campaign.tone || 'Not set'}</Fact>
            </dl>

            <div className="mt-5 border-t border-line pt-4">
              <dt className="text-[11px] font-semibold uppercase tracking-wide text-muted">
                Brief
              </dt>
              <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-body">
                {campaign.brief || (
                  <span className="text-muted">
                    No brief yet. The generators read this — adding one is the single
                    biggest improvement you can make to what they produce.
                  </span>
                )}
              </p>
            </div>
          </>
        )}
      </div>

      {/* ---- 2. What it contains ---------------------------------------- */}
      <section aria-labelledby="cmp-overview">
        <h2 id="cmp-overview" className="mb-3 font-semibold text-body">
          Overview
        </h2>
        <CampaignOverview
          counts={library.counts}
          assets={library.assets}
          loading={library.loading}
        />
      </section>

      {/* ---- 3. What it has produced ------------------------------------ */}
      <section aria-labelledby="cmp-assets">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <h2 id="cmp-assets" className="font-semibold text-body">
            Campaign assets
          </h2>
          <p className="text-xs text-muted">
            Everything the tools generate is saved here automatically.
          </p>
        </div>

        <div className="card p-4">
          <CampaignLibrary
            assets={library.assets}
            campaignId={campaign.id}
            loading={library.loading}
            error={library.error}
            onRename={library.rename}
            onEditBody={library.editBody}
            onDuplicate={library.duplicate}
            onDelete={library.remove}
          />
        </div>
      </section>

      {/* ---- 4. What to make next --------------------------------------- *
       * Every link carries the campaign id, which is what makes the tool on
       * the other end open already knowing the brief, the type, the platforms
       * and the tone — and what sends its Back button here rather than to the
       * Studio home.                                                        */}
      <section aria-labelledby="cmp-create">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <h2 id="cmp-create" className="font-semibold text-body">
            Create a creative
          </h2>
          <p className="text-xs text-muted">
            Each tool opens with this campaign loaded — none of them will ask you for it
            again.
          </p>
        </div>

        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
          {creationTools.map((tool) => (
            <Link
              key={tool.slug}
              to={campaignToolPath(tool.slug, campaign.id)}
              className="panel p-3 transition-colors hover:border-accent-line hover:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-page"
            >
              <span className="block text-sm font-semibold text-body">{tool.name}</span>
              <span className="mt-1 block text-xs leading-relaxed text-muted">
                {tool.description}
              </span>
            </Link>
          ))}
        </div>
      </section>

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
    </div>
  )
}
