import { useEffect, useState } from 'react'
import { api } from '../api'
import { briefToMarkdown, COUNTRY_NAMES, demandText, duration, hostOf, topicCoverage, usd } from '../format'
import { go } from '../router'
import type { Run, RunRecord } from '../types'
import { ActionPlan } from './Brief'
import { DetailsView } from './Details'
import { RunProgress } from './RunProgress'
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

/** Headline numbers of a finished brief (docs/UI-REDESIGN-PLAN.md U3); all from the run itself. */
function BriefKpis({ run }: { run: Run }) {
  const brief = run.brief
  if (!brief) return null
  const main = brief.phrases[0]
  const must = brief.must_cover
  const covered = must.filter((t) => t.ours_passages > 0).length
  const key = topicCoverage(run.coverage)
  const words = run.page_text.split(/\s+/).filter(Boolean).length
  return (
    <div className="kpi-row brief-kpis">
      <section className="card kpi kpi-wide">
        <h2 className="kpi-label">Main search</h2>
        <div className="kpi-value kpi-text">{main?.text ?? '—'}</div>
        {main && <div className="kpi-sub">{demandText(main)}</div>}
      </section>
      <section className="card kpi">
        <h2 className="kpi-label">Must-cover topics</h2>
        <div className="kpi-value"><span className="nums">{covered}</span><span className="kpi-of"> / {must.length}</span></div>
        <div className="kpi-sub">already on the page · <span className="nums">{key.covered}/{key.total}</span> key topics</div>
      </section>
      <section className="card kpi">
        <h2 className="kpi-label">Gaps found</h2>
        <div className="kpi-value nums">{brief.gaps.length}</div>
        <div className="kpi-sub">questions competitors leave open</div>
      </section>
      <section className="card kpi">
        <h2 className="kpi-label">Pages compared</h2>
        <div className="kpi-value nums">{run.competitors.length}</div>
        <div className="kpi-sub">top results read for the searches</div>
      </section>
      <section className="card kpi">
        <h2 className="kpi-label">Words on your page</h2>
        <div className="kpi-value nums">{words.toLocaleString()}</div>
        <div className="kpi-sub">in the text analysed</div>
      </section>
    </div>
  )
}

export function RunView({ id, onChanged }: { id: string; onChanged: () => void }) {
  const [rec, setRec] = useState<RunRecord | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('plan')
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
        const next = await api.getRun(id)
        if (cancelled) return
        failures = 0
        setReconnecting(false)
        setRec(next)
        if (next.status === 'queued' || next.status === 'running') timer = window.setTimeout(load, POLL_MS)
        else onChanged()
      } catch (e) {
        if (cancelled) return
        if ((e as Error).message === 'run not found') {
          setError('This brief was deleted.')
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
  if (!rec) return <div className="page"><p className="muted">Opening brief…</p></div>

  const { run } = rec
  const site = hostOf(run.source_url)
  const active = rec.status === 'queued' || rec.status === 'running'
  const started = rec.steps.find((s) => s.started_at)?.started_at ?? rec.created_at
  const ended = [...rec.steps].reverse().find((s) => s.finished_at)?.finished_at ?? null
  const title = site ?? run.phrases[0]?.text ?? 'Your page'

  async function remove() {
    setActionError(null)
    try {
      await api.deleteRun(id)
      onChanged()
      go({ page: 'new' })
    } catch (e) {
      setActionError((e as Error).message)
    }
  }

  async function retry() {
    setRetrying(true)
    try {
      const { id: next } = await api.startRun(run.page_text, run.settings, run.source_url)
      onChanged()
      go({ page: 'run', id: next })
    } catch (e) {
      setActionError((e as Error).message)
    } finally {
      setRetrying(false)
    }
  }

  return (
    <div className="page brief-page">
      <header className="report-head">
        <div>
          <p className="eyebrow">SEO brief</p>
          <h1>{active ? `Analysing ${title}…` : title}</h1>
          <p className="report-meta">
            <span>{new Date(rec.created_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}</span>
            <span>{COUNTRY_NAMES[run.settings.country] ?? run.settings.country}</span>
            <span>{run.settings.site_strength} website</span>
            {run.phrases.length > 0 && <span className="nums">{run.phrases.length} search{run.phrases.length === 1 ? '' : 'es'}</span>}
            {!active && <span>took {duration(started, ended)}</span>}
            <span>{usd(run.cost_usd)} AI</span>
          </p>
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
                {rec.status === 'done' && <a className="btn" href={`/api/runs/${id}/report.docx`} download>Download report (Word)</a>}
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
          leaveNote="Usually takes 2 to 4 minutes. You can leave this page; the brief will appear in Recent briefs when it’s ready."
        />
      )}

      {rec.status === 'done' && run.brief && (
        <>
          <BriefKpis run={run} />
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
