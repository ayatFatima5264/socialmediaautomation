import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { useToast } from '../context/ToastContext.jsx'
import { api } from '../lib/api'
import { formatDateTime } from '../lib/datetime'

// ---------------------------------------------------------------------------
// Settings — account administration only.
//
// Deliberately carries no posting statistics or analytics: those live on the
// Dashboard, and duplicating them here would mean two places to keep correct.
// What belongs here is everything about the account itself — who you are, the
// context the AI writes with, security, and the destructive actions.
//
// Sections that have no backend yet are shown as honestly unavailable rather
// than as buttons that quietly do nothing.
// ---------------------------------------------------------------------------

function SectionHeader({ title, description, action }) {
  return (
    <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 className="text-base font-bold">{title}</h2>
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      </div>
      {action}
    </div>
  )
}

// A labelled row inside a card. `mono` is for identifiers, where the shape of
// the value matters more than its readability as prose.
function Row({ label, value, mono }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 border-b border-line py-3 last:border-0">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className={`text-sm font-medium ${mono ? 'font-mono text-[13px]' : ''}`}>{value}</dd>
    </div>
  )
}

function ComingSoon() {
  return (
    <span className="shrink-0 rounded-full border border-line bg-inset px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-muted">
      Coming soon
    </span>
  )
}

// One row in Account & Security: a title, an explanation, and either a working
// control or a Coming soon pill.
function SecurityRow({ title, description, action, last }) {
  return (
    <div
      className={`flex flex-wrap items-center justify-between gap-4 py-4 ${
        last ? '' : 'border-b border-line'
      }`}
    >
      <div className="min-w-[16rem] flex-1">
        <div className="text-sm font-semibold">{title}</div>
        <p className="mt-0.5 text-sm leading-relaxed text-muted">{description}</p>
      </div>
      {action}
    </div>
  )
}

// ---- Profile ---------------------------------------------------------------

function ProfileCard() {
  const { user, updateUser } = useAuth()
  const toast = useToast()
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(user?.full_name || '')
  const [saving, setSaving] = useState(false)

  const displayName = user?.full_name?.trim() || 'Unnamed account'
  const initials =
    (user?.full_name?.trim() || user?.email || '?')
      .split(/\s+/)
      .slice(0, 2)
      .map((w) => w[0])
      .join('')
      .toUpperCase() || '?'

  function startEditing() {
    setName(user?.full_name || '')
    setEditing(true)
  }

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    try {
      const updated = await api.updateMe({ full_name: name })
      // Merge rather than replace so nothing the server omits gets dropped.
      updateUser(updated)
      setEditing(false)
      toast.success('Profile updated')
    } catch (err) {
      toast.error(err?.message || 'Could not update your profile')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="card p-6 md:p-7">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
        <div
          className="grid h-20 w-20 shrink-0 place-items-center rounded-2xl bg-accent text-2xl font-black text-accent-contrast"
          aria-hidden="true"
        >
          {initials}
        </div>

        <div className="min-w-0 flex-1">
          <h2 className="truncate text-xl font-bold">{displayName}</h2>
          <p className="mt-0.5 truncate text-sm text-muted">{user?.email}</p>
        </div>

        {!editing && (
          <button onClick={startEditing} className="btn btn-secondary shrink-0">
            Edit Profile
          </button>
        )}
      </div>

      {editing && (
        <form onSubmit={save} className="mt-6 border-t border-line pt-6">
          <label htmlFor="full_name" className="label">
            Display name
          </label>
          <input
            id="full_name"
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="How your name appears across the app"
            maxLength={255}
            autoFocus
          />
          <p className="mt-2 text-xs text-muted">
            Your email address cannot be changed here — it identifies your account.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? 'Saving…' : 'Save changes'}
            </button>
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="btn btn-ghost"
              disabled={saving}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      <dl className="mt-6 border-t border-line pt-2">
        <Row label="Email" value={user?.email} />
        <Row
          label="Member since"
          value={user?.created_at ? formatDateTime(user.created_at) : '—'}
        />
        <Row label="Account ID" value={`#${user?.id}`} mono />
      </dl>
    </section>
  )
}

// ---- Business profile ------------------------------------------------------

// The card adapts its call to action to whether the profile has been filled in,
// because "Complete Profile" and "Manage Profile" prompt very different actions
// and showing the wrong one is worse than showing neither.
function BusinessProfileCard() {
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    api
      .getBusinessProfile()
      .then((p) => {
        if (!cancelled) setProfile(p)
      })
      .catch(() => {
        if (!cancelled) setProfile(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // The fields that actually change what the AI produces.
  const filled = profile
    ? [
        profile.business_name,
        profile.industry,
        profile.business_description,
        profile.target_audience,
        profile.brand_voice?.length,
        profile.business_goals?.length,
      ].filter(Boolean).length
    : 0
  const total = 6
  const complete = filled === total

  return (
    <section className="card p-6 md:p-7">
      <SectionHeader
        title="Business Profile"
        description="The context AI uses to write in your voice — your industry, audience, tone, and goals."
      />

      {loading ? (
        <div className="skeleton h-2 w-full" />
      ) : (
        <>
          <div className="flex items-center gap-3">
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-inset">
              <div
                className="h-full rounded-full bg-accent transition-[width] duration-500"
                style={{ width: `${(filled / total) * 100}%` }}
              />
            </div>
            <span className="shrink-0 text-xs font-semibold text-muted">
              {filled}/{total}
            </span>
          </div>

          <p className="mt-3 text-sm text-muted">
            {complete
              ? 'Your profile is complete. Updating it changes how future content is written.'
              : `Add the remaining ${total - filled} ${
                  total - filled === 1 ? 'detail' : 'details'
                } to get noticeably more on-brand results.`}
          </p>

          <Link
            to="/business-profile"
            className={`btn mt-5 ${complete ? 'btn-secondary' : 'btn-primary'}`}
          >
            {complete ? 'Manage Profile' : 'Complete Profile'}
          </Link>
        </>
      )}
    </section>
  )
}

// ---- Account & security ----------------------------------------------------

function SecurityCard() {
  const { user } = useAuth()
  const toast = useToast()
  const [sending, setSending] = useState(false)
  const [sent, setSent] = useState(false)

  // There is no authenticated change-password endpoint, but the email reset
  // flow is fully implemented — so this triggers that rather than presenting a
  // form that would have nothing to submit to.
  async function sendReset() {
    if (!user?.email) return
    setSending(true)
    try {
      await api.forgotPassword(user.email)
      setSent(true)
      toast.success('Password reset link sent — check your inbox')
    } catch (err) {
      toast.error(err?.message || 'Could not send the reset email')
    } finally {
      setSending(false)
    }
  }

  return (
    <section className="card p-6 md:p-7">
      <SectionHeader
        title="Account & Security"
        description="Control how you sign in and keep your account protected."
      />

      <div className="-mt-1">
        <SecurityRow
          title="Password"
          description={
            sent
              ? `We sent a reset link to ${user?.email}. It expires shortly for security.`
              : 'We email you a secure link rather than asking for your current password.'
          }
          action={
            <button
              onClick={sendReset}
              className="btn btn-secondary shrink-0"
              disabled={sending || sent}
            >
              {sending ? 'Sending…' : sent ? 'Link sent' : 'Change Password'}
            </button>
          }
        />

        <SecurityRow
          title="Two-Factor Authentication"
          description="Require a second step when signing in, for stronger protection against stolen passwords."
          action={<ComingSoon />}
        />

        <SecurityRow
          last
          title="Active Sessions"
          description="You're signed in on this device. Signing out here ends this session; we can't yet list or revoke sessions on your other devices."
          action={
            <span className="inline-flex shrink-0 items-center gap-2 rounded-full border border-accent-line bg-accent-soft px-3 py-1 text-xs font-semibold text-accent">
              <span className="h-1.5 w-1.5 rounded-full bg-accent" />
              This device
            </span>
          }
        />
      </div>
    </section>
  )
}

// ---- Danger zone -----------------------------------------------------------

// Account deletion is intentionally absent: there is no endpoint for it, and a
// button that appears to delete an account but does nothing is far worse than
// its absence. Add it here once the backend supports it.
function DangerZone() {
  const { logout } = useAuth()

  return (
    <section className="card border-rose-400/40 p-6 md:p-7">
      <SectionHeader
        title="Danger Zone"
        description="Actions here end your current session. Nothing is deleted."
      />
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-line bg-inset p-4">
        <div>
          <div className="text-sm font-semibold">Log out</div>
          <p className="mt-0.5 text-sm text-muted">
            Sign out on this device. Your content and schedule are unaffected.
          </p>
        </div>
        <button onClick={logout} className="btn btn-danger shrink-0">
          Log Out
        </button>
      </div>
    </section>
  )
}

// ---- Page ------------------------------------------------------------------

export default function Settings() {
  return (
    <div className="mx-auto max-w-4xl space-y-6 pb-4">
      <header>
        <h1 className="text-2xl font-bold md:text-3xl">Settings</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
          Manage your account details, the business context your AI content is built from, and
          how you sign in. Posting activity and performance live on your{' '}
          <Link to="/dashboard" className="link-accent font-medium">
            Dashboard
          </Link>
          .
        </p>
      </header>

      <ProfileCard />
      <BusinessProfileCard />
      <SecurityCard />
      <DangerZone />
    </div>
  )
}
