// ---------------------------------------------------------------------------
// Analytics-ready abstraction. No provider loads unless its ID is configured
// via env, so this is a safe no-op in development and for privacy by default.
//
//   VITE_GA_ID       — Google Analytics 4 measurement ID (e.g. "G-XXXXXXX")
//   VITE_CLARITY_ID  — Microsoft Clarity project ID
//   VITE_ADSENSE_ID  — Google AdSense publisher ID (e.g. "ca-pub-1234567890")
//
// Nothing here loads until the visitor has granted cookie consent — analytics
// and advertising cookies are not "strictly necessary", so loading them before
// a choice is made would breach the consent requirements Google enforces for
// AdSense publishers.
//
// To add a provider later you only touch this file; call sites (initAnalytics,
// trackPageView) stay the same.
// ---------------------------------------------------------------------------

import { hasConsent, onConsentChange } from './consent'

const GA_ID = import.meta.env.VITE_GA_ID
const CLARITY_ID = import.meta.env.VITE_CLARITY_ID
const ADSENSE_ID = import.meta.env.VITE_ADSENSE_ID

let initialized = false

function loadGA(id) {
  const s = document.createElement('script')
  s.async = true
  s.src = `https://www.googletagmanager.com/gtag/js?id=${id}`
  document.head.appendChild(s)
  window.dataLayer = window.dataLayer || []
  window.gtag = function gtag() {
    window.dataLayer.push(arguments)
  }
  window.gtag('js', new Date())
  window.gtag('config', id, { send_page_view: false })
}

function loadClarity(id) {
  ;(function (c, l, a, r, i, t, y) {
    c[a] =
      c[a] ||
      function () {
        ;(c[a].q = c[a].q || []).push(arguments)
      }
    t = l.createElement(r)
    t.async = 1
    t.src = 'https://www.clarity.ms/tag/' + i
    y = l.getElementsByTagName(r)[0]
    y.parentNode.insertBefore(t, y)
  })(window, document, 'clarity', 'script', id)
}

// Google AdSense. The script is what the AdSense reviewer looks for on the
// site during the approval check, and it must appear on pages with content.
function loadAdSense(id) {
  const s = document.createElement('script')
  s.async = true
  s.crossOrigin = 'anonymous'
  s.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${id}`
  document.head.appendChild(s)
}

function loadAll() {
  if (initialized) return
  initialized = true
  if (GA_ID) loadGA(GA_ID)
  if (CLARITY_ID) loadClarity(CLARITY_ID)
  if (ADSENSE_ID) loadAdSense(ADSENSE_ID)
}

// Call once at app startup. Loads immediately if consent was already given on
// a previous visit; otherwise waits for the banner's decision.
export function initAnalytics() {
  if (typeof window === 'undefined') return
  if (hasConsent()) {
    loadAll()
    return
  }
  onConsentChange((value) => {
    if (value === 'granted') loadAll()
  })
}

// Report a client-side navigation as a page view.
export function trackPageView(path) {
  if (GA_ID && typeof window.gtag === 'function') {
    window.gtag('event', 'page_view', { page_path: path, page_location: window.location.href })
  }
}

// Generic custom event — use for CTA clicks, signups, etc.
export function trackEvent(name, params = {}) {
  if (GA_ID && typeof window.gtag === 'function') {
    window.gtag('event', name, params)
  }
}

export const analyticsEnabled = Boolean(GA_ID || CLARITY_ID)
export const adsenseEnabled = Boolean(ADSENSE_ID)
export const ADSENSE_CLIENT = ADSENSE_ID || null
