import { useState, type KeyboardEvent, type PointerEvent } from 'react'
import { monthYear } from '../format'

type Point = { month: string; score: number; estimated: boolean }

/** 0.41 -> 1, 1.78 -> 2, 4.7 -> 5: a round top for the axis, never below 1. */
function niceMax(v: number): number {
  return Math.max(1, Math.ceil(v))
}

/**
 * One series over time (dataviz: single series, so no legend; the title names it). The line is
 * SVG scaled to the box with a non-scaling 2px stroke; labels, the marker and the tooltip are
 * HTML so they never stretch on narrow screens. Hover, touch and arrow keys move the crosshair.
 * A table with every point is there for screen readers.
 */
export function LinkChart({ history, title }: { history: Point[]; title: string }) {
  const [active, setActive] = useState<number | null>(null)
  if (history.length < 2) return null
  const top = niceMax(Math.max(...history.map((p) => p.score)))
  const ticks = [top, top / 2, 0]
  const x = (i: number) => (i / (history.length - 1)) * 100
  const y = (v: number) => 100 - (v / top) * 100
  const path = history.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(2)},${y(p.score).toFixed(2)}`).join(' ')
  const point = active === null ? null : history[active]

  const pick = (e: PointerEvent<HTMLDivElement>) => {
    const box = e.currentTarget.getBoundingClientRect()
    const share = Math.min(1, Math.max(0, (e.clientX - box.left) / box.width))
    setActive(Math.round(share * (history.length - 1)))
  }
  const keys = (e: KeyboardEvent<HTMLDivElement>) => {
    const last = history.length - 1
    const step: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, Home: -last, End: last }
    if (!(e.key in step)) return
    e.preventDefault()
    // The first key press shows the latest month; later presses move from there.
    setActive((a) => (a === null ? last : Math.min(last, Math.max(0, a + step[e.key]))))
  }

  return (
    <figure className="line-chart">
      <div className="lc-body">
        <div className="lc-y" aria-hidden="true">
          {ticks.map((t) => <span key={t} style={{ top: `${y(t)}%` }}>{t % 1 ? t.toFixed(1) : t}</span>)}
        </div>
        <div
          className="lc-plot"
          role="img"
          aria-label={`${title}: from ${history[0].score} in ${monthYear(history[0].month)} to ${history[history.length - 1].score} in ${monthYear(history[history.length - 1].month)}. Use the arrow keys to read each month.`}
          tabIndex={0}
          onPointerMove={pick}
          onPointerDown={pick}
          onPointerLeave={() => setActive(null)}
          onKeyDown={keys}
          onBlur={() => setActive(null)}
        >
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            {ticks.map((t) => <line key={t} className="lc-grid" x1="0" x2="100" y1={y(t)} y2={y(t)} />)}
            <path className="lc-line" d={path} />
          </svg>
          {point && active !== null && (
            <>
              <span className="lc-cross" style={{ left: `${x(active)}%` }} />
              <span className="lc-dot" style={{ left: `${x(active)}%`, top: `${y(point.score)}%` }} />
              <span className={`lc-tip ${x(active) > 50 ? 'left' : ''}`} style={{ left: `${x(active)}%` }}>
                <strong className="nums">{point.score.toFixed(2)}</strong> {monthYear(point.month)}
                {point.estimated && <span className="muted"> (estimated)</span>}
              </span>
            </>
          )}
        </div>
      </div>
      <span className="sr-only" aria-live="polite">
        {point ? `${point.score.toFixed(2)} in ${monthYear(point.month)}${point.estimated ? ', estimated' : ''}` : ''}
      </span>
      <div className="lc-x muted small" aria-hidden="true">
        <span>{monthYear(history[0].month)}</span>
        <span>{monthYear(history[history.length - 1].month)}</span>
      </div>
      <div className="sr-only">
        <table>
        <caption>{title}</caption>
        <thead><tr><th>Month</th><th>Score</th></tr></thead>
        <tbody>
          {history.map((p) => <tr key={p.month}><td>{monthYear(p.month)}</td><td>{p.score}{p.estimated ? ' (estimated)' : ''}</td></tr>)}
        </tbody>
        </table>
      </div>
    </figure>
  )
}
