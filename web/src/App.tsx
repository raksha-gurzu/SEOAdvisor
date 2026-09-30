import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
import { GapView } from './components/GapView'
import { NewGap } from './components/NewGap'
import { NewRun } from './components/NewRun'
import { NewSnapshot } from './components/NewSnapshot'
import { RecentRuns, type RecentItem } from './components/RecentRuns'
import { RunView } from './components/RunView'
import { SnapshotView } from './components/SnapshotView'
import { Pill } from './components/ui'
import { usd, verdict } from './format'
import { toolOf, useRoute, type Tool } from './router'
import { useTheme, type ThemeChoice } from './theme'
import type { GapSummary, Health, RunSummary, SnapshotSummary } from './types'

const PROVIDERS: { key: string; label: string; required: boolean }[] = [
  { key: 'deepseek', label: 'DeepSeek (AI)', required: true },
  { key: 'gemini', label: 'Gemini (search + AI)', required: true },
  { key: 'serper', label: 'Serper (Google results)', required: false },
  { key: 'bing', label: 'Bing (search volume)', required: false },
  { key: 'openpagerank', label: 'Open PageRank (link score)', required: false },
  { key: 'crux', label: 'Chrome UX Report (speed)', required: false },
]

const THEMES: { value: ThemeChoice; label: string }[] = [
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
  { value: 'system', label: 'Auto' },
]

const TOOLS: { tool: Tool; label: string; href: string }[] = [
  { tool: 'briefs', label: 'Briefs', href: '#/' },
  { tool: 'gap', label: 'Keyword gap', href: '#/gap' },
  { tool: 'snapshot', label: 'Site snapshot', href: '#/snapshot' },
]

function Logo() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="4" width="18" height="16" rx="3" />
      <path d="M7 15l3-4 3 3 4-6" />
    </svg>
  )
}

function credits(n: number, cost: number): string {
  return `${n} credit${n === 1 ? '' : 's'} · ${usd(cost)}`
}

export default function App() {
  const route = useRoute()
  const [theme, setTheme] = useTheme()
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [gaps, setGaps] = useState<GapSummary[]>([])
  const [snaps, setSnaps] = useState<SnapshotSummary[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  const [offline, setOffline] = useState(false)
  const tool = toolOf(route)
  const onStart = route.page === 'new' || route.page === 'gap-new' || route.page === 'snap-new'
  const setupRef = useRef<HTMLDetailsElement>(null)

  // The key-status menu is a <details>: close it on a click outside, on Escape (focus goes back
  // to its button) and when the page changes, so it never stays open over the content.
  useEffect(() => {
    const close = () => { if (setupRef.current) setupRef.current.open = false }
    const onDown = (e: MouseEvent) => { if (!setupRef.current?.contains(e.target as Node)) close() }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && setupRef.current?.open) {
        close()
        setupRef.current.querySelector('summary')?.focus()
      }
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [])
  useEffect(() => { if (setupRef.current) setupRef.current.open = false }, [route])

  const refresh = useCallback(() => {
    api.listRuns().then((r) => { setRuns(r); setOffline(false) }).catch(() => setOffline(true))
    api.listGaps().then(setGaps).catch(() => setOffline(true))
    api.listSnapshots().then(setSnaps).catch(() => setOffline(true))
    api.health().then(setHealth).catch(() => setOffline(true))
  }, [])

  useEffect(() => { refresh() }, [refresh])
  // While anything is still running, keep the history tables up to date.
  const busy = [...runs, ...gaps, ...snaps].some((r) => r.status === 'queued' || r.status === 'running')
  useEffect(() => {
    if (!busy) return
    const timer = window.setInterval(refresh, 4000)
    return () => window.clearInterval(timer)
  }, [busy, refresh])
  const missing = health?.missing_for_free_mode.length ?? 0

  const briefItems: RecentItem[] = runs.map((r) => {
    const v = r.score !== null ? verdict(r.score) : null
    return {
      id: r.id, href: `#/runs/${r.id}`, title: r.title, createdAt: r.created_at, status: r.status,
      result: v ? <Pill tone={v.tone}><span className="nums">{r.score}</span> {v.label}</Pill> : '—',
      cost: usd(r.cost_usd),
    }
  })
  const gapItems: RecentItem[] = gaps.map((g) => ({
    id: g.id, href: `#/gaps/${g.id}`, title: g.title, createdAt: g.created_at, status: g.status,
    result: g.to_add !== null ? <span className="nums">{g.to_add} to add</span> : '—',
    cost: credits(g.credits_used, g.cost_usd),
  }))
  const snapItems: RecentItem[] = snaps.map((s) => ({
    id: s.id, href: `#/snapshots/${s.id}`, title: s.title, createdAt: s.created_at, status: s.status,
    result: s.found !== null && s.checked ? <span className="nums">{s.found} of {s.checked}</span> : '—',
    cost: credits(s.credits_used, s.cost_usd),
  }))

  return (
    <div className="shell">
      <header className="topbar">
        <a className="brand" href="#/">
          <span className="brand-mark"><Logo /></span>
          SEO Advisor
        </a>

        <nav className="tool-tabs" aria-label="Tools">
          {TOOLS.map((t) => (
            <a key={t.tool} href={t.href} aria-current={tool === t.tool ? (onStart ? 'page' : 'true') : undefined}>{t.label}</a>
          ))}
        </nav>

        <div className="topbar-end">
          {health && (
            <details className="setup" ref={setupRef}>
              <summary>
                <span className={`dot ${missing ? 'bad' : 'good'}`} aria-hidden="true" />
                <span className="setup-label">{missing ? `${missing} key${missing > 1 ? 's' : ''} missing` : 'Ready to go'}</span>
              </summary>
              <div className="setup-panel">
                <p className="setup-title">Data sources</p>
                <ul>
                  {PROVIDERS.map((p) => (
                    <li key={p.key}>
                      <span className={`dot ${health.keys[p.key] ? 'good' : p.required ? 'bad' : ''}`} aria-hidden="true" />
                      {p.label}
                      <span className="state">{health.keys[p.key] ? 'Connected' : p.required ? 'Required' : 'Optional'}</span>
                    </li>
                  ))}
                </ul>
              </div>
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
      </header>

      <main className="main">
        {route.page === 'new' && (
          <>
            <NewRun health={health} onStarted={refresh} />
            <div className="page">
              <RecentRuns title="Recent briefs" items={briefItems} offline={offline} empty="Your briefs will show up here." resultLabel="Score" />
            </div>
          </>
        )}
        {route.page === 'run' && <RunView key={route.id} id={route.id} onChanged={refresh} />}
        {route.page === 'gap-new' && (
          <>
            <NewGap
              key={`${route.site ?? ''}|${route.competitors?.join(',') ?? ''}`}
              health={health}
              onStarted={refresh}
              prefill={{ site: route.site, competitors: route.competitors }}
            />
            <div className="page">
              <RecentRuns title="Recent analyses" items={gapItems} offline={offline} empty="Your keyword gap analyses will show up here." resultLabel="Keywords to add" />
            </div>
          </>
        )}
        {route.page === 'gap' && <GapView key={route.id} id={route.id} onChanged={refresh} />}
        {route.page === 'snap-new' && (
          <>
            <NewSnapshot health={health} onStarted={refresh} />
            <div className="page">
              <RecentRuns title="Recent snapshots" items={snapItems} offline={offline} empty="Your site snapshots will show up here." resultLabel="Found on Google" />
            </div>
          </>
        )}
        {route.page === 'snap' && <SnapshotView key={route.id} id={route.id} onChanged={refresh} />}
      </main>
    </div>
  )
}
