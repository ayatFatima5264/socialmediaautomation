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
  // Connected, but authorized without a now-required permission (e.g. X's
  // media.write). The account stays connected — we only ask the user to
  // reconnect to grant it. Text-only publishing keeps working.
  const needsReauth = !!account?.reauth_required

  return (
    <div className="card flex h-full flex-col gap-4 p-5 transition-all duration-200 hover:-translate-y-0.5">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <AccountAvatar platform={platform} account={account} />
          <div className="min-w-0">
            <div className="truncate font-semibold leading-tight">{meta.label}</div>
            {account?.username ? (
              <div className="truncate text-xs text-muted">
                @{account.username}
              </div>
            ) : (
              <div className="truncate text-xs text-muted">
                Not linked
              </div>
            )}
          </div>
        </div>
        <div className="shrink-0 whitespace-nowrap">
          <AccountStatusBadge status={busy && !account ? 'syncing' : status} />
        </div>
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

      {/* Re-authorization notice — connected, but missing a required permission.
          Not disconnected: text-only publishing still works. */}
      {connected && needsReauth && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs">
          <p className="font-semibold text-amber-700 dark:text-amber-300">
            Reconnect required
          </p>
          <p className="mt-1 text-body">
            Grant the new media permission to post images and video from{' '}
            {meta.label}. Text-only posts still work until you do.
          </p>
        </div>
      )}

      {/* Actions — pinned to the bottom so every card is the same height */}
      <div className="mt-auto flex items-center gap-2 pt-1">
        {connected ? (
          needsReauth ? (
            <>
              <button
                onClick={onConnect}
                disabled={busy}
                className="btn btn-primary flex-1"
              >
                {busy ? (
                  <>
                    <Spinner /> Connecting…
                  </>
                ) : (
                  'Reconnect'
                )}
              </button>
              <button
                onClick={onDisconnect}
                disabled={busy}
                title="Disconnect"
                className="btn btn-ghost btn-sm"
              >
                Disconnect
              </button>
            </>
          ) : (
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
          )
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
