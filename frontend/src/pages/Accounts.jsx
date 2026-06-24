import { useEffect, useState } from 'react'
import { PLATFORMS, PLATFORM_KEYS } from '../lib/constants'
import { useToast } from '../context/ToastContext.jsx'
import PlatformIcon from '../components/PlatformIcon.jsx'
import { api, ApiError } from '../lib/api'

// Instagram connects for real via the Meta Graph API (backend). The other
// platforms remain simulated (local toggle) until their adapters are added.
const SIM_KEY = 'ss_connected'

function loadSimulated() {
  try {
    return JSON.parse(localStorage.getItem(SIM_KEY)) || {}
  } catch {
    return {}
  }
}

export default function Accounts() {
  const toast = useToast()
  const [accounts, setAccounts] = useState([]) // real, from backend
  const [simulated, setSimulated] = useState(loadSimulated)
  const [igForm, setIgForm] = useState(false)
  const [token, setToken] = useState('')
  const [pageId, setPageId] = useState('')
  const [busy, setBusy] = useState(false)

  async function refresh() {
    try {
      setAccounts(await api.listAccounts())
    } catch {
      /* not logged in / backend down — leave empty */
    }
  }

  useEffect(() => {
    refresh()
    // Handle the OAuth redirect coming back to /accounts.
    const params = new URLSearchParams(window.location.search)
    if (params.get('connected') === 'instagram') {
      toast.success('Instagram connected!')
      window.history.replaceState({}, '', '/accounts')
    } else if (params.get('error')) {
      toast.error(`Instagram connect failed: ${params.get('error')}`)
      window.history.replaceState({}, '', '/accounts')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const real = Object.fromEntries(accounts.map((a) => [a.platform, a]))

  async function connectInstagram(e) {
    e.preventDefault()
    setBusy(true)
    try {
      const acc = await api.connectInstagram({
        access_token: token.trim(),
        page_id: pageId.trim() || null,
      })
      toast.success(`Instagram connected as @${acc.username || acc.account_id}`)
      setIgForm(false)
      setToken('')
      setPageId('')
      refresh()
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Connect failed'
      toast.error(msg)
    } finally {
      setBusy(false)
    }
  }

  async function disconnect(platform) {
    try {
      await api.disconnectAccount(platform)
      toast.success(`${PLATFORMS[platform].label} disconnected`)
      refresh()
    } catch {
      toast.error('Disconnect failed')
    }
  }

  function toggleSim(p) {
    const next = { ...simulated, [p]: !simulated[p] }
    setSimulated(next)
    localStorage.setItem(SIM_KEY, JSON.stringify(next))
    toast.success(`${PLATFORMS[p].label} ${next[p] ? 'connected' : 'disconnected'} (simulated)`)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Social Accounts</h1>
        <p className="text-sm text-slate-400">
          <span className="font-semibold text-emerald-400">Instagram</span> connects for real
          via the Meta Graph API. Other platforms are{' '}
          <span className="font-semibold text-amber-400">simulated</span> until their adapters
          are added.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {PLATFORM_KEYS.map((p) => {
          const isInstagram = p === 'instagram'
          const account = real[p]
          const on = isInstagram ? !!account : !!simulated[p]
          return (
            <div key={p} className="card flex flex-col gap-4 p-5">
              <div className="flex items-center gap-3">
                <PlatformIcon platform={p} size={40} />
                <div>
                  <div className="font-semibold">{PLATFORMS[p].label}</div>
                  <div className={`text-xs ${on ? 'text-emerald-400' : 'text-slate-400'}`}>
                    {on
                      ? isInstagram
                        ? `● @${account.username || account.account_id}`
                        : '● Connected'
                      : '○ Not connected'}
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>Token status</span>
                <span className={on ? 'text-emerald-400' : 'text-slate-500'}>
                  {on ? (isInstagram ? 'Active (real)' : 'Active (simulated)') : 'None'}
                </span>
              </div>

              {isInstagram ? (
                on ? (
                  <button onClick={() => disconnect(p)} className="btn btn-ghost w-full">
                    Disconnect
                  </button>
                ) : igForm ? (
                  <form onSubmit={connectInstagram} className="flex flex-col gap-2">
                    <input
                      className="input text-xs"
                      placeholder="Access token"
                      value={token}
                      onChange={(e) => setToken(e.target.value)}
                      required
                    />
                    <input
                      className="input text-xs"
                      placeholder="Facebook Page ID (optional)"
                      value={pageId}
                      onChange={(e) => setPageId(e.target.value)}
                    />
                    <div className="flex gap-2">
                      <button type="submit" disabled={busy} className="btn btn-primary flex-1">
                        {busy ? 'Connecting…' : 'Connect'}
                      </button>
                      <button
                        type="button"
                        onClick={() => setIgForm(false)}
                        className="btn btn-ghost"
                      >
                        Cancel
                      </button>
                    </div>
                  </form>
                ) : (
                  <button onClick={() => setIgForm(true)} className="btn btn-primary w-full">
                    Connect
                  </button>
                )
              ) : (
                <button
                  onClick={() => toggleSim(p)}
                  className={`btn w-full ${on ? 'btn-ghost' : 'btn-primary'}`}
                >
                  {on ? 'Disconnect' : 'Connect'}
                </button>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
