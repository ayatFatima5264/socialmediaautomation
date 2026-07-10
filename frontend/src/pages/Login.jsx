import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { useToast } from '../context/ToastContext.jsx'
import Logo from '../components/Logo.jsx'

export default function Login() {
  const { user, login } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to="/dashboard" replace />

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    try {
      await login(email, password)
      toast.success('Welcome back!')
      navigate('/dashboard')
    } catch (err) {
      toast.error(err.message || 'Login failed')
    } finally {
      setBusy(false)
    }
  }

  return <AuthShell title="Welcome back" subtitle="Sign in to your AI post studio">
    <form onSubmit={submit} className="space-y-4">
      <div>
        <label className="label">Email</label>
        <input className="input" type="email" required value={email}
          onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
      </div>
      <div>
        <div className="flex items-center justify-between">
          <label className="label">Password</label>
          <Link to="/forgot-password" className="text-xs font-semibold link-accent">
            Forgot password?
          </Link>
        </div>
        <PasswordField value={password} onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••" autoComplete="current-password" />
      </div>
      <button className="btn btn-primary w-full" disabled={busy}>
        {busy ? 'Signing in…' : 'Sign in'}
      </button>
    </form>
    <p className="mt-6 text-center text-sm text-muted">
      No account?{' '}
      <Link to="/register" className="font-semibold link-accent">
        Create one
      </Link>
    </p>
  </AuthShell>
}

// Password input with a show/hide eye toggle. Shared by Login and Register.
export function PasswordField({ value, onChange, placeholder, autoComplete = 'current-password', required = true }) {
  const [show, setShow] = useState(false)
  return (
    <div className="relative">
      <input
        className="input pr-10"
        type={show ? 'text' : 'password'}
        required={required}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        autoComplete={autoComplete}
      />
      <button
        type="button"
        onClick={() => setShow((s) => !s)}
        className="absolute inset-y-0 right-0 grid w-10 place-items-center text-muted transition hover:text-body"
        aria-label={show ? 'Hide password' : 'Show password'}
        title={show ? 'Hide password' : 'Show password'}
        tabIndex={-1}
      >
        {show ? (
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 10 8 10 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
            <path d="M1 1l22 22" />
            <path d="M6.61 6.61A18.5 18.5 0 0 0 2 12s3 8 10 8a9.12 9.12 0 0 0 5.39-1.61" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M1 12s3-8 11-8 11 8 11 8-3 8-11 8-11-8-11-8z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
        )}
      </button>
    </div>
  )
}

export function AuthShell({ title, subtitle, children }) {
  return (
    <div className="app-bg grid min-h-screen place-items-center p-4">
      <div className="w-full max-w-md">
        <Link to="/" className="mb-6 flex items-center justify-center gap-2">
          <Logo size={40} />
          <span className="text-xl font-bold">AutoSocial AI</span>
        </Link>
        <div className="card p-7">
          <h1 className="text-2xl font-bold">{title}</h1>
          <p className="mb-6 mt-1 text-sm text-muted">{subtitle}</p>
          {children}
        </div>
      </div>
    </div>
  )
}
