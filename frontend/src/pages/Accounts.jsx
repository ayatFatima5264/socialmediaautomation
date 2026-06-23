import { useState } from 'react'
import { PLATFORMS, PLATFORM_KEYS } from '../lib/constants'
import { useToast } from '../context/ToastContext.jsx'
import PlatformIcon from '../components/PlatformIcon.jsx'

const KEY = 'ss_connected'

function loadConnected() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || {}
  } catch {
    return {}
  }
}

export default function Accounts() {
  const toast = useToast()
  const [connected, setConnected] = useState(loadConnected)

  function toggle(p) {
    const next = { ...connected, [p]: !connected[p] }
    setConnected(next)
    localStorage.setItem(KEY, JSON.stringify(next))
    toast.success(`${PLATFORMS[p].label} ${next[p] ? 'connected' : 'disconnected'} (simulated)`)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Social Accounts</h1>
        <p className="text-sm text-slate-400">
          Connect platforms to publish. Connections are{' '}
          <span className="font-semibold text-amber-400">simulated</span> — real OAuth wiring
          comes when platform API keys are added.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {PLATFORM_KEYS.map((p) => {
          const on = !!connected[p]
          return (
            <div key={p} className="card flex flex-col gap-4 p-5">
              <div className="flex items-center gap-3">
                <PlatformIcon platform={p} size={40} />
                <div>
                  <div className="font-semibold">{PLATFORMS[p].label}</div>
                  <div className={`text-xs ${on ? 'text-emerald-400' : 'text-slate-400'}`}>
                    {on ? '● Connected' : '○ Not connected'}
                  </div>
                </div>
              </div>
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>Token status</span>
                <span className={on ? 'text-emerald-400' : 'text-slate-500'}>
                  {on ? 'Active (simulated)' : 'None'}
                </span>
              </div>
              <button
                onClick={() => toggle(p)}
                className={`btn w-full ${on ? 'btn-ghost' : 'btn-primary'}`}
              >
                {on ? 'Disconnect' : 'Connect'}
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
