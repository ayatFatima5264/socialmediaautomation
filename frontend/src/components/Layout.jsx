import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { useTheme } from '../context/ThemeContext.jsx'

const NAV = [
  { to: '/', label: 'Dashboard', icon: '◧', end: true },
  { to: '/generate', label: 'AI Generator', icon: '✦' },
  { to: '/create', label: 'Create Post', icon: '✍' },
  { to: '/scheduler', label: 'Scheduler', icon: '◷' },
  { to: '/history', label: 'Post History', icon: '≡' },
  { to: '/accounts', label: 'Social Accounts', icon: '⬡' },
  { to: '/settings', label: 'Settings', icon: '⚙' },
]

export default function Layout() {
  const { user, logout } = useAuth()
  const { theme, toggle } = useTheme()
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)

  const initials = (user?.full_name || user?.email || '?').slice(0, 1).toUpperCase()

  return (
    <div className="app-bg flex min-h-screen">
      {/* Sidebar */}
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-slate-200 bg-white/70 p-4 backdrop-blur-xl dark:border-white/10 dark:bg-slate-900/40 md:flex">
        <div className="mb-8 flex items-center gap-2 px-2">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-500 text-lg font-black text-white">
            A
          </div>
          <div>
            <div className="text-sm font-bold leading-tight">AutoSocial AI</div>
            <div className="text-xs text-slate-400">AI Post Studio</div>
          </div>
        </div>

        <nav className="flex flex-col gap-1">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `nav-link ${isActive ? 'nav-link-active' : ''}`
              }
            >
              <span className="w-5 text-center text-base">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <button onClick={() => navigate('/generate')} className="btn btn-primary mt-6">
          ✦ Create Post
        </button>

        <div className="mt-auto px-2 pt-4 text-xs text-slate-400">
          Signed in as
          <div className="truncate font-medium text-slate-500 dark:text-slate-300">
            {user?.email}
          </div>
        </div>
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Topbar */}
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-slate-200 bg-white/70 px-4 py-3 backdrop-blur-xl dark:border-white/10 dark:bg-slate-900/40 md:px-6">
          <input
            placeholder="Search posts…"
            className="input max-w-xs"
            aria-label="Search"
          />
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={toggle}
              className="btn btn-ghost btn-sm"
              title="Toggle theme"
            >
              {theme === 'dark' ? '☀ Light' : '☾ Dark'}
            </button>
            <button onClick={() => navigate('/generate')} className="btn btn-primary btn-sm">
              ✦ Create Post
            </button>
            <div className="relative">
              <button
                onClick={() => setMenuOpen((o) => !o)}
                className="grid h-9 w-9 place-items-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 font-bold text-white"
              >
                {initials}
              </button>
              {menuOpen && (
                <div
                  className="card absolute right-0 mt-2 w-48 overflow-hidden p-1 text-sm"
                  onMouseLeave={() => setMenuOpen(false)}
                >
                  <div className="truncate px-3 py-2 text-xs text-slate-400">
                    {user?.email}
                  </div>
                  <button
                    onClick={() => {
                      setMenuOpen(false)
                      navigate('/settings')
                    }}
                    className="nav-link w-full"
                  >
                    Settings
                  </button>
                  <button
                    onClick={logout}
                    className="nav-link w-full text-rose-500 hover:text-rose-400"
                  >
                    Log out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        <main className="flex-1 p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
