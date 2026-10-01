import { duration } from '../format'
import type { RunStatus, Step } from '../types'
import { Alert } from './ui'

/** "34/60" while Google is being checked becomes "34 of 60 keywords". */
function runningDetail(detail: string): string {
  const m = detail.match(/^(\d+)\/(\d+)$/)
  return m ? `${m[1]} of ${m[2]} keywords` : detail
}

/** Live steps of a Keyword Gap analysis or a Site Snapshot, and the error with a retry. */
export function RunProgress({
  status,
  steps,
  error,
  stepText,
  retrying,
  onRetry,
  leaveNote,
  failedTitle,
}: {
  status: RunStatus
  steps: Step[]
  error: string | null
  stepText: Record<string, string>
  retrying: boolean
  onRetry: () => void
  leaveNote: string
  failedTitle: string
}) {
  const done = steps.filter((s) => s.status === 'done').length
  const current = steps.find((s) => s.status === 'running')
  return (
    <section className="card progress-card">
      <div className="card-body">
        <div className="progress-top">
          <h2>{status === 'failed' ? failedTitle : current ? `${stepText[current.name] ?? current.label}…` : 'Getting started…'}</h2>
          <span className="muted small nums">{done} of {steps.length}</span>
        </div>
        <div className="bar" role="progressbar" aria-valuemin={0} aria-valuemax={steps.length} aria-valuenow={done}>
          <div className="bar-fill" style={{ width: `${(done / steps.length) * 100}%` }} />
        </div>
        <ol className="steps">
          {steps.map((s) => (
            <li key={s.name} className={`step ${s.status}`}>
              <span className="step-icon" aria-hidden="true">{s.status === 'done' ? '✓' : s.status === 'failed' ? '!' : ''}</span>
              <div>
                <div>{stepText[s.name] ?? s.label}</div>
                {s.detail && s.status !== 'pending' && (
                  <div className="step-detail nums">{s.status === 'running' ? runningDetail(s.detail) : s.detail}</div>
                )}
              </div>
              <span className="step-time">{s.status === 'pending' ? '' : duration(s.started_at, s.finished_at)}</span>
            </li>
          ))}
        </ol>
        {error ? (
          <>
            <Alert tone="bad">
              <strong>Something went wrong.</strong> {error}
            </Alert>
            <div><button type="button" className="btn primary" onClick={onRetry} disabled={retrying}>{retrying ? 'Starting…' : 'Try again'}</button></div>
          </>
        ) : (
          <p className="muted small">{leaveNote}</p>
        )}
      </div>
    </section>
  )
}
