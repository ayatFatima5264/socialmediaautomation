import { createContext, useContext, useEffect, useState } from 'react'
import { api, getToken, setToken } from '../lib/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  // On mount, if we have a token, load the current user.
  useEffect(() => {
    const t = getToken()
    if (!t) {
      setLoading(false)
      return
    }
    api
      .me()
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setLoading(false))
  }, [])

  async function login(email, password) {
    const { access_token } = await api.login(email, password)
    setToken(access_token)
    setUser(await api.me())
  }

  async function register(email, password, fullName) {
    await api.register({ email, password, full_name: fullName || null })
    await login(email, password)
  }

  function logout() {
    setToken(null)
    setUser(null)
  }

  // Merge fields into the current user (e.g. after finishing onboarding), so
  // the UI updates without a full refetch.
  function updateUser(patch) {
    setUser((u) => (u ? { ...u, ...patch } : u))
  }

  return (
    <AuthContext.Provider
      value={{ user, loading, login, register, logout, updateUser }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
