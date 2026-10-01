import { useEffect, useState, type FormEvent } from 'react'
import { api } from '../api'
import { COUNTRY_NAMES, duration, siteHost, usd } from '../format'
import { go } from '../router'
import type { SnapshotRecord } from '../types'
import { RunProgress } from './RunProgress'
import { SnapshotResults } from './SnapshotResults'
import { Alert } from './ui'

const STEP_TEXT: Record<string, string> = {
  site: 'Reading the website',
  keywords: 'Finding the searches its pages target',
  google: 'Checking where it shows on Google',
  facts: 'Collecting site facts',
  summary: 'Building the snapshot',
}
const POLL_MS = 1500

/** The site bar at the top of a report (docs/UI-REDESIGN-PLAN.md U1): take a new snapshot. */
function SiteBar({ domain, country: initialCountry, keywords, onStarted }: { domain: string; country: string; keywords: number; onStarted: () => void }) {
  const [site, setSite] = useState(domain)
  const [country, setCountry] = useState(initialCountry)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const ok = !!siteHost(site)

  async function start(e: FormEvent) {
    e.preventDefault()
    if (!ok) return
    setBusy(true)
    setError(null)
    try {
      const { id } = await api.startSnapshot(site.trim(), { country, keywords })
      onStarted()
      go({ page: 'snap', id })
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="site-bar" onSubmit={start} aria-label="Take a snapshot">
      <label className="site-bar-field">
        <span className="field-label">Website</span>
        <span className="site-bar-input">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
          <input value={site} onChange={(e) => setSite(e.target.value)} inputMode="url" autoComplete="url" />
        </span>
      </label>
      <label className="site-bar-field narrow">
        <span className="field-label">Country</span>
        <select className="select site-bar-select" value={country} onChange={(e) => setCountry(e.target.value)}>
          {Object.entries(COUNTRY_NAMES).map(([code, name]) => <option key={code} value={code}>{name}</option>)}
        </select>
      </label>
      <button type="submit" className="btn primary" disabled={!ok || busy}>{busy ? 'Starting…' : 'Take snapshot'}</button>
      {error && <span className="text-bad small site-bar-error">{error}</span>}
    </form>
  )
}

export function SnapshotView({ id, onChanged }: { id: string; onChanged: () => void }) {
  const [rec, setRec] = useState<SnapshotRecord | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [reconnecting, setReconnecting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    let timer: number | undefined
    let failures = 0
    const load = async () => {
      try {
        const next = await api.getSnapshot(id)
        if (cancelled) return
        failures = 0
        setReconnecting(false)
        setRec(next)
        if (next.status === 'queued' || next.status === 'running') timer = window.setTimeout(load, POLL_MS)
        else onChanged()
      } catch (e) {
        if (cancelled) return
        if ((e as Error).message === 'snapshot not found') {
          setError('This snapshot was deleted.')
          return
        }
        // A network blip or a restarting server: keep what is on screen and try again.
        failures += 1
        setReconnecting(true)
        timer = window.setTimeout(load, Math.min(POLL_MS * 2 ** failures, 15_000))
      }
    }
    load()
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [id, onChanged])

  if (error) return <div className="page"><Alert tone="bad">{error}</Alert></div>
  if (!rec) return <div className="page"><p className="muted">Opening snapshot…</p></div>

  const { run } = rec
  const domain = run.domain || run.site
  const active = rec.status === 'queued' || rec.status === 'running'
  const started = rec.steps.find((s) => s.started_at)?.started_at ?? rec.created_at
  const ended = [...rec.steps].reverse().find((s) => s.finished_at)?.finished_at ?? null
  const country = run.settings.gap.base.country

  async function remove() {
    setActionError(null)
    try {
      await api.deleteSnapshot(id)
      onChanged()
      go({ page: 'snap-new' })
    } catch (e) {
      setActionError((e as Error).message)
    }
  }

  async function again() {
    setRetrying(true)
    setActionError(null)
    try {
      const { id: next } = await api.startSnapshot(run.site, { country, keywords: run.settings.gap.keywords })
      onChanged()
      go({ page: 'snap', id: next })
    } catch (e) {
      setActionError((e as Error).message)
    } finally {
      setRetrying(false)
    }
  }

  return (
    <div className="page wide">
      <SiteBar domain={domain} country={country} keywords={run.settings.gap.keywords} onStarted={onChanged} />

      <header className="report-head">
        <div>
          <p className="eyebrow">Site snapshot</p>
          <h1>{active ? `Reading ${domain}…` : domain}</h1>
          <p className="report-meta">
            <span>{new Date(rec.created_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}</span>
            <span>{COUNTRY_NAMES[country] ?? country}</span>
            {run.result && <span className="nums">{run.result.keywords_checked} searches checked</span>}
            {!active && <span>took {duration(started, ended)}</span>}
            {!active && <span className="nums">{run.credits_used} Serper credits</span>}
            <span>{usd(run.cost_usd)} AI</span>
          </p>
        </div>
        {!active && (
          <div className="run-actions">
            {confirming ? (
              <span className="confirm">
                Delete this snapshot?
                <button type="button" className="btn danger" onClick={remove}>Delete</button>
                <button type="button" className="btn ghost" onClick={() => setConfirming(false)}>Cancel</button>
              </span>
            ) : (
              <>
                {rec.status === 'done' && (
                  <button type="button" className="btn" onClick={again} disabled={retrying}>{retrying ? 'Starting…' : 'Take again'}</button>
                )}
                {rec.status === 'done' && (run.result?.keywords.length ?? 0) > 0 && (
                  <a className="btn" href={`/api/snapshots/${id}/keywords.csv`} download>Export CSV</a>
                )}
                <button type="button" className="btn ghost danger" onClick={() => setConfirming(true)}>Delete</button>
              </>
            )}
          </div>
        )}
      </header>

      {reconnecting && <p className="muted small" role="status">Can’t reach the server right now. Reconnecting…</p>}
      {actionError && <Alert tone="bad">{actionError}</Alert>}

      {(active || rec.status === 'failed') && (
        <RunProgress
          status={rec.status}
          steps={rec.steps}
          error={rec.error}
          stepText={STEP_TEXT}
          retrying={retrying}
          onRetry={again}
          failedTitle="The snapshot stopped"
          leaveNote="Usually takes about a minute. You can leave this page; the snapshot will appear in Recent snapshots when it’s ready."
        />
      )}

      {rec.status === 'done' && run.result && <SnapshotResults run={run} result={run.result} />}
    </div>
  )
}
