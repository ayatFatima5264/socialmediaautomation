// ---------------------------------------------------------------------------
// Cookie consent state.
//
// Google requires publishers to obtain consent before setting analytics and
// advertising cookies for visitors in the EEA, UK, and Switzerland, and an
// AdSense application is commonly rejected when no consent mechanism exists at
// all. Rather than region-sniffing (which is unreliable client-side), we ask
// everyone once — which is also the safer position for other privacy regimes.
//
// Nothing that sets a non-essential cookie may load before `hasConsent()`
// returns true. Analytics and AdSense both subscribe to this module.
// ---------------------------------------------------------------------------

const KEY = 'as_cookie_consent'

export const CONSENT_GRANTED = 'granted'
export const CONSENT_DENIED = 'denied'

const listeners = new Set()

// Reading localStorage can throw in private-browsing or embedded contexts.
function safeRead() {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}

function safeWrite(value) {
  try {
    localStorage.setItem(KEY, value)
  } catch {
    /* storage unavailable — the choice simply won't persist */
  }
}

// null = the visitor has not answered yet, so the banner should show.
export function getConsent() {
  const v = safeRead()
  return v === CONSENT_GRANTED || v === CONSENT_DENIED ? v : null
}

export function hasConsent() {
  return getConsent() === CONSENT_GRANTED
}

export function setConsent(value) {
  safeWrite(value)
  listeners.forEach((fn) => fn(value))
}

// Lets analytics/ads start the moment consent is granted, without a reload.
export function onConsentChange(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}
