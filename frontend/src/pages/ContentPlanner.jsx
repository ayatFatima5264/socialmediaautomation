import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../lib/api'
import { useToast } from '../context/ToastContext.jsx'
import ChipSelect from '../components/ChipSelect.jsx'
import { PLATFORMS, PLATFORM_KEYS } from '../lib/constants'
import {
  PLANNER_DURATIONS,
  PLANNER_FREQUENCIES,
  PLANNER_CONTENT_TYPES,
  PLANNER_GOALS,
  PLANNER_TIMEZONES,
  CONTENT_TYPE_STYLES,
} from '../lib/constants'

// The wizard's visible steps. "generating" is a transient state shown as part
// of the Generate step.
const STEPS = [
  { key: 'setup', label: 'Preferences' },
  { key: 'strategy', label: 'AI Strategy' },
  { key: 'generate', label: 'Generate' },
  { key: 'review', label: 'Review & Schedule' },
  { key: 'done', label: 'Done' },
]

const DEFAULT_SETUP = {
  duration_days: 7,
  frequency: 'daily',
  posts_per_week: 3,
  platforms: ['linkedin'],
  goals: ['Brand Awareness'],
  content_mix: ['Educational', 'Tips', 'Engagement'],
  user_prompt: '',
}

// ---- helpers --------------------------------------------------------------
const asUtc = (iso) => new Date(iso.endsWith('Z') ? iso : `${iso}Z`)

function formatWhen(iso) {
  if (!iso) return '—'
  return asUtc(iso).toLocaleString(undefined, {
    weekday: 'short', month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit',
  })
}

function toLocalInput(iso) {
  const d = asUtc(iso)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export default function ContentPlanner() {
  const toast = useToast()
  const [mode, setMode] = useState('hub') // hub | setup | strategy | generating | review | done
  const [plan, setPlan] = useState(null)
  const [settings, setSettings] = useState(null)
  const [plans, setPlans] = useState([])
  const [showSettings, setShowSettings] = useState(false)

  const reloadHub = () => {
    api.listPlans().then(setPlans).catch(() => {})
    api.plannerSettings().then(setSettings).catch(() => {})
  }
  useEffect(reloadHub, [])

  async function startQuick() {
    if (!settings?.default_platforms?.length) {
      toast.error('Choose your default platforms in Planner Settings first.')
      setShowSettings(true)
      return
    }
    try {
      const p = await api.quickGenerate()
      setPlan(p)
      setMode('generating')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Quick Generate failed')
    }
  }

  const stepIndex = STEPS.findIndex((s) => s.key === (mode === 'generating' ? 'generate' : mode))

  return (
    <div className="mx-auto max-w-6xl">
      {/* Header */}
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold">
            <span>🗓️</span> AI Content Planner
          </h1>
          <p className="text-sm text-muted">
            Let AI plan, write, and schedule your entire content calendar.
          </p>
        </div>
        <div className="ml-auto flex gap-2">
          {mode !== 'hub' && (
            <button onClick={() => { setPlan(null); setMode('hub'); reloadHub() }} className="btn btn-ghost btn-sm">
              ← Planner home
            </button>
          )}
          <button onClick={() => setShowSettings(true)} className="btn btn-ghost btn-sm">
            ⚙ Settings
          </button>
        </div>
      </div>

      {mode !== 'hub' && <StepRail current={stepIndex} />}

      {mode === 'hub' && (
        <Hub
          plans={plans}
          settings={settings}
          onQuick={startQuick}
          onAdvanced={() => setMode('setup')}
          onOpenPlan={async (id) => {
            try {
              const p = await api.getPlan(id)
              setPlan(p)
              setMode(p.status === 'strategy' ? 'strategy' : p.status === 'generating' ? 'generating' : 'review')
            } catch { toast.error('Could not open plan') }
          }}
          onDeletePlan={async (id) => {
            try { await api.deletePlan(id); toast.success('Plan deleted'); reloadHub() }
            catch { toast.error('Could not delete plan') }
          }}
        />
      )}

      {mode === 'setup' && (
        <SetupStep
          settings={settings}
          onCancel={() => setMode('hub')}
          onCreated={(p) => { setPlan(p); setMode('strategy') }}
        />
      )}

      {mode === 'strategy' && plan && (
        <StrategyStep
          plan={plan}
          setPlan={setPlan}
          onBack={() => setMode('setup')}
          onGenerated={(p) => { setPlan(p); setMode('generating') }}
        />
      )}

      {mode === 'generating' && plan && (
        <GeneratingStep planId={plan.id} onReady={(p) => { setPlan(p); setMode('review') }} />
      )}

      {mode === 'review' && plan && (
        <ReviewStep
          plan={plan}
          setPlan={setPlan}
          onApproved={(p) => { setPlan(p); setMode('done') }}
        />
      )}

      {mode === 'done' && plan && (
        <DoneStep plan={plan} onHome={() => { setPlan(null); setMode('hub'); reloadHub() }} />
      )}

      {showSettings && (
        <SettingsModal
          initial={settings}
          onClose={() => setShowSettings(false)}
          onSaved={(s) => { setSettings(s); setShowSettings(false); toast.success('Planner settings saved') }}
        />
      )}
    </div>
  )
}

// ---- Step rail ------------------------------------------------------------
function StepRail({ current }) {
  return (
    <div className="mb-6 flex items-center gap-2 overflow-x-auto pb-1">
      {STEPS.map((s, i) => {
        const done = i < current
        const active = i === current
        return (
          <div key={s.key} className="flex items-center gap-2">
            <div
              className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-medium transition ${
                active
                  ? 'border-accent bg-accent-soft text-accent'
                  : done
                    ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-300'
                    : 'border-line text-muted'
              }`}
            >
              <span className={`grid h-5 w-5 place-items-center rounded-full text-xs ${
                active ? 'bg-accent text-accent-contrast' : done ? 'bg-emerald-500 text-white' : 'bg-inset text-muted'
              }`}>
                {done ? '✓' : i + 1}
              </span>
              <span className="whitespace-nowrap">{s.label}</span>
            </div>
            {i < STEPS.length - 1 && <span className="text-muted">—</span>}
          </div>
        )
      })}
    </div>
  )
}

// ---- Hub ------------------------------------------------------------------
function Hub({ plans, settings, onQuick, onAdvanced, onOpenPlan, onDeletePlan }) {
  const hasDefaults = settings?.default_platforms?.length > 0
  return (
    <div className="space-y-8">
      <div className="grid gap-5 md:grid-cols-2">
        <button
          onClick={onQuick}
          className="card group p-7 text-left transition hover:-translate-y-0.5 hover:border-accent"
        >
          <div className="mb-3 grid h-12 w-12 place-items-center rounded-xl bg-accent text-2xl text-accent-contrast">⚡</div>
          <h2 className="text-lg font-bold">Quick Generate</h2>
          <p className="mt-1 text-sm text-muted">
            One click. Uses your saved settings to instantly plan, write, and
            schedule your next batch of content.
          </p>
          <span className="mt-4 inline-block text-sm font-semibold text-accent">
            {hasDefaults ? 'Generate now →' : 'Set defaults to enable →'}
          </span>
        </button>

        <button
          onClick={onAdvanced}
          className="card group p-7 text-left transition hover:-translate-y-0.5 hover:border-accent"
        >
          <div className="mb-3 grid h-12 w-12 place-items-center rounded-xl bg-inset text-2xl text-body">🎛️</div>
          <h2 className="text-lg font-bold">Advanced Planner</h2>
          <p className="mt-1 text-sm text-muted">
            Open the full wizard to customize duration, frequency, platforms,
            goals, and content mix before AI builds your calendar.
          </p>
          <span className="mt-4 inline-block text-sm font-semibold text-accent">
            Open wizard →
          </span>
        </button>
      </div>

      <div>
        <h3 className="mb-3 text-sm font-semibold text-muted">
          Your plans
        </h3>
        {plans.length === 0 ? (
          <div className="card p-8 text-center text-sm text-muted">
            No plans yet. Start with Quick Generate or the Advanced Planner above.
          </div>
        ) : (
          <div className="space-y-2">
            {plans.map((p) => (
              <div key={p.id} className="card flex items-center gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-semibold">{p.name}</span>
                    <PlanStatusBadge status={p.status} />
                  </div>
                  <div className="mt-0.5 text-xs text-muted">
                    {p.duration_days} days · {p.platforms.join(', ')} · {p.total_posts || 0} posts
                  </div>
                </div>
                <button onClick={() => onOpenPlan(p.id)} className="btn btn-ghost btn-sm">Open</button>
                <button onClick={() => onDeletePlan(p.id)} className="btn btn-sm text-rose-500 hover:text-rose-400">Delete</button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function PlanStatusBadge({ status }) {
  const map = {
    strategy: 'bg-slate-500/15 text-slate-500 dark:text-slate-300',
    generating: 'bg-sky-500/15 text-sky-600 dark:text-sky-300',
    ready: 'bg-amber-500/15 text-amber-600 dark:text-amber-300',
    scheduled: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-300',
    failed: 'bg-rose-500/15 text-rose-600 dark:text-rose-300',
  }
  const label = { strategy: 'Draft', generating: 'Generating', ready: 'Ready to review', scheduled: 'Scheduled', failed: 'Failed' }
  return <span className={`badge ${map[status] || map.strategy}`}>{label[status] || status}</span>
}

// ---- Step 1: Setup --------------------------------------------------------
function SetupStep({ settings, onCancel, onCreated }) {
  const toast = useToast()
  const [form, setForm] = useState(() => ({
    ...DEFAULT_SETUP,
    duration_days: settings?.default_duration_days ?? DEFAULT_SETUP.duration_days,
    frequency: settings?.default_frequency ?? DEFAULT_SETUP.frequency,
    posts_per_week: settings?.default_posts_per_week ?? DEFAULT_SETUP.posts_per_week,
    platforms: settings?.default_platforms?.length ? settings.default_platforms : DEFAULT_SETUP.platforms,
    goals: settings?.default_goals?.length ? settings.default_goals : DEFAULT_SETUP.goals,
    content_mix: settings?.default_content_mix?.length ? settings.default_content_mix : DEFAULT_SETUP.content_mix,
  }))
  const [busy, setBusy] = useState(false)
  const set = (patch) => setForm((f) => ({ ...f, ...patch }))
  const togglePlatform = (k) =>
    set({ platforms: form.platforms.includes(k) ? form.platforms.filter((p) => p !== k) : [...form.platforms, k] })

  async function submit() {
    if (!form.platforms.length) { toast.error('Select at least one platform'); return }
    setBusy(true)
    try {
      const plan = await api.createStrategy({
        duration_days: form.duration_days,
        frequency: form.frequency,
        posts_per_week: form.posts_per_week,
        platforms: form.platforms,
        goals: form.goals,
        content_mix: form.content_mix,
        user_prompt: form.user_prompt || null,
      })
      onCreated(plan)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not build strategy')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="space-y-6 lg:col-span-2">
        <Section title="Planning period" hint="How far ahead should AI plan?">
          <div className="grid gap-3 sm:grid-cols-3">
            {PLANNER_DURATIONS.map((d) => (
              <SelectCard key={d.value} active={form.duration_days === d.value} onClick={() => set({ duration_days: d.value })} title={d.label} hint={d.hint} />
            ))}
          </div>
        </Section>

        <Section title="Posting frequency" hint="How often do you want to post?">
          <div className="grid gap-3 sm:grid-cols-4">
            {PLANNER_FREQUENCIES.map((f) => (
              <SelectCard key={f.value} active={form.frequency === f.value} onClick={() => set({ frequency: f.value })} title={f.label} hint={f.hint} />
            ))}
          </div>
          {form.frequency === 'custom' && (
            <div className="mt-3 flex items-center gap-3">
              <label className="text-sm text-muted">Posts per week</label>
              <input type="number" min={1} max={7} value={form.posts_per_week}
                onChange={(e) => set({ posts_per_week: Math.max(1, Math.min(7, Number(e.target.value) || 1)) })}
                className="input w-24" />
            </div>
          )}
        </Section>

        <Section title="Platforms" hint="Where should this content go?">
          <div className="flex flex-wrap gap-2">
            {PLATFORM_KEYS.map((k) => {
              const on = form.platforms.includes(k)
              return (
                <button key={k} type="button" onClick={() => togglePlatform(k)}
                  className={`badge border px-3 py-1.5 transition ${on ? 'border-accent bg-accent-soft text-accent' : 'border-line text-muted'}`}>
                  <span className="grid h-5 w-5 place-items-center rounded-full text-[10px] font-bold text-white" style={{ background: PLATFORMS[k].color }}>{PLATFORMS[k].initial}</span>
                  {PLATFORMS[k].label}
                </button>
              )
            })}
          </div>
        </Section>

        <Section title="Content goals" hint="What should this content achieve?">
          <ChipSelect multi options={PLANNER_GOALS} value={form.goals} onChange={(v) => set({ goals: v })} />
        </Section>

        <Section title="Preferred content mix" hint="AI balances these across the plan">
          <ChipSelect multi options={PLANNER_CONTENT_TYPES} value={form.content_mix} onChange={(v) => set({ content_mix: v })} />
        </Section>

        <Section title="Extra direction" hint="Optional — anything specific to include?">
          <textarea className="input min-h-20" placeholder="e.g. Focus on our new product launch this month"
            value={form.user_prompt} onChange={(e) => set({ user_prompt: e.target.value })} />
        </Section>
      </div>

      {/* Live summary */}
      <div className="lg:col-span-1">
        <div className="card sticky top-24 p-6">
          <h3 className="text-sm font-semibold text-muted">Plan summary</h3>
          <dl className="mt-4 space-y-3 text-sm">
            <SummaryRow label="Period" value={`${form.duration_days} days`} />
            <SummaryRow label="Frequency" value={PLANNER_FREQUENCIES.find((f) => f.value === form.frequency)?.label} />
            <SummaryRow label="Platforms" value={form.platforms.length ? form.platforms.map((p) => PLATFORMS[p].label).join(', ') : 'None'} />
            <SummaryRow label="Goals" value={form.goals.length ? `${form.goals.length} selected` : 'None'} />
            <SummaryRow label="Content mix" value={form.content_mix.length ? `${form.content_mix.length} types` : 'Balanced'} />
          </dl>
          <div className="mt-6 flex flex-col gap-2">
            <button onClick={submit} disabled={busy} className="btn btn-primary">
              {busy ? 'Building strategy…' : 'Create AI strategy →'}
            </button>
            <button onClick={onCancel} className="btn btn-ghost">Cancel</button>
          </div>
          <p className="mt-3 text-center text-xs text-muted">AI proposes a calendar next — you review before anything is written.</p>
        </div>
      </div>
    </div>
  )
}

// ---- Step 2: Strategy -----------------------------------------------------
function StrategyStep({ plan, setPlan, onBack, onGenerated }) {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [regenId, setRegenId] = useState(null)

  const saveTopics = async (topics) => {
    try {
      const p = await api.updatePlanTopics(plan.id, topics)
      setPlan(p)
    } catch { toast.error('Could not save changes') }
  }

  const editTopic = (id, patch) => {
    const topics = plan.topics.map((t) => (t.id === id ? { ...t, ...patch } : t))
    setPlan({ ...plan, topics })
  }
  const commitTopic = () => saveTopics(plan.topics)
  const deleteTopic = (id) => saveTopics(plan.topics.filter((t) => t.id !== id))
  const addTopic = () => {
    const last = plan.topics[plan.topics.length - 1]
    const d = last ? last.date : new Date().toISOString().slice(0, 10)
    const weekday = new Date(`${d}T00:00:00`).toLocaleDateString(undefined, { weekday: 'long' })
    const topics = [...plan.topics, { id: `new-${Date.now()}`, date: d, weekday, content_type: 'Educational', topic: 'New topic' }]
    saveTopics(topics)
  }
  const regenerate = async (id) => {
    setRegenId(id)
    try {
      const p = await api.regeneratePlanTopic(plan.id, id)
      setPlan(p)
    } catch { toast.error('Could not regenerate topic') }
    finally { setRegenId(null) }
  }

  async function generate() {
    setBusy(true)
    try {
      const p = await api.generatePlan(plan.id)
      onGenerated(p)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not start generation')
      setBusy(false)
    }
  }

  return (
    <div>
      {/* AI Marketing Manager: plan theme + rationale + content mix */}
      <div className="card mb-5 overflow-hidden p-5">
        <div className="text-xs font-semibold uppercase tracking-wide text-accent">
          Your AI content strategy
        </div>
        <h2 className="mt-1 text-xl font-bold">{plan.theme || 'Balanced content plan'}</h2>
        {plan.summary && (
          <p className="mt-2 text-sm text-muted">{plan.summary}</p>
        )}
        <MixBreakdown topics={plan.topics} />
      </div>

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div>
          <h2 className="text-lg font-bold">Content calendar</h2>
          <p className="text-sm text-muted">
            {plan.topics.length} topics · edit, regenerate, or add before AI writes the posts.
          </p>
        </div>
        <button onClick={addTopic} className="btn btn-ghost btn-sm ml-auto">+ Add topic</button>
      </div>

      <div className="space-y-2">
        {plan.topics.map((t) => (
          <div key={t.id} className="card flex flex-wrap items-center gap-3 p-4">
            <div className="w-24 shrink-0 text-sm">
              <div className="font-semibold">{t.weekday}</div>
              <div className="text-xs text-muted">{new Date(`${t.date}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</div>
            </div>
            <select value={t.content_type} onChange={(e) => editTopic(t.id, { content_type: e.target.value })} onBlur={commitTopic}
              className={`badge shrink-0 border-0 ${CONTENT_TYPE_STYLES[t.content_type] || 'bg-slate-500/15 text-slate-500'}`}>
              {PLANNER_CONTENT_TYPES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <input value={t.topic} onChange={(e) => editTopic(t.id, { topic: e.target.value })} onBlur={commitTopic}
              className="input min-w-0 flex-1" />
            <div className="flex shrink-0 gap-1">
              <button onClick={() => regenerate(t.id)} disabled={regenId === t.id} className="btn btn-ghost btn-sm" title="Regenerate this topic">
                {regenId === t.id ? '…' : '↻'}
              </button>
              <button onClick={() => deleteTopic(t.id)} className="btn btn-sm text-rose-500 hover:text-rose-400" title="Delete">✕</button>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-6 flex items-center gap-2">
        <button onClick={onBack} className="btn btn-ghost">← Previous</button>
        <div className="ml-auto flex gap-2">
          <button onClick={generate} disabled={busy || !plan.topics.length} className="btn btn-primary px-6">
            {busy ? 'Starting…' : 'Generate posts →'}
          </button>
        </div>
      </div>
    </div>
  )
}

// Content-type distribution chips — makes the plan feel intentional & balanced.
function MixBreakdown({ topics }) {
  const counts = useMemo(() => {
    const m = new Map()
    topics.forEach((t) => m.set(t.content_type, (m.get(t.content_type) || 0) + 1))
    return [...m.entries()].sort((a, b) => b[1] - a[1])
  }, [topics])
  if (!counts.length) return null
  return (
    <div className="mt-4 flex flex-wrap gap-2">
      {counts.map(([type, n]) => (
        <span key={type} className={`badge ${CONTENT_TYPE_STYLES[type] || 'bg-slate-500/15 text-slate-500'}`}>
          {type}
          <span className="ml-1 rounded-full bg-inset px-1.5 text-[10px] font-bold">{n}</span>
        </span>
      ))}
    </div>
  )
}

// ---- Step 3: Generating (progress) ----------------------------------------
function GeneratingStep({ planId, onReady }) {
  const toast = useToast()
  const [plan, setLocal] = useState(null)
  const done = useRef(false)

  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const p = await api.getPlan(planId)
        if (!alive) return
        setLocal(p)
        if (p.status === 'ready' || p.status === 'scheduled') {
          if (!done.current) { done.current = true; onReady(p) }
          return
        }
        if (p.status === 'failed') { toast.error(p.error || 'Generation failed'); return }
        setTimeout(tick, 1800)
      } catch {
        if (alive) setTimeout(tick, 2500)
      }
    }
    tick()
    return () => { alive = false }
  }, [planId]) // eslint-disable-line react-hooks/exhaustive-deps

  const pct = plan?.total_posts ? Math.round((plan.generated_posts / plan.total_posts) * 100) : 5

  return (
    <div className="grid min-h-[50vh] place-items-center">
      <div className="w-full max-w-md text-center">
        <div className="mx-auto mb-5 grid h-16 w-16 animate-pulse place-items-center rounded-2xl bg-accent text-3xl text-accent-contrast">✦</div>
        <h2 className="text-xl font-bold">Writing your content…</h2>
        <p className="mt-2 text-sm text-muted">
          AI is generating platform-optimized posts for every topic. This can take a moment.
        </p>
        <div className="mt-6 h-2 w-full overflow-hidden rounded-full bg-inset">
          <div className="h-full rounded-full bg-accent transition-all duration-500" style={{ width: `${Math.max(5, pct)}%` }} />
        </div>
        <p className="mt-3 text-sm font-medium">
          {plan ? `${plan.generated_posts} / ${plan.total_posts || '…'} posts` : 'Starting…'}
        </p>
      </div>
    </div>
  )
}

// ---- Step 4/5/6: Review, Schedule, Approve --------------------------------
function ReviewStep({ plan, setPlan, onApproved }) {
  const toast = useToast()
  const [selected, setSelected] = useState(() => new Set())
  const [busy, setBusy] = useState(false)

  const pending = plan.posts.filter((p) => p.approval_status === 'pending')
  const reload = async () => { try { setPlan(await api.getPlan(plan.id)) } catch { /* ignore */ } }

  const toggle = (id) => setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })

  async function approve(all) {
    const ids = all ? [] : [...selected]
    if (!all && !ids.length) { toast.error('Select at least one post'); return }
    setBusy(true)
    try {
      const p = await api.approvePlan(plan.id, all ? { all: true } : { post_ids: ids })
      onApproved(p)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not approve')
    } finally { setBusy(false) }
  }

  const stats = useMemo(() => {
    const platforms = new Set(plan.posts.map((p) => p.platform))
    return { posts: plan.posts.length, platforms: platforms.size, pending: pending.length }
  }, [plan, pending.length])

  // Group posts by calendar day for a calendar-preview feel.
  const groups = useMemo(() => {
    const m = new Map()
    for (const post of plan.posts) {
      const key = post.scheduled_time
        ? asUtc(post.scheduled_time).toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })
        : 'Unscheduled'
      if (!m.has(key)) m.set(key, [])
      m.get(key).push(post)
    }
    return [...m.entries()]
  }, [plan.posts])

  return (
    <div>
      {/* Stat row */}
      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile value={stats.posts} label="Posts" />
        <StatTile value={stats.platforms} label="Platforms" />
        <StatTile value={stats.pending} label="Awaiting approval" />
        <StatTile value={plan.duration_days} label="Days" />
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-bold">Review & schedule</h2>
        <p className="text-sm text-muted">Nothing publishes until you approve.</p>
        <div className="ml-auto flex gap-2">
          <button onClick={() => approve(false)} disabled={busy} className="btn btn-ghost btn-sm">Approve selected ({selected.size})</button>
          <button onClick={() => approve(true)} disabled={busy || !pending.length} className="btn btn-primary btn-sm">
            {busy ? 'Approving…' : 'Approve all'}
          </button>
        </div>
      </div>

      <div className="space-y-6">
        {groups.map(([day, posts]) => (
          <div key={day}>
            <div className="mb-2 flex items-center gap-2">
              <h3 className="text-sm font-bold">{day}</h3>
              <span className="text-xs text-muted">{posts.length} post{posts.length === 1 ? '' : 's'}</span>
              <div className="h-px flex-1 bg-line" />
            </div>
            <div className="space-y-3">
              {posts.map((post) => (
                <PostCard key={post.id} post={post} selected={selected.has(post.id)} onToggle={() => toggle(post.id)} onChanged={reload} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function PostCard({ post, selected, onToggle, onChanged }) {
  const toast = useToast()
  const [editing, setEditing] = useState(false)
  const [content, setContent] = useState(post.content)
  const [busy, setBusy] = useState(false)
  const p = PLATFORMS[post.platform] || { label: post.platform, color: '#64748b', initial: '?' }
  const approved = post.approval_status === 'approved'

  const save = async () => {
    setBusy(true)
    try { await api.updatePlannerPost(post.id, { content }); setEditing(false); onChanged() }
    catch { toast.error('Could not save') } finally { setBusy(false) }
  }
  const regenerate = async () => {
    setBusy(true)
    try { await api.regeneratePlannerPost(post.id); toast.success('Regenerated'); onChanged() }
    catch { toast.error('Could not regenerate') } finally { setBusy(false) }
  }
  const remove = async () => {
    setBusy(true)
    try { await api.deletePlannerPost(post.id); onChanged() }
    catch { toast.error('Could not delete') } finally { setBusy(false) }
  }
  const reschedule = async (value) => {
    if (!value) return
    setBusy(true)
    try { await api.updatePlannerPost(post.id, { scheduled_time: new Date(value).toISOString() }); onChanged() }
    catch (err) { toast.error(err instanceof ApiError ? err.message : 'Could not reschedule') }
    finally { setBusy(false) }
  }

  return (
    <div className={`card p-4 ${selected ? 'ring-2 ring-accent' : ''}`}>
      <div className="flex items-start gap-3">
        <input type="checkbox" checked={selected} onChange={onToggle} className="mt-1 h-4 w-4 accent-accent" disabled={approved} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="badge border border-line">
              <span className="grid h-4 w-4 place-items-center rounded-full text-[9px] font-bold text-white" style={{ background: p.color }}>{p.initial}</span>
              {p.label}
            </span>
            {post.content_type && <span className={`badge ${CONTENT_TYPE_STYLES[post.content_type] || 'bg-slate-500/15 text-slate-500'}`}>{post.content_type}</span>}
            {approved
              ? <span className="badge bg-emerald-500/15 text-emerald-600 dark:text-emerald-300">Approved</span>
              : <span className="badge bg-amber-500/15 text-amber-600 dark:text-amber-300">Pending</span>}
            <span className="ml-auto text-xs text-muted">{post.character_count} chars</span>
          </div>

          {post.topic && <div className="mt-2 text-xs font-medium text-muted">Topic: {post.topic}</div>}

          {editing ? (
            <textarea className="input mt-2 min-h-32" value={content} onChange={(e) => setContent(e.target.value)} />
          ) : (
            <p className="mt-2 whitespace-pre-wrap text-sm text-body">{post.content}</p>
          )}

          {post.hashtags?.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {post.hashtags.map((h) => <span key={h} className="text-xs text-accent">#{h}</span>)}
            </div>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-1.5 text-xs text-muted">
              🕑
              <input type="datetime-local" value={toLocalInput(post.scheduled_time)} onChange={(e) => reschedule(e.target.value)} className="input px-2 py-1 text-xs" disabled={busy} />
            </label>
            <div className="ml-auto flex gap-1">
              {editing ? (
                <>
                  <button onClick={save} disabled={busy} className="btn btn-primary btn-sm">Save</button>
                  <button onClick={() => { setEditing(false); setContent(post.content) }} className="btn btn-ghost btn-sm">Cancel</button>
                </>
              ) : (
                <>
                  <button onClick={() => setEditing(true)} className="btn btn-ghost btn-sm">Edit</button>
                  <button onClick={regenerate} disabled={busy} className="btn btn-ghost btn-sm">↻ Regenerate</button>
                  <button onClick={remove} disabled={busy} className="btn btn-sm text-rose-500 hover:text-rose-400">Delete</button>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ---- Step: Done (success) -------------------------------------------------
function DoneStep({ plan, onHome }) {
  const navigate = useNavigate()
  const scheduled = plan.posts.filter((p) => p.approval_status === 'approved').length
  return (
    <div className="grid min-h-[50vh] place-items-center">
      <div className="w-full max-w-lg text-center">
        <div className="mb-4 text-5xl">🎉</div>
        <h2 className="text-2xl font-bold">Your content calendar is ready</h2>
        <p className="mx-auto mt-2 max-w-sm text-muted">
          {scheduled} post{scheduled === 1 ? '' : 's'} approved and scheduled. AutoSocial AI will publish them at the recommended times.
        </p>
        <div className="mt-6 grid grid-cols-3 gap-3">
          <StatTile value={plan.posts.length} label="Posts created" />
          <StatTile value={scheduled} label="Scheduled" />
          <StatTile value={new Set(plan.posts.map((p) => p.platform)).size} label="Platforms" />
        </div>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <button onClick={() => navigate('/scheduler')} className="btn btn-primary px-6">Go to Calendar</button>
          <button onClick={onHome} className="btn btn-ghost px-6">Back to Planner</button>
        </div>
      </div>
    </div>
  )
}

// ---- Planner Settings modal ----------------------------------------------
function SettingsModal({ initial, onClose, onSaved }) {
  const toast = useToast()
  const [form, setForm] = useState({
    default_duration_days: initial?.default_duration_days ?? 7,
    default_frequency: initial?.default_frequency ?? 'daily',
    default_posts_per_week: initial?.default_posts_per_week ?? 3,
    default_platforms: initial?.default_platforms ?? ['linkedin'],
    default_goals: initial?.default_goals ?? ['Brand Awareness'],
    default_content_mix: initial?.default_content_mix ?? ['Educational', 'Tips', 'Engagement'],
    auto_mode: initial?.auto_mode ?? false,
    timezone: initial?.timezone ?? 'UTC',
  })
  const [busy, setBusy] = useState(false)
  const set = (patch) => setForm((f) => ({ ...f, ...patch }))
  const togglePlatform = (k) =>
    set({ default_platforms: form.default_platforms.includes(k) ? form.default_platforms.filter((p) => p !== k) : [...form.default_platforms, k] })

  async function save() {
    setBusy(true)
    try {
      const s = await api.updatePlannerSettings(form)
      onSaved(s)
    } catch (err) { toast.error(err instanceof ApiError ? err.message : 'Could not save') }
    finally { setBusy(false) }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" onClick={onClose}>
      <div className="card w-full max-w-lg p-6" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center">
          <h2 className="text-lg font-bold">Planner Settings</h2>
          <button onClick={onClose} className="btn btn-ghost btn-sm ml-auto">✕</button>
        </div>
        <p className="mb-4 text-sm text-muted">
          These defaults power Quick Generate and pre-fill the wizard.
        </p>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Default period</label>
              <select className="select" value={form.default_duration_days} onChange={(e) => set({ default_duration_days: Number(e.target.value) })}>
                {PLANNER_DURATIONS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Default frequency</label>
              <select className="select" value={form.default_frequency} onChange={(e) => set({ default_frequency: e.target.value })}>
                {PLANNER_FREQUENCIES.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
              </select>
            </div>
          </div>

          <div>
            <label className="label">Timezone</label>
            <select className="select" value={form.timezone} onChange={(e) => set({ timezone: e.target.value })}>
              {PLANNER_TIMEZONES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>

          <div>
            <label className="label">Default platforms</label>
            <div className="flex flex-wrap gap-2">
              {PLATFORM_KEYS.map((k) => {
                const on = form.default_platforms.includes(k)
                return (
                  <button key={k} type="button" onClick={() => togglePlatform(k)}
                    className={`badge border px-2.5 py-1 transition ${on ? 'border-accent bg-accent-soft text-accent' : 'border-line text-muted'}`}>
                    {PLATFORMS[k].label}
                  </button>
                )
              })}
            </div>
          </div>

          <div>
            <label className="label">Default content mix</label>
            <ChipSelect multi options={PLANNER_CONTENT_TYPES} value={form.default_content_mix} onChange={(v) => set({ default_content_mix: v })} />
          </div>

          {/* Auto Mode — OFF only for now */}
          <div className="rounded-xl border border-line p-3">
            <div className="flex items-center gap-2">
              <span className="font-medium">Auto Mode</span>
              <span className="rounded-full bg-accent-soft px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent">Coming soon</span>
              <span className="ml-auto inline-flex h-6 w-11 items-center rounded-full bg-inset px-0.5">
                <span className="h-5 w-5 rounded-full bg-surface shadow-sm" />
              </span>
            </div>
            <p className="mt-1 text-xs text-muted">
              When enabled later, AI will schedule and publish automatically. For now every plan waits for your approval.
            </p>
          </div>
        </div>

        <div className="mt-6 flex gap-2">
          <button onClick={save} disabled={busy} className="btn btn-primary flex-1">{busy ? 'Saving…' : 'Save settings'}</button>
          <button onClick={onClose} className="btn btn-ghost">Cancel</button>
        </div>
      </div>
    </div>
  )
}

// ---- small shared bits ----------------------------------------------------
function Section({ title, hint, children }) {
  return (
    <div className="card p-5">
      <div className="mb-3">
        <h3 className="font-semibold">{title}</h3>
        {hint && <p className="text-xs text-muted">{hint}</p>}
      </div>
      {children}
    </div>
  )
}

function SelectCard({ active, onClick, title, hint }) {
  return (
    <button type="button" onClick={onClick}
      className={`rounded-xl border p-4 text-left transition ${active ? 'border-accent bg-accent-soft' : 'border-line hover:border-accent'}`}>
      <div className="font-semibold">{title}</div>
      {hint && <div className="text-xs text-muted">{hint}</div>}
    </button>
  )
}

function SummaryRow({ label, value }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right font-medium">{value}</dd>
    </div>
  )
}

function StatTile({ value, label }) {
  return (
    <div className="card p-4 text-center">
      <div className="text-2xl font-black">{value}</div>
      <div className="text-xs text-muted">{label}</div>
    </div>
  )
}
