/** Per-device settings. Never leaves the browser. */

export interface Prefs {
  /** Pool filter on the patterns view. */
  pool: string
  /** content_hash of the schedule this device has already seen. */
  seenHash: string | null
  theme: 'system' | 'light' | 'dark'
}

const KEY = 'swimwatch.prefs.v1'

const DEFAULTS: Prefs = { pool: '', seenHash: null, theme: 'system' }

export function loadPrefs(): Prefs {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return { ...DEFAULTS }
    return { ...DEFAULTS, ...(JSON.parse(raw) as Partial<Prefs>) }
  } catch {
    // Private windows and blocked site data both throw here. Defaults are
    // correct in that case; the app must not fail to render over a preference.
    return { ...DEFAULTS }
  }
}

export function savePrefs(next: Partial<Prefs>): Prefs {
  const merged = { ...loadPrefs(), ...next }
  try {
    localStorage.setItem(KEY, JSON.stringify(merged))
  } catch {
    /* nothing to do — the app works fine without persistence */
  }
  return merged
}

export function applyTheme(theme: Prefs['theme']): void {
  const root = document.documentElement
  if (theme === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', theme)
}
