import { useEffect, useState } from 'react'
import { PLATFORM_KEYS, PLATFORMS } from '../lib/constants'
import { useToast } from '../context/ToastContext.jsx'
import { api, ApiError } from '../lib/api'
import AccountCard from '../components/AccountCard.jsx'
import ConnectionSummary from '../components/ConnectionSummary.jsx'
import AccountSelectModal from '../components/AccountSelectModal.jsx'

// Empty per-platform summary used while the first load is in flight, so the
// summary strip and layout don't jump once data arrives.
const EMPTY_SUMMARY = PLATFORM_KEYS.map((p) => ({
  platform: p,
  connected: false,
  status: 'not_connected',
}))

export default function Accounts() {
  const toast = useToast()
  const [overview, setOverview] = useState(null) // null = loading
  const [busy, setBusy] = useState({}) // { [platform]: true }
  // Multi-account picker: { platform, pendingId, candidates } or null.
  const [selection, setSelection] = useState(null)
  const [selecting, setSelecting] = useState(false)
  // Persistent connect error banner: { platform, message } or null.
  const [connectError, setConnectError] = useState(null)

  async function load() {
    try {
      setOverview(await api.accountsOverview())
    } catch {
      // Not logged in / backend down — show an empty (but usable) page.
      setOverview({
        accounts: [],
        summary: EMPTY_SUMMARY,
        connected_count: 0,
        total_platforms: PLATFORM_KEYS.length,
      })
    }
  }

  async function openSelection(platform, pendingId) {
    try {
      const data = await api.pendingConnection(pendingId)
      setSelection({ platform, pendingId, candidates: data.candidates })
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Selection expired')
    }
  }

  useEffect(() => {
    load()
    // Handle the OAuth redirect landing back on /accounts.
    const params = new URLSearchParams(window.location.search)
    const connected = params.get('connected')
    const select = params.get('select')
    const pending = params.get('pending')
    const error = params.get('error')
    if (connected) {
      const label = PLATFORMS[connected]?.label || connected
      toast.success(`${label} connected!`)
      window.history.replaceState({}, '', '/accounts')
    } else if (select && pending) {
      // Several accounts to choose from — open the picker.
      openSelection(select, pending)
      window.history.replaceState({}, '', '/accounts')
    } else if (error) {
      // Show a persistent banner (not just a fleeting toast) with the reason.
      setConnectError({ platform: params.get('platform'), message: error })
      window.history.replaceState({}, '', '/accounts')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function confirmSelection(accountId) {
    if (!selection) return
    setSelecting(true)
    try {
      await api.selectAccount(selection.pendingId, accountId)
      toast.success(`${PLATFORMS[selection.platform]?.label || 'Account'} connected!`)
      setSelection(null)
      await load()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not connect account')
    } finally {
      setSelecting(false)
    }
  }

  const setBusyFor = (platform, value) =>
    setBusy((b) => ({ ...b, [platform]: value }))

  async function connect(platform) {
    setBusyFor(platform, true)
    try {
      const res = await api.connectAccount(platform)
      // Real OAuth: bounce the browser to the provider's consent screen.
      if (res.authorize_url) {
        window.location.href = res.authorize_url
        return
      }
      // Inline (dev) connect completed — refresh from the server.
      toast.success(res.message || `${PLATFORMS[platform].label} connected`)
      await load()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Connect failed')
    } finally {
      setBusyFor(platform, false)
    }
  }

  async function disconnect(platform) {
    setBusyFor(platform, true)
    // Optimistic: drop the account immediately, roll back on failure.
    const prev = overview
    setOverview((o) => applyRemoval(o, platform))
    try {
      await api.disconnectAccount(platform)
      toast.success(`${PLATFORMS[platform].label} disconnected`)
      await load()
    } catch (err) {
      setOverview(prev) // roll back
      toast.error(err instanceof ApiError ? err.message : 'Disconnect failed')
    } finally {
      setBusyFor(platform, false)
    }
  }

  async function refresh(platform) {
    setBusyFor(platform, true)
    try {
      const res = await api.refreshAccount(platform)
      toast.success(res.message || `${PLATFORMS[platform].label} refreshed`)
      await load()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Refresh failed')
    } finally {
      setBusyFor(platform, false)
    }
  }

  const loading = overview === null
  const accountsByPlatform = Object.fromEntries(
    (overview?.accounts || []).map((a) => [a.platform, a]),
  )
  const noneConnected = !loading && overview.connected_count === 0

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Social Accounts</h1>
        <p className="text-sm text-muted">
          Connect one account per platform to publish across all of them from one place.
        </p>
      </div>

      {connectError && (
        <ConnectErrorBanner
          platform={connectError.platform}
          message={connectError.message}
          onDismiss={() => setConnectError(null)}
        />
      )}

      {loading ? (
        <SummarySkeleton />
      ) : (
        <ConnectionSummary
          summary={overview.summary}
          connectedCount={overview.connected_count}
          total={overview.total_platforms}
        />
      )}

      {noneConnected && <EmptyState />}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {loading
          ? PLATFORM_KEYS.map((p) => <CardSkeleton key={p} />)
          : PLATFORM_KEYS.map((p) => (
              <AccountCard
                key={p}
                platform={p}
                account={accountsByPlatform[p] || null}
                busy={!!busy[p]}
                onConnect={() => connect(p)}
                onDisconnect={() => disconnect(p)}
                onRefresh={() => refresh(p)}
              />
            ))}
      </div>

      {selection && (
        <AccountSelectModal
          platform={selection.platform}
          candidates={selection.candidates}
          busy={selecting}
          onSelect={confirmSelection}
          onClose={() => setSelection(null)}
        />
      )}
    </div>
  )
}

function applyRemoval(overview, platform) {
  if (!overview) return overview
  const accounts = overview.accounts.filter((a) => a.platform !== platform)
  return {
    ...overview,
    accounts,
    connected_count: accounts.length,
    summary: overview.summary.map((s) =>
      s.platform === platform
        ? { ...s, connected: false, status: 'not_connected' }
        : s,
    ),
  }
}

// Persistent, dismissible banner explaining why a connect attempt failed.
// Facebook's own "You've connected… Got it" dialog only means permission was
// granted on Facebook — this banner reports whether the account actually linked.
function ConnectErrorBanner({ platform, message, onDismiss }) {
  const label = PLATFORMS[platform]?.label || 'Account'
  const isInstagram = platform === 'instagram'
  return (
    <div className="card border border-rose-500/30 bg-rose-500/10 p-5">
      <div className="flex items-start gap-3">
        <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-rose-500/20 text-lg">
          ⚠️
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold text-rose-700 dark:text-rose-300">
            {label} was not connected
          </h3>
          <p className="mt-1 text-sm text-body">{message}</p>

          {isInstagram && (
            <div className="mt-3 rounded-xl bg-inset p-3 text-xs text-muted">
              <p className="mb-1 font-semibold">To fix this:</p>
              <ol className="list-decimal space-y-1 pl-4">
                <li>Make your Instagram a <b>Professional</b> account (Business or Creator).</li>
                <li>Link it to a <b>Facebook Page</b> you manage (Meta Business Suite → Settings → Instagram accounts).</li>
                <li>Click <b>Connect Instagram</b> again and grant that Page.</li>
              </ol>
              <p className="mt-2 text-muted">
                Note: Facebook's "You've connected… Got it" popup only confirms
                permission was granted — it doesn't mean the Instagram account linked here.
              </p>
            </div>
          )}
        </div>
        <button
          onClick={onDismiss}
          className="shrink-0 rounded-lg px-2 py-1 text-sm text-muted hover:bg-inset"
          aria-label="Dismiss"
        >
          ✕
        </button>
      </div>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="card flex flex-col items-center gap-3 p-10 text-center">
      <div className="grid h-16 w-16 place-items-center rounded-2xl bg-accent-soft text-3xl">
        🔗
      </div>
      <h3 className="text-lg font-semibold">No social accounts connected yet.</h3>
      <p className="max-w-md text-sm text-muted">
        Connect your social media accounts to start publishing posts across
        multiple platforms from one place.
      </p>
    </div>
  )
}

function SummarySkeleton() {
  return <div className="skeleton h-28 w-full rounded-2xl" />
}

function CardSkeleton() {
  return (
    <div className="card flex h-full flex-col gap-4 p-5">
      <div className="flex items-center gap-3">
        <div className="skeleton h-11 w-11 rounded-lg" />
        <div className="flex-1 space-y-2">
          <div className="skeleton h-3 w-24" />
          <div className="skeleton h-2.5 w-16" />
        </div>
      </div>
      <div className="space-y-2">
        <div className="skeleton h-2.5 w-full" />
        <div className="skeleton h-2.5 w-2/3" />
      </div>
      <div className="skeleton mt-auto h-9 w-full rounded-xl" />
    </div>
  )
}
