import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useToast } from '../context/ToastContext.jsx'
import { formatDateTime, localInputToISO, parseServerDate } from '../lib/datetime'
import { PLATFORMS } from '../lib/constants'
import PlatformIcon from '../components/PlatformIcon.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import ScheduleModal from '../components/ScheduleModal.jsx'

const FILTERS = ['all', 'draft', 'scheduled', 'published', 'failed']

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

  async function doReschedule(localValue) {
    const id = rescheduleId
    await action(
      () => api.updatePost(id, { scheduled_time: localInputToISO(localValue) }),
      'Post rescheduled',
    )
    setRescheduleId(null)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Post History</h1>
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

      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-xs uppercase text-slate-400 dark:border-white/10">
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
                  <tr key={i} className="border-b border-slate-100 dark:border-white/5">
                    <td colSpan={5} className="px-4 py-3">
                      <div className="skeleton h-6 w-full" />
                    </td>
                  </tr>
                ))
              ) : posts.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-12 text-center text-slate-500">
                    No posts found.
                  </td>
                </tr>
              ) : (
                posts.map((p) => (
                  <tr key={p.id} className="border-b border-slate-100 last:border-0 dark:border-white/5">
                    <td className="max-w-xs px-4 py-3">
                      <div className="truncate">{p.content}</div>
                      {p.error && <div className="truncate text-xs text-rose-400">{p.error}</div>}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <PlatformIcon platform={p.platform} size={22} />
                        <span className="hidden text-xs text-slate-400 sm:inline">
                          {PLATFORMS[p.platform]?.label}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3"><StatusBadge status={p.status} /></td>
                    <td className="px-4 py-3 text-xs text-slate-400">
                      {p.status === 'scheduled'
                        ? formatDateTime(p.scheduled_time)
                        : p.status === 'published'
                          ? formatDateTime(p.published_time)
                          : formatDateTime(p.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-1">
                        {p.status !== 'published' && (
                          <button
                            className="btn btn-ghost btn-sm"
                            onClick={() => action(() => api.publishPost(p.id), 'Published (simulated)')}
                          >
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
