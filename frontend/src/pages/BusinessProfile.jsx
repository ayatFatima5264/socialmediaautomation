import { useEffect, useMemo, useRef, useState } from 'react'
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
import BrandKitFields from '../components/brand/BrandKitFields.jsx'
import HelpTip from '../components/HelpTip.jsx'
import { profileCompletion } from '../lib/businessProfile'
import { invalidateBrandKit } from '../hooks/useBrandKit'

// ---------------------------------------------------------------------------
// Settings → Business Profile. Edit every onboarding answer at any time. Uses
// the same options + ChipSelect as the wizard so the two stay consistent.
//
// Laid out as a form column plus a sticky summary rail. The form was
// previously a single narrow card that left most of the screen empty on
// desktop while the Save button sat below the fold — you had to scroll past
// six field groups to find out whether your edit had been kept.
// ---------------------------------------------------------------------------

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
  // Brand Kit — overlaid on generated images.
  logo_url: null,
  brand_colors: [],
  phone: '',
  email: '',
  address: '',
}

const DESCRIPTION_MAX = 600

// Map a stored string onto a chip choice (+ "Other" free text) pair.
function toChoice(value, options) {
  if (!value) return ['', '']
  return options.includes(value) ? [value, ''] : ['Other', value]
}

// Collapse the form's split "choice + other" fields back to the canonical API
// shape. Used for saving and for measuring completeness, so both agree.
function toPayload(form) {
  const industry = form.industry === 'Other' ? form.industry_other.trim() : form.industry
  const target_audience =
    form.audience_choice === 'Other' ? form.audience_other.trim() : form.audience_choice
  return {
    business_name: form.business_name.trim() || null,
    industry: industry || null,
    business_description: form.business_description.trim() || null,
    target_audience: target_audience || null,
    brand_voice: form.brand_voice,
    business_goals: form.business_goals,
    website: form.website.trim() || null,
    logo_url: form.logo_url || null,
    brand_colors: form.brand_colors || [],
    phone: (form.phone || '').trim() || null,
    email: (form.email || '').trim() || null,
    address: (form.address || '').trim() || null,
  }
}

// A titled group of related fields.
function Card({ title, description, children }) {
  return (
    <section className="card p-4 md:p-5">
      <h2 className="text-sm font-bold">{title}</h2>
      {description && <p className="mt-0.5 text-xs text-muted">{description}</p>}
      <div className="mt-3 space-y-3">{children}</div>
    </section>
  )
}

function Field({ label, hint, children }) {
  return (
    <div>
      <label className="label mb-2 flex items-center justify-between gap-3">
        <span>{label}</span>
        {hint && <span className="text-xs font-normal text-muted">{hint}</span>}
      </label>
      {children}
    </div>
  )
}

export default function BusinessProfile() {
  const toast = useToast()
  const [form, setForm] = useState(BLANK)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  // Snapshot of what's on the server, so Save can be disabled when nothing
  // has actually changed rather than inviting a pointless request.
  const saved = useRef(BLANK)

  const set = (patch) => setForm((f) => ({ ...f, ...patch }))

  useEffect(() => {
    api
      .getBusinessProfile()
      .then((p) => {
        const [industry, industry_other] = toChoice(p.industry, INDUSTRIES)
        const [audience_choice, audience_other] = toChoice(p.target_audience, TARGET_AUDIENCES)
        const next = {
          business_name: p.business_name || '',
          industry,
          industry_other,
          business_description: p.business_description || '',
          audience_choice,
          audience_other,
          brand_voice: p.brand_voice || [],
          business_goals: p.business_goals || [],
          website: p.website || '',
          logo_url: p.logo_url || null,
          brand_colors: p.brand_colors || [],
          phone: p.phone || '',
          email: p.email || '',
          address: p.address || '',
        }
        saved.current = next
        setForm(next)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const payload = useMemo(() => toPayload(form), [form])
  const { filled, total, complete, missing } = useMemo(
    () => profileCompletion(payload),
    [payload],
  )
  const dirty = useMemo(
    () => JSON.stringify(form) !== JSON.stringify(saved.current),
    [form],
  )

  async function save() {
    setSaving(true)
    try {
      await api.updateBusinessProfile(payload)
      saved.current = form
      // The Brand Kit is cached for the Generator's overlay — drop it so the
      // next generated image picks up the logo/colours just saved.
      invalidateBrandKit()
      toast.success('Business profile saved')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not save')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="mx-auto -mt-1 max-w-7xl md:-mt-3">
        <div className="skeleton h-6 w-72" />
        <div className="mt-3 grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="space-y-3">
            <div className="skeleton h-64 rounded-xl" />
            <div className="skeleton h-48 rounded-xl" />
            <div className="skeleton h-56 rounded-xl" />
          </div>
          <div className="skeleton hidden h-72 rounded-xl lg:block" />
        </div>
      </div>
    )
  }

  // Save and Back travel together. The header link alone was easy to miss once
  // you had scrolled down the form — the point you most want to leave is right
  // after saving, which is exactly where the header is off screen.
  const actions = (
    <div className="space-y-2">
      <button
        onClick={save}
        disabled={saving || !dirty}
        className="btn btn-primary w-full"
        title={dirty ? undefined : 'No changes to save'}
      >
        {saving ? 'Saving…' : dirty ? 'Save changes' : 'Saved'}
      </button>
      <Link to="/settings" className="btn btn-secondary w-full">
        ← Back to Settings
      </Link>
    </div>
  )

  return (
    <div className="mx-auto -mt-1 max-w-7xl pb-4 md:-mt-3">
      {/* Backlink, title and the explanation all on one line — the paragraph
          version pushed the first field a third of the way down the screen. */}
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Link to="/settings" className="text-sm text-muted transition hover:text-body">
          ← Settings
        </Link>
        <h1 className="flex items-center gap-2 text-lg font-bold">
          Business Profile
          <HelpTip label="About the Business Profile">
            Everything here is context the AI writes with. The more specific you are, the less
            editing you'll do later. Every field is optional.
          </HelpTip>
        </h1>
      </header>

      <div className="mt-3 grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
        {/* ---- Form column -------------------------------------------- */}
        <div className="min-w-0 space-y-3">
          <Card title="The basics" description="Who you are and where to find you.">
            <div className="grid gap-3 sm:grid-cols-2">
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
                  className="select"
                  value={form.industry}
                  onChange={(e) => set({ industry: e.target.value })}
                >
                  <option value="">Select an industry…</option>
                  {INDUSTRIES.map((i) => (
                    <option key={i} value={i}>
                      {i}
                    </option>
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
            </div>

            <Field label="Website" hint="Optional">
              <input
                className="input"
                type="url"
                inputMode="url"
                placeholder="https://example.com"
                value={form.website}
                onChange={(e) => set({ website: e.target.value })}
              />
            </Field>
          </Card>

          <Card
            title="What you do"
            description="The single most useful field — it shapes almost every generated post."
          >
            <Field
              label="Business Description"
              hint={`${form.business_description.length}/${DESCRIPTION_MAX}`}
            >
              <textarea
                className="input min-h-32 resize-y"
                maxLength={DESCRIPTION_MAX}
                placeholder="What does your business do, and what makes it different from the obvious alternative?"
                value={form.business_description}
                onChange={(e) => set({ business_description: e.target.value })}
              />
            </Field>
          </Card>

          <Card title="Who you're talking to" description="Content is written for this reader.">
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
          </Card>

          <Card
            title="How you sound"
            description="Tone and intent — these steer wording and the call to action."
          >
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
          </Card>

          <Card
            title="Brand Kit"
            description="Overlaid on generated images as sharp, editable layers — and used to steer the AI's colour palette."
          >
            <BrandKitFields value={form} onChange={set} />
          </Card>

          {/* On small screens the rail stacks below, so this is the natural
              end-of-form action. Hidden on desktop where the rail is sticky. */}
          <div className="lg:hidden">{actions}</div>
        </div>

        {/* ---- Summary rail -------------------------------------------- */}
        <aside className="hidden lg:block">
          <div className="sticky top-0 space-y-3">
            <section className="card p-4">
              <div className="flex items-baseline justify-between gap-3">
                <h2 className="text-sm font-bold">Profile strength</h2>
                <span className="text-xs font-semibold text-muted">
                  {filled}/{total}
                </span>
              </div>

              <div className="mt-3 h-2 overflow-hidden rounded-full bg-inset">
                <div
                  className="h-full rounded-full bg-accent transition-[width] duration-500"
                  style={{ width: `${(filled / total) * 100}%` }}
                />
              </div>

              {complete ? (
                <p className="mt-3 text-sm text-muted">
                  Everything the AI needs is filled in. Refining the description is usually
                  what improves results next.
                </p>
              ) : (
                <>
                  <p className="mt-3 text-sm text-muted">Still missing:</p>
                  <ul className="mt-2 space-y-1.5">
                    {missing.map((m) => (
                      <li key={m} className="flex items-center gap-2 text-sm text-muted">
                        <span
                          aria-hidden="true"
                          className="h-1.5 w-1.5 shrink-0 rounded-full border border-muted"
                        />
                        {m}
                      </li>
                    ))}
                  </ul>
                </>
              )}

              <div className="mt-5">{actions}</div>
              {dirty && (
                <p className="mt-2 text-center text-xs text-muted">You have unsaved changes</p>
              )}
            </section>

            <section className="card p-4">
              <h2 className="text-sm font-bold">How this gets used</h2>
              <dl className="mt-3 space-y-3 text-sm">
                {[
                  ['Description', 'Supplies the facts and framing behind every post.'],
                  ['Audience', 'Sets reading level, examples, and what counts as a benefit.'],
                  ['Brand voice', 'Controls wording, formality, and sentence rhythm.'],
                  ['Goals', 'Decides the call to action each post ends on.'],
                ].map(([term, detail]) => (
                  <div key={term}>
                    <dt className="font-semibold text-body">{term}</dt>
                    <dd className="mt-0.5 leading-relaxed text-muted">{detail}</dd>
                  </div>
                ))}
              </dl>
            </section>
          </div>
        </aside>
      </div>
    </div>
  )
}
