import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  INDUSTRIES,
  TARGET_AUDIENCES,
  BRAND_VOICES,
  BUSINESS_GOALS,
} from '../lib/constants'
import { useAuth } from '../context/AuthContext.jsx'
import { useToast } from '../context/ToastContext.jsx'
import { api, ApiError } from '../lib/api'
import ChipSelect from '../components/ChipSelect.jsx'

// Business Onboarding Wizard — shown once to new users. Welcome → 5 questions →
// completion. Every question can be skipped; whatever's filled is saved and the
// rest is left empty. No content is generated here — the profile is only saved.
const TOTAL_QUESTION_STEPS = 5

export default function Onboarding() {
  const navigate = useNavigate()
  const toast = useToast()
  const { updateUser } = useAuth()

  const [step, setStep] = useState(0) // 0 welcome, 1-5 questions, 6 completion
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    business_name: '',
    industry: '',
    industry_other: '',
    business_description: '',
    audience_choice: '',
    audience_other: '',
    brand_voice: [],
    business_goals: [],
    website: '',
  })

  const set = (patch) => setForm((f) => ({ ...f, ...patch }))

  function buildPayload() {
    const industry =
      form.industry === 'Other' ? form.industry_other.trim() : form.industry
    const target_audience =
      form.audience_choice === 'Other'
        ? form.audience_other.trim()
        : form.audience_choice
    return {
      business_name: form.business_name.trim() || null,
      industry: industry || null,
      business_description: form.business_description.trim() || null,
      target_audience: target_audience || null,
      brand_voice: form.brand_voice,
      business_goals: form.business_goals,
      website: form.website.trim() || null,
    }
  }

  async function finish() {
    setSaving(true)
    try {
      await api.updateBusinessProfile(buildPayload())
      await api.completeOnboarding()
      updateUser({ onboarding_completed: true })
      setStep(6) // completion screen
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not save profile')
    } finally {
      setSaving(false)
    }
  }

  // ---- Welcome ----------------------------------------------------------
  if (step === 0) {
    return (
      <Shell>
        <div className="text-center">
          <div className="mx-auto mb-5 grid h-16 w-16 place-items-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-500 text-3xl">
            ✦
          </div>
          <h1 className="text-2xl font-bold">Welcome to AutoSocial AI</h1>
          <p className="mx-auto mt-3 max-w-md text-slate-500 dark:text-slate-400">
            Let's personalize your AI experience so we can generate content that
            better matches your business.
          </p>
          <p className="mt-2 text-sm text-slate-400">This setup takes less than 2 minutes.</p>
          <button onClick={() => setStep(1)} className="btn btn-primary mt-8 w-full sm:w-auto sm:px-10">
            Get Started
          </button>
        </div>
      </Shell>
    )
  }

  // ---- Completion -------------------------------------------------------
  if (step === 6) {
    return (
      <Shell>
        <div className="text-center">
          <div className="mb-4 text-5xl">🎉</div>
          <h1 className="text-2xl font-bold">You're all set!</h1>
          <p className="mx-auto mt-3 max-w-md text-slate-500 dark:text-slate-400">
            Your business profile has been saved. AutoSocial AI will use this
            information to generate more personalized content.
          </p>
          <button onClick={() => navigate('/dashboard')} className="btn btn-primary mt-8 w-full sm:w-auto sm:px-10">
            Go to Dashboard
          </button>
        </div>
      </Shell>
    )
  }

  // ---- Question steps ---------------------------------------------------
  const isLast = step === TOTAL_QUESTION_STEPS
  const steps = {
    1: {
      title: 'Business Information',
      body: (
        <div className="space-y-4">
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
        </div>
      ),
    },
    2: {
      title: 'Target Audience',
      body: (
        <Field label="Who is your target audience?">
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
      ),
    },
    3: {
      title: 'Brand Voice',
      body: (
        <Field label="How should AutoSocial AI write for your brand?" hint="Select all that apply">
          <ChipSelect
            multi
            options={BRAND_VOICES}
            value={form.brand_voice}
            onChange={(v) => set({ brand_voice: v })}
          />
        </Field>
      ),
    },
    4: {
      title: 'Business Goals',
      body: (
        <Field label="What do you want to achieve with your social media?" hint="Select all that apply">
          <ChipSelect
            multi
            options={BUSINESS_GOALS}
            value={form.business_goals}
            onChange={(v) => set({ business_goals: v })}
          />
        </Field>
      ),
    },
    5: {
      title: 'Website',
      body: (
        <Field label="Do you have a website?" hint="Optional">
          <input
            className="input"
            placeholder="https://example.com"
            value={form.website}
            onChange={(e) => set({ website: e.target.value })}
          />
        </Field>
      ),
    },
  }

  const current = steps[step]

  return (
    <Shell>
      <ProgressBar step={step} total={TOTAL_QUESTION_STEPS} />
      <h2 className="mb-1 text-xl font-bold">{current.title}</h2>
      <p className="mb-5 text-sm text-slate-400">
        Step {step} of {TOTAL_QUESTION_STEPS}
      </p>

      <div className="min-h-[12rem]">{current.body}</div>

      <div className="mt-8 flex items-center gap-2">
        <button onClick={() => setStep(step - 1)} className="btn btn-ghost">
          Previous
        </button>
        <div className="ml-auto flex gap-2">
          <button onClick={() => setStep(step + 1)} className="btn btn-ghost">
            Skip
          </button>
          {isLast ? (
            <button onClick={finish} disabled={saving} className="btn btn-primary px-6">
              {saving ? 'Saving…' : 'Finish'}
            </button>
          ) : (
            <button onClick={() => setStep(step + 1)} className="btn btn-primary px-6">
              Next
            </button>
          )}
        </div>
      </div>
    </Shell>
  )
}

function Shell({ children }) {
  return (
    <div className="app-bg grid min-h-screen place-items-center p-4">
      <div className="card w-full max-w-xl p-8">{children}</div>
    </div>
  )
}

function ProgressBar({ step, total }) {
  const pct = Math.round((step / total) * 100)
  return (
    <div className="mb-6 h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-white/10">
      <div
        className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-300"
        style={{ width: `${pct}%` }}
      />
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
