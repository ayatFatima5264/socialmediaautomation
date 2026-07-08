import { PLATFORMS } from '../lib/constants'
import { formatDateTime, formatRelative } from '../lib/datetime'
import PlatformIcon from './PlatformIcon.jsx'
import AccountStatusBadge from './AccountStatusBadge.jsx'

// Connected account's avatar with the platform chip badged on its corner. Falls
// back to the plain platform chip when there's no profile picture.
function AccountAvatar({ platform, account }) {
  if (account?.profile_picture) {
    return (
      <span className="relative shrink-0">
        <img
          src={account.profile_picture}
          alt=""
          className="h-11 w-11 rounded-full object-cover"
        />
        <span className="absolute -bottom-1 -right-1 rounded-md ring-2 ring-surface">
          <PlatformIcon platform={platform} size={18} />
        </span>
      </span>
    )
  }
  return <PlatformIcon platform={platform} size={44} />
}

// A tiny inline spinner (no extra deps), used inside buttons while processing.
function Spinner() {
  return (
    <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
  )
}

// One platform card. Fixed height across the grid (h-full + flex column with the
// action pinned to the bottom via mt-auto), subtle hover lift, light/dark aware.
export default function AccountCard({
  platform,
  account,
  busy = false,
  onConnect,
  onDisconnect,
  onRefresh,
}) {
  const meta = PLATFORMS[platform]
  const status = account ? account.status : 'not_connected'
  const connected = status === 'connected'
  const needsReconnect = status === 'token_expired' || status === 'error'

  return (
    <div className="card flex h-full flex-col gap-4 p-5 transition-all duration-200 hover:-translate-y-0.5">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <AccountAvatar platform={platform} account={account} />
          <div>
            <div className="font-semibold leading-tight">{meta.label}</div>
            {account?.username ? (
              <div className="text-xs text-muted">
                @{account.username}
              </div>
            ) : (
              <div className="text-xs text-muted">
                Not linked
              </div>
            )}
          </div>
        </div>
        <AccountStatusBadge status={busy && !account ? 'syncing' : status} />
      </div>

      {/* Details */}
      <dl className="space-y-1.5 text-xs text-muted">
        <div className="flex items-center justify-between gap-2">
          <dt>Display name</dt>
          <dd className="truncate font-medium text-body">
            {account?.display_name || '—'}
          </dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt>Connected</dt>
          <dd className="font-medium text-body">
            {account?.connected_at ? formatDateTime(account.connected_at) : '—'}
          </dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt>Last sync</dt>
          <dd className="font-medium text-body">
            {account?.last_synced_at ? formatRelative(account.last_synced_at) : '—'}
          </dd>
        </div>
      </dl>

      {/* Actions — pinned to the bottom so every card is the same height */}
      <div className="mt-auto flex items-center gap-2 pt-1">
        {connected ? (
          <>
            <button
              onClick={onDisconnect}
              disabled={busy}
              className="btn btn-danger flex-1"
            >
              {busy ? <Spinner /> : 'Disconnect'}
            </button>
            <button
              onClick={onRefresh}
              disabled={busy}
              title="Refresh / re-sync"
              className="btn btn-ghost btn-sm"
            >
              Sync
            </button>
          </>
        ) : (
          <button
            onClick={onConnect}
            disabled={busy}
            className="btn btn-primary w-full"
          >
            {busy ? (
              <>
                <Spinner /> Connecting…
              </>
            ) : needsReconnect ? (
              'Reconnect'
            ) : (
              'Connect'
            )}
          </button>
        )}
      </div>
    </div>
  )
}
