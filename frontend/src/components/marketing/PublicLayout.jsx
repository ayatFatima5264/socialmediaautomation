import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext.jsx'
import { MARKETING_NAV, FOOTER_COLUMNS, SITE } from '../../config/site'
import { trackPageView } from '../../lib/analytics'
import Logo from '../Logo.jsx'
import CookieConsent from './CookieConsent.jsx'

function Brand() {
  return (
    <Link to="/" className="flex items-center gap-2">
      <Logo size={36} />
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
      {/* Keyboard users can jump past the nav straight to the content. Visible
          only while focused, per the standard skip-link pattern. */}
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-accent focus:px-4 focus:py-2 focus:font-semibold focus:text-accent-contrast"
      >
        Skip to main content
      </a>

      {/* Top navigation */}
      <header className="sticky top-0 z-30 border-b border-line bg-sidebar backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3 md:px-6">
          <Brand />

          {/* Desktop nav. The app's sidebar pill (`nav-link-active`) reads as a
              selected row in a list, which is right inside the product and
              wrong on a marketing header — here the current page is marked with
              an underline instead. */}
          <nav className="ml-6 hidden items-center gap-1 md:flex">
            {MARKETING_NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? 'text-body underline decoration-accent decoration-2 underline-offset-[10px]'
                      : 'text-muted hover:text-body'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2">
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
                  end={item.end}
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
      <main id="main" className="flex-1">
        <Outlet />
      </main>

      <PublicFooter />
      <CookieConsent />
    </div>
  )
}

function FooterLink({ link, className }) {
  // Every footer entry is an internal route now that the placeholder "#" links
  // are gone; `href` is still honoured for anything genuinely external.
  return link.to ? (
    <Link to={link.to} className={className}>
      {link.label}
    </Link>
  ) : (
    <a href={link.href} className={className} target="_blank" rel="noreferrer">
      {link.label}
    </a>
  )
}

function PublicFooter() {
  const linkCls =
    'inline-flex items-center text-muted transition hover:text-accent'
  return (
    <footer className="border-t border-line bg-surface">
      <div className="mx-auto grid max-w-6xl gap-10 px-4 py-14 md:grid-cols-[1.4fr_repeat(3,1fr)] md:px-6">
        <div>
          <Brand />
          <p className="mt-3 max-w-xs text-sm leading-relaxed text-muted">
            Create, plan and publish your social content from one place —
            across Instagram, Facebook, LinkedIn, X, Threads and Pinterest.
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

// Own social profiles, rendered only for the ones that have a URL in
// config/site.js. Every icon here used to point at a placeholder handle that
// does not exist, so the whole row was dead links; now an icon appears when the
// profile is real, and the row disappears entirely when none are.
const SOCIAL_MARKS = {
  facebook: {
    label: 'Facebook',
    path: 'M13.5 21v-8h2.7l.4-3.1h-3.1V7.9c0-.9.25-1.5 1.55-1.5H16.7V3.6c-.28-.04-1.25-.12-2.38-.12-2.35 0-3.96 1.44-3.96 4.07v2.27H7.6V13h2.76v8h3.14z',
  },
  linkedin: {
    label: 'LinkedIn',
    path: 'M6.94 6.5A1.94 1.94 0 113.06 6.5a1.94 1.94 0 013.88 0zM3.4 8.9h3.1V21H3.4V8.9zM9.1 8.9h2.97v1.65h.04c.41-.78 1.42-1.6 2.93-1.6 3.13 0 3.71 2.06 3.71 4.74V21h-3.1v-5.35c0-1.28-.02-2.92-1.78-2.92-1.78 0-2.05 1.39-2.05 2.83V21H9.1V8.9z',
  },
  x: {
    label: 'X',
    path: 'M17.53 3H20.5l-6.49 7.41L21.75 21h-6l-4.7-6.14L5.68 21H2.7l6.94-7.93L2.25 3h6.15l4.25 5.62L17.53 3zm-1.05 16.2h1.65L7.6 4.71H5.83L16.48 19.2z',
  },
  instagram: {
    label: 'Instagram',
    path: 'M12 7.2a4.8 4.8 0 100 9.6 4.8 4.8 0 000-9.6zm0 7.9a3.1 3.1 0 110-6.2 3.1 3.1 0 010 6.2zM17.4 5.5a1.12 1.12 0 100 2.24 1.12 1.12 0 000-2.24zM12 3.7c2.7 0 3 .01 4.07.06 2.73.12 4.05 1.46 4.17 4.17.05 1.06.06 1.38.06 4.07s-.01 3-.06 4.07c-.12 2.7-1.44 4.05-4.17 4.17-1.06.05-1.37.06-4.07.06s-3-.01-4.07-.06c-2.73-.12-4.05-1.47-4.17-4.17C3.71 15 3.7 14.69 3.7 12s.01-3 .06-4.07C3.88 5.22 5.2 3.88 7.93 3.76 9 3.71 9.3 3.7 12 3.7z',
  },
}

function SocialIcons() {
  const live = Object.entries(SOCIAL_MARKS).filter(([key]) => SITE.socials?.[key])
  if (live.length === 0) return null

  const cls =
    'grid h-9 w-9 place-items-center rounded-lg border border-line text-muted transition hover:border-accent-line hover:text-accent'
  return (
    <div className="flex items-center gap-2">
      {live.map(([key, mark]) => (
        <a
          key={key}
          href={SITE.socials[key]}
          aria-label={mark.label}
          className={cls}
          target="_blank"
          rel="noreferrer"
        >
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor" aria-hidden="true">
            <path d={mark.path} />
          </svg>
        </a>
      ))}
    </div>
  )
}
