import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { useTheme } from '../context/ThemeContext.jsx'
import { formatDateTime } from '../lib/datetime'

export default function Settings() {
  const { user, logout } = useAuth()
  const { theme, toggle } = useTheme()

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-2xl font-bold">Settings</h1>

      <section className="card p-5">
        <h2 className="mb-4 font-semibold">Profile</h2>
        <dl className="space-y-3 text-sm">
          <Row label="Name" value={user?.full_name || '—'} />
          <Row label="Email" value={user?.email} />
          <Row label="Member since" value={user?.created_at ? formatDateTime(user.created_at) : '—'} />
          <Row label="Account ID" value={`#${user?.id}`} />
        </dl>
      </section>

      <Link
        to="/business-profile"
        className="card flex items-center justify-between p-5 transition hover:-translate-y-0.5"
      >
        <div>
          <h2 className="font-semibold">Business Profile</h2>
          <p className="text-sm text-muted">
            Tell the AI about your business for more personalized content.
          </p>
        </div>
        <span className="text-muted">→</span>
      </Link>

      <section className="card p-5">
        <h2 className="mb-4 font-semibold">Appearance</h2>
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-medium">Theme</div>
            <div className="text-xs text-muted">Currently {theme}</div>
          </div>
          <button onClick={toggle} className="btn btn-ghost">
            Switch to {theme === 'dark' ? 'light' : 'dark'}
          </button>
        </div>
      </section>

      <section className="card p-5 opacity-70">
        <h2 className="mb-2 font-semibold">Notifications & API limits</h2>
        <p className="text-sm text-muted">Coming soon.</p>
      </section>

      <button onClick={logout} className="btn btn-danger">
        Log out
      </button>
    </div>
  )
}

function Row({ label, value }) {
  return (
    <div className="flex justify-between gap-4 border-b border-line pb-3 last:border-0">
      <dt className="text-muted">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  )
}
