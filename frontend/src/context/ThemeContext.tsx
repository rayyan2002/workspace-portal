import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { ThemeContext, THEME_STORAGE_KEY } from './theme-context'
import type { ThemePreference } from './theme-context'

function readStoredPreference(): ThemePreference {
  const stored = localStorage.getItem(THEME_STORAGE_KEY)
  return stored === 'light' || stored === 'dark' ? stored : 'system'
}

function systemPrefersDark(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

/**
 * Applies the choice as a `data-theme` attribute on <html>.
 *
 * 'system' REMOVES the attribute rather than writing a resolved value: the
 * stylesheet's `prefers-color-scheme` block is guarded by
 * `:not([data-theme="light"])`, so with no attribute the OS drives the palette and
 * keeps driving it if the user changes their OS setting while the tab is open.
 */
function applyTheme(preference: ThemePreference) {
  const root = document.documentElement
  if (preference === 'system') {
    root.removeAttribute('data-theme')
  } else {
    root.setAttribute('data-theme', preference)
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(readStoredPreference)
  const [systemIsDark, setSystemIsDark] = useState(systemPrefersDark)

  // Also applied before paint by a small script in index.html — this effect alone
  // would let the light palette show for a frame before React mounts.
  useEffect(() => {
    applyTheme(preference)
  }, [preference])

  // Follow the OS live while the preference is 'system'.
  useEffect(() => {
    const query = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = (event: MediaQueryListEvent) => setSystemIsDark(event.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])

  const setPreference = (next: ThemePreference) => {
    setPreferenceState(next)
    localStorage.setItem(THEME_STORAGE_KEY, next)
  }

  const resolved: 'light' | 'dark' =
    preference === 'system' ? (systemIsDark ? 'dark' : 'light') : preference

  return (
    <ThemeContext.Provider value={{ preference, resolved, setPreference }}>
      {children}
    </ThemeContext.Provider>
  )
}
