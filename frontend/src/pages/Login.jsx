import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { useToast } from '../context/ToastContext.jsx'

export default function Login() {
  const { user, login } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to="/" replace />

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    try {
      await login(email, password)
      toast.success('Welcome back!')
      navigate('/')
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
        <label className="label">Password</label>
        <input className="input" type="password" required value={password}
          onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
      </div>
      <button className="btn btn-primary w-full" disabled={busy}>
        {busy ? 'Signing in…' : 'Sign in'}
      </button>
    </form>
    <p className="mt-6 text-center text-sm text-slate-400">
      No account?{' '}
      <Link to="/register" className="font-semibold text-indigo-400 hover:text-indigo-300">
        Create one
      </Link>
    </p>
  </AuthShell>
}

export function AuthShell({ title, subtitle, children }) {
  return (
    <div className="app-bg grid min-h-screen place-items-center p-4">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center justify-center gap-2">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-500 text-xl font-black text-white">
            S
          </div>
          <span className="text-xl font-bold">Social SaaS</span>
        </div>
        <div className="card p-7">
          <h1 className="text-2xl font-bold">{title}</h1>
          <p className="mb-6 mt-1 text-sm text-slate-400">{subtitle}</p>
          {children}
        </div>
      </div>
    </div>
  )
}
