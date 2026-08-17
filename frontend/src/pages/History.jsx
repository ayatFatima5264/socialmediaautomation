import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useToast } from '../context/ToastContext.jsx'
import { formatDateTime, localInputToISO, parseServerDate } from '../lib/datetime'
import { PLATFORMS } from '../lib/constants'
import { publishOutcome } from '../lib/publish'
import PlatformIcon from '../components/PlatformIcon.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import ScheduleModal from '../components/ScheduleModal.jsx'

const FILTERS = ['all', 'draft', 'scheduled', 'published', 'failed']

// The date a post is judged by depends on where it is in its life: a scheduled
// post is about when it will go out, a published one about when it did.
function postDate(p) {
  if (p.status === 'scheduled') return formatDateTime(p.scheduled_time)
  if (p.status === 'published') return formatDateTime(p.published_time)
  return formatDateTime(p.created_at)
}

export default function History() {
  const toast = useToast()
  const [posts, setPosts] = useState(null)
  const [filter, setFilter] = useState('all')
  const [rescheduleId, setRescheduleId] = useState(null)

  function load() {
    setPosts(null)
    api
      .listPosts(filter === 'all' ? undefined : filter)
      .then(setPosts)
      .catch((e) => {
        toast.error(e.message)
        setPosts([])
      })
  }
  useEffect(load, [filter]) // eslint-disable-line

  async function action(fn, okMsg) {
    try {
      await fn()
      toast.success(okMsg)
      load()
    } catch (e) {
      toast.error(e.message)
    }
  }

  // Publish reports the real outcome: a non-throwing response can still be a
  // platform failure (status 'failed') or a simulated publish (sim_ external id).
  async function publishAction(post) {
    try {
      const updated = await api.publishPost(post.id)
      const outcome = publishOutcome(updated, PLATFORMS[updated.platform]?.label || 'the platform')
      if (outcome.ok) toast.success(outcome.message)
      else toast.error(outcome.message)
      load()
    } catch (e) {
      toast.error(e.message)
    }
  }

  async function doReschedule(localValue) {
    const id = rescheduleId
    await action(
      () => api.updatePost(id, { scheduled_time: localInputToISO(localValue) }),
      'Post rescheduled',
    )
    setRescheduleId(null)
  }

  // The same four actions serve the phone cards and the desktop table, so they
  // live in one place — two copies of this drift the moment a status rule
  // changes.
  function RowActions({ post: p, className = '' }) {
    return (
      <div className={`flex flex-wrap gap-1 ${className}`}>
        {p.status !== 'published' && (
          <button className="btn btn-ghost btn-sm" onClick={() => publishAction(p)}>
            Publish
          </button>
        )}
        {(p.status === 'draft' || p.status === 'scheduled' || p.status === 'failed') && (
          <button className="btn btn-ghost btn-sm" onClick={() => setRescheduleId(p.id)}>
            {p.status === 'scheduled' ? 'Reschedule' : 'Schedule'}
          </button>
        )}
        {p.status === 'scheduled' && (
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => action(() => api.cancelPost(p.id), 'Schedule cancelled')}
          >
            Cancel
          </button>
        )}
        <button
          className="btn btn-danger btn-sm"
          onClick={() => action(() => api.deletePost(p.id), 'Post deleted')}
        >
          Delete
        </button>
      </div>
    )
  }

  return (
    <div className="-mt-1 space-y-3 pb-4 md:-mt-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-bold">Post History</h1>
        <div className="flex flex-wrap gap-1">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`btn btn-sm ${filter === f ? 'btn-primary' : 'btn-ghost'}`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* ---- Phones: one card per post ---------------------------------
          A five-column table with a four-button action group needs ~860px.
          Inside a 390px screen that meant a sideways scroll where the caption
          was cut to a third of a line and the buttons lived off-screen, so the
          only column you could actually read was the one you were not looking
          for. Stacked, every post shows its caption, platform, status, time
          and actions with nothing hidden. */}
      <div className="space-y-2.5 lg:hidden">
        {posts === null
          ? [0, 1, 2, 3].map((i) => (
              <div key={i} className="card p-4">
                <div className="skeleton h-6 w-full" />
              </div>
            ))
          : posts.length === 0
            ? <div className="card px-4 py-12 text-center text-muted">No posts found.</div>
            : posts.map((p) => (
                <div key={p.id} className="card space-y-3 p-4">
                  <p className="line-clamp-3 text-sm text-body">{p.content}</p>
                  {p.error && <p className="text-xs text-rose-400">{p.error}</p>}
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-muted">
                    <span className="flex items-center gap-1.5">
                      <PlatformIcon platform={p.platform} size={18} />
                      {PLATFORMS[p.platform]?.label}
                    </span>
                    <StatusBadge status={p.status} />
                    <span>{postDate(p)}</span>
                  </div>
                  <RowActions post={p} className="border-t border-line pt-3" />
                </div>
              ))}
      </div>

      {/* `lg`, not `md`: inside the app shell the 256px sidebar appears at
          `md`, so a 768px screen leaves about 480px for content — less than
          the table needs. The cards stay until the window is genuinely wide
          enough for five columns. */}
      <div className="card hidden overflow-hidden lg:block">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line text-xs uppercase text-muted">
              <tr>
                <th className="px-4 py-3 font-medium">Content</th>
                <th className="px-4 py-3 font-medium">Platform</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">When</th>
                <th className="px-4 py-3 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {posts === null ? (
                [0, 1, 2, 3].map((i) => (
                  <tr key={i} className="border-b border-line">
                    <td colSpan={5} className="px-4 py-3">
                      <div className="skeleton h-6 w-full" />
                    </td>
                  </tr>
                ))
              ) : posts.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-12 text-center text-muted">
                    No posts found.
                  </td>
                </tr>
              ) : (
                posts.map((p) => (
                  <tr key={p.id} className="border-b border-line last:border-0">
                    <td className="max-w-xs px-4 py-3">
                      <div className="truncate">{p.content}</div>
                      {p.error && <div className="truncate text-xs text-rose-400">{p.error}</div>}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <PlatformIcon platform={p.platform} size={22} />
                        <span className="hidden text-xs text-muted sm:inline">
                          {PLATFORMS[p.platform]?.label}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3"><StatusBadge status={p.status} /></td>
                    <td className="px-4 py-3 text-xs text-muted">{postDate(p)}</td>
                    <td className="px-4 py-3">
                      <RowActions post={p} className="justify-end" />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <ScheduleModal
        open={rescheduleId !== null}
        title="Schedule / reschedule post"
        onClose={() => setRescheduleId(null)}
        onConfirm={doReschedule}
      />
    </div>
  )
}
