import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext.jsx'
import { useTheme } from '../../context/ThemeContext.jsx'
import { MARKETING_NAV, FOOTER_COLUMNS, SITE } from '../../config/site'
import { trackPageView } from '../../lib/analytics'

function Brand() {
  return (
    <Link to="/" className="flex items-center gap-2">
      <div className="grid h-9 w-9 place-items-center rounded-xl bg-accent text-lg font-black text-accent-contrast">
        A
      </div>
      <span className="text-lg font-bold">{SITE.name}</span>
    </Link>
  )
}

// Authenticated user menu — avatar + dropdown (Dashboard / Settings / Logout).
// Shown in place of Login / Sign Up once a user is signed in (Notion/Buffer style).
function UserMenu() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  const name = user?.full_name || user?.email || 'Account'
  const initial = name.slice(0, 1).toUpperCase()

  // Close on outside click.
  useEffect(() => {
    function onDoc(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 rounded-full border border-line py-1 pl-1 pr-3 transition hover:bg-inset"
      >
        <span className="grid h-7 w-7 place-items-center rounded-full bg-accent text-xs font-bold text-accent-contrast">
          {initial}
        </span>
        <span className="hidden max-w-[10rem] truncate text-sm font-medium sm:block">
          {user?.full_name || user?.email}
        </span>
        <span className="text-xs text-muted">▾</span>
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-2 w-56 overflow-hidden rounded-2xl border border-line bg-surface p-1 text-sm shadow-sm">
          <div className="border-b border-line px-3 py-2">
            <div className="truncate font-medium">{user?.full_name || 'Signed in'}</div>
            <div className="truncate text-xs text-muted">{user?.email}</div>
          </div>
          <button onClick={() => { setOpen(false); navigate('/dashboard') }} className="nav-link w-full">
            <span className="w-5 text-center">◧</span> Go to Dashboard
          </button>
          <button onClick={() => { setOpen(false); navigate('/settings') }} className="nav-link w-full">
            <span className="w-5 text-center">⚙</span> Settings
          </button>
          <button
            onClick={() => { setOpen(false); logout(); navigate('/') }}
            className="nav-link w-full text-rose-500 hover:text-rose-400"
          >
            <span className="w-5 text-center">⏻</span> Logout
          </button>
        </div>
      )}
    </div>
  )
}

// Login / Sign Up for guests. Authenticated users get the UserMenu instead, so
// Login and Sign Up are never shown to them.
function AuthArea({ onNavigate }) {
  const { user } = useAuth()
  if (user) return <UserMenu />
  return (
    <>
      <Link to="/login" onClick={onNavigate} className="btn btn-ghost btn-sm">
        Login
      </Link>
      <Link to="/register" onClick={onNavigate} className="btn btn-primary btn-sm">
        Sign Up
      </Link>
    </>
  )
}

export default function PublicLayout() {
  const { theme, toggle } = useTheme()
  const { user } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const closeMenu = () => setMenuOpen(false)
  const { pathname } = useLocation()

  // Report each marketing page view (no-op unless analytics is configured).
  useEffect(() => {
    trackPageView(pathname)
  }, [pathname])

  return (
    <div className="app-bg flex min-h-screen flex-col">
      {/* Top navigation */}
      <header className="sticky top-0 z-30 border-b border-line bg-sidebar backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3 md:px-6">
          <Brand />

          <nav className="ml-6 hidden items-center gap-1 md:flex">
            {MARKETING_NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => `nav-link ${isActive ? 'nav-link-active' : ''}`}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <button onClick={toggle} className="btn btn-ghost btn-sm" title="Toggle theme">
              {theme === 'dark' ? '☀' : '☾'}
            </button>
            <div className="hidden items-center gap-2 md:flex">
              <AuthArea />
            </div>
            <button
              onClick={() => setMenuOpen((o) => !o)}
              className="btn btn-ghost btn-sm md:hidden"
              aria-label="Toggle menu"
            >
              ☰
            </button>
          </div>
        </div>

        {/* Mobile menu */}
        {menuOpen && (
          <div className="border-t border-line px-4 py-3 md:hidden">
            <nav className="flex flex-col gap-1">
              {MARKETING_NAV.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  onClick={closeMenu}
                  className={({ isActive }) => `nav-link ${isActive ? 'nav-link-active' : ''}`}
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
            <div className="mt-3 flex items-center gap-2">
              {user ? <UserMenu /> : <AuthArea onNavigate={closeMenu} />}
            </div>
          </div>
        )}
      </header>

      {/* Page content */}
      <main className="flex-1">
        <Outlet />
      </main>

      <PublicFooter />
    </div>
  )
}

function FooterLink({ link, className }) {
  const inner = (
    <>
      {link.label}
      {link.badge && (
        <span className="ml-1.5 rounded-full bg-accent-soft px-1.5 py-0.5 text-[10px] font-semibold text-accent">
          {link.badge}
        </span>
      )}
    </>
  )
  // Internal route vs placeholder/external link.
  return link.to ? (
    <Link to={link.to} className={className}>
      {inner}
    </Link>
  ) : (
    <a href={link.href || '#'} className={className}>
      {inner}
    </a>
  )
}

function PublicFooter() {
  const linkCls =
    'inline-flex items-center text-muted transition hover:text-accent'
  return (
    <footer className="border-t border-line bg-surface">
      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-12 md:grid-cols-5 md:px-6">
        <div className="md:col-span-1">
          <Brand />
          <p className="mt-3 max-w-xs text-sm text-muted">
            Generate, schedule, and publish on-brand social content with AI —
            across every platform, from one studio.
          </p>
        </div>
        {FOOTER_COLUMNS.map((col) => (
          <div key={col.title}>
            <div className="mb-3 text-sm font-semibold text-body">
              {col.title}
            </div>
            <ul className="space-y-2 text-sm">
              {col.links.map((l) => (
                <li key={l.label}>
                  <FooterLink link={l} className={linkCls} />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-col-reverse items-center justify-between gap-4 px-4 py-6 md:flex-row md:px-6">
          <p className="text-xs text-muted">
            © 2026 {SITE.name}. All rights reserved.
          </p>
          <SocialIcons />
        </div>
      </div>
    </footer>
  )
}

function SocialIcons() {
  const cls =
    'grid h-9 w-9 place-items-center rounded-lg border border-line text-muted transition hover:border-accent-line hover:text-accent'
  return (
    <div className="flex items-center gap-2">
      <a href={SITE.socials.facebook} aria-label="Facebook" className={cls} target="_blank" rel="noreferrer">
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor" aria-hidden="true">
          <path d="M13.5 21v-8h2.7l.4-3.1h-3.1V7.9c0-.9.25-1.5 1.55-1.5H16.7V3.6c-.28-.04-1.25-.12-2.38-.12-2.35 0-3.96 1.44-3.96 4.07v2.27H7.6V13h2.76v8h3.14z" />
        </svg>
      </a>
      <a href={SITE.socials.instagram} aria-label="Instagram" className={cls} target="_blank" rel="noreferrer">
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <rect x="3" y="3" width="18" height="18" rx="5" />
          <circle cx="12" cy="12" r="3.5" />
          <circle cx="17.3" cy="6.7" r="1" fill="currentColor" stroke="none" />
        </svg>
      </a>
      <a href={SITE.socials.linkedin} aria-label="LinkedIn" className={cls} target="_blank" rel="noreferrer">
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor" aria-hidden="true">
          <path d="M6.94 6.5A1.94 1.94 0 113.06 6.5a1.94 1.94 0 013.88 0zM3.4 8.9h3.1V21H3.4V8.9zM9.1 8.9h2.97v1.65h.04c.41-.78 1.42-1.6 2.93-1.6 3.13 0 3.71 2.06 3.71 4.74V21h-3.1v-5.35c0-1.28-.02-2.92-1.78-2.92-1.78 0-2.05 1.39-2.05 2.83V21H9.1V8.9z" />
        </svg>
      </a>
      <a href={SITE.socials.x} aria-label="X" className={cls} target="_blank" rel="noreferrer">
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor" aria-hidden="true">
          <path d="M17.53 3H20.5l-6.49 7.41L21.75 21h-6l-4.7-6.14L5.68 21H2.7l6.94-7.93L2.25 3h6.15l4.25 5.62L17.53 3zm-1.05 16.2h1.65L7.6 4.71H5.83L16.48 19.2z" />
        </svg>
      </a>
    </div>
  )
}
