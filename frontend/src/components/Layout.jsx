import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { useTheme } from '../context/ThemeContext.jsx'

const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: '◧', end: true },
  { to: '/planner', label: 'Content Planner', icon: '🗓️' },
  { to: '/generate', label: 'AI Generator', icon: '✦' },
  { to: '/create', label: 'Create Post', icon: '✍' },
  { to: '/scheduler', label: 'Scheduler', icon: '◷' },
  { to: '/history', label: 'Post History', icon: '≡' },
  { to: '/accounts', label: 'Social Accounts', icon: '⬡' },
  { to: '/settings', label: 'Settings', icon: '⚙' },
]

function Brand() {
  return (
    <Link to="/dashboard" className="flex items-center gap-2 px-2">
      <div className="grid h-9 w-9 shrink-0 place-items-center rounded-[10px] bg-accent text-lg font-black text-accent-contrast">
        A
      </div>
      <div className="min-w-0">
        <div className="truncate text-sm font-bold leading-tight text-body">AutoSocial AI</div>
        <div className="truncate text-xs text-muted">AI Post Studio</div>
      </div>
    </Link>
  )
}

function NavItems({ onNavigate }) {
  return (
    <nav className="flex flex-col gap-1">
      {NAV.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          onClick={onNavigate}
          className={({ isActive }) => `nav-link ${isActive ? 'nav-link-active' : ''}`}
        >
          <span className="w-5 shrink-0 text-center text-base">{item.icon}</span>
          <span className="truncate">{item.label}</span>
        </NavLink>
      ))}
    </nav>
  )
}

export default function Layout() {
  const { user, logout } = useAuth()
  const { theme, toggle } = useTheme()
  const navigate = useNavigate()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)

  // Close the mobile drawer whenever the route changes.
  useEffect(() => {
    setDrawerOpen(false)
  }, [location.pathname])

  const initials = (user?.full_name || user?.email || '?').slice(0, 1).toUpperCase()

  return (
    <div className="app-bg flex min-h-screen">
      {/* ---- Desktop sidebar ---------------------------------------- */}
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-line bg-sidebar p-4 md:flex">
        <div className="mb-8">
          <Brand />
        </div>
        <NavItems />
        <button onClick={() => navigate('/generate')} className="btn btn-primary mt-6">
          ✦ Create Post
        </button>
        <div className="mt-auto px-2 pt-4 text-xs text-muted">
          Signed in as
          <div className="truncate font-medium text-body">{user?.email}</div>
        </div>
      </aside>

      {/* ---- Mobile drawer ------------------------------------------ */}
      {drawerOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setDrawerOpen(false)}
            aria-hidden
          />
          <aside className="absolute inset-y-0 left-0 flex w-72 max-w-[85%] flex-col border-r border-line bg-sidebar p-4 shadow-xl">
            <div className="mb-6 flex items-center justify-between">
              <Brand />
              <button
                onClick={() => setDrawerOpen(false)}
                className="btn btn-ghost btn-sm"
                aria-label="Close menu"
              >
                ✕
              </button>
            </div>
            <NavItems onNavigate={() => setDrawerOpen(false)} />
            <button
              onClick={() => navigate('/generate')}
              className="btn btn-primary mt-6"
            >
              ✦ Create Post
            </button>
            <div className="mt-auto px-2 pt-4 text-xs text-muted">
              Signed in as
              <div className="truncate font-medium text-body">{user?.email}</div>
            </div>
          </aside>
        </div>
      )}

      {/* ---- Main column -------------------------------------------- */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Topbar */}
        <header className="sticky top-0 z-30 flex items-center gap-2 border-b border-line bg-sidebar px-3 py-3 sm:gap-3 sm:px-4 md:px-6">
          <button
            onClick={() => setDrawerOpen(true)}
            className="btn btn-ghost btn-sm shrink-0 md:hidden"
            aria-label="Open menu"
          >
            ☰
          </button>

          <input
            placeholder="Search posts…"
            className="input hidden max-w-xs sm:block"
            aria-label="Search"
          />

          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={toggle}
              className="btn btn-ghost btn-sm shrink-0"
              title="Toggle theme"
              aria-label="Toggle light or dark mode"
            >
              {theme === 'dark' ? '☀' : '☾'}
              <span className="hidden sm:inline">{theme === 'dark' ? 'Light' : 'Dark'}</span>
            </button>
            <button
              onClick={() => navigate('/generate')}
              className="btn btn-primary btn-sm hidden shrink-0 sm:inline-flex"
            >
              ✦ Create
            </button>
            <div className="relative shrink-0">
              <button
                onClick={() => setMenuOpen((o) => !o)}
                className="grid h-9 w-9 place-items-center rounded-full bg-accent font-bold text-accent-contrast"
                aria-label="Account menu"
              >
                {initials}
              </button>
              {menuOpen && (
                <div
                  className="menu absolute right-0 z-50 mt-2 w-48"
                  onMouseLeave={() => setMenuOpen(false)}
                >
                  <div className="truncate px-3 py-2 text-xs text-muted">{user?.email}</div>
                  <button
                    onClick={() => {
                      setMenuOpen(false)
                      navigate('/settings')
                    }}
                    className="menu-item"
                  >
                    Settings
                  </button>
                  <button
                    onClick={() => {
                      setMenuOpen(false)
                      logout()
                      navigate('/')
                    }}
                    className="menu-item text-rose-500 hover:text-rose-400"
                  >
                    Log out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        <main className="min-w-0 flex-1 p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
