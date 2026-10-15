import { createContext, useContext } from 'react'

export type ThemePreference = 'light' | 'dark' | 'system'

export interface ThemeContextValue {
  /** What the user chose. 'system' defers to the OS. */
  preference: ThemePreference
  /** What is actually on screen right now — 'system' resolved to a real theme. */
  resolved: 'light' | 'dark'
  setPreference: (preference: ThemePreference) => void
}

/**
 * Context and hook live apart from the provider component.
 *
 * Fast Refresh only re-renders reliably when a module exports components alone, so
 * a hook sitting beside its provider quietly degrades HMR for the whole file. Keeping
 * the non-component exports here is the fix, not a lint workaround.
 */
export const ThemeContext = createContext<ThemeContextValue | null>(null)

export const THEME_STORAGE_KEY = 'themePreference'

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}
