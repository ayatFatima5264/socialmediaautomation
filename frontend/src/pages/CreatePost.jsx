import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useToast } from '../context/ToastContext.jsx'
import { useAuth } from '../context/AuthContext.jsx'
import { PLATFORMS, PLATFORM_KEYS } from '../lib/constants'
import { localInputToISO } from '../lib/datetime'
import PlatformIcon from '../components/PlatformIcon.jsx'

const EMOJIS = ['😀', '😂', '🙌', '🔥', '✨', '🎉', '❤️', '👍', '🚀', '💡',
  '📈', '🙏', '😎', '🤝', '📢', '🌟', '✅', '💪', '👀', '🎯']

// Platforms that surface a dedicated "first comment" field in their UI.
const FIRST_COMMENT_PLATFORMS = new Set(['instagram', 'linkedin'])

function minLocal() {
  const d = new Date(Date.now() + 60_000)
  d.setSeconds(0, 0)
  const tz = d.getTimezoneOffset()
  return new Date(d.getTime() - tz * 60_000).toISOString().slice(0, 16)
}

export default function CreatePost() {
  const toast = useToast()
  const navigate = useNavigate()
  const { user } = useAuth()

  const [selected, setSelected] = useState(['instagram', 'facebook'])
  const [content, setContent] = useState('')
  const [media, setMedia] = useState([]) // {id, url, type, name}
  const [link, setLink] = useState('')
  const [hashtags, setHashtags] = useState([])
  const [hashtagDraft, setHashtagDraft] = useState('')
  const [location, setLocation] = useState('')
  const [firstComment, setFirstComment] = useState('')
  const [scheduleMode, setScheduleMode] = useState('now') // 'now' | 'later'
  const [scheduleAt, setScheduleAt] = useState(minLocal())
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null) // success summary
  const [activeTab, setActiveTab] = useState('instagram')

  const textRef = useRef(null)
  const fileRef = useRef(null)
  const [emojiOpen, setEmojiOpen] = useState(false)

  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone

  // Keep the preview tab on a platform that's actually selected.
  useEffect(() => {
    if (selected.length && !selected.includes(activeTab)) setActiveTab(selected[0])
  }, [selected, activeTab])

  // Revoke object URLs when media is removed / on unmount.
  useEffect(() => {
    return () => media.forEach((m) => URL.revokeObjectURL(m.url))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function togglePlatform(p) {
    setSelected((s) => (s.includes(p) ? s.filter((x) => x !== p) : [...s, p]))
  }

  // --- text editor helpers --------------------------------------------------
  function applyToSelection(transform, { block = false } = {}) {
    const el = textRef.current
    if (!el) return
    const start = el.selectionStart
    const end = el.selectionEnd
    const before = content.slice(0, start)
    const sel = content.slice(start, end)
    const after = content.slice(end)
    const next = transform(sel || '')
    const updated = before + next + after
    setContent(updated)
    requestAnimationFrame(() => {
      el.focus()
      const caret = before.length + next.length
      el.setSelectionRange(caret, caret)
    })
    void block
  }

  function insertAtCursor(text) {
    applyToSelection((sel) => sel + text)
  }

  function wrap(marker) {
    applyToSelection((sel) => `${marker}${sel || 'text'}${marker}`)
  }

  function prefixLines(makePrefix) {
    applyToSelection((sel) => {
      const lines = (sel || 'item').split('\n')
      return lines.map((l, i) => `${makePrefix(i)}${l}`).join('\n')
    })
  }

  function insertLink() {
    const url = window.prompt('Link URL', 'https://')
    if (!url) return
    applyToSelection((sel) => `${sel || url} (${url})`)
  }

  // --- hashtags -------------------------------------------------------------
  function commitHashtag() {
    const tags = hashtagDraft
      .split(/[\s,]+/)
      .map((t) => t.replace(/^#/, '').trim())
      .filter(Boolean)
    if (tags.length) {
      setHashtags((h) => Array.from(new Set([...h, ...tags])))
    }
    setHashtagDraft('')
  }

  function removeHashtag(tag) {
    setHashtags((h) => h.filter((t) => t !== tag))
  }

  // --- media ----------------------------------------------------------------
  function addFiles(fileList) {
    const items = Array.from(fileList).map((file) => {
      const type = file.type.startsWith('video')
        ? 'video'
        : file.type === 'image/gif'
          ? 'gif'
          : 'image'
      return { id: `${file.name}-${file.size}-${file.lastModified}`, url: URL.createObjectURL(file), type, name: file.name }
    })
    setMedia((m) => [...m, ...items.filter((it) => !m.some((x) => x.id === it.id))])
  }

  function onDrop(e) {
    e.preventDefault()
    if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files)
  }

  function removeMedia(id) {
    setMedia((m) => {
      const found = m.find((x) => x.id === id)
      if (found) URL.revokeObjectURL(found.url)
      return m.filter((x) => x.id !== id)
    })
  }

  function moveMedia(idx, dir) {
    setMedia((m) => {
      const next = [...m]
      const j = idx + dir
      if (j < 0 || j >= next.length) return m
      ;[next[idx], next[j]] = [next[j], next[idx]]
      return next
    })
  }

  // --- derived: per-platform warnings --------------------------------------
  const charCount = content.length
  const imageCount = media.filter((m) => m.type !== 'video').length

  const warnings = useMemo(() => {
    const out = {}
    for (const p of selected) {
      const list = []
      const limit = PLATFORMS[p]?.limit || 0
      if (limit && charCount > limit) {
        list.push(`Exceeds ${PLATFORMS[p].label} limit by ${charCount - limit} chars`)
      }
      if (p === 'instagram' && imageCount === 0) {
        list.push('Instagram requires at least one image')
      }
      if (p === 'pinterest' && imageCount === 0) {
        list.push('Pinterest needs an image (portrait recommended)')
      }
      if (p === 'twitter' && charCount > 280) {
        list.push('X character limit exceeded')
      }
      if (!content.trim() && hashtags.length === 0) {
        list.push('Add a caption (text or hashtags) to publish')
      }
      out[p] = list
    }
    return out
  }, [selected, charCount, imageCount, content, hashtags])

  const hasBlockingIssue = selected.some((p) => (warnings[p] || []).length > 0)

  // --- actions --------------------------------------------------------------
  function clearAll() {
    media.forEach((m) => URL.revokeObjectURL(m.url))
    setContent('')
    setMedia([])
    setLink('')
    setHashtags([])
    setHashtagDraft('')
    setLocation('')
    setFirstComment('')
    setScheduleMode('now')
    setScheduleAt(minLocal())
  }

  async function submit(asDraft = false) {
    if (!selected.length) return toast.error('Select at least one platform')
    // The backend stores text posts, so a caption (text or hashtags) is required.
    const text = content.trim() || hashtags.map((t) => `#${t}`).join(' ')
    if (!text) return toast.error('Add a caption (text or hashtags) first')
    if (busy) return

    setBusy(true)
    try {
      const scheduled = !asDraft && scheduleMode === 'later'
      const body = {
        content: text,
        hashtags,
        ...(scheduled ? { scheduled_time: localInputToISO(scheduleAt) } : {}),
      }
      // One post per platform (mirrors the rest of the app).
      const created = await Promise.all(
        selected.map((p) => api.createPost({ ...body, platform: p })),
      )
      if (!asDraft && scheduleMode === 'now') {
        await Promise.all(created.map((post) => api.publishPost(post.id)))
      }

      if (asDraft) {
        toast.success(`Saved ${created.length} draft(s)`)
      } else {
        setResult({
          scheduled,
          platforms: [...selected],
          when: scheduled ? new Date(scheduleAt).toLocaleString() : 'Now',
          mediaCount: media.length,
          charCount,
        })
      }
    } catch (err) {
      toast.error(err.message || 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  if (result) {
    return (
      <SuccessScreen
        result={result}
        onAnother={() => {
          setResult(null)
          clearAll()
        }}
        onScheduled={() => navigate('/scheduler')}
        onDashboard={() => navigate('/')}
      />
    )
  }

  const previewData = {
    user,
    content,
    media,
    link,
    hashtags,
    location,
    firstComment,
    when: scheduleMode === 'later' ? new Date(scheduleAt).toLocaleString() : 'now',
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Create Post</h1>
        <p className="text-sm text-slate-400">
          Write your own content, add media, and publish across platforms.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,440px)]">
        {/* ---- Left: Composer ---- */}
        <div className="space-y-5">
          {/* Platforms */}
          <section className="card p-5">
            <h2 className="mb-3 text-sm font-semibold">Select platforms</h2>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {PLATFORM_KEYS.map((p) => {
                const on = selected.includes(p)
                return (
                  <button
                    key={p}
                    type="button"
                    onClick={() => togglePlatform(p)}
                    aria-pressed={on}
                    className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-sm font-medium transition ${
                      on
                        ? 'border-indigo-500 bg-indigo-500/15 text-indigo-300'
                        : 'border-slate-300 text-slate-500 hover:bg-slate-100 dark:border-white/10 dark:text-slate-300 dark:hover:bg-white/5'
                    }`}
                  >
                    <PlatformIcon platform={p} size={20} />
                    {PLATFORMS[p].label}
                  </button>
                )
              })}
            </div>
          </section>

          {/* Content */}
          <section className="card p-5">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-semibold">Post content</h2>
              <CharCounter selected={selected} count={charCount} />
            </div>

            <div className="relative mb-2 flex flex-wrap items-center gap-1">
              <ToolBtn onClick={() => wrap('**')} title="Bold">𝐁</ToolBtn>
              <ToolBtn onClick={() => wrap('*')} title="Italic"><span className="italic">I</span></ToolBtn>
              <ToolBtn onClick={() => prefixLines(() => '• ')} title="Bullet list">•</ToolBtn>
              <ToolBtn onClick={() => prefixLines((i) => `${i + 1}. `)} title="Numbered list">1.</ToolBtn>
              <ToolBtn onClick={() => insertAtCursor('@')} title="Mention">@</ToolBtn>
              <ToolBtn onClick={insertLink} title="Insert link">🔗</ToolBtn>
              <ToolBtn onClick={() => setEmojiOpen((o) => !o)} title="Emoji">😊</ToolBtn>
              {emojiOpen && (
                <div
                  className="card absolute left-0 top-9 z-10 grid grid-cols-10 gap-1 p-2"
                  onMouseLeave={() => setEmojiOpen(false)}
                >
                  {EMOJIS.map((e) => (
                    <button
                      key={e}
                      type="button"
                      className="rounded p-1 text-lg hover:bg-slate-200 dark:hover:bg-white/10"
                      onClick={() => {
                        insertAtCursor(e)
                        setEmojiOpen(false)
                      }}
                    >
                      {e}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <textarea
              ref={textRef}
              className="input min-h-40 resize-y"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="What's on your mind?"
            />
          </section>

          {/* Media */}
          <section className="card p-5">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold">Media</h2>
              <span className="text-[11px] text-slate-400">shown in preview</span>
            </div>
            <div
              onDrop={onDrop}
              onDragOver={(e) => e.preventDefault()}
              onClick={() => fileRef.current?.click()}
              className="grid cursor-pointer place-items-center rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-400 transition hover:border-indigo-400 dark:border-white/15"
            >
              <div>
                <div className="text-2xl">⬆️</div>
                Drag & drop or click to upload — images, GIFs, videos
              </div>
              <input
                ref={fileRef}
                type="file"
                accept="image/*,video/*"
                multiple
                className="hidden"
                onChange={(e) => {
                  if (e.target.files?.length) addFiles(e.target.files)
                  e.target.value = ''
                }}
              />
            </div>

            {media.length > 0 && (
              <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-4">
                {media.map((m, idx) => (
                  <div key={m.id} className="group relative aspect-square overflow-hidden rounded-lg border border-slate-200 dark:border-white/10">
                    {m.type === 'video' ? (
                      <video src={m.url} className="h-full w-full object-cover" />
                    ) : (
                      <img src={m.url} alt={m.name} className="h-full w-full object-cover" />
                    )}
                    <div className="absolute inset-x-0 bottom-0 flex justify-between bg-black/50 px-1 py-0.5 text-xs text-white opacity-0 transition group-hover:opacity-100">
                      <button type="button" onClick={(e) => { e.stopPropagation(); moveMedia(idx, -1) }} title="Move left">←</button>
                      <button type="button" onClick={(e) => { e.stopPropagation(); removeMedia(m.id) }} title="Remove">🗑</button>
                      <button type="button" onClick={(e) => { e.stopPropagation(); moveMedia(idx, 1) }} title="Move right">→</button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Link + hashtags + meta */}
          <section className="card space-y-4 p-5">
            <div>
              <label className="label" htmlFor="link">Add link (optional)</label>
              <input
                id="link"
                className="input"
                value={link}
                onChange={(e) => setLink(e.target.value)}
                placeholder="https://example.com/article"
              />
            </div>

            <div>
              <label className="label">Hashtags</label>
              <div className="flex flex-wrap gap-1.5">
                {hashtags.map((t) => (
                  <span key={t} className="badge bg-indigo-500/15 text-indigo-300">
                    #{t}
                    <button type="button" onClick={() => removeHashtag(t)} className="ml-1 hover:text-white">×</button>
                  </span>
                ))}
              </div>
              <input
                className="input mt-2"
                value={hashtagDraft}
                onChange={(e) => setHashtagDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ',') {
                    e.preventDefault()
                    commitHashtag()
                  }
                }}
                onBlur={commitHashtag}
                placeholder="Type a tag and press Enter"
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="label" htmlFor="loc">Location (optional)</label>
                <input
                  id="loc"
                  className="input"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  placeholder="e.g. London, UK"
                />
              </div>
              <div>
                <label className="label" htmlFor="fc">First comment (optional)</label>
                <input
                  id="fc"
                  className="input"
                  value={firstComment}
                  onChange={(e) => setFirstComment(e.target.value)}
                  placeholder="Great for IG / LinkedIn"
                />
              </div>
            </div>
          </section>

          {/* Schedule */}
          <section className="card space-y-3 p-5">
            <h2 className="text-sm font-semibold">Publishing</h2>
            <div className="flex flex-wrap gap-4 text-sm">
              <label className="flex items-center gap-2">
                <input
                  type="radio"
                  name="when"
                  checked={scheduleMode === 'now'}
                  onChange={() => setScheduleMode('now')}
                />
                Publish now
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="radio"
                  name="when"
                  checked={scheduleMode === 'later'}
                  onChange={() => setScheduleMode('later')}
                />
                Schedule for later
              </label>
            </div>
            {scheduleMode === 'later' && (
              <div>
                <input
                  type="datetime-local"
                  className="input"
                  value={scheduleAt}
                  min={minLocal()}
                  onChange={(e) => setScheduleAt(e.target.value)}
                />
                <p className="mt-1 text-xs text-slate-400">Timezone: {tz}</p>
              </div>
            )}
          </section>

          {/* Buttons */}
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => submit(false)}
              disabled={busy || hasBlockingIssue}
              className="btn btn-primary"
            >
              {busy ? 'Working…' : scheduleMode === 'later' ? 'Schedule' : 'Publish'}
            </button>
            <button onClick={() => submit(true)} disabled={busy} className="btn btn-ghost">
              Save Draft
            </button>
            <button onClick={clearAll} disabled={busy} className="btn btn-ghost">
              Clear
            </button>
          </div>
        </div>

        {/* ---- Right: Live preview ---- */}
        <div className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          <div className="card p-4">
            <div className="mb-3 flex flex-wrap gap-1">
              {(selected.length ? selected : PLATFORM_KEYS).map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setActiveTab(p)}
                  className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition ${
                    activeTab === p
                      ? 'bg-indigo-500/15 text-indigo-300'
                      : 'text-slate-400 hover:bg-slate-100 dark:hover:bg-white/5'
                  }`}
                >
                  <PlatformIcon platform={p} size={16} />
                  {PLATFORMS[p].label}
                </button>
              ))}
            </div>

            {!selected.length ? (
              <div className="grid place-items-center p-10 text-center text-sm text-slate-400">
                Select a platform to preview.
              </div>
            ) : (
              <PlatformPreview platform={activeTab} data={previewData} />
            )}

            {(warnings[activeTab] || []).length > 0 && (
              <div className="mt-3 space-y-1">
                {warnings[activeTab].map((w) => (
                  <div key={w} className="flex items-start gap-2 rounded-lg bg-amber-500/10 px-2.5 py-1.5 text-xs text-amber-600 dark:text-amber-300">
                    <span>⚠️</span>
                    {w}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Publish summary */}
          <div className="card p-4 text-sm">
            <h3 className="mb-2 text-sm font-semibold">Summary</h3>
            <SummaryRow label="Platforms" value={selected.length ? selected.map((p) => PLATFORMS[p].label).join(', ') : '—'} />
            <SummaryRow label="When" value={scheduleMode === 'later' ? new Date(scheduleAt).toLocaleString() : 'Now'} />
            <SummaryRow label="Media" value={`${media.length} file(s)`} />
            <SummaryRow label="Characters" value={charCount} />
            <SummaryRow
              label="Status"
              value={hasBlockingIssue ? 'Needs attention' : 'Ready'}
              warn={hasBlockingIssue}
            />
          </div>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
function ToolBtn({ onClick, title, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className="grid h-8 w-8 place-items-center rounded-lg border border-slate-200 text-sm hover:bg-slate-100 dark:border-white/10 dark:hover:bg-white/10"
    >
      {children}
    </button>
  )
}

function CharCounter({ selected, count }) {
  // Tightest limit among the selected platforms drives the colour.
  const limit = selected.reduce(
    (min, p) => Math.min(min, PLATFORMS[p]?.limit || Infinity),
    Infinity,
  )
  const over = Number.isFinite(limit) && count > limit
  return (
    <span className={`text-xs ${over ? 'text-rose-400' : 'text-slate-400'}`}>
      {count}
      {Number.isFinite(limit) ? ` / ${limit}` : ''}
    </span>
  )
}

function SummaryRow({ label, value, warn }) {
  return (
    <div className="flex justify-between gap-3 border-b border-slate-100 py-1.5 last:border-0 dark:border-white/5">
      <span className="text-slate-400">{label}</span>
      <span className={`text-right font-medium ${warn ? 'text-amber-500' : ''}`}>{value}</span>
    </div>
  )
}

// --- per-platform preview ---------------------------------------------------
function PlatformPreview({ platform, data }) {
  const { user, content, media, link, hashtags, location, firstComment, when } = data
  const name = user?.full_name || user?.email?.split('@')[0] || 'Your Brand'
  const handle = '@' + (user?.email?.split('@')[0] || 'yourbrand')
  const initial = name.slice(0, 1).toUpperCase()
  const accent = PLATFORMS[platform]?.color || '#6366f1'
  const showFirstComment = FIRST_COMMENT_PLATFORMS.has(platform) && firstComment.trim()
  const tags = hashtags.map((t) => `#${t}`).join(' ')

  return (
    <div className="mx-auto max-w-sm overflow-hidden rounded-2xl border border-slate-200 bg-white text-slate-900 shadow-sm dark:border-white/10 dark:bg-slate-900 dark:text-slate-100">
      {/* header */}
      <div className="flex items-center gap-2 p-3">
        <span
          className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-sm font-bold text-white"
          style={{ background: accent }}
        >
          {initial}
        </span>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold">{name}</div>
          <div className="truncate text-xs text-slate-400">
            {platform === 'twitter' || platform === 'threads' ? handle : 'Sponsored'} · {when}
          </div>
        </div>
        <span className="ml-auto"><PlatformIcon platform={platform} size={18} /></span>
      </div>

      {/* text */}
      {content.trim() && (
        <p className="whitespace-pre-wrap px-3 pb-2 text-sm leading-relaxed">{content}</p>
      )}
      {tags && <p className="px-3 pb-2 text-sm text-sky-500">{tags}</p>}
      {location.trim() && (
        <p className="px-3 pb-2 text-xs text-slate-400">📍 {location}</p>
      )}

      {/* media */}
      {media.length > 0 && <PreviewMedia media={media} platform={platform} />}

      {/* link preview */}
      {link.trim() && media.length === 0 && <LinkPreview url={link} />}

      {/* engagement bar */}
      <div className="flex items-center gap-4 border-t border-slate-100 px-3 py-2 text-xs text-slate-400 dark:border-white/5">
        <span>♡ Like</span>
        <span>💬 Comment</span>
        <span>↗ Share</span>
      </div>

      {showFirstComment && (
        <div className="border-t border-slate-100 px-3 py-2 text-xs dark:border-white/5">
          <span className="font-semibold">{handle}</span>{' '}
          <span className="text-slate-500 dark:text-slate-300">{firstComment}</span>
        </div>
      )}
    </div>
  )
}

function PreviewMedia({ media, platform }) {
  // Pinterest leans portrait; everything else shows a square-ish frame.
  const ratio = platform === 'pinterest' ? '2 / 3' : '1 / 1'
  if (media.length === 1) {
    const m = media[0]
    return m.type === 'video' ? (
      <video src={m.url} controls className="w-full bg-black" style={{ aspectRatio: ratio }} />
    ) : (
      <img src={m.url} alt="" className="w-full object-cover" style={{ aspectRatio: ratio }} />
    )
  }
  return (
    <div className="grid grid-cols-2 gap-0.5">
      {media.slice(0, 4).map((m, i) => (
        <div key={m.id} className="relative">
          {m.type === 'video' ? (
            <video src={m.url} className="aspect-square w-full object-cover" />
          ) : (
            <img src={m.url} alt="" className="aspect-square w-full object-cover" />
          )}
          {i === 3 && media.length > 4 && (
            <div className="absolute inset-0 grid place-items-center bg-black/50 text-lg font-bold text-white">
              +{media.length - 4}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function LinkPreview({ url }) {
  let domain = url
  try {
    domain = new URL(url.startsWith('http') ? url : `https://${url}`).hostname
  } catch {
    /* keep raw */
  }
  return (
    <div className="m-3 overflow-hidden rounded-xl border border-slate-200 dark:border-white/10">
      <div className="grid h-28 place-items-center bg-slate-100 text-3xl dark:bg-white/5">🔗</div>
      <div className="p-2">
        <div className="text-xs uppercase text-slate-400">{domain}</div>
        <div className="truncate text-sm font-medium">{url}</div>
      </div>
    </div>
  )
}

// --- success screen ---------------------------------------------------------
function SuccessScreen({ result, onAnother, onScheduled, onDashboard }) {
  return (
    <div className="grid min-h-[60vh] place-items-center">
      <div className="card max-w-md p-8 text-center">
        <div className="mx-auto mb-4 grid h-20 w-20 place-items-center rounded-full bg-emerald-500/15 text-4xl">
          ✅
        </div>
        <h2 className="text-xl font-bold">
          {result.scheduled ? 'Post scheduled successfully' : 'Post published successfully'}
        </h2>
        <p className="mt-1 text-sm text-slate-400">
          {result.scheduled ? `Going live ${result.when}` : 'Your content is on its way.'}
        </p>

        <div className="mt-5 rounded-xl border border-slate-200 p-3 text-left text-sm dark:border-white/10">
          <SummaryRow label="Platforms" value={result.platforms.map((p) => PLATFORMS[p].label).join(', ')} />
          <SummaryRow label="When" value={result.when} />
          <SummaryRow label="Media" value={`${result.mediaCount} file(s)`} />
          <SummaryRow label="Characters" value={result.charCount} />
        </div>

        <div className="mt-6 flex flex-col gap-2">
          <button onClick={onAnother} className="btn btn-primary">Create another post</button>
          <button onClick={onScheduled} className="btn btn-ghost">View scheduled posts</button>
          <button onClick={onDashboard} className="btn btn-ghost">Go to dashboard</button>
        </div>
      </div>
    </div>
  )
}
