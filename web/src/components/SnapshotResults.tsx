import { useState, type ReactNode } from 'react'
import {
  bandText,
  bingText,
  CHECK_TEXT,
  COUNTRY_NAMES,
  intentText,
  monthYear,
  pathOf,
  safeHref,
  VITAL_TEXT,
  vitalTone,
  vitalValue,
} from '../format'
import { go } from '../router'
import type { SnapshotResult, SnapshotRun } from '../types'
import { LinkChart } from './LinkChart'
import { Disclosure, Pill } from './ui'

type Filter = 'all' | 'found' | 'not'
const FORM_FACTOR: Record<string, string> = { PHONE: 'Phones', DESKTOP: 'Desktops', TABLET: 'Tablets' }

/** An estimate gets "~". Zero is exact only when the site is not in the results (no clicks from
 *  them); a ranked page can round down to 0 and is still an estimate. */
function visitsText(v: number, ranked: boolean): string {
  return v === 0 && !ranked ? '0' : `~${v.toLocaleString()}`
}

function Tile({ label, value, children }: { label: string; value: ReactNode; children?: ReactNode }) {
  return (
    <section className="card fact-tile">
      <h2 className="fact-label">{label}</h2>
      <div className="fact-value">{value}</div>
      {children && <div className="fact-sub muted small">{children}</div>}
    </section>
  )
}

function LinkTile({ result }: { result: SnapshotResult }) {
  const link = result.facts.link
  if (!link) return <Tile label="Link score" value={<span className="fact-none">Couldn’t load</span>}>The lookup failed. The details below say why.</Tile>
  if (link.status === 'not_set_up') {
    return <Tile label="Link score" value={<span className="fact-none">Not set up</span>}>Add OPENPAGERANK_API_KEY to .env (free).</Tile>
  }
  if (link.status === 'not_found') return <Tile label="Link score" value={<span className="fact-none">No link data</span>}>Open PageRank has no links to this site.</Tile>
  if (link.status === 'error') return <Tile label="Link score" value={<span className="fact-none">Couldn’t load</span>}>{link.note}</Tile>
  return (
    <Tile label="Link score" value={<><span className="nums">{link.score?.toFixed(2)}</span><span className="fact-of"> / 10</span></>}>
      <span className="nums">{(link.referring_domains ?? 0).toLocaleString()}</span> referring domains (Open PageRank’s weighted count)
    </Tile>
  )
}

function PopularityTile({ result }: { result: SnapshotResult }) {
  const { tranco_rank, tranco_read, majestic, majestic_read } = result.facts
  const value = tranco_rank ? <span className="nums">#{tranco_rank.toLocaleString()}</span> : <span className="fact-none">{tranco_read ? 'Not in top 1M' : 'Couldn’t load'}</span>
  return (
    <Tile label="Popularity" value={value}>
      {tranco_rank ? 'Tranco rank of all websites. ' : 'Tranco lists the 1 million most visited sites. '}
      {majestic
        ? <>Majestic: <span className="nums">{majestic.ref_subnets.toLocaleString()}</span> linking networks.</>
        : majestic_read ? 'Not in Majestic’s top 1M.' : 'The Majestic list couldn’t load.'}
    </Tile>
  )
}

function SpeedTile({ result }: { result: SnapshotResult }) {
  const speed = result.facts.speed
  if (result.vitals.length > 0) {
    return (
      <Tile label="Speed for real visitors" value={
        <ul className="vitals">
          {result.vitals.map((v) => (
            <li key={v.metric}>
              <span>{VITAL_TEXT[v.metric]?.label ?? v.metric}</span>
              <Pill tone={vitalTone(v.status)}><span className="nums">{vitalValue(v.metric, v.p75)}</span> · {v.status}</Pill>
            </li>
          ))}
        </ul>
      }>{FORM_FACTOR[speed?.form_factor ?? ''] ?? 'All devices'}, 75% of visits, last 28 days (Chrome).</Tile>
    )
  }
  if (!speed) return <Tile label="Speed for real visitors" value={<span className="fact-none">Couldn’t load</span>}>The lookup failed. The details below say why.</Tile>
  if (speed.status === 'not_set_up') {
    return <Tile label="Speed for real visitors" value={<span className="fact-none">Not set up</span>}>Needs a Chrome UX Report key (CRUX_API_KEY).</Tile>
  }
  if (speed.status === 'no_data') {
    return <Tile label="Speed for real visitors" value={<span className="fact-none">Not enough data</span>}>Too few Chrome visitors to measure. Common for smaller sites.</Tile>
  }
  return <Tile label="Speed for real visitors" value={<span className="fact-none">Couldn’t load</span>}>{speed.note}</Tile>
}

function AgeTile({ result }: { result: SnapshotResult }) {
  const dates = result.facts.dates
  const registered = monthYear(dates?.registered ?? null)
  const seen = monthYear(dates?.first_seen ?? null)
  return (
    <Tile label="Site age" value={
      <dl className="age">
        <div>
          <dt>Registered{dates?.registered_domain && dates.registered_domain !== result.domain ? ` (${dates.registered_domain})` : ''}</dt>
          <dd>{registered ?? 'Unknown'}</dd>
        </div>
        <div><dt>First seen online</dt><dd>{seen ?? 'Unknown'}</dd></div>
      </dl>
    }>
      {dates?.registered && dates.first_seen && dates.first_seen < dates.registered
        ? 'The name was online before the current registration (an earlier owner, or a lapse).'
        : 'Registry record and first Wayback Machine capture.'}
    </Tile>
  )
}

/** Why there is no visit estimate: nothing checked, no Bing key, or Bing too low. */
function noVisitsReason(result: SnapshotResult): string {
  if (result.keywords_checked === 0) return 'No searches were checked.'
  if (result.keywords.every((k) => k.bing_status === 'no_key')) return 'Needs a Bing Webmaster key for search numbers.'
  return 'Too low to measure: Bing has no search numbers for these searches.'
}

export function SnapshotResults({ run, result }: { run: SnapshotRun; result: SnapshotResult }) {
  const [filter, setFilter] = useState<Filter>('all')
  const { domain, keywords, depth } = result
  const found = keywords.filter((k) => k.ranked)
  const shown = filter === 'found' ? found : filter === 'not' ? keywords.filter((k) => !k.ranked) : keywords
  const maxGroup = Math.max(1, ...result.groups.map((g) => g.count))
  const country = COUNTRY_NAMES[run.settings.gap.base.country] ?? run.settings.gap.base.country
  const link = result.facts.link
  // Any ranked search with a Bing number: then a total of 0 is a rounded estimate, not exact.
  const anyRankedVisits = keywords.some((k) => k.ranked && k.visits !== null)
  const checks = result.checks?.checks ?? []
  const tabs: [Filter, string, number][] = [
    ['all', 'All', keywords.length],
    ['found', `In top ${depth}`, found.length],
    ['not', 'Not yet', keywords.length - found.length],
  ]

  return (
    <>
      <div className="fact-tiles">
        <LinkTile result={result} />
        <PopularityTile result={result} />
        <Tile
          label="Found on Google"
          value={result.keywords_checked === 0
            ? <span className="fact-none">Not checked</span>
            : <><span className="nums">{result.keywords_found}</span><span className="fact-of"> of {result.keywords_checked}</span></>}
        >
          {result.keywords_checked === 0
            ? 'No searches were checked on Google. The details below say why.'
            : `searches its pages target are in the top ${depth} (${country}).`}
        </Tile>
        <Tile
          label="Estimated visits"
          value={result.visits === null ? <span className="fact-none">—</span> : <><span className="nums">{visitsText(result.visits, anyRankedVisits)}</span><span className="fact-of"> a month</span></>}
        >
          {result.visits === null
            ? noVisitsReason(result)
            : result.visits === 0 && !anyRankedVisits
              ? `From the ${result.visits_keywords} searches with Bing numbers: the site isn’t in the top ${depth} for them.`
              : `Rough, from the ${result.visits_keywords} searches with Bing numbers.`}
        </Tile>
        <SpeedTile result={result} />
        <AgeTile result={result} />
        <Tile
          label="Pages in sitemap"
          value={result.sitemap_files
            ? <><span className="fact-of">{result.sitemap_capped ? 'at least ' : ''}</span><span className="nums">{result.sitemap_urls.toLocaleString()}</span></>
            : <span className="fact-none">No sitemap</span>}
        >
          {!result.sitemap_files
            ? 'No sitemap was found.'
            : result.sitemap_capped
              ? `In the first ${result.sitemap_files} sitemap files; the site lists more.`
              : `In ${result.sitemap_files} sitemap file${result.sitemap_files === 1 ? '' : 's'}.`}
        </Tile>
      </div>

      {link?.status === 'ok' && link.history.length > 1 && (
        <section className="card">
          <div className="card-body">
            <div>
              <h2 className="section-title">Link score over time</h2>
              <p className="muted small">Open PageRank, 0 to 10, recomputed each month from the Common Crawl link graph. Higher means more and stronger sites link here.</p>
            </div>
            <LinkChart history={link.history} title="Link score over time" />
          </div>
        </section>
      )}

      <section className="card">
        <div className="card-body">
          <div>
            <h2 className="section-title">Where the site shows on Google</h2>
            <p className="muted small">Out of {result.keywords_checked} searches its pages target, checked on the first {depth / 10} pages of Google in {country}.</p>
          </div>
          {result.keywords_checked === 0 ? (
            <p className="muted">No searches were checked. The details below say why.</p>
          ) : (
            <ul className="group-bars">
              {result.groups.map((g) => (
                <li key={g.label}>
                  <span className="group-label">{g.low === null ? g.label.replace(/^./, (c) => c.toUpperCase()) : `Positions ${g.label.replace('-', '–')}`}</span>
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
              {domain} isn’t in the top {depth} for any of these searches yet. The table below lists them: they are the searches to work on.
            </p>
          )}
        </div>
      </section>

      {keywords.length > 0 && (
        <section className="card" id="snapshot-keywords">
          <div className="card-body">
            <div className="table-top">
              <h2 className="section-title">Searches its pages target</h2>
              <div className="tabs" role="group" aria-label="Show searches">
                {tabs.map(([id, label, count]) => (
                  <button key={id} type="button" aria-pressed={filter === id} onClick={() => setFilter(id)}>
                    {label} <span className="tab-count nums">{count}</span>
                  </button>
                ))}
              </div>
            </div>
            <div className="table-scroll">
              <table className="table snap-table">
                <thead>
                  <tr>
                    <th scope="col">Search</th>
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
                    const band = bandText(k.difficulty_band)
                    return (
                      <tr key={k.keyword}>
                        <td>
                          <div className="kw-cell">{k.keyword}</div>
                          <div className="muted small">{intentText(k.intent)}</div>
                        </td>
                        <td className="num">{k.position === null ? <span className="pos none">—</span> : <span className="pos">{k.position}</span>}</td>
                        <td className="url">{href ? <a href={href} target="_blank" rel="noopener noreferrer">{pathOf(k.url, domain)}</a> : '—'}</td>
                        <td className="num">{bingText(k)}</td>
                        <td className="num">{k.visits === null ? '—' : visitsText(k.visits, k.ranked)}</td>
                        <td>{k.difficulty_band ? <Pill tone={band.tone}>{band.label}</Pill> : <span className="muted small">Unknown</span>}</td>
                      </tr>
                    )
                  })}
                  {shown.length === 0 && <tr><td colSpan={6} className="muted">No searches in this group.</td></tr>}
                </tbody>
              </table>
            </div>
            <p className="muted small">“—” in Position means not on the first {depth / 10} pages, not “never ranks”. The page shown is the one that ranks, or the one built for the search.</p>
          </div>
        </section>
      )}

      <div className="two-up">
        <section className="card">
          <div className="card-body">
            <h2 className="section-title">Top pages</h2>
            {result.top_pages.length === 0 ? (
              <p className="muted small">No page is in the top {depth} for the searches checked.</p>
            ) : (
              <ol className="plain-list comp-list">
                {result.top_pages.map((p) => {
                  const href = safeHref(p.url)
                  return (
                    <li key={p.url}>
                      <span className="pos">{p.best_position}</span>
                      <span>
                        {href ? <a className="url" href={href} target="_blank" rel="noopener noreferrer">{pathOf(p.url, domain)}</a> : p.url}
                        <span className="muted small"> · {p.keywords.length} search{p.keywords.length === 1 ? '' : 'es'}{p.visits !== null ? ` · ${visitsText(p.visits, true)} visits` : ''}</span>
                      </span>
                    </li>
                  )
                })}
              </ol>
            )}
          </div>
        </section>

        <section className="card">
          <div className="card-body">
            <div>
              <h2 className="section-title">Competitors on Google</h2>
              <p className="muted small">Sites on page 1 for 2 or more of these searches. A suggestion: some may be platforms, not rivals.</p>
            </div>
            {result.competitors.length === 0 ? (
              <p className="muted small">No site shows up often enough to suggest.</p>
            ) : (
              <>
                <ol className="plain-list comp-list">
                  {result.competitors.map((c) => (
                    <li key={c.domain}>
                      <span className="pos">{c.best_position}</span>
                      <span><strong>{c.domain}</strong> <span className="muted small">page 1 for {c.keywords} searches, e.g. {c.examples.join(', ')}</span></span>
                    </li>
                  ))}
                </ol>
                <div>
                  <button
                    type="button"
                    className="btn"
                    onClick={() => go({ page: 'gap-new', site: domain, competitors: result.competitors.slice(0, 4).map((c) => c.domain) })}
                  >
                    Compare in Keyword Gap
                  </button>
                </div>
              </>
            )}
          </div>
        </section>
      </div>

      <section className="card">
        <div className="card-body">
          <div>
            <h2 className="section-title">Technical basics</h2>
            <p className="muted small">Checked on {result.checks?.home || result.home} against Google’s own guidance.</p>
          </div>
          {checks.length === 0 ? (
            <p className="muted small">The technical checks could not run. The details below say why.</p>
          ) : (
            <ul className="check-list">
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
          )}
        </div>
      </section>

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
