import type { ReactNode } from 'react'
import { relativeTime } from '../format'
import type { RunStatus } from '../types'
import { Pill } from './ui'

export interface RecentItem {
  id: string
  href: string
  title: string
  createdAt: string
  status: RunStatus
  result: ReactNode // the key number when done (score, keywords to add, found/checked)
  cost: string
}

const STATUS: Record<RunStatus, { label: string; tone: 'good' | 'warn' | 'bad' | 'neutral' }> = {
  queued: { label: 'Waiting', tone: 'neutral' },
  running: { label: 'Running', tone: 'warn' },
  done: { label: 'Done', tone: 'good' },
  failed: { label: 'Didn’t finish', tone: 'bad' },
}

/** A tool's run history, on its start page (docs/UI-REDESIGN-PLAN.md, owner decision). */
export function RecentRuns({
  title,
  items,
  offline,
  empty,
  resultLabel,
}: {
  title: string
  items: RecentItem[]
  offline: boolean
  empty: string
  resultLabel: string
}) {
  return (
    <section className="card recent" aria-labelledby="recent-title">
      <div className="card-body">
        <div className="card-title-row">
          <h2 className="section-title" id="recent-title">{title}</h2>
          {items.length > 0 && <span className="muted small nums">{items.length}</span>}
        </div>
        {offline ? (
          <p className="text-bad small">The server isn’t running. Start it, then reload this page.</p>
        ) : items.length === 0 ? (
          <p className="muted small">{empty}</p>
        ) : (
          <div className="table-scroll">
            <table className="table recent-table">
              <thead>
                <tr>
                  <th scope="col">Site</th>
                  <th scope="col">When</th>
                  <th scope="col">Status</th>
                  <th scope="col" className="num">{resultLabel}</th>
                  <th scope="col" className="num">Cost</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => {
                  const s = STATUS[r.status]
                  return (
                    <tr key={r.id}>
                      <td><a className="recent-link" href={r.href}>{r.title}</a></td>
                      <td className="muted">{relativeTime(r.createdAt)}</td>
                      <td><Pill tone={s.tone}>{s.label}</Pill></td>
                      <td className="num">{r.status === 'done' ? r.result : '—'}</td>
                      <td className="num muted">{r.cost}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  )
}
