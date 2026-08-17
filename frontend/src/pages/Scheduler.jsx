import { useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'
import { useToast } from '../context/ToastContext.jsx'
import { formatDateTime, parseServerDate } from '../lib/datetime'
import { PLATFORMS } from '../lib/constants'
import { publishOutcome } from '../lib/publish'
import PlatformIcon from '../components/PlatformIcon.jsx'

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

export default function Scheduler() {
  const toast = useToast()
  const [posts, setPosts] = useState([])
  const [cursor, setCursor] = useState(() => {
    const d = new Date()
    return new Date(d.getFullYear(), d.getMonth(), 1)
  })

  function load() {
    api.listPosts().then(setPosts).catch((e) => toast.error(e.message))
  }
  useEffect(load, []) // eslint-disable-line

  const scheduled = posts.filter((p) => p.status === 'scheduled')

  // Map of 'YYYY-M-D' (local) -> posts scheduled that day.
  const byDay = useMemo(() => {
    const m = {}
    for (const p of posts) {
      if (!p.scheduled_time) continue
      const d = parseServerDate(p.scheduled_time)
      const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
      ;(m[key] ||= []).push(p)
    }
    return m
  }, [posts])

  const year = cursor.getFullYear()
  const month = cursor.getMonth()
  const firstDay = new Date(year, month, 1).getDay()
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const cells = []
  for (let i = 0; i < firstDay; i++) cells.push(null)
  for (let d = 1; d <= daysInMonth; d++) cells.push(d)

  const today = new Date()
  const isToday = (d) =>
    d === today.getDate() && month === today.getMonth() && year === today.getFullYear()

  async function cancel(id) {
    try {
      await api.cancelPost(id)
      toast.success('Schedule cancelled')
      load()
    } catch (e) {
      toast.error(e.message)
    }
  }
  async function publishNow(id) {
    try {
      const post = await api.publishPost(id)
      const outcome = publishOutcome(post, PLATFORMS[post.platform]?.label || 'the platform')
      if (outcome.ok) toast.success(outcome.message)
      else toast.error(outcome.message)
      load()
    } catch (e) {
      toast.error(e.message)
    }
  }

  // The negative top margin trims the shared <main> padding; the height calc
  // hands those pixels back so the panes still end at the bottom of the viewport.
  return (
    <div className="split-shell -mt-1 gap-3 md:-mt-3 lg:h-[calc(100%+0.75rem)] lg:gap-4">
      <h1 className="shrink-0 text-lg font-bold">Scheduler</h1>

      <div className="split-grid gap-4 lg:grid-cols-[1fr_320px]">
        {/* Calendar */}
        <div className="card split-pane p-4 lg:h-full">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">
              {cursor.toLocaleString(undefined, { month: 'long', year: 'numeric' })}
            </h2>
            <div className="flex gap-2">
              <button className="btn btn-ghost btn-sm" onClick={() => setCursor(new Date(year, month - 1, 1))}>
                ‹
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => setCursor(new Date(today.getFullYear(), today.getMonth(), 1))}>
                Today
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => setCursor(new Date(year, month + 1, 1))}>
                ›
              </button>
            </div>
          </div>

          <div className="grid grid-cols-7 gap-1 text-center text-xs text-muted">
            {WEEKDAYS.map((w) => (
              <div key={w} className="py-1 font-medium">{w}</div>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1">
            {cells.map((d, i) => {
              const key = d ? `${year}-${month}-${d}` : null
              const dayPosts = key ? byDay[key] || [] : []
              return (
                <div
                  key={i}
                  className={`min-h-20 rounded-lg border p-1 text-left ${
                    d
                      ? 'border-line'
                      : 'border-transparent'
                  } ${isToday(d) ? 'ring-1 ring-accent' : ''}`}
                >
                  {d && (
                    <>
                      <div className="px-1 text-xs text-muted">{d}</div>
                      <div className="mt-0.5 space-y-0.5">
                        {dayPosts.slice(0, 3).map((p) => (
                          // The caption is hidden below `sm`. Seven day
                          // columns on a 390px screen leave about 9px inside
                          // this chip once the icon and padding are taken out,
                          // so the text rendered as a sliver of a single
                          // letter — it looked like a glitch and said nothing.
                          // The icon alone marks the day, and the Pending list
                          // underneath carries the caption, time and actions.
                          <div
                            key={p.id}
                            title={p.content}
                            className="flex items-center justify-center gap-1 truncate rounded bg-amber-500/15 px-1 py-0.5 text-[10px] text-amber-300 sm:justify-start"
                          >
                            <PlatformIcon platform={p.platform} size={12} />
                            <span className="hidden truncate sm:inline">{p.content}</span>
                          </div>
                        ))}
                        {dayPosts.length > 3 && (
                          <div className="px-1 text-[10px] text-muted">
                            +{dayPosts.length - 3} more
                          </div>
                        )}
                      </div>
                    </>
                  )}
                </div>
              )
            })}
          </div>
        </div>

        {/* Pending list */}
        <div className="card split-pane p-4 lg:h-full">
          <h2 className="mb-4 font-semibold">Pending ({scheduled.length})</h2>
          {scheduled.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted">No scheduled posts.</p>
          ) : (
            <ul className="space-y-3">
              {scheduled
                .slice()
                .sort((a, b) => parseServerDate(a.scheduled_time) - parseServerDate(b.scheduled_time))
                .map((p) => (
                  <li key={p.id} className="rounded-xl border border-line p-3">
                    <div className="flex items-center gap-2">
                      <PlatformIcon platform={p.platform} size={24} />
                      <span className="text-xs text-amber-400">{formatDateTime(p.scheduled_time)}</span>
                    </div>
                    <p className="mt-2 line-clamp-2 text-sm text-body">{p.content}</p>
                    <div className="mt-2 flex gap-2">
                      <button className="btn btn-primary btn-sm" onClick={() => publishNow(p.id)}>
                        Publish now
                      </button>
                      <button className="btn btn-ghost btn-sm" onClick={() => cancel(p.id)}>
                        Cancel
                      </button>
                    </div>
                  </li>
                ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
