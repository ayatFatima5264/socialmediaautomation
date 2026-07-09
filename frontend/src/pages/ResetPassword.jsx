import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../lib/api'
import { useToast } from '../context/ToastContext.jsx'
import { AuthShell, PasswordField } from './Login.jsx'

export default function ResetPassword() {
  const [params] = useSearchParams()
  const token = params.get('token') || ''
  const toast = useToast()
  const navigate = useNavigate()
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    if (password.length < 8) { toast.error('Password must be at least 8 characters'); return }
    if (password !== confirm) { toast.error('Passwords do not match'); return }
    setBusy(true)
    try {
      const res = await api.resetPassword(token, password)
      toast.success(res?.message || 'Password reset')
      navigate('/login')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not reset password')
    } finally {
      setBusy(false)
    }
  }

  if (!token) {
    return (
      <AuthShell title="Reset password" subtitle="Set a new password">
        <div className="space-y-4">
          <div className="rounded-xl border border-line bg-inset p-4 text-sm">
            This reset link is missing or invalid. Please request a new one.
          </div>
          <Link to="/forgot-password" className="btn btn-primary w-full">Request a new link</Link>
        </div>
      </AuthShell>
    )
  }

  return (
    <AuthShell title="Reset password" subtitle="Set a new password for your account">
      <form onSubmit={submit} className="space-y-4">
        <div>
          <label className="label">New password</label>
          <PasswordField value={password} onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 8 characters" autoComplete="new-password" />
        </div>
        <div>
          <label className="label">Confirm new password</label>
          <PasswordField value={confirm} onChange={(e) => setConfirm(e.target.value)}
            placeholder="Re-enter password" autoComplete="new-password" />
        </div>
        <button className="btn btn-primary w-full" disabled={busy}>
          {busy ? 'Resetting…' : 'Reset password'}
        </button>
      </form>
      <p className="mt-6 text-center text-sm text-muted">
        <Link to="/login" className="font-semibold link-accent">Back to sign in</Link>
      </p>
    </AuthShell>
  )
}
