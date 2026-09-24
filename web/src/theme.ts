import { useEffect, useState } from 'react'

export type ThemeChoice = 'light' | 'dark' | 'system'
const KEY = 'seo-advisor-theme'

function read(): ThemeChoice {
  try {
    const v = localStorage.getItem(KEY)
    return v === 'dark' || v === 'system' || v === 'light' ? v : 'light'
  } catch {
    return 'light'
  }
}

/** Light by default; "system" follows the OS. Stored per browser (a convenience only). */
export function useTheme(): [ThemeChoice, (t: ThemeChoice) => void] {
  const [theme, setTheme] = useState<ThemeChoice>(read)
  useEffect(() => {
    const root = document.documentElement
    if (theme === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', theme)
    try { localStorage.setItem(KEY, theme) } catch { /* private mode: keep in memory */ }
  }, [theme])
  return [theme, setTheme]
}
