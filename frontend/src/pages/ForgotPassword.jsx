import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../lib/api'
import { AuthShell } from './Login.jsx'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    try {
      await api.forgotPassword(email)
      setSent(true)
    } catch (err) {
      // The endpoint is intentionally generic; still guard against network errors.
      if (err instanceof ApiError && err.status === 0) {
        setSent(false)
      } else {
        setSent(true) // don't reveal whether the email exists
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell title="Forgot password" subtitle="We'll email you a reset link">
      {sent ? (
        <div className="space-y-4">
          <div className="rounded-xl border border-line bg-inset p-4 text-sm">
            If an account exists for <span className="font-semibold">{email}</span>, we've
            sent password reset instructions. Check your inbox (and spam folder) —
            the link expires in 30 minutes.
          </div>
          <Link to="/login" className="btn btn-primary w-full">Back to sign in</Link>
        </div>
      ) : (
        <>
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="label">Email</label>
              <input className="input" type="email" required value={email}
                onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
            </div>
            <button className="btn btn-primary w-full" disabled={busy}>
              {busy ? 'Sending…' : 'Send reset link'}
            </button>
          </form>
          <p className="mt-6 text-center text-sm text-muted">
            Remembered it?{' '}
            <Link to="/login" className="font-semibold link-accent">Back to sign in</Link>
          </p>
        </>
      )}
    </AuthShell>
  )
}
