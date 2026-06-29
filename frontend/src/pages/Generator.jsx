import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { useToast } from '../context/ToastContext.jsx'
import {
  PLATFORMS,
  PLATFORM_KEYS,
  TONES,
  ASPECT_RATIOS,
  IMAGE_STYLES,
  IMAGE_QUALITIES,
  CAROUSEL_SLIDE_OPTIONS,
  PLATFORM_ASPECT_DEFAULT,
  DEFAULT_IMAGE_SETTINGS,
} from '../lib/constants'
import { localInputToISO } from '../lib/datetime'
import { loadFirstAvailable } from '../lib/imageLoader'
import PlatformIcon from '../components/PlatformIcon.jsx'
import ScheduleModal from '../components/ScheduleModal.jsx'

const STORAGE_KEY = 'composer_state_v1'

// --- session persistence ----------------------------------------------------
function loadState() {
  try {
    return JSON.parse(sessionStorage.getItem(STORAGE_KEY)) || null
  } catch {
    return null
  }
}

const SAVED = loadState()

// Effective per-platform settings: global, with an optional override layered on
// top for the shape controls (aspect ratio / carousel / slides).
function resolveSettings(global, override) {
  const useOverride = override?.enabled
  return {
    aiImage: useOverride ? override.aiImage : global.aiImage,
    style: global.style,
    quality: global.quality,
    negative: global.negative,
    promptEnhancer: global.promptEnhancer,
    aspectRatio: useOverride ? override.aspectRatio : global.aspectRatio,
    carousel: useOverride ? override.carousel : global.carousel,
    slides: useOverride ? override.slides : global.slides,
  }
}

export default function Generator() {
  const toast = useToast()

  // Caption inputs (existing multi-platform behaviour, preserved).
  const [topic, setTopic] = useState(SAVED?.topic ?? '')
  const [tone, setTone] = useState(SAVED?.tone ?? 'professional')
  const [audience, setAudience] = useState(SAVED?.audience ?? '')
  const [selected, setSelected] = useState(SAVED?.selected ?? ['instagram', 'facebook'])
  const [includeHashtags, setIncludeHashtags] = useState(SAVED?.includeHashtags ?? true)
  const [variants, setVariants] = useState(SAVED?.variants ?? false)

  // Global image settings (apply to all selected platforms) + per-platform
  // overrides keyed by platform.
  const [img, setImg] = useState({ ...DEFAULT_IMAGE_SETTINGS, ...(SAVED?.img || {}) })
  const [overrides, setOverrides] = useState(SAVED?.overrides ?? {})
  const [showAdvanced, setShowAdvanced] = useState(false)

  const [loading, setLoading] = useState(false)
  const [drafts, setDrafts] = useState(() =>
    (SAVED?.drafts || []).map((d) => ({
      ...d,
      imgLoading: false,
      imgError: d.imgError ?? null,
      capLoading: false,
      igBusy: false,
      // Keep only terminal statuses across a refresh; drop transient ones.
      status: ['published', 'scheduled', 'failed'].includes(d.status) ? d.status : null,
    })),
  )
  const [meta, setMeta] = useState(SAVED?.meta ?? null)
  const [scheduleFor, setScheduleFor] = useState(null) // single-card schedule
  const [scheduleAllOpen, setScheduleAllOpen] = useState(false)
  const [confirmModal, setConfirmModal] = useState(null) // {title, message, ...}
  const [bulkBusy, setBulkBusy] = useState(false)
  const busyRef = useRef(false) // guards against double-submit

  // Unsaved generated content = at least one card not yet published/scheduled.
  const hasUnsaved = drafts.some((d) => !['published', 'scheduled'].includes(d.status))

  // Warn before leaving / refreshing with unsaved generated content.
  useEffect(() => {
    if (!hasUnsaved) return undefined
    const handler = (e) => {
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [hasUnsaved])

  // Persist composer state so a refresh restores the session.
  useEffect(() => {
    const slim = drafts.map(({ imgLoading, capLoading, igBusy, ...keep }) => keep)
    const payload = {
      topic, tone, audience, selected, includeHashtags, variants,
      img, overrides, meta, drafts: slim,
    }
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
    } catch {
      /* quota / serialization issues are non-fatal */
    }
  }, [topic, tone, audience, selected, includeHashtags, variants, img, overrides, meta, drafts])

  function togglePlatform(p) {
    setSelected((s) => (s.includes(p) ? s.filter((x) => x !== p) : [...s, p]))
  }

  function updateImg(patch) {
    setImg((s) => ({ ...s, ...patch }))
  }

  function toggleOverride(p) {
    setOverrides((o) => {
      const cur = o[p]
      if (cur?.enabled) return { ...o, [p]: { ...cur, enabled: false } }
      // Seed a fresh override from the platform's recommended aspect ratio.
      return {
        ...o,
        [p]: {
          enabled: true,
          aiImage: cur?.aiImage ?? img.aiImage,
          aspectRatio: cur?.aspectRatio ?? PLATFORM_ASPECT_DEFAULT[p] ?? img.aspectRatio,
          carousel: cur?.carousel ?? img.carousel,
          slides: cur?.slides ?? img.slides,
        },
      }
    })
  }

  function updateOverride(p, patch) {
    setOverrides((o) => ({ ...o, [p]: { ...o[p], ...patch } }))
  }

  function updateDraft(i, patch) {
    setDrafts((d) =>
      d.map((c, idx) =>
        idx === i ? { ...c, ...(typeof patch === 'function' ? patch(c) : patch) } : c,
      ),
    )
  }

  function hashtagList(str) {
    return (str || '')
      .split(/[\s,]+/)
      .map((t) => t.replace(/^#/, '').trim())
      .filter(Boolean)
  }

  // Display hashtags with a leading # (round-trips: hashtagList strips it again).
  function formatHashtags(arr) {
    return (arr || []).map((t) => `#${String(t).replace(/^#/, '')}`).join(' ')
  }

  function captionBase() {
    return {
      topic,
      tone,
      audience: audience || null,
      include_hashtags: includeHashtags,
      variants,
    }
  }

  // --- generation -----------------------------------------------------------
  function generate(e) {
    e.preventDefault()
    if (busyRef.current) return
    if (!topic.trim()) return toast.error('Please describe your idea first')
    // Protect unsaved generated content before replacing it.
    if (hasUnsaved) {
      setConfirmModal({
        title: 'Start a new generation?',
        message:
          'You have unsaved generated content. Generating again will replace it.',
        cancelLabel: 'Stay',
        confirmLabel: 'Discard & Generate',
        danger: true,
        onConfirm: () => {
          setConfirmModal(null)
          runGenerate()
        },
      })
      return
    }
    runGenerate()
  }

  async function runGenerate() {
    busyRef.current = true
    setLoading(true)
    setDrafts([])
    try {
      const platforms = selected.length ? selected : PLATFORM_KEYS
      const base = captionBase()

      // 1. Captions — one request per platform (existing multi-platform flow).
      const responses = await Promise.all(
        platforms.map((p) => api.generate({ ...base, platform: p })),
      )
      const cards = responses.flatMap((r) =>
        r.results.map((res) => ({
          platform: res.platform,
          content: res.text,
          hashtags: formatHashtags(res.hashtags),
          imagePrompt: topic, // base prompt for image (re)generation
          settings: resolveSettings(img, overrides[res.platform]),
          images: [],
          imgLoading: false,
          imgError: null,
          capLoading: false,
          igBusy: false,
        })),
      )
      setDrafts(cards)
      setMeta({ provider: responses[0]?.provider, model: responses[0]?.model })
      toast.success(`Generated ${cards.length} caption(s)`)

      // 2. Images — independent per card, so a failure never loses captions.
      cards.forEach((c, i) => {
        if (c.settings.aiImage) generateCardImages(i, c)
      })
    } catch (err) {
      toast.error(err.message || 'Generation failed')
    } finally {
      setLoading(false)
      busyRef.current = false
    }
  }

  async function generateCardImages(i, card) {
    const s = card.settings
    updateDraft(i, { imgLoading: true, imgError: null })
    try {
      const res = await api.generateImages({
        prompt: card.imagePrompt || topic,
        platform: card.platform,
        aspect_ratio: s.aspectRatio,
        carousel: s.carousel,
        slides: s.carousel ? s.slides : 1,
        style: s.style,
        quality: s.quality,
        negative_prompt: s.negative || null,
        prompt_enhancer: s.promptEnhancer,
      })
      updateDraft(i, { images: res.images, imgLoading: false, imgError: null })
    } catch (err) {
      updateDraft(i, {
        imgLoading: false,
        imgError: err.message || 'Image generation failed',
      })
    }
  }

  async function regenerateCaption(i) {
    const c = drafts[i]
    updateDraft(i, { capLoading: true })
    try {
      const r = await api.generate({ ...captionBase(), platform: c.platform })
      const res = r.results[0]
      updateDraft(i, {
        content: res.text,
        hashtags: formatHashtags(res.hashtags),
        capLoading: false,
      })
      toast.success('Caption regenerated')
    } catch (err) {
      updateDraft(i, { capLoading: false })
      toast.error(err.message || 'Caption regeneration failed')
    }
  }

  async function regenerateSlide(i, slideIndex) {
    const c = drafts[i]
    const s = c.settings
    const slide = c.images[slideIndex]
    updateDraft(i, { imgLoading: true })
    try {
      const res = await api.generateImages({
        prompt: slide?.label || c.imagePrompt || topic,
        platform: c.platform,
        aspect_ratio: s.aspectRatio,
        carousel: false,
        slides: 1,
        style: s.style,
        quality: s.quality,
        negative_prompt: s.negative || null,
        prompt_enhancer: s.promptEnhancer,
      })
      const fresh = res.images[0]
      updateDraft(i, (cur) => ({
        imgLoading: false,
        images: cur.images.map((im, idx) =>
          idx === slideIndex ? { ...fresh, label: im.label } : im,
        ),
      }))
    } catch (err) {
      updateDraft(i, { imgLoading: false })
      toast.error(err.message || 'Slide regeneration failed')
    }
  }

  async function regenerateEntirePost(i) {
    await regenerateCaption(i)
    await generateCardImages(i, drafts[i])
  }

  // --- content helpers ------------------------------------------------------
  async function copyCaption(c) {
    const tags = hashtagList(c.hashtags).map((t) => `#${t}`).join(' ')
    const text = [c.content, tags].filter(Boolean).join('\n\n')
    try {
      await navigator.clipboard.writeText(text)
      toast.success('Caption copied')
    } catch {
      toast.error('Could not copy to clipboard')
    }
  }

  async function downloadImage(url, name) {
    try {
      const res = await fetch(url)
      const blob = await res.blob()
      const obj = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = obj
      a.download = name
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(obj)
    } catch {
      window.open(url, '_blank', 'noopener') // CORS fallback
    }
  }

  async function downloadAll(c) {
    for (let idx = 0; idx < c.images.length; idx++) {
      // Sequential to avoid the browser blocking a burst of downloads.
      // eslint-disable-next-line no-await-in-loop
      await downloadImage(c.images[idx].url, `${c.platform}-${idx + 1}.png`)
    }
  }

  // --- persistence / publishing (existing behaviour, image-aware) -----------
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

  // Publish one card, tracking its status (used by both the per-card button
  // and Publish All). Returns true on success; never throws.
  async function publishCard(i) {
    const c = drafts[i]
    updateDraft(i, { status: 'publishing', publishError: null })
    try {
      const post = await api.createPost({
        platform: c.platform,
        content: c.content,
        hashtags: hashtagList(c.hashtags),
      })
      await api.publishPost(post.id)
      updateDraft(i, { status: 'published' })
      return true
    } catch (err) {
      updateDraft(i, { status: 'failed', publishError: err.message })
      return false
    }
  }

  async function publishNow(i) {
    const ok = await publishCard(i)
    if (ok) toast.success(`Published to ${PLATFORMS[drafts[i].platform].label} (simulated)`)
    else toast.error('Publish failed')
  }

  // --- bulk actions ---------------------------------------------------------
  function requestPublishAll() {
    if (!drafts.length || bulkBusy) return
    if (drafts.length === 1) {
      publishNow(0)
      return
    }
    setConfirmModal({
      title: 'Publish to Multiple Platforms?',
      message: 'You are about to publish this content to:',
      list: drafts.map((d) => PLATFORMS[d.platform]?.label || d.platform),
      confirmLabel: 'Publish All',
      onConfirm: doPublishAll,
    })
  }

  async function doPublishAll() {
    setConfirmModal(null)
    setBulkBusy(true)
    try {
      // Non-blocking: each card resolves its own success/failure independently.
      const results = await Promise.allSettled(drafts.map((_, i) => publishCard(i)))
      const ok = results.filter((r) => r.status === 'fulfilled' && r.value).length
      const fail = drafts.length - ok
      if (fail === 0) toast.success(`Published all ${ok} platform(s)`)
      else toast.error(`${ok} published · ${fail} failed`)
    } finally {
      setBulkBusy(false)
    }
  }

  async function scheduleAll(localValue) {
    const iso = localInputToISO(localValue)
    setScheduleAllOpen(false)
    setBulkBusy(true)
    try {
      const results = await Promise.allSettled(
        drafts.map(async (c, i) => {
          updateDraft(i, { status: 'publishing' })
          await api.createPost({
            platform: c.platform,
            content: c.content,
            hashtags: hashtagList(c.hashtags),
            scheduled_time: iso,
          })
          updateDraft(i, { status: 'scheduled' })
        }),
      )
      const ok = results.filter((r) => r.status === 'fulfilled').length
      const fail = drafts.length - ok
      results.forEach((r, i) => {
        if (r.status === 'rejected') updateDraft(i, { status: 'failed' })
      })
      if (fail === 0) toast.success(`Scheduled all ${ok} platform(s)`)
      else toast.error(`${ok} scheduled · ${fail} failed`)
    } finally {
      setBulkBusy(false)
    }
  }

  async function saveAllDrafts() {
    if (!drafts.length || bulkBusy) return
    setBulkBusy(true)
    try {
      const results = await Promise.allSettled(
        drafts.map((c) =>
          api.createPost({
            platform: c.platform,
            content: c.content,
            hashtags: hashtagList(c.hashtags),
          }),
        ),
      )
      const ok = results.filter((r) => r.status === 'fulfilled').length
      const fail = drafts.length - ok
      if (fail === 0) toast.success(`Saved ${ok} draft(s)`)
      else toast.error(`${ok} saved · ${fail} failed`)
    } finally {
      setBulkBusy(false)
    }
  }

  function requestClearAll() {
    if (!drafts.length) return
    setConfirmModal({
      title: 'Discard Generated Content?',
      message:
        'This will remove all generated captions, images, hashtags, and unsaved changes for every platform. This action cannot be undone.',
      confirmLabel: 'Yes, Clear Everything',
      cancelLabel: 'Cancel',
      danger: true,
      onConfirm: () => {
        setDrafts([])
        setMeta(null)
        setConfirmModal(null)
        toast.success('Cleared all generated content')
      },
    })
  }

  // --- per-platform card management -----------------------------------------
  function clearPlatform(i) {
    setDrafts((d) => d.filter((_, idx) => idx !== i))
  }

  function duplicatePlatform(i) {
    setDrafts((d) => {
      const copy = { ...d[i], status: null, publishError: null }
      const next = [...d]
      next.splice(i + 1, 0, copy)
      return next
    })
  }

  async function downloadAssets(c) {
    if (c.images.length) await downloadAll(c)
    // Always offer the caption text too.
    const tags = hashtagList(c.hashtags).map((t) => `#${t}`).join(' ')
    const text = [c.content, tags].filter(Boolean).join('\n\n')
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${c.platform}-caption.txt`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  async function publishInstagram(i) {
    const c = drafts[i]
    const caption = [c.content, hashtagList(c.hashtags).map((t) => `#${t}`).join(' ')]
      .filter(Boolean)
      .join('\n\n')
    const firstImage = c.images[0]?.url
    updateDraft(i, { igBusy: true })
    try {
      const res = await api.publishInstagram({
        caption,
        image_url: firstImage || null,
        image_prompt: firstImage ? null : c.imagePrompt || c.content,
        content: c.content,
        hashtags: hashtagList(c.hashtags),
      })
      if (res.image_url) {
        updateDraft(i, (cur) => ({
          images: cur.images.length ? cur.images : [{ url: res.image_url, label: null }],
        }))
      }
      toast.success('Published to Instagram — see it in History')
    } catch (err) {
      toast.error(err.message || 'Instagram publish failed')
    } finally {
      updateDraft(i, { igBusy: false })
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

  const platformsForOverride = selected.length ? selected : []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">AI Generator</h1>
        <p className="text-sm text-slate-400">
          Describe an idea — get platform-optimized captions and AI images you control.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[380px_1fr]">
        {/* ---- Input panel ---- */}
        <form onSubmit={generate} className="card h-fit space-y-5 p-5">
          {/* Step 1 — Prompt */}
          <div>
            <label className="label" htmlFor="topic">
              Describe your idea
            </label>
            <textarea
              id="topic"
              className="input min-h-24 resize-y"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="e.g. A post about the launch of our new eco-friendly coffee beans"
            />
          </div>

          <div>
            <label className="label" htmlFor="tone">
              Tone
            </label>
            <select
              id="tone"
              className="input"
              value={tone}
              onChange={(e) => setTone(e.target.value)}
            >
              {TONES.map((t) => (
                <option key={t} value={t}>
                  {t[0].toUpperCase() + t.slice(1)}
                </option>
              ))}
            </select>
          </div>

          {/* Step 2 — Platforms */}
          <div>
            <label className="label">Platforms (none = all)</label>
            <div className="flex flex-wrap gap-2">
              {PLATFORM_KEYS.map((p) => {
                const on = selected.includes(p)
                return (
                  <button
                    type="button"
                    key={p}
                    aria-pressed={on}
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

          {/* Step 3 — Image Settings (global) */}
          <div className="rounded-xl border border-slate-200 p-3 dark:border-white/10">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold">Image Settings</span>
              <label className="flex items-center gap-2 text-xs text-slate-400">
                AI Image
                <Switch
                  checked={img.aiImage}
                  onChange={(v) => updateImg({ aiImage: v })}
                  label="AI Image"
                />
              </label>
            </div>

            {img.aiImage && (
              <div className="mt-3 space-y-3">
                <SettingsGrid
                  aspectRatio={img.aspectRatio}
                  carousel={img.carousel}
                  slides={img.slides}
                  onChange={updateImg}
                />
                <div>
                  <label className="label" htmlFor="style">
                    Image Style
                  </label>
                  <select
                    id="style"
                    className="input"
                    value={img.style}
                    onChange={(e) => updateImg({ style: e.target.value })}
                  >
                    {IMAGE_STYLES.map((s) => (
                      <option key={s.value} value={s.value}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            )}
          </div>

          {/* Per-platform overrides */}
          {platformsForOverride.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                Per-platform overrides
              </div>
              <p className="text-xs text-slate-400">
                Override a platform to turn its image on/off or change its shape —
                e.g. images for some platforms, caption-only for others.
              </p>
              {platformsForOverride.map((p) => {
                const ov = overrides[p]
                const on = !!ov?.enabled
                // What this platform will actually use (global unless overridden).
                const eff = resolveSettings(img, ov)
                return (
                  <div
                    key={p}
                    className="rounded-xl border border-slate-200 p-3 text-sm dark:border-white/10"
                  >
                    <div className="flex items-center justify-between">
                      <span className="flex items-center gap-2 font-medium">
                        <PlatformIcon platform={p} size={18} />
                        {PLATFORMS[p].label}
                        <span className="text-[11px] font-normal text-slate-400">
                          {eff.aiImage
                            ? `image · ${eff.aspectRatio}${eff.carousel ? ` · ${eff.slides} slides` : ''}`
                            : 'caption only'}
                        </span>
                      </span>
                      <button
                        type="button"
                        onClick={() => toggleOverride(p)}
                        aria-pressed={on}
                        title={
                          on
                            ? 'Using custom settings for this platform'
                            : 'Use settings just for this platform'
                        }
                        className={`rounded-lg border px-2.5 py-1 text-xs font-medium transition ${
                          on
                            ? 'border-indigo-500 bg-indigo-500/15 text-indigo-300'
                            : 'border-slate-300 text-slate-400 hover:bg-slate-100 dark:border-white/10 dark:hover:bg-white/5'
                        }`}
                      >
                        {on ? '✓ Custom' : '+ Override'}
                      </button>
                    </div>
                    {on && (
                      <div className="mt-3 space-y-3">
                        <label className="flex items-center justify-between">
                          <span>AI Image</span>
                          <Switch
                            checked={ov.aiImage}
                            onChange={(v) => updateOverride(p, { aiImage: v })}
                            label={`AI Image for ${PLATFORMS[p].label}`}
                          />
                        </label>
                        {ov.aiImage ? (
                          <SettingsGrid
                            aspectRatio={ov.aspectRatio}
                            carousel={ov.carousel}
                            slides={ov.slides}
                            onChange={(patch) => updateOverride(p, patch)}
                          />
                        ) : (
                          <p className="text-xs text-slate-400">
                            Caption only — no image for {PLATFORMS[p].label}.
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}

          {/* Step 4 — Advanced (collapsed) */}
          <div className="rounded-xl border border-slate-200 dark:border-white/10">
            <button
              type="button"
              onClick={() => setShowAdvanced((v) => !v)}
              aria-expanded={showAdvanced}
              className="flex w-full items-center justify-between px-3 py-2 text-sm font-medium"
            >
              Advanced Settings
              <span className="text-slate-400">{showAdvanced ? '▲' : '▼'}</span>
            </button>
            {showAdvanced && (
              <div className="space-y-3 border-t border-slate-200 p-3 dark:border-white/10">
                <div>
                  <label className="label" htmlFor="audience">
                    Audience (optional)
                  </label>
                  <input
                    id="audience"
                    className="input"
                    value={audience}
                    onChange={(e) => setAudience(e.target.value)}
                    placeholder="e.g. startup founders"
                  />
                </div>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={includeHashtags}
                    onChange={(e) => setIncludeHashtags(e.target.checked)}
                  />
                  Include hashtags
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={variants}
                    onChange={(e) => setVariants(e.target.checked)}
                  />
                  Short + long variants
                </label>

                {img.aiImage && (
                  <>
                    <div className="border-t border-slate-200 pt-3 dark:border-white/10">
                      <label className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={img.promptEnhancer}
                          onChange={(e) => updateImg({ promptEnhancer: e.target.checked })}
                        />
                        Improve my image prompt automatically
                      </label>
                    </div>
                    <div>
                      <label className="label" htmlFor="quality">
                        Image Quality
                      </label>
                      <select
                        id="quality"
                        className="input"
                        value={img.quality}
                        onChange={(e) => updateImg({ quality: e.target.value })}
                      >
                        {IMAGE_QUALITIES.map((q) => (
                          <option key={q.value} value={q.value}>
                            {q.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="label" htmlFor="negative">
                        Negative prompt (avoid…)
                      </label>
                      <input
                        id="negative"
                        className="input"
                        value={img.negative}
                        onChange={(e) => updateImg({ negative: e.target.value })}
                        placeholder="e.g. text, watermark, humans"
                      />
                    </div>
                    <div className="flex items-center gap-2 text-xs text-slate-400">
                      <span className="rounded-md border border-dashed border-slate-300 px-2 py-1 dark:border-white/10">
                        Brand Kit · coming soon
                      </span>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>

          {/* Step 5 — Generate */}
          <button className="btn btn-primary w-full" disabled={loading}>
            {loading ? 'Generating…' : '✦ Generate'}
          </button>
        </form>

        {/* ---- Output panel ---- */}
        <div className="space-y-4">
          {/* Global action bar (sticky) */}
          {drafts.length > 0 && (
            <div className="sticky top-2 z-10 flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white/85 px-3 py-2 shadow-sm backdrop-blur dark:border-white/10 dark:bg-slate-900/80">
              <span className="text-xs text-slate-400">
                {drafts.length} platform{drafts.length > 1 ? 's' : ''}
                {meta && (
                  <>
                    {' · '}
                    <span className="font-semibold text-indigo-400">{meta.provider}</span>
                  </>
                )}
              </span>
              <div className="ml-auto flex flex-wrap gap-2">
                <button
                  onClick={requestPublishAll}
                  disabled={bulkBusy}
                  className="btn btn-primary btn-sm"
                >
                  {bulkBusy ? 'Working…' : '⤴ Publish All'}
                </button>
                <button
                  onClick={() => setScheduleAllOpen(true)}
                  disabled={bulkBusy}
                  className="btn btn-ghost btn-sm"
                >
                  🗓 Schedule All
                </button>
                <button onClick={saveAllDrafts} disabled={bulkBusy} className="btn btn-ghost btn-sm">
                  Save Draft
                </button>
                <button
                  onClick={requestClearAll}
                  disabled={bulkBusy}
                  className="btn btn-danger btn-sm"
                >
                  Clear All
                </button>
              </div>
            </div>
          )}

          {loading && <CardSkeleton />}

          {!loading && drafts.length === 0 && (
            <div className="card grid place-items-center p-12 text-center text-slate-500">
              <div>
                <div className="mb-3 text-5xl">✦</div>
                <div className="font-medium text-slate-600 dark:text-slate-300">
                  Describe your idea and let AI generate platform-ready content.
                </div>
                <div className="mt-1 text-sm text-slate-400">
                  Your captions and images will appear here.
                </div>
              </div>
            </div>
          )}

          {drafts.map((c, i) => (
            <PostCard
              key={`${c.platform}-${i}`}
              c={c}
              limit={PLATFORMS[c.platform]?.limit || 0}
              label={PLATFORMS[c.platform]?.label || c.platform}
              onContent={(v) => updateDraft(i, { content: v })}
              onHashtags={(v) => updateDraft(i, { hashtags: v })}
              onImageResolved={(idx, url) =>
                updateDraft(i, (cur) => ({
                  images: cur.images.map((im, j) => (j === idx ? { ...im, url } : im)),
                }))
              }
              onCopy={() => copyCaption(c)}
              onDownload={(url, name) => downloadImage(url, name)}
              onDownloadAll={() => downloadAll(c)}
              onDownloadAssets={() => downloadAssets(c)}
              onRegenCaption={() => regenerateCaption(i)}
              onRegenImages={() => generateCardImages(i, c)}
              onRegenSlide={(idx) => regenerateSlide(i, idx)}
              onRegenAll={() => regenerateEntirePost(i)}
              onSave={() => saveDraft(i)}
              onSchedule={() => setScheduleFor(i)}
              onPublish={() => publishNow(i)}
              onPublishInstagram={() => publishInstagram(i)}
              onClearPlatform={() => clearPlatform(i)}
              onDuplicate={() => duplicatePlatform(i)}
            />
          ))}
        </div>
      </div>

      <ScheduleModal
        open={scheduleFor !== null}
        title="Schedule this post"
        onClose={() => setScheduleFor(null)}
        onConfirm={doSchedule}
      />

      <ScheduleModal
        open={scheduleAllOpen}
        title={`Schedule all ${drafts.length} platform(s)`}
        onClose={() => setScheduleAllOpen(false)}
        onConfirm={scheduleAll}
      />

      <ConfirmModal modal={confirmModal} onCancel={() => setConfirmModal(null)} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Reusable aspect / carousel / slides controls (used by global + overrides).
// ---------------------------------------------------------------------------
function SettingsGrid({ aspectRatio, carousel, slides, onChange }) {
  return (
    <div className="space-y-3">
      <div>
        <label className="label">Aspect Ratio</label>
        <select
          className="input"
          value={aspectRatio}
          onChange={(e) => onChange({ aspectRatio: e.target.value })}
        >
          {ASPECT_RATIOS.map((a) => (
            <option key={a.value} value={a.value}>
              {a.label}
            </option>
          ))}
        </select>
      </div>
      <label className="flex items-center justify-between text-sm">
        <span>Carousel</span>
        <Switch
          checked={carousel}
          onChange={(v) => onChange({ carousel: v })}
          label="Carousel"
        />
      </label>
      {carousel && (
        <div>
          <label className="label">Slides</label>
          <select
            className="input"
            value={slides}
            onChange={(e) => onChange({ slides: Number(e.target.value) })}
          >
            {CAROUSEL_SLIDE_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Generated post card: caption + image(s) + actions.
// ---------------------------------------------------------------------------
function PostCard({
  c, limit, label,
  onContent, onHashtags, onImageResolved, onCopy, onDownload, onDownloadAll,
  onDownloadAssets, onRegenCaption, onRegenImages, onRegenSlide, onRegenAll,
  onSave, onSchedule, onPublish, onPublishInstagram, onClearPlatform, onDuplicate,
}) {
  const over = c.content.length > limit
  const isCarousel = c.settings.carousel && c.images.length > 1

  return (
    <div className="card p-5">
      <div className="mb-3 flex items-center gap-2">
        <PlatformIcon platform={c.platform} />
        <span className="font-semibold">{label}</span>
        {c.settings.aiImage && (
          <span className="badge bg-slate-500/15 text-slate-400">
            {c.settings.aspectRatio}
            {c.settings.carousel ? ` · ${c.settings.slides} slides` : ''}
          </span>
        )}
        <StatusChip status={c.status} error={c.publishError} />
        <div className="ml-auto flex items-center gap-2">
          <span className={`text-xs ${over ? 'text-rose-400' : 'text-slate-400'}`}>
            {c.content.length} / {limit}
          </span>
          <MoreMenu
            items={[
              { label: '🗑 Clear Platform', onClick: onClearPlatform, danger: true },
              { label: '⧉ Duplicate', onClick: onDuplicate },
              { label: '⬇ Download Assets', onClick: onDownloadAssets },
              { label: '📋 Copy Caption', onClick: onCopy },
            ]}
          />
        </div>
      </div>

      <textarea
        className="input min-h-32 resize-y"
        value={c.content}
        onChange={(e) => onContent(e.target.value)}
        aria-label={`${label} caption`}
      />

      <label className="label mt-3">Hashtags</label>
      <input
        className="input"
        value={c.hashtags}
        onChange={(e) => onHashtags(e.target.value)}
        placeholder="space or comma separated"
      />

      {/* Images */}
      {c.settings.aiImage && (
        <div className="mt-4">
          {c.imgLoading && (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <span className="skeleton h-4 w-4 rounded-full" />
              Generating images…
            </div>
          )}

          {!c.imgLoading && c.imgError && (
            <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-500 dark:text-rose-300">
              <div className="font-medium">Caption generated. Image generation failed.</div>
              <div className="mt-0.5 text-xs opacity-80">{c.imgError}</div>
              <button onClick={onRegenImages} className="btn btn-danger btn-sm mt-2">
                ↻ Retry Image
              </button>
            </div>
          )}

          {!c.imgLoading && c.images.length > 0 && (
            <>
              <div
                className={
                  isCarousel
                    ? 'grid grid-cols-2 gap-2 sm:grid-cols-3'
                    : 'max-w-xs'
                }
              >
                {c.images.map((im, idx) => (
                  <figure key={idx} className="group relative">
                    <SmartImage
                      candidates={[im.url, ...(im.fallbacks || [])]}
                      alt={im.label || `${label} image ${idx + 1}`}
                      aspectRatio={c.settings.aspectRatio}
                      onResolved={(url) => onImageResolved(idx, url)}
                    />
                    {isCarousel && (
                      <figcaption className="mt-1 flex items-center justify-between gap-1 text-[11px] text-slate-400">
                        <span className="truncate">
                          {idx + 1}. {im.label}
                        </span>
                        <button
                          onClick={() => onRegenSlide(idx)}
                          className="shrink-0 underline hover:text-indigo-400"
                          title="Regenerate this slide"
                        >
                          ↻
                        </button>
                      </figcaption>
                    )}
                  </figure>
                ))}
              </div>

              <div className="mt-2 flex flex-wrap gap-2">
                {isCarousel ? (
                  <button onClick={onDownloadAll} className="btn btn-ghost btn-sm">
                    ⬇ Download All
                  </button>
                ) : (
                  <button
                    onClick={() => onDownload(c.images[0].url, `${c.platform}.png`)}
                    className="btn btn-ghost btn-sm"
                  >
                    ⬇ Download
                  </button>
                )}
                <button onClick={onRegenImages} className="btn btn-ghost btn-sm">
                  ↻ Regenerate {isCarousel ? 'All' : 'Image'}
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="mt-4 flex flex-wrap gap-2">
        <button onClick={onCopy} className="btn btn-ghost btn-sm">
          ⧉ Copy Caption
        </button>
        <button onClick={onRegenCaption} disabled={c.capLoading} className="btn btn-ghost btn-sm">
          {c.capLoading ? 'Regenerating…' : '↻ Regenerate Caption'}
        </button>
        <button onClick={onRegenAll} className="btn btn-ghost btn-sm">
          ↻ Regenerate Post
        </button>
        <button onClick={onSave} className="btn btn-ghost btn-sm">
          Save Draft
        </button>
        <button onClick={onSchedule} className="btn btn-ghost btn-sm">
          Schedule
        </button>
        <button
          onClick={onPublish}
          disabled={c.status === 'publishing'}
          className="btn btn-primary btn-sm"
        >
          {c.status === 'publishing' ? 'Publishing…' : 'Publish Now'}
        </button>
        {c.platform === 'instagram' && (
          <button
            onClick={onPublishInstagram}
            disabled={c.igBusy}
            className="btn btn-sm bg-pink-600 text-white hover:bg-pink-500"
          >
            {c.igBusy ? 'Publishing…' : '📸 Publish to Instagram'}
          </button>
        )}
      </div>
    </div>
  )
}

// Loads the first working source from a candidate list, through a global
// concurrency gate (avoids rate-limit 429s), falling back automatically.
function SmartImage({ candidates, alt, aspectRatio, onResolved }) {
  const [src, setSrc] = useState(null)
  const [failed, setFailed] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const ratio = aspectRatio.replace(':', '/')
  const key = candidates.join('|')

  useEffect(() => {
    let cancelled = false
    setSrc(null)
    setFailed(false)
    loadFirstAvailable(candidates).then((url) => {
      if (cancelled) return
      if (url) {
        setSrc(url)
        onResolved?.(url)
      } else {
        setFailed(true)
      }
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, reloadKey])

  if (failed) {
    return (
      <div
        className="grid place-items-center rounded-xl border border-dashed border-slate-300 text-center text-xs text-slate-400 dark:border-white/10"
        style={{ aspectRatio: ratio }}
      >
        <div>
          <div>Image unavailable</div>
          <button
            type="button"
            onClick={() => setReloadKey((k) => k + 1)}
            className="mt-1 underline hover:text-indigo-400"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }
  if (!src) {
    return <div className="skeleton w-full rounded-xl" style={{ aspectRatio: ratio }} />
  }
  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      className="w-full rounded-xl object-cover"
      style={{ aspectRatio: ratio }}
    />
  )
}

// Per-card publish/schedule status chip.
function StatusChip({ status, error }) {
  if (!status) return null
  const map = {
    publishing: { text: '⏳ Publishing…', cls: 'bg-sky-500/15 text-sky-500 dark:text-sky-300' },
    published: { text: '✓ Published', cls: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-300' },
    scheduled: { text: '🗓 Scheduled', cls: 'bg-amber-500/15 text-amber-600 dark:text-amber-300' },
    failed: { text: '❌ Failed', cls: 'bg-rose-500/15 text-rose-600 dark:text-rose-300' },
  }
  const s = map[status]
  if (!s) return null
  return (
    <span className={`badge ${s.cls}`} title={error || ''}>
      {s.text}
    </span>
  )
}

// Compact "⋮" dropdown menu for per-card actions.
function MoreMenu({ items }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label="More actions"
        aria-haspopup="menu"
        className="grid h-7 w-7 place-items-center rounded-lg text-lg text-slate-400 hover:bg-slate-200 dark:hover:bg-white/10"
      >
        ⋮
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div
            role="menu"
            className="card absolute right-0 z-20 mt-1 w-44 overflow-hidden p-1 text-sm"
          >
            {items.map((it) => (
              <button
                key={it.label}
                role="menuitem"
                onClick={() => {
                  setOpen(false)
                  it.onClick?.()
                }}
                className={`block w-full rounded-lg px-3 py-2 text-left hover:bg-slate-100 dark:hover:bg-white/10 ${
                  it.danger ? 'text-rose-500' : ''
                }`}
              >
                {it.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// Generic confirmation modal (discard / publish-all / leave warnings).
function ConfirmModal({ modal, onCancel }) {
  if (!modal) return null
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={onCancel}
    >
      <div className="card w-full max-w-md p-5" onClick={(e) => e.stopPropagation()}>
        <h3 className="mb-1 text-lg font-bold">{modal.title}</h3>
        <p className="text-sm text-slate-500 dark:text-slate-300">{modal.message}</p>
        {modal.list && (
          <ul className="mt-3 space-y-1 rounded-xl border border-slate-200 p-3 text-sm dark:border-white/10">
            {modal.list.map((item) => (
              <li key={item} className="flex items-center gap-2">
                <span className="text-emerald-500">✔</span>
                {item}
              </li>
            ))}
          </ul>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <button className="btn btn-ghost" onClick={onCancel}>
            {modal.cancelLabel || 'Cancel'}
          </button>
          <button
            className={`btn ${modal.danger ? 'btn-danger' : 'btn-primary'}`}
            onClick={modal.onConfirm}
          >
            {modal.confirmLabel || 'Confirm'}
          </button>
        </div>
      </div>
    </div>
  )
}

// Accessible on/off switch matching the design system.
function Switch({ checked, onChange, label }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition ${
        checked ? 'bg-indigo-500' : 'bg-slate-300 dark:bg-white/15'
      }`}
    >
      <span
        className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition ${
          checked ? 'translate-x-5' : 'translate-x-0.5'
        }`}
      />
    </button>
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
