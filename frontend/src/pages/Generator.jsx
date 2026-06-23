import { useState } from 'react'
import { api } from '../lib/api'
import { useToast } from '../context/ToastContext.jsx'
import { PLATFORMS, PLATFORM_KEYS, TONES } from '../lib/constants'
import { localInputToISO } from '../lib/datetime'
import PlatformIcon from '../components/PlatformIcon.jsx'
import ScheduleModal from '../components/ScheduleModal.jsx'

export default function Generator() {
  const toast = useToast()
  const [topic, setTopic] = useState('')
  const [tone, setTone] = useState('professional')
  const [audience, setAudience] = useState('')
  const [selected, setSelected] = useState(['twitter', 'linkedin'])
  const [includeHashtags, setIncludeHashtags] = useState(true)
  const [variants, setVariants] = useState(false)
  const [loading, setLoading] = useState(false)
  const [drafts, setDrafts] = useState([]) // editable cards
  const [meta, setMeta] = useState(null) // {provider, model}
  const [scheduleFor, setScheduleFor] = useState(null) // draft index awaiting schedule

  function togglePlatform(p) {
    setSelected((s) => (s.includes(p) ? s.filter((x) => x !== p) : [...s, p]))
  }

  async function generate(e) {
    e.preventDefault()
    if (!topic.trim()) return toast.error('Please enter a topic')
    setLoading(true)
    setDrafts([])
    try {
      const platforms = selected.length ? selected : PLATFORM_KEYS
      const base = {
        topic,
        tone,
        audience: audience || null,
        include_hashtags: includeHashtags,
        variants,
      }
      const responses = await Promise.all(
        platforms.map((p) => api.generate({ ...base, platform: p })),
      )
      const cards = responses.flatMap((r) =>
        r.results.map((res) => ({
          platform: res.platform,
          content: res.text,
          hashtags: (res.hashtags || []).join(' '),
        })),
      )
      setDrafts(cards)
      setMeta({ provider: responses[0]?.provider, model: responses[0]?.model })
      toast.success(`Generated ${cards.length} post(s)`)
    } catch (err) {
      toast.error(err.message || 'Generation failed')
    } finally {
      setLoading(false)
    }
  }

  function updateDraft(i, patch) {
    setDrafts((d) => d.map((c, idx) => (idx === i ? { ...c, ...patch } : c)))
  }

  function hashtagList(str) {
    return str
      .split(/[\s,]+/)
      .map((t) => t.replace(/^#/, '').trim())
      .filter(Boolean)
  }

  async function saveDraft(i) {
    const c = drafts[i]
    try {
      await api.createPost({
        platform: c.platform,
        content: c.content,
        hashtags: hashtagList(c.hashtags),
      })
      toast.success(`Saved ${PLATFORMS[c.platform].label} draft`)
    } catch (err) {
      toast.error(err.message)
    }
  }

  async function publishNow(i) {
    const c = drafts[i]
    try {
      const post = await api.createPost({
        platform: c.platform,
        content: c.content,
        hashtags: hashtagList(c.hashtags),
      })
      await api.publishPost(post.id)
      toast.success(`Published to ${PLATFORMS[c.platform].label} (simulated)`)
    } catch (err) {
      toast.error(err.message)
    }
  }

  async function doSchedule(localValue) {
    const i = scheduleFor
    const c = drafts[i]
    try {
      await api.createPost({
        platform: c.platform,
        content: c.content,
        hashtags: hashtagList(c.hashtags),
        scheduled_time: localInputToISO(localValue),
      })
      toast.success(`Scheduled ${PLATFORMS[c.platform].label} post`)
      setScheduleFor(null)
    } catch (err) {
      toast.error(err.message)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">AI Generator</h1>
        <p className="text-sm text-slate-400">
          Describe your idea — get platform-optimized posts instantly.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
        {/* Input panel */}
        <form onSubmit={generate} className="card h-fit space-y-4 p-5">
          <div>
            <label className="label">Topic *</label>
            <textarea
              className="input min-h-20 resize-y"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="e.g. Launching our new AI scheduling feature"
            />
          </div>

          <div>
            <label className="label">Tone</label>
            <select className="input" value={tone} onChange={(e) => setTone(e.target.value)}>
              {TONES.map((t) => (
                <option key={t} value={t}>
                  {t[0].toUpperCase() + t.slice(1)}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="label">Platforms (none = all)</label>
            <div className="flex flex-wrap gap-2">
              {PLATFORM_KEYS.map((p) => {
                const on = selected.includes(p)
                return (
                  <button
                    type="button"
                    key={p}
                    onClick={() => togglePlatform(p)}
                    className={`flex items-center gap-1.5 rounded-xl border px-2.5 py-1.5 text-xs font-medium transition ${
                      on
                        ? 'border-indigo-500 bg-indigo-500/15 text-indigo-300'
                        : 'border-slate-300 text-slate-400 dark:border-white/10'
                    }`}
                  >
                    <PlatformIcon platform={p} size={18} />
                    {PLATFORMS[p].label}
                  </button>
                )
              })}
            </div>
          </div>

          <div>
            <label className="label">Audience (optional)</label>
            <input
              className="input"
              value={audience}
              onChange={(e) => setAudience(e.target.value)}
              placeholder="e.g. startup founders"
            />
          </div>

          <div className="flex flex-col gap-2 text-sm">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={includeHashtags}
                onChange={(e) => setIncludeHashtags(e.target.checked)} />
              Include hashtags
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={variants}
                onChange={(e) => setVariants(e.target.checked)} />
              Short + long variants
            </label>
          </div>

          <button className="btn btn-primary w-full" disabled={loading}>
            {loading ? 'Generating…' : '✦ Generate Post'}
          </button>
        </form>

        {/* Output panel */}
        <div className="space-y-4">
          {meta && (
            <div className="text-xs text-slate-500">
              Generated with <span className="font-semibold text-indigo-400">{meta.provider}</span>
              {' · '}
              {meta.model}
            </div>
          )}

          {loading && <CardSkeleton />}

          {!loading && drafts.length === 0 && (
            <div className="card grid place-items-center p-12 text-center text-slate-500">
              <div>
                <div className="mb-2 text-4xl">✦</div>
                Your generated posts will appear here.
              </div>
            </div>
          )}

          {drafts.map((c, i) => {
            const limit = PLATFORMS[c.platform]?.limit || 0
            const over = c.content.length > limit
            return (
              <div key={i} className="card p-5">
                <div className="mb-3 flex items-center gap-2">
                  <PlatformIcon platform={c.platform} />
                  <span className="font-semibold">{PLATFORMS[c.platform].label}</span>
                  <span className={`ml-auto text-xs ${over ? 'text-rose-400' : 'text-slate-400'}`}>
                    {c.content.length} / {limit}
                  </span>
                </div>

                <textarea
                  className="input min-h-32 resize-y"
                  value={c.content}
                  onChange={(e) => updateDraft(i, { content: e.target.value })}
                />

                <label className="label mt-3">Hashtags</label>
                <input
                  className="input"
                  value={c.hashtags}
                  onChange={(e) => updateDraft(i, { hashtags: e.target.value })}
                  placeholder="space or comma separated"
                />

                <div className="mt-4 flex flex-wrap gap-2">
                  <button onClick={() => saveDraft(i)} className="btn btn-ghost btn-sm">
                    Save Draft
                  </button>
                  <button onClick={() => setScheduleFor(i)} className="btn btn-ghost btn-sm">
                    Schedule
                  </button>
                  <button onClick={() => publishNow(i)} className="btn btn-primary btn-sm">
                    Publish Now
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <ScheduleModal
        open={scheduleFor !== null}
        title="Schedule this post"
        onClose={() => setScheduleFor(null)}
        onConfirm={doSchedule}
      />
    </div>
  )
}

function CardSkeleton() {
  return (
    <div className="card space-y-3 p-5">
      <div className="skeleton h-5 w-40" />
      <div className="skeleton h-32 w-full" />
      <div className="skeleton h-9 w-full" />
    </div>
  )
}
