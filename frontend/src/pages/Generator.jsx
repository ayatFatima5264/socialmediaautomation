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
import { publishOutcome } from '../lib/publish'
import { loadFirstAvailable } from '../lib/imageLoader'
import {
  CONTENT_TYPES,
  CONTENT_TYPE_ORDER,
  contentTypeStates,
  isLinkedInOnly,
} from '../lib/contentTypes'
import PlatformIcon from '../components/PlatformIcon.jsx'
import ScheduleModal from '../components/ScheduleModal.jsx'
import { SourceDropdown, Accordion } from '../components/FormControls.jsx'

const STORAGE_KEY = 'composer_state_v1'

// "Create From" content sources. Each resolves to a source-text string that
// feeds the same generation pipeline, so the output stays consistent.
const SOURCE_TYPES = [
  { id: 'prompt', label: 'Prompt', icon: '✎' },
  { id: 'article', label: 'Article', icon: '📰' },
  { id: 'blog', label: 'Blog URL', icon: '🔗' },
  { id: 'website', label: 'Website URL', icon: '🌐' },
  { id: 'product', label: 'Product Page', icon: '🛍' },
  { id: 'existing', label: 'Existing Post', icon: '♺' },
  { id: 'youtube', label: 'YouTube', icon: '▶' },
  { id: 'file', label: 'PDF / DOCX', icon: '📄' },
  { id: 'text', label: 'Plain Text', icon: '🅣' },
  { id: 'image', label: 'Image', icon: '🖼' },
]

const URL_SOURCES = ['blog', 'website', 'product', 'youtube']
const URL_LABELS = { blog: 'Blog', website: 'Website', product: 'Product page', youtube: 'YouTube video' }

// Existing-post transforms — prepended as a directive to the pasted post.
const TRANSFORMS = {
  rewrite: 'Rewrite this social media post in a fresh way',
  improve: 'Improve and polish this social media post',
  expand: 'Expand this social media post with more detail',
  shorten: 'Shorten this social media post while keeping the key message',
  tone: 'Rewrite this social media post in a different tone',
}
const TRANSFORM_LABELS = {
  rewrite: 'Rewrite', improve: 'Improve', expand: 'Expand',
  shorten: 'Shorten', tone: 'Change Tone',
}

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

  // "Create From" source selection + per-source inputs.
  const [sourceType, setSourceType] = useState(SAVED?.sourceType ?? 'prompt')
  const [sourceText, setSourceText] = useState(SAVED?.sourceText ?? '') // article / text / existing
  const [sourceUrl, setSourceUrl] = useState(SAVED?.sourceUrl ?? '')
  const [transform, setTransform] = useState(SAVED?.transform ?? 'rewrite')
  const [extracted, setExtracted] = useState(null) // {title, text} from URL/file
  const [extractBusy, setExtractBusy] = useState(false)
  const [imageData, setImageData] = useState(null) // {dataUrl, name}
  const [imageNote, setImageNote] = useState(SAVED?.imageNote ?? '')
  const [activeSource, setActiveSource] = useState(SAVED?.activeSource ?? '') // text behind current results

  // Caption inputs (existing multi-platform behaviour, preserved).
  const [topic, setTopic] = useState(SAVED?.topic ?? '')
  const [tone, setTone] = useState(SAVED?.tone ?? 'professional')
  const [audience, setAudience] = useState(SAVED?.audience ?? '')
  const [selected, setSelected] = useState(SAVED?.selected ?? ['instagram', 'facebook'])
  const [includeHashtags, setIncludeHashtags] = useState(SAVED?.includeHashtags ?? true)
  const [variants, setVariants] = useState(SAVED?.variants ?? false)

  // Content type (Social Post / Image / Video / Carousel / Link / LinkedIn Article).
  const [contentType, setContentType] = useState(SAVED?.contentType ?? 'post')
  const [article, setArticle] = useState(SAVED?.article ?? null) // generated article result
  const [articleBusy, setArticleBusy] = useState(false)

  // Global image settings (apply to all selected platforms) + per-platform
  // overrides keyed by platform.
  const [img, setImg] = useState({ ...DEFAULT_IMAGE_SETTINGS, ...(SAVED?.img || {}) })
  const [overrides, setOverrides] = useState(SAVED?.overrides ?? {})
  const [showAdvanced, setShowAdvanced] = useState(false)
  // Advanced option groups are collapsed by default to keep the form compact.
  const [imgOpen, setImgOpen] = useState(false)
  const [ovOpen, setOvOpen] = useState(false)

  const [loading, setLoading] = useState(false)
  const [drafts, setDrafts] = useState(() =>
    (SAVED?.drafts || []).map((d) => ({
      ...d,
      imgLoading: false,
      imgError: d.imgError ?? null,
      capLoading: false,
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

  // Unsaved generated content = a generated article, or a card not yet
  // published/scheduled.
  const hasUnsaved =
    !!article || drafts.some((d) => !['published', 'scheduled'].includes(d.status))

  const ctStates = contentTypeStates(selected)

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
    const slim = drafts.map(({ imgLoading, capLoading, ...keep }) => keep)
    const payload = {
      topic, tone, audience, selected, includeHashtags, variants,
      img, overrides, meta, drafts: slim,
      sourceType, sourceText, sourceUrl, transform, imageNote, activeSource,
      contentType, article,
    }
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
    } catch {
      /* quota / serialization issues are non-fatal */
    }
  }, [topic, tone, audience, selected, includeHashtags, variants, img, overrides, meta, drafts,
    sourceType, sourceText, sourceUrl, transform, imageNote, activeSource, contentType, article])

  function togglePlatform(p) {
    const adding = !selected.includes(p)
    // Adding another platform while a LinkedIn Article is in play needs a choice.
    if (contentType === 'article' && adding && p !== 'linkedin') {
      setConfirmModal({
        title: 'LinkedIn Article Not Supported',
        message:
          'LinkedIn Articles can only be published to LinkedIn. Choose how you want to continue.',
        actions: [
          { label: 'Keep LinkedIn Only', variant: 'primary', onClick: () => setConfirmModal(null) },
          {
            label: 'Convert to Social Post',
            variant: 'ghost',
            onClick: () => convertArticleToPost(p),
          },
          { label: 'Cancel', variant: 'ghost', onClick: () => setConfirmModal(null) },
        ],
      })
      return
    }
    setSelected((s) => (s.includes(p) ? s.filter((x) => x !== p) : [...s, p]))
  }

  function useLinkedInOnly() {
    setSelected(['linkedin'])
    setContentType('article')
  }

  // Keep the content type valid for the selection (silent fallback to post).
  useEffect(() => {
    if (contentType !== 'post' && !ctStates[contentType]?.enabled && !article) {
      setContentType('post')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected])

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

  function captionBase(topicText) {
    return {
      topic: topicText,
      tone,
      audience: audience || null,
      include_hashtags: includeHashtags,
      variants,
    }
  }

  // --- "Create From" source handling ---------------------------------------
  // Can we attempt a generation? (cheap, synchronous check — no network).
  function sourceReady() {
    switch (sourceType) {
      case 'prompt': return !!topic.trim()
      case 'article':
      case 'text':
      case 'existing': return !!sourceText.trim()
      case 'file': return !!extracted?.text
      case 'image': return !!imageData
      default: return URL_SOURCES.includes(sourceType) ? !!sourceUrl.trim() : false
    }
  }

  const SOURCE_HINTS = {
    prompt: 'Please describe your idea first',
    article: 'Paste the article text first',
    text: 'Paste some text first',
    existing: 'Paste the post you want to transform',
    file: 'Upload a document first',
    image: 'Upload an image first',
  }

  async function doExtractUrl() {
    const url = sourceUrl.trim()
    if (!url) throw new Error('Enter a URL first')
    setExtractBusy(true)
    try {
      const res = await api.extractUrl(url)
      const ex = { title: res.title, text: res.text }
      setExtracted(ex)
      return ex
    } finally {
      setExtractBusy(false)
    }
  }

  function fetchUrl() {
    doExtractUrl()
      .then((ex) => toast.success(`Fetched ${ex.text.length} characters`))
      .catch((err) => toast.error(err.message || 'Could not fetch that URL'))
  }

  async function handleDocFile(file) {
    if (!file) return
    setExtractBusy(true)
    try {
      const res = await api.extractFile(file)
      setExtracted({ title: file.name, text: res.text })
      toast.success(`Read ${res.text.length} characters from ${file.name}`)
    } catch (err) {
      setExtracted(null)
      toast.error(err.message || 'Could not read that file')
    } finally {
      setExtractBusy(false)
    }
  }

  function handleImageFile(file) {
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => setImageData({ dataUrl: reader.result, name: file.name })
    reader.readAsDataURL(file)
  }

  // Resolve the selected source into { text, imageOverride } (may fetch).
  async function resolveSource() {
    switch (sourceType) {
      case 'prompt':
        return { text: topic.trim() }
      case 'article':
      case 'text':
        return { text: sourceText.trim() }
      case 'existing':
        return { text: `${TRANSFORMS[transform]}:\n\n${sourceText.trim()}` }
      case 'file':
        if (!extracted?.text) throw new Error('Upload a document first')
        return { text: extracted.text }
      case 'image':
        if (!imageData) throw new Error('Upload an image first')
        return {
          text: `A social media post about ${imageNote.trim() || 'this image'}.`,
          imageOverride: imageData.dataUrl,
        }
      default: {
        // URL sources — use the fetched content, or fetch now.
        const ex = extracted || (await doExtractUrl())
        if (!ex?.text) throw new Error('Fetch the content first')
        return { text: ex.text }
      }
    }
  }

  // --- generation -----------------------------------------------------------
  function generate(e) {
    e.preventDefault()
    if (busyRef.current) return
    if (!sourceReady()) return toast.error(SOURCE_HINTS[sourceType] || 'Add a source first')
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
          startGeneration()
        },
      })
      return
    }
    startGeneration()
  }

  function startGeneration() {
    if (contentType === 'article') runGenerateArticle()
    else runGenerate()
  }

  // Apply content-type intent to a card's image settings.
  function withContentType(settings) {
    if (contentType === 'image') return { ...settings, aiImage: true, carousel: false }
    if (contentType === 'carousel') return { ...settings, aiImage: true, carousel: true }
    if (contentType === 'video') return { ...settings, aiImage: false } // no AI video
    return settings
  }

  async function runGenerate({ preResolved, platformsOverride } = {}) {
    busyRef.current = true
    setLoading(true)

    // Resolve the chosen source first (URLs/files may fetch). Don't clear
    // existing results until we know we have usable source text.
    let resolved = preResolved
    if (!resolved) {
      try {
        resolved = await resolveSource()
      } catch (err) {
        setLoading(false)
        busyRef.current = false
        return toast.error(err.message || 'Could not read that source')
      }
    }
    const sourceText = (resolved.text || '').trim()
    if (sourceText.length < 2) {
      setLoading(false)
      busyRef.current = false
      return toast.error('Not enough content to generate from')
    }

    setArticle(null) // normal posts replace any prior article
    setActiveSource(sourceText)
    setDrafts([])
    try {
      const platforms = platformsOverride || (selected.length ? selected : PLATFORM_KEYS)
      const base = captionBase(sourceText)

      // 1. Captions — one request per platform (existing multi-platform flow).
      const responses = await Promise.all(
        platforms.map((p) => api.generate({ ...base, platform: p })),
      )
      const cards = responses.flatMap((r) =>
        r.results.map((res) => ({
          platform: res.platform,
          content: res.text,
          hashtags: formatHashtags(res.hashtags),
          imagePrompt: sourceText, // base prompt for image (re)generation
          settings: withContentType(resolveSettings(img, overrides[res.platform])),
          // Image source: use the uploaded image directly instead of AI gen.
          images: resolved.imageOverride
            ? [{ url: resolved.imageOverride, label: null }]
            : [],
          imgLoading: false,
          imgError: null,
          capLoading: false,
        })),
      )
      setDrafts(cards)
      setMeta({ provider: responses[0]?.provider, model: responses[0]?.model })
      toast.success(`Generated ${cards.length} caption(s)`)

      // 2. Images — independent per card; skipped when the user supplied one.
      if (!resolved.imageOverride) {
        cards.forEach((c, i) => {
          if (c.settings.aiImage) generateCardImages(i, c)
        })
      }
    } catch (err) {
      toast.error(err.message || 'Generation failed')
    } finally {
      setLoading(false)
      busyRef.current = false
    }
  }

  // --- LinkedIn Article generation -----------------------------------------
  async function runGenerateArticle() {
    busyRef.current = true
    setArticleBusy(true)
    let resolved
    try {
      resolved = await resolveSource()
    } catch (err) {
      setArticleBusy(false)
      busyRef.current = false
      return toast.error(err.message || 'Could not read that source')
    }
    const sourceText = (resolved.text || '').trim()
    setActiveSource(sourceText)
    setDrafts([])
    setArticle(null)
    try {
      const a = await api.generateArticle({
        topic: sourceText,
        audience: audience || null,
        tone,
      })
      const readingMin = a.reading_time_min
      // Build cover-image candidates (16:9) via the same image pipeline.
      let cover = null
      try {
        const imgRes = await api.generateImages({
          prompt: a.cover_image_prompt || a.title,
          aspect_ratio: '16:9',
          style: img.style,
          quality: img.quality,
        })
        cover = imgRes.images[0]
      } catch {
        /* cover is optional — the article still stands without it */
      }
      setArticle({
        title: a.title,
        body: a.body,
        tags: a.tags,
        seoKeywords: a.seo_keywords,
        readingTime: readingMin,
        cover, // {url, fallbacks} | null
        coverPrompt: a.cover_image_prompt || a.title,
        status: null,
      })
      setMeta({ provider: a.provider, model: a.model })
      toast.success('Article generated')
    } catch (err) {
      toast.error(err.message || 'Article generation failed')
    } finally {
      setArticleBusy(false)
      busyRef.current = false
    }
  }

  // Convert an in-progress article into a normal multi-platform post: the
  // article body becomes the source and AI re-summarizes it per platform.
  function convertArticleToPost(addPlatform) {
    const body = article?.body || activeSource
    const newSelected = selected.includes(addPlatform)
      ? selected
      : [...selected, addPlatform]
    setContentType('post')
    setSourceType('text')
    setSourceText(body)
    setSelected(newSelected)
    setArticle(null)
    setConfirmModal(null)
    runGenerate({ preResolved: { text: body }, platformsOverride: newSelected })
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
      const r = await api.generate({
        ...captionBase(c.imagePrompt || activeSource),
        platform: c.platform,
      })
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
  // and Publish All). Returns the publish outcome; never throws.
  async function publishCard(i) {
    const c = drafts[i]
    const label = PLATFORMS[c.platform]?.label || c.platform
    updateDraft(i, { status: 'publishing', publishError: null })
    try {
      const created = await api.createPost({
        platform: c.platform,
        content: c.content,
        hashtags: hashtagList(c.hashtags),
        // Attach the generated visuals so platforms that need/support media
        // (Instagram, X, LinkedIn) publish with the image, not text-only.
        media: (c.images || [])
          .filter((im) => im?.url)
          .map((im) => ({ type: 'image', url: im.url })),
      })
      // The publish endpoint returns the updated post — inspect it for the real
      // outcome (a non-throwing response can still be a platform failure).
      const post = await api.publishPost(created.id)
      const outcome = publishOutcome(post, label)
      updateDraft(i, {
        status: outcome.ok ? 'published' : 'failed',
        publishError: outcome.ok ? null : outcome.message,
      })
      return outcome
    } catch (err) {
      updateDraft(i, { status: 'failed', publishError: err.message })
      return { ok: false, simulated: false, message: err.message }
    }
  }

  async function publishNow(i) {
    const outcome = await publishCard(i)
    if (outcome.ok) toast.success(outcome.message)
    else toast.error(outcome.message || 'Publish failed')
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
      const ok = results.filter((r) => r.status === 'fulfilled' && r.value?.ok).length
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

  // --- article actions ------------------------------------------------------
  function updateArticle(patch) {
    setArticle((a) => (a ? { ...a, ...patch } : a))
  }

  function articleContent() {
    return `${article.title}\n\n${article.body}`
  }

  async function saveArticleDraft() {
    if (!article) return
    updateArticle({ status: 'publishing' })
    try {
      await api.createPost({
        platform: 'linkedin', content: articleContent(), hashtags: article.tags,
        media: article.cover?.url
          ? [{ type: 'image', url: article.cover.url }]
          : [],
      })
      updateArticle({ status: 'saved' })
      toast.success('Article saved as draft')
    } catch (err) {
      updateArticle({ status: null })
      toast.error(err.message || 'Could not save the article')
    }
  }

  async function publishArticleLinkedIn() {
    if (!article) return
    updateArticle({ status: 'publishing' })
    try {
      const created = await api.createPost({
        platform: 'linkedin', content: articleContent(), hashtags: article.tags,
        // Attach the article cover so LinkedIn publishes it with the article.
        media: article.cover?.url
          ? [{ type: 'image', url: article.cover.url }]
          : [],
      })
      const post = await api.publishPost(created.id)
      const outcome = publishOutcome(post, 'LinkedIn')
      updateArticle({ status: outcome.ok ? 'published' : null })
      if (outcome.ok) toast.success(outcome.message)
      else toast.error(outcome.message)
    } catch (err) {
      updateArticle({ status: null })
      toast.error(err.message || 'LinkedIn publish failed')
    }
  }

  async function regenerateCover() {
    if (!article) return
    try {
      const imgRes = await api.generateImages({
        prompt: article.coverPrompt, aspect_ratio: '16:9',
        style: img.style, quality: img.quality,
      })
      updateArticle({ cover: imgRes.images[0] })
    } catch (err) {
      toast.error(err.message || 'Cover regeneration failed')
    }
  }

  const platformsForOverride = selected.length ? selected : []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">AI Generator</h1>
        <p className="text-sm text-muted">
          Describe an idea — get platform-optimized captions and AI images you control.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[380px_1fr]">
        {/* ---- Input panel ---- */}
        <form onSubmit={generate} className="card h-fit space-y-5 p-5">
          {/* Step 0 — Create From (single dropdown, was a 10-pill grid) */}
          <div>
            <label className="label">Create from</label>
            <SourceDropdown
              options={SOURCE_TYPES}
              value={sourceType}
              onChange={(id) => {
                setSourceType(id)
                setExtracted(null) // sources don't share fetched content
              }}
            />
          </div>

          {/* Step 1 — Source input (only the relevant field shows) */}
          {sourceType === 'prompt' && (
            <div>
              <label className="label" htmlFor="topic">Describe your idea</label>
              <textarea
                id="topic"
                className="input min-h-24 resize-y"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="e.g. A post about the launch of our new eco-friendly coffee beans"
              />
            </div>
          )}

          {(sourceType === 'article' || sourceType === 'text') && (
            <div>
              <label className="label">
                {sourceType === 'article' ? 'Paste article' : 'Plain text'}
              </label>
              <textarea
                className="input min-h-36 resize-y"
                value={sourceText}
                onChange={(e) => setSourceText(e.target.value)}
                placeholder="Paste the text to turn into platform-ready posts…"
              />
              <div className="mt-1 text-right text-xs text-muted">
                {sourceText.length.toLocaleString()} chars
              </div>
            </div>
          )}

          {sourceType === 'existing' && (
            <div className="space-y-2">
              <div>
                <label className="label">Existing post</label>
                <textarea
                  className="input min-h-28 resize-y"
                  value={sourceText}
                  onChange={(e) => setSourceText(e.target.value)}
                  placeholder="Paste your existing social media post…"
                />
              </div>
              <div>
                <label className="label">Action</label>
                <select
                  className="select"
                  value={transform}
                  onChange={(e) => setTransform(e.target.value)}
                >
                  {Object.keys(TRANSFORMS).map((k) => (
                    <option key={k} value={k}>{TRANSFORM_LABELS[k]}</option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {URL_SOURCES.includes(sourceType) && (
            <div>
              <label className="label">{URL_LABELS[sourceType]} URL</label>
              <div className="flex gap-2">
                <input
                  className="input"
                  value={sourceUrl}
                  onChange={(e) => {
                    setSourceUrl(e.target.value)
                    setExtracted(null)
                  }}
                  placeholder={sourceType === 'youtube' ? 'https://youtube.com/watch?v=…' : 'https://…'}
                />
                <button
                  type="button"
                  onClick={fetchUrl}
                  disabled={extractBusy}
                  className="btn btn-ghost btn-sm whitespace-nowrap"
                >
                  {extractBusy ? 'Fetching…' : 'Fetch Content'}
                </button>
              </div>
              {extracted && <ExtractedPreview extracted={extracted} onClear={() => setExtracted(null)} />}
            </div>
          )}

          {sourceType === 'file' && (
            <div>
              <label className="label">Upload PDF, DOCX or TXT</label>
              <input
                type="file"
                accept=".pdf,.docx,.txt,.md"
                className="block w-full text-sm text-muted file:mr-3 file:rounded-lg file:border-0 file:bg-accent-soft file:px-3 file:py-1.5 file:text-accent"
                onChange={(e) => handleDocFile(e.target.files?.[0])}
              />
              {extractBusy && <div className="mt-2 text-xs text-muted">Reading document…</div>}
              {extracted && <ExtractedPreview extracted={extracted} onClear={() => setExtracted(null)} />}
            </div>
          )}

          {sourceType === 'image' && (
            <div className="space-y-2">
              <div>
                <label className="label">Upload image</label>
                <input
                  type="file"
                  accept="image/*"
                  className="block w-full text-sm text-muted file:mr-3 file:rounded-lg file:border-0 file:bg-accent-soft file:px-3 file:py-1.5 file:text-accent"
                  onChange={(e) => handleImageFile(e.target.files?.[0])}
                />
                {imageData && (
                  <img
                    src={imageData.dataUrl}
                    alt={imageData.name}
                    className="mt-2 max-h-40 rounded-xl object-cover"
                  />
                )}
              </div>
              <div>
                <label className="label">What's it about? (optional)</label>
                <input
                  className="input"
                  value={imageNote}
                  onChange={(e) => setImageNote(e.target.value)}
                  placeholder="e.g. our new product launch photo"
                />
                <p className="mt-1 text-xs text-muted">
                  Your image becomes the post visual; add a note to steer the caption.
                </p>
              </div>
            </div>
          )}

          <div>
            <label className="label" htmlFor="tone">
              Tone
            </label>
            <select
              id="tone"
              className="select"
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

          {/* Step 2 — Platforms (icon-only circular toggles) */}
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
                    aria-label={PLATFORMS[p].label}
                    title={PLATFORMS[p].label}
                    onClick={() => togglePlatform(p)}
                    className={`grid h-8 w-8 shrink-0 place-items-center rounded-full border transition ${
                      on
                        ? 'border-accent bg-accent-soft ring-1 ring-accent'
                        : 'border-line text-muted hover:bg-inset'
                    }`}
                  >
                    <PlatformIcon platform={p} size={18} />
                  </button>
                )
              })}
            </div>
          </div>

          {/* Content Type — segmented control */}
          <div>
            <label className="label">Content type</label>
            <div className="flex flex-wrap gap-1 rounded-xl border border-line bg-inset p-1">
              {CONTENT_TYPE_ORDER.map((id) => {
                const ct = CONTENT_TYPES[id]
                const st = ctStates[id]
                const enabled = st?.enabled
                const active = contentType === id
                return (
                  <button
                    type="button"
                    key={id}
                    disabled={!enabled}
                    aria-pressed={active}
                    title={enabled ? ct.label : st?.reason}
                    onClick={() => enabled && setContentType(id)}
                    className={`flex min-w-[84px] flex-1 items-center justify-center gap-1 rounded-lg px-2 py-1.5 text-xs font-medium transition ${
                      active
                        ? 'bg-accent text-accent-contrast'
                        : enabled
                          ? 'text-muted hover:bg-surface'
                          : 'cursor-not-allowed text-muted opacity-50'
                    }`}
                  >
                    <span>{enabled ? ct.icon : '🔒'}</span>
                    {ct.label}
                  </button>
                )
              })}
            </div>

            {/* Actionable affordance for the locked LinkedIn Article type
                (the per-type "why" now lives in each segment's tooltip). */}
            {ctStates.article && !ctStates.article.enabled && !isLinkedInOnly(selected) && !article && (
              <button
                type="button"
                onClick={useLinkedInOnly}
                className="btn btn-primary btn-sm mt-2"
              >
                🔒 LinkedIn Article — switch to LinkedIn only
              </button>
            )}
          </div>

          {/* Step 3 — Image Settings (collapsible) — hidden in Article mode */}
          {contentType !== 'article' && (
            <Accordion
              title="Image Settings"
              open={imgOpen}
              onToggle={() => setImgOpen((v) => !v)}
            >
              <label className="flex items-center justify-between text-sm">
                <span>AI Image</span>
                <Switch
                  checked={img.aiImage}
                  onChange={(v) => updateImg({ aiImage: v })}
                  label="AI Image"
                />
              </label>
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
                      className="select"
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
            </Accordion>
          )}

          {/* Per-platform overrides (collapsible) */}
          {contentType !== 'article' && platformsForOverride.length > 0 && (
            <Accordion
              title="Per-platform overrides"
              open={ovOpen}
              onToggle={() => setOvOpen((v) => !v)}
            >
              <div className="space-y-2">
              <p className="text-xs text-muted">
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
                    className="rounded-xl border border-line p-3 text-sm"
                  >
                    <div className="flex items-center justify-between">
                      <span className="flex items-center gap-2 font-medium">
                        <PlatformIcon platform={p} size={18} />
                        {PLATFORMS[p].label}
                        <span className="text-[11px] font-normal text-muted">
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
                            ? 'border-accent bg-accent-soft text-accent'
                            : 'border-line text-muted hover:bg-inset'
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
                          <p className="text-xs text-muted">
                            Caption only — no image for {PLATFORMS[p].label}.
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
              </div>
            </Accordion>
          )}

          {/* Step 4 — Advanced (collapsed) */}
          <div className="rounded-xl border border-line">
            <button
              type="button"
              onClick={() => setShowAdvanced((v) => !v)}
              aria-expanded={showAdvanced}
              className="flex w-full items-center justify-between px-3 py-2 text-sm font-medium"
            >
              Advanced Settings
              <span className="text-muted">{showAdvanced ? '▲' : '▼'}</span>
            </button>
            {showAdvanced && (
              <div className="space-y-3 border-t border-line p-3">
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
                    <div className="border-t border-line pt-3">
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
                        className="select"
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
                    <div className="flex items-center gap-2 text-xs text-muted">
                      <span className="rounded-md border border-dashed border-line px-2 py-1">
                        Brand Kit · coming soon
                      </span>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>

          {/* Step 5 — Generate */}
          <button className="btn btn-primary w-full" disabled={loading || articleBusy}>
            {loading || articleBusy
              ? 'Generating…'
              : contentType === 'article'
                ? '✦ Generate Article'
                : '✦ Generate'}
          </button>
        </form>

        {/* ---- Output panel ---- */}
        <div className="space-y-4">
          {/* Article mode renders a dedicated editor */}
          {contentType === 'article' ? (
            articleBusy ? (
              <CardSkeleton />
            ) : article ? (
              <ArticleEditor
                article={article}
                onChange={updateArticle}
                onRegenCover={regenerateCover}
                onSave={saveArticleDraft}
                onPublish={publishArticleLinkedIn}
              />
            ) : (
              <div className="card grid place-items-center p-12 text-center text-muted">
                <div>
                  <div className="mb-3 text-5xl">📰</div>
                  <div className="font-medium text-muted">
                    Describe your idea and let AI write a LinkedIn article.
                  </div>
                  <div className="mt-1 text-sm text-muted">
                    Title, cover, body, tags and SEO keywords — all editable.
                  </div>
                </div>
              </div>
            )
          ) : (
          <>
          {/* Global action bar (sticky) */}
          {drafts.length > 0 && (
            <div className="sticky top-2 z-10 flex flex-wrap items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2 shadow-sm backdrop-blur">
              <span className="text-xs text-muted">
                {drafts.length} platform{drafts.length > 1 ? 's' : ''}
                {meta && (
                  <>
                    {' · '}
                    <span className="font-semibold text-accent">{meta.provider}</span>
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
            <div className="card grid place-items-center p-12 text-center text-muted">
              <div>
                <div className="mb-3 text-5xl">✦</div>
                <div className="font-medium text-muted">
                  Describe your idea and let AI generate platform-ready content.
                </div>
                <div className="mt-1 text-sm text-muted">
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
              onClearPlatform={() => clearPlatform(i)}
              onDuplicate={() => duplicatePlatform(i)}
            />
          ))}
          </>
          )}
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
          className="select"
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
            className="select"
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
  onSave, onSchedule, onPublish, onClearPlatform, onDuplicate,
}) {
  const over = c.content.length > limit
  const isCarousel = c.settings.carousel && c.images.length > 1

  return (
    <div className="card p-5">
      <div className="mb-3 flex items-center gap-2">
        <PlatformIcon platform={c.platform} />
        <span className="font-semibold">{label}</span>
        {c.settings.aiImage && (
          <span className="badge bg-inset text-muted">
            {c.settings.aspectRatio}
            {c.settings.carousel ? ` · ${c.settings.slides} slides` : ''}
          </span>
        )}
        <StatusChip status={c.status} error={c.publishError} />
        <div className="ml-auto flex items-center gap-2">
          <span className={`text-xs ${over ? 'text-rose-400' : 'text-muted'}`}>
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
            <div className="flex items-center gap-2 text-sm text-muted">
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
                      <figcaption className="mt-1 flex items-center justify-between gap-1 text-[11px] text-muted">
                        <span className="truncate">
                          {idx + 1}. {im.label}
                        </span>
                        <button
                          onClick={() => onRegenSlide(idx)}
                          className="shrink-0 underline hover:text-accent"
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
        className="grid place-items-center rounded-xl border border-dashed border-line text-center text-xs text-muted"
        style={{ aspectRatio: ratio }}
      >
        <div>
          <div>Image unavailable</div>
          <button
            type="button"
            onClick={() => setReloadKey((k) => k + 1)}
            className="mt-1 underline hover:text-accent"
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
    saved: { text: '✓ Saved', cls: 'bg-inset text-muted' },
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
        className="grid h-7 w-7 place-items-center rounded-lg text-lg text-muted hover:bg-inset"
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
                className={`block w-full rounded-lg px-3 py-2 text-left hover:bg-inset ${
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
        <p className="text-sm text-muted">{modal.message}</p>
        {modal.list && (
          <ul className="mt-3 space-y-1 rounded-xl border border-line p-3 text-sm">
            {modal.list.map((item) => (
              <li key={item} className="flex items-center gap-2">
                <span className="text-emerald-500">✔</span>
                {item}
              </li>
            ))}
          </ul>
        )}
        <div className="mt-5 flex flex-wrap justify-end gap-2">
          {modal.actions ? (
            modal.actions.map((a) => (
              <button
                key={a.label}
                onClick={a.onClick}
                className={`btn ${a.variant === 'primary' ? 'btn-primary' : a.variant === 'danger' ? 'btn-danger' : 'btn-ghost'}`}
              >
                {a.label}
              </button>
            ))
          ) : (
            <>
              <button className="btn btn-ghost" onClick={onCancel}>
                {modal.cancelLabel || 'Cancel'}
              </button>
              <button
                className={`btn ${modal.danger ? 'btn-danger' : 'btn-primary'}`}
                onClick={modal.onConfirm}
              >
                {modal.confirmLabel || 'Confirm'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// LinkedIn Article editor — title, cover, rich body, tags, SEO, reading time.
function ArticleEditor({ article, onChange, onRegenCover, onSave, onPublish }) {
  const [showPreview, setShowPreview] = useState(false)
  const words = article.body.trim() ? article.body.trim().split(/\s+/).length : 0
  const readingTime = Math.max(1, Math.round(words / 200))

  return (
    <div className="card space-y-4 p-5">
      <div className="flex items-center gap-2">
        <PlatformIcon platform="linkedin" />
        <span className="font-semibold">LinkedIn Article</span>
        <StatusChip status={article.status} />
        <span className="ml-auto text-xs text-muted">
          {words} words · {readingTime} min read
        </span>
      </div>

      {/* Cover image */}
      <div>
        {article.cover ? (
          <figure className="group relative">
            <SmartImage
              candidates={[article.cover.url, ...(article.cover.fallbacks || [])]}
              alt="Article cover"
              aspectRatio="16:9"
            />
          </figure>
        ) : (
          <div className="grid aspect-[16/9] w-full place-items-center rounded-xl border border-dashed border-line text-sm text-muted">
            No cover image
          </div>
        )}
        <button onClick={onRegenCover} className="btn btn-ghost btn-sm mt-2">
          ↻ Regenerate Cover
        </button>
      </div>

      {!showPreview ? (
        <>
          <div>
            <label className="label">Title</label>
            <input
              className="input text-lg font-semibold"
              value={article.title}
              onChange={(e) => onChange({ title: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Article body</label>
            <textarea
              className="input min-h-80 resize-y leading-relaxed"
              value={article.body}
              onChange={(e) => onChange({ body: e.target.value })}
            />
          </div>
          <TagEditor label="Tags" tags={article.tags} onChange={(tags) => onChange({ tags })} />
          <TagEditor
            label="SEO keywords"
            tags={article.seoKeywords}
            onChange={(seoKeywords) => onChange({ seoKeywords })}
          />
        </>
      ) : (
        <article className="prose-sm max-w-none">
          <h1 className="text-2xl font-bold">{article.title}</h1>
          <div className="mt-1 text-xs text-muted">{readingTime} min read</div>
          <div className="mt-3 whitespace-pre-wrap text-sm leading-relaxed">{article.body}</div>
          {article.tags.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-1.5">
              {article.tags.map((t) => (
                <span key={t} className="badge bg-accent-soft text-accent">#{t}</span>
              ))}
            </div>
          )}
        </article>
      )}

      <div className="flex flex-wrap gap-2 border-t border-line pt-3">
        <button onClick={() => setShowPreview((p) => !p)} className="btn btn-ghost btn-sm">
          {showPreview ? '✎ Edit' : '👁 Preview'}
        </button>
        <button onClick={onSave} className="btn btn-ghost btn-sm">Save Draft</button>
        <button
          onClick={onPublish}
          disabled={article.status === 'publishing'}
          className="btn btn-sm bg-[#0A66C2] text-white hover:brightness-110"
        >
          {article.status === 'publishing' ? 'Publishing…' : 'Publish to LinkedIn'}
        </button>
      </div>
    </div>
  )
}

// Chip-style tag editor (Enter/comma to add, × to remove).
function TagEditor({ label, tags, onChange }) {
  const [draft, setDraft] = useState('')
  function commit() {
    const next = draft.split(/[\s,]+/).map((t) => t.replace(/^#/, '').trim()).filter(Boolean)
    if (next.length) onChange(Array.from(new Set([...tags, ...next])))
    setDraft('')
  }
  return (
    <div>
      <label className="label">{label}</label>
      <div className="flex flex-wrap gap-1.5">
        {tags.map((t) => (
          <span key={t} className="badge bg-inset text-muted">
            {t}
            <button onClick={() => onChange(tags.filter((x) => x !== t))} className="ml-1 hover:text-rose-400">×</button>
          </span>
        ))}
      </div>
      <input
        className="input mt-2"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault()
            commit()
          }
        }}
        onBlur={commit}
        placeholder={`Add ${label.toLowerCase()}…`}
      />
    </div>
  )
}

// Small preview of text extracted from a URL or document.
function ExtractedPreview({ extracted, onClear }) {
  return (
    <div className="mt-2 rounded-xl border border-line bg-inset p-2.5 text-xs">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="truncate font-medium text-muted">
          ✓ {extracted.title || 'Extracted content'} · {extracted.text.length.toLocaleString()} chars
        </span>
        <button
          type="button"
          onClick={onClear}
          className="shrink-0 text-muted hover:text-rose-400"
        >
          Clear
        </button>
      </div>
      <p className="line-clamp-3 text-muted">
        {extracted.text.slice(0, 240)}…
      </p>
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
        checked ? 'bg-accent' : 'bg-inset'
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
