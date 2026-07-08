import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useToast } from '../context/ToastContext.jsx'
import { formatDateTime, formatRelative, parseServerDate } from '../lib/datetime'
import PlatformIcon from '../components/PlatformIcon.jsx'
import StatusBadge from '../components/StatusBadge.jsx'

const STAT_CARDS = [
  { key: 'total', label: 'Total Posts', accent: 'bg-accent' },
  { key: 'scheduled', label: 'Scheduled', accent: 'bg-amber-400' },
  { key: 'published', label: 'Published', accent: 'bg-emerald-400' },
  { key: 'failed', label: 'Failed', accent: 'bg-rose-400' },
]

export default function Dashboard() {
  const [posts, setPosts] = useState(null)
  const toast = useToast()
  const navigate = useNavigate()

  useEffect(() => {
    api
      .listPosts()
      .then(setPosts)
      .catch((e) => {
        toast.error(e.message)
        setPosts([])
      })
  }, []) // eslint-disable-line

  const loading = posts === null
  const stats = {
    total: posts?.length || 0,
    scheduled: posts?.filter((p) => p.status === 'scheduled').length || 0,
    published: posts?.filter((p) => p.status === 'published').length || 0,
    failed: posts?.filter((p) => p.status === 'failed').length || 0,
  }

  const upcoming = (posts || [])
    .filter((p) => p.status === 'scheduled')
    .sort((a, b) => parseServerDate(a.scheduled_time) - parseServerDate(b.scheduled_time))
    .slice(0, 5)

  const recent = (posts || [])
    .slice()
    .sort((a, b) => parseServerDate(b.created_at) - parseServerDate(a.created_at))
    .slice(0, 6)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-sm text-muted">Your content at a glance</p>
        </div>
        <button onClick={() => navigate('/generate')} className="btn btn-primary">
          ✦ Generate Post with AI
        </button>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {STAT_CARDS.map((c) => (
          <div key={c.key} className="card p-5">
            <div className={`mb-3 h-1.5 w-10 rounded-full ${c.accent}`} />
            <div className="text-3xl font-extrabold">
              {loading ? <span className="skeleton inline-block h-8 w-10" /> : stats[c.key]}
            </div>
            <div className="mt-1 text-sm text-muted">{c.label}</div>
          </div>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Upcoming */}
        <div className="card p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-semibold">📅 Upcoming Schedule</h2>
            <button onClick={() => navigate('/scheduler')} className="text-sm link-accent">
              View all
            </button>
          </div>
          {loading ? (
            <SkeletonRows />
          ) : upcoming.length === 0 ? (
            <Empty text="Nothing scheduled yet." />
          ) : (
            <ul className="space-y-3">
              {upcoming.map((p) => (
                <li key={p.id} className="flex items-center gap-3">
                  <PlatformIcon platform={p.platform} />
                  <span className="min-w-0 flex-1 truncate text-sm">{p.content}</span>
                  <span className="shrink-0 text-xs text-amber-400">
                    {formatDateTime(p.scheduled_time)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Recent activity */}
        <div className="card p-5">
          <h2 className="mb-4 font-semibold">📈 Recent Activity</h2>
          {loading ? (
            <SkeletonRows />
          ) : recent.length === 0 ? (
            <Empty text="No posts yet — generate your first one!" />
          ) : (
            <ul className="space-y-3">
              {recent.map((p) => (
                <li key={p.id} className="flex items-center gap-3">
                  <PlatformIcon platform={p.platform} size={28} />
                  <span className="min-w-0 flex-1 truncate text-sm text-body">
                    {p.content}
                  </span>
                  <StatusBadge status={p.status} />
                  <span className="hidden shrink-0 text-xs text-muted sm:block">
                    {formatRelative(p.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}

function SkeletonRows() {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((i) => (
        <div key={i} className="skeleton h-8 w-full" />
      ))}
    </div>
  )
}

function Empty({ text }) {
  return <p className="py-6 text-center text-sm text-muted">{text}</p>
}
