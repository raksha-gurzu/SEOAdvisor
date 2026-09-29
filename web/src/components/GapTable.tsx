import { Fragment, useMemo, useState, type ReactNode } from 'react'
import { bandText, bingText, CATEGORY_TEXT, fitText, intentText, safeHref } from '../format'
import type { GapCategory, GapRow, KeywordRanking, KeywordGapResult } from '../types'
import { DomainDot, Pill } from './ui'

export type TabId = GapCategory | 'all' | 'none'
type SortKey = 'keyword' | 'searches' | 'difficulty' | 'fit' | 'lift' | 'proof' | `pos:${number}`
const PAGE_SIZE = 25
const TABS: TabId[] = ['all', 'missing', 'weak', 'untapped', 'strong', 'shared', 'unique', 'none']

function tabLabel(tab: TabId): string {
  if (tab === 'all') return 'All'
  if (tab === 'none') return 'No site ranks'
  return CATEGORY_TEXT[tab].label
}

function inTab(row: GapRow, tab: TabId): boolean {
  if (tab === 'all') return row.categories.length > 0
  if (tab === 'none') return row.categories.length === 0
  return row.categories.includes(tab)
}

/** Sort value; null always sorts last whatever the direction. */
function value(row: GapRow, key: SortKey, domains: string[]): number | string | null {
  if (key.startsWith('pos:')) return row.positions[domains[Number(key.slice(4))]]
  switch (key) {
    case 'keyword': return row.keyword
    case 'searches': return row.bing_status === 'measured' ? row.bing_searches : null
    case 'difficulty': return row.difficulty
    case 'fit': return row.business_fit
    case 'lift': return row.traffic_lift
    default: return row.proof
  }
}

interface Filters {
  include: string
  exclude: string
  intent: string
  band: string
  minCompetitors: number
  yours: 'any' | 'page1' | 'page2plus' | 'none'
  measuredOnly: boolean
}
const NO_FILTERS: Filters = { include: '', exclude: '', intent: '', band: '', minCompetitors: 0, yours: 'any', measuredOnly: false }

function passes(row: GapRow, f: Filters, domains: string[]): boolean {
  const kw = row.keyword.toLowerCase()
  if (f.include && !kw.includes(f.include.toLowerCase().trim())) return false
  const excluded = f.exclude.split(',').map((w) => w.trim().toLowerCase()).filter(Boolean)
  if (excluded.some((w) => kw.includes(w))) return false
  if (f.intent && row.intent !== f.intent) return false
  if (f.band && row.difficulty_band !== f.band) return false
  const ranking = domains.slice(1).filter((d) => row.positions[d] !== null).length
  if (ranking < f.minCompetitors) return false
  const ours = row.positions[domains[0]]
  if (f.yours === 'page1' && !(ours !== null && ours <= 10)) return false
  if (f.yours === 'page2plus' && !(ours !== null && ours > 10)) return false
  if (f.yours === 'none' && ours !== null) return false
  if (f.measuredOnly && row.bing_status !== 'measured') return false
  return true
}

export function GapTable({
  result,
  rankings,
  tab,
  onTab,
}: {
  result: KeywordGapResult
  rankings: KeywordRanking[]
  tab: TabId
  onTab: (tab: TabId) => void
}) {
  const { domains } = result
  const [filters, setFilters] = useState<Filters>(NO_FILTERS)
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: 'proof', desc: true })
  // Page and open row belong to the tab they were set on: when the tab changes (here or from
  // the overlap bars), the table starts on page 1 with nothing open, with no extra render.
  const [paging, setPaging] = useState<{ tab: TabId; page: number; open: string | null }>({ tab, page: 0, open: null })
  const page = paging.tab === tab ? paging.page : 0
  const open = paging.tab === tab ? paging.open : null
  const setPage = (next: number) => setPaging({ tab, page: next, open: null })
  const setOpen = (keyword: string | null) => setPaging({ tab, page, open: keyword })
  const byKeyword = useMemo(() => new Map(rankings.map((r) => [r.keyword, r])), [rankings])
  const counts = useMemo(
    () => Object.fromEntries(TABS.map((t) => [t, result.rows.filter((r) => inTab(r, t)).length])) as Record<TabId, number>,
    [result.rows],
  )

  const rows = useMemo(() => {
    const out = result.rows.filter((r) => inTab(r, tab) && passes(r, filters, domains))
    return out.sort((a, b) => {
      const va = value(a, sort.key, domains)
      const vb = value(b, sort.key, domains)
      if (va === null || vb === null) return va === vb ? a.keyword.localeCompare(b.keyword) : va === null ? 1 : -1
      const cmp = typeof va === 'string' ? va.localeCompare(vb as string) : (va as number) - (vb as number)
      return (sort.desc ? -cmp : cmp) || a.keyword.localeCompare(b.keyword)
    })
  }, [result.rows, tab, filters, sort, domains])

  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE))
  const shown = rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const filtered = JSON.stringify(filters) !== JSON.stringify(NO_FILTERS)
  const update = (patch: Partial<Filters>) => { setFilters({ ...filters, ...patch }); setPage(0) }

  function header(key: SortKey, label: ReactNode, className = '') {
    const active = sort.key === key
    const firstDesc = key !== 'keyword' && !key.startsWith('pos:') && key !== 'difficulty'
    return (
      <th key={key} className={className} aria-sort={active ? (sort.desc ? 'descending' : 'ascending') : 'none'}>
        <button
          type="button"
          className="sort"
          onClick={() => { setSort(active ? { key, desc: !sort.desc } : { key, desc: firstDesc }); setPage(0) }}
        >
          {label}
          <span aria-hidden="true" className="sort-arrow">{active ? (sort.desc ? '▾' : '▴') : ''}</span>
        </button>
      </th>
    )
  }

  return (
    <section className="card" id="keyword-table">
      <div className="card-body">
        <div className="table-top">
          <h2 className="section-title">All keywords checked</h2>
          <span className="muted small nums">{rows.length} shown</span>
        </div>

        <div className="tabs scroll-x" role="tablist" aria-label="Keyword groups">
          {TABS.map((t) => (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={tab === t}
              title={t in CATEGORY_TEXT ? CATEGORY_TEXT[t].rule : t === 'none' ? 'None of the sites is on the first pages checked' : 'Keywords where at least one site ranks'}
              id={`gap-tab-${t}`}
              onClick={() => onTab(t)}
            >
              {tabLabel(t)} <span className="nums tab-count">{counts[t]}</span>
            </button>
          ))}
        </div>

        <div className="filters">
          <input className="input" type="search" aria-label="Keywords containing" placeholder="Contains…" value={filters.include} onChange={(e) => update({ include: e.target.value })} />
          <input className="input" type="search" aria-label="Leave out keywords containing (comma-separated)" placeholder="Leave out… (a, b)" value={filters.exclude} onChange={(e) => update({ exclude: e.target.value })} />
          <select className="select" aria-label="Your position" value={filters.yours} onChange={(e) => update({ yours: e.target.value as Filters['yours'] })}>
            <option value="any">Your position: any</option>
            <option value="page1">You’re on page 1</option>
            <option value="page2plus">You’re on page 2 or lower</option>
            <option value="none">You’re not found</option>
          </select>
          <select className="select" aria-label="Competitors ranking" value={filters.minCompetitors} onChange={(e) => update({ minCompetitors: Number(e.target.value) })}>
            <option value={0}>Competitors ranking: any</option>
            {domains.slice(1).map((_, i) => <option key={i} value={i + 1}>At least {i + 1} competitor{i ? 's' : ''}</option>)}
          </select>
          <select className="select" aria-label="Intent" value={filters.intent} onChange={(e) => update({ intent: e.target.value })}>
            <option value="">Intent: any</option>
            <option value="commercial">Comparing options</option>
            <option value="informational">Learning</option>
            <option value="transactional">Ready to act</option>
            <option value="unknown">Unclear</option>
          </select>
          <select className="select" aria-label="Difficulty" value={filters.band} onChange={(e) => update({ band: e.target.value })}>
            <option value="">Difficulty: any</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
          <label className="check">
            <input type="checkbox" checked={filters.measuredOnly} onChange={(e) => update({ measuredOnly: e.target.checked })} />
            Only with Bing numbers
          </label>
          {filtered && <button type="button" className="link" onClick={() => { setFilters(NO_FILTERS); setPage(0) }}>Clear filters</button>}
        </div>

        <div className="table-scroll">
          <table className="table gap-table">
            <thead>
              <tr>
                {header('keyword', 'Keyword', 'kw-col')}
                {domains.map((d, i) => header(`pos:${i}`, <><DomainDot index={i} /><span className="dom-head">{i === 0 ? 'You' : d}</span></>, 'num'))}
                {header('searches', 'Bing searches', 'num')}
                {header('difficulty', 'Difficulty')}
                {header('fit', 'Fit')}
                {header('lift', 'Visits lift', 'num')}
              </tr>
            </thead>
            <tbody>
              {shown.length === 0 && (
                <tr><td colSpan={domains.length + 5} className="muted">No keywords match. {filtered && 'Try clearing the filters.'}</td></tr>
              )}
              {shown.map((row) => {
                const ranked = domains.map((d) => row.positions[d]).filter((p): p is number => p !== null)
                const best = ranked.length ? Math.min(...ranked) : null
                const isOpen = open === row.keyword
                const band = bandText(row.difficulty_band)
                return (
                  <Fragment key={row.keyword}>
                    <tr className={isOpen ? 'open' : ''}>
                      <td className="kw-col">
                        <button type="button" className="kw-toggle" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : row.keyword)}>
                          <span aria-hidden="true" className="caret">{isOpen ? '▾' : '▸'}</span>
                          <span className="kw">{row.keyword}</span>
                        </button>
                        <div className="kw-meta">
                          {row.categories.map((c) => <span key={c} className="tag">{CATEGORY_TEXT[c].label}</span>)}
                          {row.cluster !== row.keyword && <span className="muted small">group: {row.cluster}</span>}
                        </div>
                      </td>
                      {domains.map((d) => {
                        const pos = row.positions[d]
                        const href = safeHref(row.urls[d])
                        if (pos === null) return <td key={d} className="num"><span className="pos none" title="Not on the pages checked">—</span></td>
                        const isBest = pos === best
                        const chip = (
                          <span className={`pos ${isBest ? 'best' : ''}`}>
                            {pos}
                            {isBest && <span className="sr-only"> (best position)</span>}
                          </span>
                        )
                        return (
                          <td key={d} className="num">
                            {href ? <a href={href} target="_blank" rel="noopener noreferrer" title={`${d} #${pos}${isBest ? ' (best)' : ''}: ${row.urls[d]}`}>{chip}</a> : chip}
                          </td>
                        )
                      })}
                      <td className="num">
                        <span className={row.bing_status === 'measured' ? '' : 'muted small'}>{bingText(row)}</span>
                      </td>
                      <td>{row.difficulty_band ? <Pill tone={band.tone}>{band.label}</Pill> : <span className="muted small">Unknown</span>}</td>
                      <td className="small">{fitText(row.business_fit)}</td>
                      <td className="num">{row.traffic_lift ? `+${row.traffic_lift.toLocaleString()}` : <span className="muted">—</span>}</td>
                    </tr>
                    {isOpen && (
                      <tr className="detail-row">
                        <td colSpan={domains.length + 5}>
                          <RowDetail row={row} ranking={byKeyword.get(row.keyword)} domains={domains} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>

        {pages > 1 && (
          <div className="pager">
            <button type="button" className="btn ghost" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
            <span className="muted small nums">Page {page + 1} of {pages}</span>
            <button type="button" className="btn ghost" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>Next</button>
          </div>
        )}
      </div>
    </section>
  )
}

function RowDetail({ row, ranking, domains }: { row: GapRow; ranking: KeywordRanking | undefined; domains: string[] }) {
  const ownerIndex = (domain: string) =>
    domains.findIndex((d) => domain === d || domain.endsWith(`.${d}`) || domain === `www.${d}`)
  const targets = Object.entries(row.pages)
  return (
    <div className="row-detail">
      <div>
        <h3 className="detail-title">Google results checked</h3>
        {ranking && ranking.results.length ? (
          <ol className="serp-list">
            {ranking.results.map((item) => {
              const owner = ownerIndex(item.domain)
              const href = safeHref(item.url)
              return (
                <li key={item.url} className={owner >= 0 ? 'ours' : ''}>
                  <span className="serp-rank nums">{item.rank}</span>
                  {owner >= 0 ? <DomainDot index={owner} /> : <span className="dot-space" />}
                  <div className="serp-item">
                    {href ? <a href={href} target="_blank" rel="noopener noreferrer">{item.title || item.url}</a> : <span>{item.title || item.url}</span>}
                    <span className="muted small">{item.domain}</span>
                  </div>
                </li>
              )
            })}
          </ol>
        ) : (
          <p className="muted small">No results were returned for this keyword.</p>
        )}
      </div>
      <div className="detail-side">
        <div>
          <h3 className="detail-title">Why people search this</h3>
          <p className="small">{intentText(row.intent)} (from the kinds of pages Google shows).</p>
        </div>
        {row.google_estimate !== null && (
          <div>
            <h3 className="detail-title">Estimated visits a month</h3>
            <ul className="plain-list">
              {domains.map((d, i) => (
                <li key={d}><DomainDot index={i} />{d}<span className="nums">{(row.visits[d] ?? 0).toLocaleString()}</span></li>
              ))}
            </ul>
            <p className="muted small">From about {row.google_estimate.toLocaleString()} Google searches a month (rough estimate).</p>
          </div>
        )}
        {targets.length > 0 && (
          <div>
            <h3 className="detail-title">Pages built for this keyword</h3>
            <ul className="plain-list">
              {targets.map(([d, url]) => {
                const href = safeHref(url)
                return <li key={d}><DomainDot index={Math.max(0, domains.indexOf(d))} />{href ? <a className="url" href={href} target="_blank" rel="noopener noreferrer">{url}</a> : url}</li>
              })}
            </ul>
          </div>
        )}
        {ranking && ranking.people_also_ask.length > 0 && (
          <div>
            <h3 className="detail-title">People also ask</h3>
            <ul className="plain-list">{ranking.people_also_ask.map((q, i) => <li key={`${i}-${q}`}>{q}</li>)}</ul>
          </div>
        )}
        {ranking && ranking.related_searches.length > 0 && (
          <div>
            <h3 className="detail-title">Related searches</h3>
            <div className="phrase-facts">{ranking.related_searches.map((q, i) => <Pill key={`${i}-${q}`}>{q}</Pill>)}</div>
          </div>
        )}
      </div>
    </div>
  )
}
