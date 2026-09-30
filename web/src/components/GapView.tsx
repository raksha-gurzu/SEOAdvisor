import { useEffect, useState } from 'react'
import { api } from '../api'
import { COUNTRY_NAMES, duration, usd } from '../format'
import { go } from '../router'
import type { GapRecord } from '../types'
import { GapResults } from './GapResults'
import { RunProgress } from './RunProgress'
import { Alert, DomainDot } from './ui'

const STEP_TEXT: Record<string, string> = {
  sites: 'Reading the websites',
  keywords: 'Finding the keywords each site targets',
  google: 'Checking where each site shows up on Google',
  metrics: 'Measuring the keywords',
  compare: 'Comparing the sites',
}
const POLL_MS = 1500

export function GapView({ id, onChanged }: { id: string; onChanged: () => void }) {
  const [rec, setRec] = useState<GapRecord | null>(null)
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
        const next = await api.getGap(id)
        if (cancelled) return
        failures = 0
        setReconnecting(false)
        setRec(next)
        if (next.status === 'queued' || next.status === 'running') timer = window.setTimeout(load, POLL_MS)
        else onChanged()
      } catch (e) {
        if (cancelled) return
        if ((e as Error).message === 'analysis not found') {
          setError('This analysis was deleted.')
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
  if (!rec) return <div className="page"><p className="muted">Opening analysis…</p></div>

  const { run } = rec
  const ours = run.domains[0] ?? run.site
  const active = rec.status === 'queued' || rec.status === 'running'
  const started = rec.steps.find((s) => s.started_at)?.started_at ?? rec.created_at
  const ended = [...rec.steps].reverse().find((s) => s.finished_at)?.finished_at ?? null
  const n = run.competitors.length

  async function remove() {
    setActionError(null)
    try {
      await api.deleteGap(id)
      onChanged()
      go({ page: 'gap-new' })
    } catch (e) {
      setActionError((e as Error).message)
    }
  }

  async function retry() {
    setRetrying(true)
    try {
      const settings = { country: run.settings.base.country, depth: run.settings.depth, keywords: run.settings.keywords }
      const { id: next } = await api.startGap(run.site, run.competitors, settings)
      onChanged()
      go({ page: 'gap', id: next })
    } catch (e) {
      setActionError((e as Error).message)
    } finally {
      setRetrying(false)
    }
  }

  return (
    <div className="page wide">
      <div className="compare-bar" role="group" aria-label="Sites compared">
        <span className="field-label">Comparing</span>
        <ul className="compare-sites">
          {(run.domains.length ? run.domains : [run.site, ...run.competitors]).map((d, i) => (
            <li key={d}><DomainDot index={i} /><span>{d}</span>{i === 0 && <span className="chip brand">You</span>}</li>
          ))}
        </ul>
        <button type="button" className="btn ghost" onClick={() => go({ page: 'gap-new', site: run.site, competitors: run.competitors })}>
          Edit comparison
        </button>
      </div>

      <header className="report-head">
        <div>
          <p className="eyebrow">Keyword gap</p>
          <h1>{active ? `Comparing ${ours}…` : ours}</h1>
          <p className="report-meta">
            <span>vs {n} competitor{n === 1 ? '' : 's'}</span>
            <span>{new Date(rec.created_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}</span>
            <span>{COUNTRY_NAMES[run.settings.base.country] ?? run.settings.base.country}</span>
            {run.result && <span className="nums">{run.result.rows.length} keywords checked</span>}
            {!active && <span>took {duration(started, ended)}</span>}
            {!active && <span className="nums">{run.credits_used} Serper credits</span>}
            <span>{usd(run.cost_usd)} AI</span>
          </p>
        </div>
        {!active && (
          <div className="run-actions">
            {confirming ? (
              <span className="confirm">
                Delete this analysis?
                <button type="button" className="btn danger" onClick={remove}>Delete</button>
                <button type="button" className="btn ghost" onClick={() => setConfirming(false)}>Cancel</button>
              </span>
            ) : (
              <>
                {rec.status === 'done' && (
                  <button type="button" className="btn" onClick={retry} disabled={retrying}>{retrying ? 'Starting…' : 'Take again'}</button>
                )}
                {rec.status === 'done' && <a className="btn" href={`/api/gaps/${id}/keywords.csv`} download>Export CSV</a>}
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
          onRetry={retry}
          failedTitle="The analysis stopped"
          leaveNote="Usually takes 1 to 3 minutes. You can leave this page; the analysis will appear in Recent analyses when it’s ready."
        />
      )}

      {rec.status === 'done' && run.result && <GapResults run={run} result={run.result} />}
    </div>
  )
}
