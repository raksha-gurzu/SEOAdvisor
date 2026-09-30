import { useState } from 'react'
import { bandText, CATEGORY_TEXT, fitText, safeHref } from '../format'
import { go } from '../router'
import type { GapCategory, GapRun, KeywordGapResult } from '../types'
import { GapTable, type TabId } from './GapTable'
import { Disclosure, DomainDot } from './ui'

const OVERLAP: GapCategory[] = ['missing', 'weak', 'untapped', 'strong', 'shared', 'unique']

export function GapResults({ run, result }: { run: GapRun; result: KeywordGapResult }) {
  const [tab, setTab] = useState<TabId>('all')
  const { domains } = result
  const pagesRead = Object.fromEntries(run.sites.map((s) => [s.domain, s.pages.length]))
  const maxCount = Math.max(1, ...OVERLAP.map((c) => result.counts[c]))
  const pagesChecked = Math.ceil(run.settings.depth / 10)
  const showTab = (t: TabId) => {
    setTab(t)
    const still = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    document.getElementById('keyword-table')?.scrollIntoView({ behavior: still ? 'auto' : 'smooth', block: 'start' })
    // Keyboard users land on the chosen tab, not back on the bar they clicked.
    window.setTimeout(() => document.getElementById(`gap-tab-${t}`)?.focus({ preventScroll: true }), 0)
  }

  return (
    <>
      <div className="site-tiles">
        {domains.map((d, i) => {
          const found = result.rows.filter((r) => r.positions[d] !== null)
          const page1 = found.filter((r) => (r.positions[d] ?? 99) <= 10).length
          const visits = result.rows.reduce((sum, r) => sum + (r.visits[d] ?? 0), 0)
          // 0 is not shown as "~0": it would read as "no traffic" when the truth is that Bing has
          // numbers only for keywords this site isn't found for (plan D11).
          const known = visits > 0
          return (
            <section key={d} className={`card kpi site-kpi ${i === 0 ? 'you' : ''}`}>
              <h2 className="site-name"><DomainDot index={i} /><span className="site-domain">{d}</span>{i === 0 && <span className="chip brand">You</span>}</h2>
              <div className="kpi-value">
                <span className="nums">{found.length}</span><span className="kpi-of"> / {result.rows.length}</span>
              </div>
              <div className="kpi-sub">on the first {pagesChecked} page{pagesChecked === 1 ? '' : 's'} of Google</div>
              <div className="kpi-sub kpi-facts">
                <span><span className="nums">{page1}</span> on page 1</span>
                <span title={known ? 'Rough estimate from Bing numbers' : 'Not enough data: Bing has no numbers for the keywords this site is found for'}>
                  visits <span className="nums">{known ? `~${visits.toLocaleString()}/mo` : '—'}</span>
                </span>
                <span><span className="nums">{pagesRead[d] ?? 0}</span> pages read</span>
              </div>
            </section>
          )
        })}
      </div>

      <div className="snap-grid-2">
      <section className="card">
          <div className="card-body">
            <div>
              <h2 className="section-title">Top keywords to add</h2>
              <p className="muted small">
                Keywords your competitors show up for and you don’t (or rank lower). Ordered by how well they fit your business, then by how
                high competitors rank for them, then by how easy the results look.
              </p>
            </div>
            {result.top.length === 0 ? (
              <p className="muted">No keyword to add fits your business well enough. Try competitors that sell what you sell.</p>
            ) : (
              <ol className="opportunities">
                {result.top.map((o, i) => {
                  const band = bandText(o.difficulty_band)
                  const href = safeHref(o.best_url)
                  return (
                    <li key={o.keyword} className="opportunity">
                      <span className="opp-num nums">{i + 1}</span>
                      <div className="opp-body">
                        <div className="opp-top">
                          <strong className="opp-kw">{o.keyword}</strong>
                          <span className="chip">{CATEGORY_TEXT[o.category].label}</span>
                          <span className="chip brand">{fitText(o.business_fit)}</span>
                          {o.difficulty_band && <span className={`chip ${band.tone}`}>{o.difficulty !== null && <span className="nums">{o.difficulty}</span>} {band.label} difficulty</span>}
                          {!!o.traffic_lift && <span className="chip good">+{o.traffic_lift.toLocaleString()} visits/mo</span>}
                        </div>
                        <p className="small">{o.reason}</p>
                        {href && (
                          <a className="small url" href={href} target="_blank" rel="noopener noreferrer">
                            See {o.best_competitor}’s page (#{o.best_position})
                          </a>
                        )}
                      </div>
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
              <h2 className="section-title">How your keywords compare</h2>
              <p className="muted small">Out of {result.rows.length} keywords checked on Google. Groups overlap, as in Semrush: every Missing keyword is also Untapped. Click a bar to see its keywords.</p>
            </div>
            <ul className="overlap-bars">
              {OVERLAP.map((c) => (
                <li key={c}>
                  <button type="button" className="overlap-row" onClick={() => showTab(c)} title={CATEGORY_TEXT[c].rule}>
                    <span className="overlap-label">
                      <strong>{CATEGORY_TEXT[c].label}</strong>
                      <span className="muted small">{CATEGORY_TEXT[c].rule}</span>
                    </span>
                    <span className="overlap-track">
                      <span className="overlap-bar" style={{ width: `${(result.counts[c] / maxCount) * 100}%` }} />
                      <span className="overlap-value nums">{result.counts[c]}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            {result.unranked.length > 0 && (
              <p className="muted small">
                {result.unranked.length} more keyword{result.unranked.length === 1 ? '' : 's'} had none of the sites on the first {Math.ceil(run.settings.depth / 10)} page{run.settings.depth > 10 ? 's' : ''}.{' '}
                <button type="button" className="link" onClick={() => showTab('none')}>Show them</button>
              </p>
            )}
          </div>
        </section>
      </div>

      <GapTable result={result} rankings={run.ranks?.rankings ?? []} tab={tab} onTab={setTab} />

      {(result.suggested_competitors ?? []).length > 0 && (
        <section className="card">
          <div className="card-body">
            <div>
              <h2 className="section-title">Sites Google shows for your keywords</h2>
              <p className="muted small">
                These sites are on page 1 for the searches that fit your business, and you did not enter them. Forums, videos and big
                platforms are left out. They may be better competitors to compare with.
              </p>
            </div>
            <ol className="plain-list comp-list">
              {result.suggested_competitors.map((c) => (
                <li key={c.domain}>
                  <span className="pos">{c.best_position}</span>
                  <span><strong>{c.domain}</strong> <span className="muted small">on page 1 for {c.keywords} of your keywords, e.g. {c.examples.join(', ')}</span></span>
                </li>
              ))}
            </ol>
            <div>
              <button
                type="button"
                className="btn"
                onClick={() => go({ page: 'gap-new', site: domains[0], competitors: result.suggested_competitors.slice(0, 4).map((c) => c.domain) })}
              >
                Compare with these
              </button>
            </div>
          </div>
        </section>
      )}

      {result.competitors.length > 0 && (
        <div className="competitor-panels">
          {result.competitors.map((p) => {
            const i = domains.indexOf(p.domain)
            return (
              <section key={p.domain} className="card">
                <div className="card-body">
                  <div className="site-name"><DomainDot index={i} /><span>{p.domain}</span></div>
                  <p className="muted small nums">
                    On the first pages for {p.keywords_ranked} of {result.rows.length} keywords
                    {p.visits_known > 0 ? ` · ~${p.visits_known.toLocaleString()} visits a month (estimated)` : ''}
                  </p>
                  {p.top.length === 0 ? (
                    <p className="muted small">None of the keywords checked.</p>
                  ) : (
                    <ol className="plain-list comp-list">
                      {p.top.map((k) => {
                        const href = safeHref(k.url)
                        return (
                          <li key={k.keyword}>
                            <span className="pos">{k.position}</span>
                            {href ? <a href={href} target="_blank" rel="noopener noreferrer">{k.keyword}</a> : k.keyword}
                            {k.visits !== null && <span className="muted small nums">~{k.visits} visits</span>}
                          </li>
                        )
                      })}
                    </ol>
                  )}
                </div>
              </section>
            )
          })}
        </div>
      )}

      <section className="card">
        <div className="card-body method">
          <h2 className="section-title">How we calculate this</h2>
          <ul className="plain-list">
            <li>We read up to {run.settings.pages_per_site} pages of each site, found the searches each page is built for, and checked {run.ranks?.rankings.length ?? result.rows.length} of them on Google{run.ranks && run.ranks.not_checked.length > 0 ? ` (${run.ranks.not_checked.length} more could not be checked)` : ''}. Paid tools like Semrush check millions of keywords, so this finds the main gaps, not every keyword.</li>
            <li>Positions come from the first {Math.ceil(run.settings.depth / 10)} page{run.settings.depth > 10 ? 's' : ''} of Google in one check. Google moves results a few places between searches, and “—” means “not on those pages”, not “never ranks”.</li>
            <li>Search numbers come from Bing. Bing has numbers for only some keywords; the others show “Too low”. Google searches ≈ Bing × {run.google_per_bing ? run.google_per_bing.toFixed(1) : '—'} (share of searches in this country{run.shares_source ? `: ${run.shares_source}` : ''}), a rough estimate.</li>
            <li>Visits = Google searches × the share of clicks at that position ({run.ctr_source}). Even paid tools are off by about 50%; use visits to compare keywords, not as a forecast. AI Overviews aren’t detected and can halve clicks.</li>
            <li>Difficulty comes from how popular the sites in the top 10 are (Tranco list), shown as Low, Medium or High. Competitor brand names are left out{result.brand_keywords.length ? ` (${result.brand_keywords.length} hidden)` : ''}.</li>
          </ul>
          {(run.notes.length > 0 || (run.discovery?.ours_no_demand.length ?? 0) > 0) && (
            <Disclosure summary="Details from this analysis">
              {(run.discovery?.ours_no_demand.length ?? 0) > 0 && (
                <p className="small">
                  <strong>Your pages target searches nobody makes:</strong> {run.discovery!.ours_no_demand.join(', ')}. Consider wording people actually search.
                </p>
              )}
              <ul className="plain-list small">{run.notes.map((n, i) => <li key={`${i}-${n}`}>{n}</li>)}</ul>
            </Disclosure>
          )}
        </div>
      </section>
    </>
  )
}
