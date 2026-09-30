import { useState, type ReactNode } from 'react'
import {
  bandText,
  bingText,
  CHECK_TEXT,
  COUNTRY_NAMES,
  intentChip,
  monthYear,
  pathOf,
  safeHref,
  VITAL_TEXT,
  vitalTone,
  vitalValue,
} from '../format'
import { go } from '../router'
import type { SnapshotKeyword, SnapshotResult, SnapshotRun } from '../types'
import { LinkChart } from './LinkChart'
import { Disclosure, Pill } from './ui'

type Filter = 'all' | 'found' | 'not'
const PAGE_SIZE = 10
type Period = '1Y' | '2Y' | '5Y' | 'All'
const PERIOD_MONTHS: Record<Period, number> = { '1Y': 12, '2Y': 24, '5Y': 60, All: Infinity }
const FORM_FACTOR: Record<string, string> = { PHONE: 'Phones', DESKTOP: 'Desktops', TABLET: 'Tablets' }

/** An estimate gets "~". Zero is exact only when the site is not in the results (no clicks from
 *  them); a ranked page can round down to 0 and is still an estimate. */
function visitsText(v: number, ranked: boolean): string {
  return v === 0 && !ranked ? '0' : `~${v.toLocaleString()}`
}

/** Why there is no visit estimate: nothing checked, no Bing key, or Bing too low. */
function noVisitsReason(result: SnapshotResult): string {
  if (result.keywords_checked === 0) return 'No searches were checked.'
  if (result.keywords.every((k) => k.bing_status === 'no_key')) return 'Needs a Bing Webmaster key for search numbers.'
  return 'Too low to measure: Bing has no search numbers for these searches.'
}

function Kpi({ label, value, children, extra }: { label: string; value: ReactNode; children?: ReactNode; extra?: ReactNode }) {
  return (
    <section className="card kpi">
      <h2 className="kpi-label">{label}</h2>
      <div className="kpi-value">{value}</div>
      {children && <div className="kpi-sub">{children}</div>}
      {extra}
    </section>
  )
}

const None = ({ children }: { children: ReactNode }) => <span className="kpi-none">{children}</span>

/** A small, decorative trend line; the chart below carries the values. */
function Sparkline({ points }: { points: number[] }) {
  if (points.length < 2) return null
  const top = Math.max(1, Math.ceil(Math.max(...points)))
  const d = points.map((v, i) => `${i ? 'L' : 'M'}${((i / (points.length - 1)) * 100).toFixed(2)},${(30 - (v / top) * 28).toFixed(2)}`).join(' ')
  return (
    <svg className="kpi-spark" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true">
      <path d={d} />
    </svg>
  )
}

function LinkKpi({ result }: { result: SnapshotResult }) {
  const link = result.facts.link
  if (!link) return <Kpi label="Link score" value={<None>Couldn’t load</None>}>The lookup failed. The details below say why.</Kpi>
  if (link.status === 'not_set_up') return <Kpi label="Link score" value={<None>Not set up</None>}>Add OPENPAGERANK_API_KEY to .env (free).</Kpi>
  if (link.status === 'not_found') return <Kpi label="Link score" value={<None>No link data</None>}>Open PageRank has no links to this site.</Kpi>
  if (link.status === 'error') return <Kpi label="Link score" value={<None>Couldn’t load</None>}>{link.note}</Kpi>
  return (
    <Kpi
      label="Link score"
      value={<><span className="nums">{link.score?.toFixed(2)}</span><span className="kpi-of"> / 10</span></>}
      extra={<Sparkline points={link.history.map((p) => p.score)} />}
    >
      <span className="nums">{(link.referring_domains ?? 0).toLocaleString()}</span> referring domains (weighted), Open PageRank
    </Kpi>
  )
}

function PopularityKpi({ result }: { result: SnapshotResult }) {
  const { tranco_rank, tranco_read, majestic, majestic_read } = result.facts
  const value = tranco_rank ? <span className="nums">#{tranco_rank.toLocaleString()}</span> : <None>{tranco_read ? 'Not in top 1M' : 'Couldn’t load'}</None>
  return (
    <Kpi label="Popularity" value={value}>
      {tranco_rank ? 'Tranco rank. ' : 'Tranco top 1M sites. '}
      {majestic
        ? <>Majestic: <span className="nums">{majestic.ref_subnets.toLocaleString()}</span> linking networks.</>
        : majestic_read ? 'Not in Majestic’s top 1M.' : 'Majestic list couldn’t load.'}
    </Kpi>
  )
}

function AgeKpi({ result }: { result: SnapshotResult }) {
  const dates = result.facts.dates
  const registered = monthYear(dates?.registered ?? null)
  const seen = monthYear(dates?.first_seen ?? null)
  const other = dates?.registered_domain && dates.registered_domain !== result.domain ? ` (${dates.registered_domain})` : ''
  return (
    <Kpi label={`Registered${other}`} value={registered ? <span className="nums">{registered}</span> : <None>Unknown</None>}>
      First seen online: {seen ?? 'unknown'}
      {dates?.registered && dates.first_seen && dates.first_seen < dates.registered ? ', before the current registration.' : '.'}
    </Kpi>
  )
}

function IntentChip({ intent }: { intent: string }) {
  const i = intentChip(intent)
  return <span className={`chip ${i.tone}`}>{i.label}</span>
}

function DifficultyChip({ k }: { k: SnapshotKeyword }) {
  if (k.difficulty === null || !k.difficulty_band) return <span className="muted small">Unknown</span>
  const band = bandText(k.difficulty_band)
  return <span className={`chip ${band.tone}`}><span className="nums">{k.difficulty}</span> {band.label}</span>
}

function HealthRing({ passed, total }: { passed: number; total: number }) {
  const c = 2 * Math.PI * 30
  return (
    <svg className="ring-mini" width="76" height="76" viewBox="0 0 76 76" role="img" aria-label={`${passed} of ${total} checks pass`}>
      <circle cx="38" cy="38" r="30" className="ring-mini-track" />
      <circle cx="38" cy="38" r="30" className="ring-mini-fill" strokeDasharray={`${(c * passed) / Math.max(1, total)} ${c}`} transform="rotate(-90 38 38)" />
      <text x="38" y="43" textAnchor="middle">{passed}/{total}</text>
    </svg>
  )
}

function SpeedItem({ result }: { result: SnapshotResult }) {
  const speed = result.facts.speed
  if (result.vitals.length > 0) {
    return (
      <li>
        <span className="check-icon neutral" aria-hidden="true">i</span>
        <div>
          <div className="check-label"><strong>Speed for real visitors</strong></div>
          <ul className="vitals">
            {result.vitals.map((v) => (
              <li key={v.metric}>
                <span>{VITAL_TEXT[v.metric]?.label ?? v.metric}</span>
                <Pill tone={vitalTone(v.status)}><span className="nums">{vitalValue(v.metric, v.p75)}</span> · {v.status}</Pill>
              </li>
            ))}
          </ul>
          <div className="muted small">{FORM_FACTOR[speed?.form_factor ?? ''] ?? 'All devices'}, 75% of visits, last 28 days (Chrome).</div>
        </div>
      </li>
    )
  }
  const [word, detail] = !speed
    ? ['Couldn’t load', 'The lookup failed. The details below say why.']
    : speed.status === 'not_set_up'
      ? ['Not set up', 'Add a Chrome UX Report key (CRUX_API_KEY) to measure it.']
      : speed.status === 'no_data'
        ? ['Not enough data', 'Too few Chrome visitors to measure. Common for smaller sites.']
        : ['Couldn’t load', speed.note]
  return (
    <li>
      <span className="check-icon neutral" aria-hidden="true">i</span>
      <div>
        <div className="check-label"><strong>Speed for real visitors</strong> <Pill>{word}</Pill></div>
        <div className="muted small">{detail}</div>
      </div>
    </li>
  )
}

export function SnapshotResults({ run, result }: { run: SnapshotRun; result: SnapshotResult }) {
  const [filter, setFilter] = useState<Filter>('all')
  const [query, setQuery] = useState('')
  const [period, setPeriod] = useState<Period>('All')
  const [pageNo, setPageNo] = useState(0)
  const { domain, keywords, depth } = result
  const found = keywords.filter((k) => k.ranked)
  const byTab = filter === 'found' ? found : filter === 'not' ? keywords.filter((k) => !k.ranked) : keywords
  const q = query.trim().toLowerCase()
  const matching = q ? byTab.filter((k) => k.keyword.includes(q)) : byTab
  const pages = Math.max(1, Math.ceil(matching.length / PAGE_SIZE))
  const pageIndex = Math.min(pageNo, pages - 1)
  const shown = matching.slice(pageIndex * PAGE_SIZE, (pageIndex + 1) * PAGE_SIZE)
  const maxGroup = Math.max(1, ...result.groups.map((g) => g.count))
  const country = COUNTRY_NAMES[run.settings.gap.base.country] ?? run.settings.gap.base.country
  const link = result.facts.link
  const history = link?.status === 'ok' ? link.history : []
  const periodHistory = history.slice(-Math.min(history.length, PERIOD_MONTHS[period]))
  // Any ranked search with a Bing number: then a total of 0 is a rounded estimate, not exact.
  const anyRankedVisits = keywords.some((k) => k.ranked && k.visits !== null)
  const checks = result.checks?.checks ?? []
  const passed = checks.filter((c) => c.status === 'pass').length
  const issues = checks.filter((c) => c.status !== 'pass')
  const toCheck = checks.filter((c) => c.status === 'warn').length
  const toFix = checks.filter((c) => c.status === 'fail').length
  const tabs: [Filter, string, number][] = [
    ['all', 'All', keywords.length],
    ['found', `In top ${depth}`, found.length],
    ['not', 'Not yet', keywords.length - found.length],
  ]

  return (
    <>
      <div className="kpi-row">
        <LinkKpi result={result} />
        <PopularityKpi result={result} />
        <Kpi
          label="Found on Google"
          value={result.keywords_checked === 0
            ? <None>Not checked</None>
            : <><span className="nums">{result.keywords_found}</span><span className="kpi-of"> / {result.keywords_checked}</span></>}
        >
          {result.keywords_checked === 0 ? 'No searches were checked. The details below say why.' : `searches in the top ${depth} · ${country}`}
        </Kpi>
        <Kpi
          label="Est. visits"
          value={result.visits === null
            ? <None>—</None>
            : <><span className="nums">{visitsText(result.visits, anyRankedVisits)}</span><span className="kpi-of"> / mo</span></>}
        >
          {result.visits === null
            ? noVisitsReason(result)
            : result.visits === 0 && !anyRankedVisits
              ? `From ${result.visits_keywords} searches with Bing numbers; not in the top ${depth} for them.`
              : `Rough, from ${result.visits_keywords} searches with Bing numbers.`}
        </Kpi>
        <AgeKpi result={result} />
        <Kpi
          label="Pages in sitemap"
          value={result.sitemap_files
            ? <><span className="kpi-of">{result.sitemap_capped ? 'at least ' : ''}</span><span className="nums">{result.sitemap_urls.toLocaleString()}</span></>
            : <None>No sitemap</None>}
        >
          {!result.sitemap_files
            ? 'No sitemap was found.'
            : result.sitemap_capped
              ? `In the first ${result.sitemap_files} sitemap files; the site lists more.`
              : `${result.sitemap_files} sitemap file${result.sitemap_files === 1 ? '' : 's'}`}
        </Kpi>
      </div>

      <div className="snap-grid-2">
        <section className="card">
          <div className="card-body">
            <div className="card-title-row">
              <div>
                <h2 className="section-title">Link score over time</h2>
                <p className="muted small">Open PageRank, 0 to 10, monthly{history.length ? ` · ${history.length} months` : ''}</p>
              </div>
              {history.length > 1 && (
                <div className="tabs" role="group" aria-label="Period">
                  {(Object.keys(PERIOD_MONTHS) as Period[]).map((p) => (
                    <button key={p} type="button" aria-pressed={period === p} onClick={() => setPeriod(p)} disabled={PERIOD_MONTHS[p] < Infinity && history.length <= 2}>
                      {p}
                    </button>
                  ))}
                </div>
              )}
            </div>
            {periodHistory.length > 1 ? (
              <LinkChart history={periodHistory} title="Link score over time" />
            ) : (
              <p className="muted small">No link history for this site.</p>
            )}
          </div>
        </section>

        <section className="card">
          <div className="card-body">
            <div>
              <h2 className="section-title">Google positions</h2>
              <p className="muted small">{result.keywords_checked} searches the pages target · top {depth} · {country}</p>
            </div>
            {result.keywords_checked === 0 ? (
              <p className="muted small">No searches were checked. The details below say why.</p>
            ) : (
              <ul className="group-bars">
                {result.groups.map((g) => (
                  <li key={g.label}>
                    <span className="group-label">{g.low === null ? g.label.replace(/^./, (c) => c.toUpperCase()) : g.low === 1 ? `Top ${g.high}` : g.label.replace('-', '–')}</span>
                    <span className="overlap-track">
                      <span className={`overlap-bar ${g.low === null ? 'outside' : ''}`} style={{ width: `${(g.count / maxGroup) * 100}%` }} />
                      <span className="overlap-value nums">{g.count}</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {result.keywords_checked > 0 && result.keywords_found === 0 && (
              <p className="callout">
                {domain} is not in the top {depth} for any of these {result.keywords_checked} searches yet. They are the searches to work on.
              </p>
            )}
          </div>
        </section>
      </div>

      <div className="snap-grid-main">
        <section className="card" id="snapshot-keywords">
          <div className="card-body">
            <div className="table-top">
              <div>
                <h2 className="section-title">Searches its pages target</h2>
                <p className="muted small">A sample of {keywords.length} · positions from one Google check</p>
              </div>
              {keywords.length > 0 && (
                <div className="table-tools">
                  <label className="search-field">
                    <span className="sr-only">Filter searches</span>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
                    <input type="search" placeholder="Filter searches" value={query} onChange={(e) => { setQuery(e.target.value); setPageNo(0) }} />
                  </label>
                  <div className="tabs" role="group" aria-label="Show searches">
                    {tabs.map(([id, label, count]) => (
                      <button key={id} type="button" aria-pressed={filter === id} onClick={() => { setFilter(id); setPageNo(0) }}>
                        {label} <span className="tab-count nums">{count}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
            {keywords.length === 0 ? (
              <p className="muted small">No searches were checked. The details below say why.</p>
            ) : (
              <>
                <div className="table-scroll">
                  <table className="table snap-table">
                    <thead>
                      <tr>
                        <th scope="col">Search</th>
                        <th scope="col">Intent</th>
                        <th scope="col" className="num">Position</th>
                        <th scope="col">Page</th>
                        <th scope="col" className="num">Bing searches</th>
                        <th scope="col" className="num">Visits</th>
                        <th scope="col">Difficulty</th>
                      </tr>
                    </thead>
                    <tbody>
                      {shown.map((k) => {
                        const href = safeHref(k.url)
                        return (
                          <tr key={k.keyword}>
                            <td className="kw-cell">{k.keyword}</td>
                            <td><IntentChip intent={k.intent} /></td>
                            <td className="num">
                              {k.position === null
                                ? <span className="pos none" aria-label={`Not in top ${depth}`}>—</span>
                                : <span className="pos">{k.position}</span>}
                            </td>
                            <td className="url">{href ? <a href={href} target="_blank" rel="noopener noreferrer" title={k.url}>{pathOf(k.url, domain)}</a> : '—'}</td>
                            <td className="num">{bingText(k)}</td>
                            <td className="num">{k.visits === null ? '—' : visitsText(k.visits, k.ranked)}</td>
                            <td><DifficultyChip k={k} /></td>
                          </tr>
                        )
                      })}
                      {shown.length === 0 && <tr><td colSpan={7} className="muted">No searches match.</td></tr>}
                    </tbody>
                  </table>
                </div>
                <div className="table-foot">
                  <p className="muted small">
                    {matching.length === 0 ? 'No searches' : `${pageIndex * PAGE_SIZE + 1}–${pageIndex * PAGE_SIZE + shown.length} of ${matching.length}`}. “—” in Position means not on the first {depth / 10} pages, not “never ranks”.
                  </p>
                  {pages > 1 && (
                    <div className="pager">
                      <button type="button" className="btn ghost" disabled={pageIndex === 0} onClick={() => setPageNo(pageIndex - 1)}>Previous</button>
                      <span className="muted small nums">Page {pageIndex + 1} of {pages}</span>
                      <button type="button" className="btn ghost" disabled={pageIndex >= pages - 1} onClick={() => setPageNo(pageIndex + 1)}>Next</button>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </section>

        <div className="side-stack">
          <section className="card">
            <div className="card-body">
              <div>
                <h2 className="section-title">Competitors on Google</h2>
                <p className="muted small">Page 1 for 2 or more of these searches. A suggestion: some are platforms, not rivals.</p>
              </div>
              {result.competitors.length === 0 ? (
                <p className="muted small">No site shows up often enough to suggest.</p>
              ) : (
                <>
                  <ol className="rank-list">
                    {result.competitors.map((c) => (
                      <li key={c.domain} title={`For example: ${c.examples.join(', ')}`}>
                        <span className="rank-chip nums">#{c.best_position}</span>
                        <strong>{c.domain}</strong>
                        <span className="muted small nums">{c.keywords} searches</span>
                      </li>
                    ))}
                  </ol>
                  <button
                    type="button"
                    className="btn outline"
                    onClick={() => go({ page: 'gap-new', site: domain, competitors: result.competitors.slice(0, 4).map((c) => c.domain) })}
                  >
                    Compare in Keyword Gap
                  </button>
                </>
              )}
            </div>
          </section>

          <section className="card">
            <div className="card-body">
              <div className="health-head">
                {checks.length > 0 && <HealthRing passed={passed} total={checks.length} />}
                <div>
                  <h2 className="section-title">Technical health</h2>
                  <p className="muted small">{checks.length ? `${checks.length} checks against Google’s rules` : 'The checks could not run. The details below say why.'}</p>
                  {checks.length > 0 && (
                    <div className="chip-row">
                      <span className="chip good">{passed} pass</span>
                      {toCheck > 0 && <span className="chip warn">{toCheck} to check</span>}
                      {toFix > 0 && <span className="chip bad">{toFix} to fix</span>}
                    </div>
                  )}
                </div>
              </div>
              <ul className="check-list compact">
                {issues.map((c) => {
                  const t = CHECK_TEXT[c.status]
                  return (
                    <li key={c.key}>
                      <span className={`check-icon ${t.tone}`} aria-hidden="true">{t.icon}</span>
                      <div>
                        <div className="check-label"><strong>{c.label}</strong> <Pill tone={t.tone}>{t.word}</Pill></div>
                        <div className="muted small">{c.detail}</div>
                      </div>
                    </li>
                  )
                })}
                <SpeedItem result={result} />
              </ul>
              {checks.length > 0 && (
                <Disclosure summary={`All ${checks.length} checks`}>
                  <ul className="check-list compact">
                    {checks.map((c) => {
                      const t = CHECK_TEXT[c.status]
                      return (
                        <li key={c.key}>
                          <span className={`check-icon ${t.tone}`} aria-hidden="true">{t.icon}</span>
                          <div>
                            <div className="check-label"><strong>{c.label}</strong> <Pill tone={t.tone}>{t.word}</Pill></div>
                            <div className="muted small">{c.detail}</div>
                          </div>
                        </li>
                      )
                    })}
                  </ul>
                </Disclosure>
              )}
            </div>
          </section>

          {result.top_pages.length > 0 && (
            <section className="card">
              <div className="card-body">
                <h2 className="section-title">Top pages</h2>
                <ol className="rank-list">
                  {result.top_pages.map((p) => {
                    const href = safeHref(p.url)
                    return (
                      <li key={p.url}>
                        <span className="rank-chip nums">#{p.best_position}</span>
                        {href ? <a className="url" href={href} target="_blank" rel="noopener noreferrer" title={p.url}>{pathOf(p.url, domain)}</a> : <span>{p.url}</span>}
                        <span className="muted small nums">{p.visits !== null ? `${visitsText(p.visits, true)} visits` : `${p.keywords.length} search${p.keywords.length === 1 ? '' : 'es'}`}</span>
                      </li>
                    )
                  })}
                </ol>
              </div>
            </section>
          )}
        </div>
      </div>

      <section className="card">
        <div className="card-body method">
          <h2 className="section-title">How we calculate this</h2>
          <ul className="plain-list">
            <li>We read {run.sample?.pages.length ?? 0} pages of the site, named the search each page is built for, and checked {result.keywords_checked} of them on Google. This is a sample: paid tools track millions of searches, and no free source gives a site’s total traffic or keyword count.</li>
            <li>Positions come from the first {depth / 10} pages of Google in one check. Google moves results a few places between searches.</li>
            <li>Visits = Bing searches × (Google’s share ÷ Bing’s share of searches in this country) × the share of clicks at that position. Only searches with Bing numbers count. Even paid tools miss by about half: use it to compare, not as a forecast.</li>
            <li>Link score: Open PageRank, from the Common Crawl link graph. It is not Google’s PageRank, and not an “authority” score from a paid tool.</li>
            <li>Popularity: the Tranco list (a research ranking of the most visited sites). Linking networks: Majestic Million, by Majestic (majestic.com), licensed under CC BY 3.0.</li>
            {result.vitals.length > 0 && <li>Speed: Chrome UX Report, by Google, licensed under CC BY 4.0. Thresholds from web.dev (good, needs work, poor).</li>}
            <li>Site age: the domain registry (RDAP) and the Internet Archive’s Wayback Machine.</li>
          </ul>
          {run.notes.length > 0 && (
            <Disclosure summary="Details from this snapshot">
              <ul className="plain-list small">{run.notes.map((n, i) => <li key={`${i}-${n}`}>{n}</li>)}</ul>
            </Disclosure>
          )}
        </div>
      </section>
    </>
  )
}
