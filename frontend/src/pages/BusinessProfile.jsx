import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  INDUSTRIES,
  TARGET_AUDIENCES,
  BRAND_VOICES,
  BUSINESS_GOALS,
} from '../lib/constants'
import { useToast } from '../context/ToastContext.jsx'
import { api, ApiError } from '../lib/api'
import ChipSelect from '../components/ChipSelect.jsx'

// Settings → Business Profile. Edit every onboarding answer at any time. Uses
// the same options + ChipSelect as the wizard so the two stay consistent.
const BLANK = {
  business_name: '',
  industry: '',
  industry_other: '',
  business_description: '',
  audience_choice: '',
  audience_other: '',
  brand_voice: [],
  business_goals: [],
  website: '',
}

// Map a stored string onto a chip choice (+ "Other" free text) pair.
function toChoice(value, options) {
  if (!value) return ['', '']
  return options.includes(value) ? [value, ''] : ['Other', value]
}

export default function BusinessProfile() {
  const toast = useToast()
  const [form, setForm] = useState(BLANK)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const set = (patch) => setForm((f) => ({ ...f, ...patch }))

  useEffect(() => {
    api
      .getBusinessProfile()
      .then((p) => {
        const [industry, industry_other] = toChoice(p.industry, INDUSTRIES)
        const [audience_choice, audience_other] = toChoice(
          p.target_audience,
          TARGET_AUDIENCES,
        )
        setForm({
          business_name: p.business_name || '',
          industry,
          industry_other,
          business_description: p.business_description || '',
          audience_choice,
          audience_other,
          brand_voice: p.brand_voice || [],
          business_goals: p.business_goals || [],
          website: p.website || '',
        })
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  async function save() {
    setSaving(true)
    try {
      const industry =
        form.industry === 'Other' ? form.industry_other.trim() : form.industry
      const target_audience =
        form.audience_choice === 'Other'
          ? form.audience_other.trim()
          : form.audience_choice
      await api.updateBusinessProfile({
        business_name: form.business_name.trim() || null,
        industry: industry || null,
        business_description: form.business_description.trim() || null,
        target_audience: target_audience || null,
        brand_voice: form.brand_voice,
        business_goals: form.business_goals,
        website: form.website.trim() || null,
      })
      toast.success('Business profile saved')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not save')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="skeleton h-96 max-w-2xl rounded-2xl" />
  }

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <Link to="/settings" className="text-sm text-slate-400 hover:text-slate-200">
          ← Settings
        </Link>
        <h1 className="mt-1 text-2xl font-bold">Business Profile</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          AutoSocial AI uses this to generate more relevant, on-brand content.
          Every field is optional.
        </p>
      </div>

      <section className="card space-y-4 p-5">
        <Field label="Business Name">
          <input
            className="input"
            placeholder="e.g. Croyten"
            value={form.business_name}
            onChange={(e) => set({ business_name: e.target.value })}
          />
        </Field>

        <Field label="Industry">
          <select
            className="input"
            value={form.industry}
            onChange={(e) => set({ industry: e.target.value })}
          >
            <option value="">Select an industry…</option>
            {INDUSTRIES.map((i) => (
              <option key={i} value={i}>{i}</option>
            ))}
          </select>
          {form.industry === 'Other' && (
            <input
              className="input mt-2"
              placeholder="Your industry"
              value={form.industry_other}
              onChange={(e) => set({ industry_other: e.target.value })}
            />
          )}
        </Field>

        <Field label="Business Description">
          <textarea
            className="input min-h-24"
            placeholder="What does your business do?"
            value={form.business_description}
            onChange={(e) => set({ business_description: e.target.value })}
          />
        </Field>

        <Field label="Target Audience">
          <ChipSelect
            options={TARGET_AUDIENCES}
            value={form.audience_choice}
            onChange={(v) => set({ audience_choice: v })}
          />
          {form.audience_choice === 'Other' && (
            <input
              className="input mt-3"
              placeholder="Describe your audience"
              value={form.audience_other}
              onChange={(e) => set({ audience_other: e.target.value })}
            />
          )}
        </Field>

        <Field label="Brand Voice" hint="Select all that apply">
          <ChipSelect
            multi
            options={BRAND_VOICES}
            value={form.brand_voice}
            onChange={(v) => set({ brand_voice: v })}
          />
        </Field>

        <Field label="Business Goals" hint="Select all that apply">
          <ChipSelect
            multi
            options={BUSINESS_GOALS}
            value={form.business_goals}
            onChange={(v) => set({ business_goals: v })}
          />
        </Field>

        <Field label="Website" hint="Optional">
          <input
            className="input"
            placeholder="https://example.com"
            value={form.website}
            onChange={(e) => set({ website: e.target.value })}
          />
        </Field>
      </section>

      <button onClick={save} disabled={saving} className="btn btn-primary">
        {saving ? 'Saving…' : 'Save changes'}
      </button>
    </div>
  )
}

function Field({ label, hint, children }) {
  return (
    <div>
      <label className="label mb-2 flex items-center justify-between">
        <span>{label}</span>
        {hint && <span className="text-xs font-normal text-slate-400">{hint}</span>}
      </label>
      {children}
    </div>
  )
}
