import type { ReactNode } from 'react'
import { checklistLabel, competition, usd } from '../format'
import type { Details as DetailsT, Run } from '../types'
import { Disclosure, Pill } from './ui'

const BUCKET: Record<string, { label: string; tone: 'brand' | 'neutral' | 'warn' }> = {
  must: { label: 'Must have', tone: 'brand' },
  worth: { label: 'Nice to have', tone: 'neutral' },
  rare: { label: 'Rare', tone: 'neutral' },
  noise: { label: 'Ignored', tone: 'warn' },
}

const shortUrl = (url: string) => url.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '')

export function DetailsView({ run, details }: { run: Run; details: DetailsT }) {
  const brief = run.brief!
  const topics = run.coverage.filter((c) => c.bucket !== 'noise')
  return (
    <div className="details">
      <Section title="How the score works" hint="A measure of topic coverage compared with top-ranking pages. It guides your edits; it can’t promise a ranking.">
        <p className="arithmetic">{brief.score_arithmetic}</p>
        <ul className="checklist">
          {Object.entries(brief.checklist).map(([key, ok]) => (
            <li key={key}><span className={ok ? 'ok' : 'no'} aria-label={ok ? 'passes' : 'fails'}>{ok ? '✓' : '✕'}</span>{checklistLabel(key)}</li>
          ))}
        </ul>
        {details.stuffing_warnings.length > 0 && (
          <ul className="plain-list">{details.stuffing_warnings.map((w) => <li key={w} className="text-bad">{w}</li>)}</ul>
        )}
      </Section>

      <Section title="Pages we compared" hint={`Your page reads as a ${details.ours_page_type || 'general'} page. These pages rank for your searches and passed our quality filters.`}>
        <div className="table-scroll">
          <table className="table">
            <thead><tr><th>Google position</th><th>Page</th><th>Type</th></tr></thead>
            <tbody>
              {run.competitors.map((c) => (
                <tr key={c.url}>
                  <td className="num">{c.source.replace('google#', '#')}</td>
                  <td><a className="url" href={c.url} target="_blank" rel="noreferrer">{shortUrl(c.url)}</a></td>
                  <td>{c.page_type}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {details.dropped.length > 0 && (
          <Disclosure summary={`${details.dropped.length} pages we left out, and why`}>
            <ul className="plain-list">
              {details.dropped.map((d) => (
                <li key={d.url}><a className="url" href={d.url} target="_blank" rel="noreferrer">{shortUrl(d.url)}</a><span className="muted small">{d.reason}</span></li>
              ))}
            </ul>
          </Disclosure>
        )}
      </Section>

      <Section title="Every topic we found" hint="All topics from the compared pages, and how often your page covers each one.">
        <div className="table-scroll">
          <table className="table">
            <thead><tr><th>Topic</th><th>Importance</th><th className="num">Top pages</th><th className="num">Your page</th></tr></thead>
            <tbody>
              {topics.map((t) => (
                <tr key={t.topic}>
                  <td>{t.topic}</td>
                  <td><Pill tone={BUCKET[t.bucket].tone}>{BUCKET[t.bucket].label}</Pill></td>
                  <td className="num">{t.covered_by} of {t.total}</td>
                  <td className="num">{t.ours_passages === 0 ? '—' : `${t.ours_passages}×`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="How the searches were chosen" hint={`We checked ${details.candidates.length} possible searches for demand, competition and fit with your page.`}>
        <div className="table-scroll">
          <table className="table">
            <thead><tr><th>Search</th><th>Competition</th><th className="num">Fit</th></tr></thead>
            <tbody>
              {details.clusters.map((c, i) => (
                <tr key={c.head} className={i < run.phrases.length ? 'chosen' : ''}>
                  <td>{c.head}{i < run.phrases.length && <> <Pill tone="good">chosen</Pill></>}{c.weak_spots.length > 0 && <div className="muted small">{c.weak_spots.join(' · ')}</div>}</td>
                  <td><Pill tone={competition(c.difficulty).tone}>{competition(c.difficulty).label} ({c.difficulty})</Pill></td>
                  <td className="num">{Math.round(c.fit * 100)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Disclosure summary={`All ${details.candidates.length} searches considered`}>
          <ul className="plain-list">
            {details.candidates.map((c) => (
              <li key={c.keyword}><strong>{c.keyword}</strong><span className="muted small">{c.kept ? 'chosen' : c.reason || 'ranked lower'}</span></li>
            ))}
          </ul>
        </Disclosure>
      </Section>

      <Section title="Google results we studied">
        {details.serps.map((s) => (
          <Disclosure key={s.phrase} summary={`“${s.phrase}”: ${s.items.length} results`}>
            <ol className="plain-list">
              {s.items.map((i) => (
                <li key={i.url}><span className="muted small nums">#{i.rank}</span><a className="url" href={i.url} target="_blank" rel="noreferrer">{i.title && !i.title.includes('.') ? i.title : shortUrl(i.url)}</a></li>
              ))}
            </ol>
          </Disclosure>
        ))}
      </Section>

      <Section title="Cost">
        <p>{usd(run.cost_usd)} in AI usage across {run.costs.length} calls. Search data is free.</p>
      </Section>
    </div>
  )
}

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="card">
      <div className="card-body">
        <h2>{title}</h2>
        {hint && <p className="section-hint">{hint}</p>}
        {children}
      </div>
    </section>
  )
}
