import { useState } from 'react'
import { PLATFORMS } from '../lib/constants'
import PlatformIcon from './PlatformIcon.jsx'

// Shown when one OAuth login exposes several connectable accounts (e.g. multiple
// Instagram Business accounts across a user's Facebook Pages). The user picks
// exactly one; only that account is connected.
export default function AccountSelectModal({ platform, candidates, busy, onSelect, onClose }) {
  const [selected, setSelected] = useState(candidates[0]?.account_id || null)
  const label = PLATFORMS[platform]?.label || platform

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="card w-full max-w-md p-6">
        <div className="mb-1 flex items-center gap-2">
          <PlatformIcon platform={platform} size={28} />
          <h2 className="text-lg font-bold">Choose an {label} account</h2>
        </div>
        <p className="mb-4 text-sm text-slate-500 dark:text-slate-400">
          Your login has access to several {label} accounts. Select the one to connect.
        </p>

        <div className="max-h-72 space-y-2 overflow-y-auto">
          {candidates.map((c) => {
            const on = selected === c.account_id
            return (
              <button
                key={c.account_id}
                onClick={() => setSelected(c.account_id)}
                className={`flex w-full items-center gap-3 rounded-xl border p-3 text-left transition ${
                  on
                    ? 'border-indigo-500 bg-indigo-500/10'
                    : 'border-slate-200 hover:bg-slate-100 dark:border-white/10 dark:hover:bg-white/5'
                }`}
              >
                {c.profile_picture ? (
                  <img
                    src={c.profile_picture}
                    alt=""
                    className="h-10 w-10 shrink-0 rounded-full object-cover"
                  />
                ) : (
                  <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-slate-200 text-sm font-semibold dark:bg-white/10">
                    {(c.username || '?')[0].toUpperCase()}
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <div className="truncate font-semibold">
                    @{c.username || c.account_id}
                  </div>
                  {c.page_name && (
                    <div className="truncate text-xs text-slate-500 dark:text-slate-400">
                      via {c.page_name}
                    </div>
                  )}
                </div>
                <span
                  className={`h-4 w-4 shrink-0 rounded-full border-2 ${
                    on ? 'border-indigo-500 bg-indigo-500' : 'border-slate-300 dark:border-white/20'
                  }`}
                />
              </button>
            )
          })}
        </div>

        <div className="mt-5 flex gap-2">
          <button onClick={onClose} disabled={busy} className="btn btn-ghost flex-1">
            Cancel
          </button>
          <button
            onClick={() => onSelect(selected)}
            disabled={busy || !selected}
            className="btn btn-primary flex-1"
          >
            {busy ? 'Connecting…' : 'Connect'}
          </button>
        </div>
      </div>
    </div>
  )
}
