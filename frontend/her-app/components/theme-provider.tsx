'use client'

import * as React from 'react'

type Theme = 'light' | 'dark' | 'system'
type ResolvedTheme = 'light' | 'dark'

export type ThemeProviderProps = {
  children: React.ReactNode
  defaultTheme?: Theme
  enableSystem?: boolean
  attribute?: 'class' | string
  disableTransitionOnChange?: boolean
}

type ThemeContextValue = {
  theme: Theme
  resolvedTheme: ResolvedTheme
  setTheme: (theme: Theme) => void
}

const ThemeContext = React.createContext<ThemeContextValue | null>(null)
const STORAGE_KEY = 'theme'
const DEFAULT_CONTEXT: ThemeContextValue = {
  theme: 'system',
  resolvedTheme: 'light',
  setTheme: () => {},
}

function getSystemTheme(): ResolvedTheme {
  if (typeof window === 'undefined') return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(attribute: string, theme: ResolvedTheme) {
  const root = document.documentElement
  if (attribute === 'class') {
    root.classList.remove('light', 'dark')
    root.classList.add(theme)
    return
  }
  root.setAttribute(attribute, theme)
}

export function ThemeProvider({
  children,
  defaultTheme = 'system',
  enableSystem = true,
  attribute = 'class',
}: ThemeProviderProps) {
  const [theme, setThemeState] = React.useState<Theme>(defaultTheme)
  const [resolvedTheme, setResolvedTheme] = React.useState<ResolvedTheme>('light')

  React.useEffect(() => {
    const storedTheme = (() => {
      try {
        return (window.localStorage.getItem(STORAGE_KEY) as Theme | null) ?? null
      } catch {
        return null
      }
    })()

    const nextTheme = storedTheme ?? defaultTheme
    const nextResolvedTheme =
      nextTheme === 'system' && enableSystem ? getSystemTheme() : (nextTheme as ResolvedTheme)

    setThemeState(nextTheme)
    setResolvedTheme(nextResolvedTheme)
    applyTheme(attribute, nextResolvedTheme)
  }, [attribute, defaultTheme, enableSystem])

  React.useEffect(() => {
    if (!enableSystem || theme !== 'system') return

    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const handleChange = () => {
      const nextResolvedTheme = getSystemTheme()
      setResolvedTheme(nextResolvedTheme)
      applyTheme(attribute, nextResolvedTheme)
    }

    media.addEventListener('change', handleChange)
    return () => media.removeEventListener('change', handleChange)
  }, [attribute, enableSystem, theme])

  const setTheme = React.useCallback((nextTheme: Theme) => {
    const nextResolvedTheme =
      nextTheme === 'system' && enableSystem ? getSystemTheme() : (nextTheme as ResolvedTheme)

    setThemeState(nextTheme)
    setResolvedTheme(nextResolvedTheme)
    applyTheme(attribute, nextResolvedTheme)

    try {
      window.localStorage.setItem(STORAGE_KEY, nextTheme)
    } catch {
      // Ignore storage failures.
    }
  }, [attribute, enableSystem])

  const value = React.useMemo(
    () => ({
      theme,
      resolvedTheme,
      setTheme,
    }),
    [theme, resolvedTheme, setTheme],
  )

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  )
}

export function useTheme() {
  const context = React.useContext(ThemeContext)
  return context ?? DEFAULT_CONTEXT
}
