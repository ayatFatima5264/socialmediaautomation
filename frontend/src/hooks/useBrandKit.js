import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import { DEFAULT_TEMPLATE } from '../lib/brandKit/templates'
import { hasBrandAssets } from '../lib/brandKit/layers'

// ---------------------------------------------------------------------------
// Loads the user's Brand Kit (their business profile) and remembers their
// overlay preferences.
//
// The profile is cached at module scope: several surfaces show branded images
// at once, and each mounting its own fetch would mean a burst of identical
// requests on every page load. `refresh()` clears it after an edit.
//
// Preferences persist to localStorage rather than the server — they are a
// per-device view setting, like a zoom level, not account data.
// ---------------------------------------------------------------------------

const PREFS_KEY = 'as_brand_kit_settings'

export const DEFAULT_BRAND_SETTINGS = {
  enabled: false,
  template: DEFAULT_TEMPLATE,
  logoPosition: 'bottom-right',
  includeContact: true,
}

let cache = null
let inflight = null

function readPrefs() {
  try {
    const raw = localStorage.getItem(PREFS_KEY)
    return raw ? { ...DEFAULT_BRAND_SETTINGS, ...JSON.parse(raw) } : DEFAULT_BRAND_SETTINGS
  } catch {
    return DEFAULT_BRAND_SETTINGS
  }
}

function writePrefs(value) {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(value))
  } catch {
    /* storage unavailable — settings just won't persist */
  }
}

export function invalidateBrandKit() {
  cache = null
  inflight = null
}

export default function useBrandKit() {
  const [brandKit, setBrandKit] = useState(cache)
  const [loading, setLoading] = useState(!cache)
  const [settings, setSettingsState] = useState(readPrefs)

  useEffect(() => {
    if (cache) return
    let cancelled = false
    inflight = inflight || api.getBusinessProfile()
    inflight
      .then((p) => {
        cache = p
        if (!cancelled) setBrandKit(p)
      })
      .catch(() => {
        if (!cancelled) setBrandKit(null)
      })
      .finally(() => {
        inflight = null
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const setSettings = useCallback((patch) => {
    setSettingsState((s) => {
      const next = typeof patch === 'function' ? patch(s) : { ...s, ...patch }
      writePrefs(next)
      return next
    })
  }, [])

  const refresh = useCallback(async () => {
    invalidateBrandKit()
    setLoading(true)
    try {
      const p = await api.getBusinessProfile()
      cache = p
      setBrandKit(p)
      return p
    } finally {
      setLoading(false)
    }
  }, [])

  return {
    brandKit,
    loading,
    settings,
    setSettings,
    refresh,
    // True when there is actually something to overlay — the UI uses this to
    // explain why the toggle is off rather than showing a control that
    // silently does nothing.
    available: hasBrandAssets(brandKit),
  }
}
