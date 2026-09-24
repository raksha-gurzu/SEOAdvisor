import { useEffect, useState } from 'react'
import { api } from '../api'
import { briefToMarkdown, COUNTRY_NAMES, duration, hostOf, relativeTime, usd } from '../format'
import { go } from '../router'
import type { RunRecord } from '../types'
import { ActionPlan } from './Brief'
import { DetailsView } from './Details'
import { Alert, CopyButton } from './ui'

type Tab = 'plan' | 'details' | 'text'
const TABS: { id: Tab; label: string }[] = [
  { id: 'plan', label: 'Action plan' },
  { id: 'details', label: 'Details' },
  { id: 'text', label: 'Page text' },
]
const STEP_TEXT: Record<string, string> = {
  keywords: 'Finding searches your page can win',
  serp: 'Checking what Google shows for them',
  competitors: 'Reading the pages that rank today',
  coverage: 'Comparing their topics with yours',
  brief: 'Writing your action plan',
  draft: 'Writing suggested content for your page',
}
const POLL_MS = 1500

export function RunView({ id, onChanged }: { id: string; onChanged: () => void }) {
  const [rec, setRec] = useState<RunRecord | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('plan')
  const [confirming, setConfirming] = useState(false)
  const [retrying, setRetrying] = useState(false)

  useEffect(() => {
    let cancelled = false
    let timer: number | undefined
    const load = async () => {
      try {
        const next = await api.getRun(id)
        if (cancelled) return
        setRec(next)
        if (next.status === 'queued' || next.status === 'running') timer = window.setTimeout(load, POLL_MS)
        else onChanged()
      } catch (e) {
        if (!cancelled) setError((e as Error).message === 'run not found' ? 'This brief was deleted.' : (e as Error).message)
      }
    }
    load()
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [id, onChanged])

  if (error) return <div className="page"><Alert tone="bad">{error}</Alert></div>
  if (!rec) return <div className="page"><p className="muted">Opening brief…</p></div>

  const { run } = rec
  const site = hostOf(run.source_url)
  const active = rec.status === 'queued' || rec.status === 'running'
  const done = rec.steps.filter((s) => s.status === 'done').length
  const current = rec.steps.find((s) => s.status === 'running')
  const started = rec.steps.find((s) => s.started_at)?.started_at ?? rec.created_at
  const ended = [...rec.steps].reverse().find((s) => s.finished_at)?.finished_at ?? null
  const title = site ?? run.phrases[0]?.text ?? 'Your page'

  async function remove() {
    await api.deleteRun(id)
    onChanged()
    go({ page: 'new' })
  }

  async function retry() {
    setRetrying(true)
    try {
      const { id: next } = await api.startRun(run.page_text, run.settings, run.source_url)
      onChanged()
      go({ page: 'run', id: next })
    } finally {
      setRetrying(false)
    }
  }

  return (
    <div className="page">
      <header className="run-head">
        <div>
          <h1>{active ? `Analysing ${title}` : `SEO brief for ${title}`}</h1>
          <div className="run-meta">
            <span>{relativeTime(rec.created_at)}</span>
            <span>{COUNTRY_NAMES[run.settings.country] ?? run.settings.country}</span>
            <span>{run.settings.site_strength} website</span>
            {!active && <span>took {duration(started, ended)}</span>}
            <span>{usd(run.cost_usd)} AI cost</span>
          </div>
        </div>
        {!active && (
          <div className="run-actions">
            {confirming ? (
              <span className="confirm">
                Delete this brief?
                <button type="button" className="btn danger" onClick={remove}>Delete</button>
                <button type="button" className="btn ghost" onClick={() => setConfirming(false)}>Cancel</button>
              </span>
            ) : (
              <>
                {run.brief && <CopyButton text={briefToMarkdown(run.brief, site)} label="Copy brief" className="btn" />}
                {rec.status === 'done' && <a className="btn ghost" href={`/api/runs/${id}/report.docx`} download>Download report (Word)</a>}
                <button type="button" className="btn ghost danger" onClick={() => setConfirming(true)}>Delete</button>
              </>
            )}
          </div>
        )}
      </header>

      {(active || rec.status === 'failed') && (
        <section className="card progress-card">
          <div className="card-body">
            <div className="progress-top">
              <h2>{rec.status === 'failed' ? 'The analysis stopped' : current ? `${STEP_TEXT[current.name]}…` : 'Getting started…'}</h2>
              <span className="muted small nums">{done} of {rec.steps.length}</span>
            </div>
            <div className="bar" role="progressbar" aria-valuemin={0} aria-valuemax={rec.steps.length} aria-valuenow={done}>
              <div className="bar-fill" style={{ width: `${(done / rec.steps.length) * 100}%` }} />
            </div>
            <ol className="steps">
              {rec.steps.map((s) => (
                <li key={s.name} className={`step ${s.status}`}>
                  <span className="step-icon" aria-hidden="true">{s.status === 'done' ? '✓' : s.status === 'failed' ? '!' : ''}</span>
                  <div>
                    <div>{STEP_TEXT[s.name] ?? s.label}</div>
                    {s.status === 'done' && s.detail && <div className="step-detail">{s.detail}</div>}
                  </div>
                  <span className="step-time">{s.status === 'pending' ? '' : duration(s.started_at, s.finished_at)}</span>
                </li>
              ))}
            </ol>
            {rec.error ? (
              <>
                <Alert tone="bad">
                  <strong>Something went wrong.</strong> {rec.error}
                </Alert>
                <div><button type="button" className="btn primary" onClick={retry} disabled={retrying}>{retrying ? 'Starting…' : 'Try again'}</button></div>
              </>
            ) : (
              <p className="muted small">Usually takes 2 to 4 minutes. You can leave this page; the brief will appear in the sidebar when it’s ready.</p>
            )}
          </div>
        </section>
      )}

      {rec.status === 'done' && run.brief && (
        <>
          <div className="tabs" role="tablist" aria-label="Brief views">
            {TABS.map((t) => (
              <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}>{t.label}</button>
            ))}
          </div>
          {tab === 'plan' && <ActionPlan brief={run.brief} run={run} details={rec.details} />}
          {tab === 'details' && rec.details && <DetailsView run={run} details={rec.details} />}
          {tab === 'text' && <section className="card"><div className="card-body"><p className="page-text">{run.page_text}</p></div></section>}
        </>
      )}
    </div>
  )
}
