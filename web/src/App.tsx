import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { GapView } from './components/GapView'
import { NewGap } from './components/NewGap'
import { NewRun } from './components/NewRun'
import { RunView } from './components/RunView'
import { NewSnapshot } from './components/NewSnapshot'
import { SnapshotView } from './components/SnapshotView'
import { Pill } from './components/ui'
import { relativeTime, verdict } from './format'
import { go, toolOf, useRoute } from './router'
import { useTheme, type ThemeChoice } from './theme'
import type { GapSummary, Health, RunStatus, RunSummary, SnapshotSummary } from './types'

const PROVIDERS: { key: string; label: string; required: boolean }[] = [
  { key: 'deepseek', label: 'DeepSeek (AI)', required: true },
  { key: 'gemini', label: 'Gemini (search + AI)', required: true },
  { key: 'serper', label: 'Serper (Google results)', required: false },
  { key: 'bing', label: 'Bing (search volume)', required: false },
  { key: 'openpagerank', label: 'Open PageRank (link score)', required: false },
  { key: 'crux', label: 'Chrome UX Report (speed)', required: false },
]
function historyTime(status: RunStatus, createdAt: string): string {
  if (status === 'running' || status === 'queued') return 'Analysing…'
  return status === 'failed' ? 'Didn’t finish' : relativeTime(createdAt)
}

const THEMES: { value: ThemeChoice; label: string }[] = [
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
  { value: 'system', label: 'Auto' },
]

export default function App() {
  const route = useRoute()
  const [theme, setTheme] = useTheme()
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [gaps, setGaps] = useState<GapSummary[]>([])
  const [snaps, setSnaps] = useState<SnapshotSummary[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  const [offline, setOffline] = useState(false)
  const tool = toolOf(route)

  const refresh = useCallback(() => {
    api.listRuns().then((r) => { setRuns(r); setOffline(false) }).catch(() => setOffline(true))
    api.listGaps().then(setGaps).catch(() => setOffline(true))
    api.listSnapshots().then(setSnaps).catch(() => setOffline(true))
    api.health().then(setHealth).catch(() => setOffline(true))
  }, [])

  useEffect(() => { refresh() }, [refresh])
  // While anything is still running, keep the sidebar history up to date.
  const busy = [...runs, ...gaps, ...snaps].some((r) => r.status === 'queued' || r.status === 'running')
  useEffect(() => {
    if (!busy) return
    const timer = window.setInterval(refresh, 4000)
    return () => window.clearInterval(timer)
  }, [busy, refresh])
  const missing = health?.missing_for_free_mode.length ?? 0

  return (
    <div className="shell">
      <aside className="sidebar">
        <a className="brand" href="#/">
          <img src="/favicon.svg" alt="" width={28} height={28} />
          SEO Advisor
        </a>

        <div className="tool-switch" role="group" aria-label="Tool">
          <button type="button" aria-pressed={tool === 'briefs'} onClick={() => tool !== 'briefs' && go({ page: 'new' })}>Briefs</button>
          <button type="button" aria-pressed={tool === 'gap'} onClick={() => tool !== 'gap' && go({ page: 'gap-new' })}>Keyword gap</button>
          <button type="button" aria-pressed={tool === 'snapshot'} onClick={() => tool !== 'snapshot' && go({ page: 'snap-new' })}>Snapshot</button>
        </div>

        {tool === 'briefs' ? (
          <>
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
                      <span className="history-time">{historyTime(r.status, r.created_at)}</span>
                      {v && r.status === 'done' && <Pill tone={v.tone}>{r.score}</Pill>}
                    </a>
                  )
                })}
              </div>
            </nav>
          </>
        ) : tool === 'snapshot' ? (
          <>
            <button type="button" className="btn primary block" onClick={() => go({ page: 'snap-new' })}>
              + New snapshot
            </button>

            <nav aria-label="Recent snapshots">
              <p className="side-label">Recent snapshots</p>
              <div className="history">
                {offline && <p className="side-note text-bad">The server isn’t running.</p>}
                {!offline && snaps.length === 0 && <p className="side-note">Your snapshots will show up here.</p>}
                {snaps.map((s) => (
                  <a key={s.id} href={`#/snapshots/${s.id}`} className={route.page === 'snap' && route.id === s.id ? 'active' : ''}>
                    <span className="history-title">{s.title}</span>
                    <span className="history-time">{historyTime(s.status, s.created_at)}</span>
                    {s.status === 'done' && s.found !== null && !!s.checked && (
                      <Pill tone="brand"><span className="nums">{s.found}/{s.checked}</span> found</Pill>
                    )}
                  </a>
                ))}
              </div>
            </nav>
          </>
        ) : (
          <>
            <button type="button" className="btn primary block" onClick={() => go({ page: 'gap-new' })}>
              + New gap analysis
            </button>

            <nav aria-label="Recent gap analyses">
              <p className="side-label">Recent analyses</p>
              <div className="history">
                {offline && <p className="side-note text-bad">The server isn’t running.</p>}
                {!offline && gaps.length === 0 && <p className="side-note">Your analyses will show up here.</p>}
                {gaps.map((g) => (
                  <a key={g.id} href={`#/gaps/${g.id}`} className={route.page === 'gap' && route.id === g.id ? 'active' : ''}>
                    <span className="history-title">{g.title}</span>
                    <span className="history-time">{historyTime(g.status, g.created_at)}</span>
                    {g.status === 'done' && g.to_add !== null && (
                      <Pill tone="brand"><span className="nums">{g.to_add}</span> to add</Pill>
                    )}
                  </a>
                ))}
              </div>
            </nav>
          </>
        )}

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
        {route.page === 'new' && <NewRun health={health} onStarted={refresh} />}
        {route.page === 'run' && <RunView key={route.id} id={route.id} onChanged={refresh} />}
        {route.page === 'gap-new' && (
          <NewGap
            key={`${route.site ?? ''}|${route.competitors?.join(',') ?? ''}`}
            health={health}
            onStarted={refresh}
            prefill={{ site: route.site, competitors: route.competitors }}
          />
        )}
        {route.page === 'gap' && <GapView key={route.id} id={route.id} onChanged={refresh} />}
        {route.page === 'snap-new' && <NewSnapshot health={health} onStarted={refresh} />}
        {route.page === 'snap' && <SnapshotView key={route.id} id={route.id} onChanged={refresh} />}
      </main>
    </div>
  )
}
