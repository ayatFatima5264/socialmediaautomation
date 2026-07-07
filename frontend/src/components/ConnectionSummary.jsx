import { Link } from 'react-router-dom'
import { PLATFORMS } from '../lib/constants'
import PlatformIcon from './PlatformIcon.jsx'

// Top-of-page summary: an at-a-glance progress bar + per-platform ticks, plus a
// "Continue to Create Post" CTA that only enables once something is connected.
export default function ConnectionSummary({ summary, connectedCount, total }) {
  const pct = total ? Math.round((connectedCount / total) * 100) : 0
  const canContinue = connectedCount > 0

  return (
    <div className="card flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex-1">
        <div className="mb-2 flex items-baseline justify-between gap-4">
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-200">
            Connected Platforms
          </h2>
          <span className="text-sm font-semibold text-indigo-600 dark:text-indigo-300">
            {connectedCount} / {total} Connected
          </span>
        </div>

        {/* Progress bar */}
        <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-white/10">
          <div
            className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>

        {/* Per-platform ticks */}
        <div className="mt-3 flex flex-wrap gap-2">
          {summary.map((s) => (
            <span
              key={s.platform}
              title={`${PLATFORMS[s.platform]?.label}: ${s.connected ? 'connected' : 'not connected'}`}
              className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs ${
                s.connected
                  ? 'border-emerald-500/30 text-emerald-600 dark:text-emerald-300'
                  : 'border-slate-300 text-slate-400 dark:border-white/10 dark:text-slate-500'
              }`}
            >
              <PlatformIcon platform={s.platform} size={16} />
              {s.connected ? '✓' : '○'}
            </span>
          ))}
        </div>
      </div>

      {/* CTA — disabled with a tooltip until at least one account is connected */}
      <div
        title={
          canContinue
            ? 'Create a post across your connected platforms'
            : 'Connect at least one social account to publish posts.'
        }
      >
        {canContinue ? (
          <Link to="/create" className="btn btn-primary whitespace-nowrap">
            Continue to Create Post →
          </Link>
        ) : (
          <button
            disabled
            className="btn btn-primary pointer-events-none whitespace-nowrap opacity-50"
          >
            Continue to Create Post →
          </button>
        )}
      </div>
    </div>
  )
}
