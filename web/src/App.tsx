import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { NewRun } from './components/NewRun'
import { RunView } from './components/RunView'
import { Pill } from './components/ui'
import { relativeTime, verdict } from './format'
import { go, useRoute } from './router'
import { useTheme, type ThemeChoice } from './theme'
import type { Health, RunSummary } from './types'

const PROVIDERS: { key: string; label: string; required: boolean }[] = [
  { key: 'deepseek', label: 'DeepSeek (AI)', required: true },
  { key: 'gemini', label: 'Gemini (search + AI)', required: true },
  { key: 'serper', label: 'Serper (Google results)', required: false },
  { key: 'bing', label: 'Bing (search volume)', required: false },
]
const THEMES: { value: ThemeChoice; label: string }[] = [
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
  { value: 'system', label: 'Auto' },
]

export default function App() {
  const route = useRoute()
  const [theme, setTheme] = useTheme()
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  const [offline, setOffline] = useState(false)

  const refresh = useCallback(() => {
    api.listRuns().then((r) => { setRuns(r); setOffline(false) }).catch(() => setOffline(true))
    api.health().then(setHealth).catch(() => setOffline(true))
  }, [])

  useEffect(() => { refresh() }, [refresh])
  const missing = health?.missing_for_free_mode.length ?? 0

  return (
    <div className="shell">
      <aside className="sidebar">
        <a className="brand" href="#/">
          <img src="/favicon.svg" alt="" width={28} height={28} />
          SEO Advisor
        </a>

        <button type="button" className="btn primary block" onClick={() => go({ page: 'new' })}>
          + New brief
        </button>

        <nav aria-label="Recent briefs">
          <p className="side-label">Recent briefs</p>
          <div className="history">
            {offline && <p className="side-note text-bad">The server isn’t running.</p>}
            {!offline && runs.length === 0 && <p className="side-note">Your briefs will show up here.</p>}
            {runs.map((r) => {
              const v = r.score !== null ? verdict(r.score) : null
              return (
                <a key={r.id} href={`#/runs/${r.id}`} className={route.page === 'run' && route.id === r.id ? 'active' : ''}>
                  <span className="history-title">{r.title}</span>
                  <span className="history-time">{r.status === 'running' || r.status === 'queued' ? 'Analysing…' : r.status === 'failed' ? 'Didn’t finish' : relativeTime(r.created_at)}</span>
                  {v && r.status === 'done' && <Pill tone={v.tone}>{r.score}</Pill>}
                </a>
              )
            })}
          </div>
        </nav>

        <div className="side-foot">
          {health && (
            <details className="setup">
              <summary>
                <span className={`dot ${missing ? 'bad' : 'good'}`} aria-hidden="true" />
                {missing ? `Setup: ${missing} key${missing > 1 ? 's' : ''} missing` : 'Ready to go'}
              </summary>
              <ul>
                {PROVIDERS.map((p) => (
                  <li key={p.key}>
                    <span className={`dot ${health.keys[p.key] ? 'good' : p.required ? 'bad' : ''}`} aria-hidden="true" />
                    {p.label}
                    <span className="state">{health.keys[p.key] ? 'Connected' : p.required ? 'Required' : 'Optional'}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
          <div className="theme-switch" role="group" aria-label="Colour theme">
            {THEMES.map((t) => (
              <button key={t.value} type="button" aria-pressed={theme === t.value} onClick={() => setTheme(t.value)}>
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </aside>

      <main className="main">
        {route.page === 'new'
          ? <NewRun health={health} onStarted={refresh} />
          : <RunView key={route.id} id={route.id} onChanged={refresh} />}
      </main>
    </div>
  )
}
