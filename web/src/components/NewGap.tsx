import { useEffect, useState } from 'react'
import { api } from '../api'
import { COUNTRY_NAMES, maxCredits, siteHost } from '../format'
import { go } from '../router'
import type { GapDefaults, GapSettingsIn, Health } from '../types'
import { Alert, DomainDot } from './ui'

const KEY_NAMES: Record<string, string> = { deepseek: 'DEEPSEEK_API_KEY', serper: 'SERPER_API_KEY' }
const DEPTH_LABELS: Record<number, string> = {
  10: 'First page of Google',
  20: 'First 2 pages (recommended)',
  30: 'First 3 pages',
  50: 'First 5 pages',
}

type Field = 'site' | number

/** blog.x.com and x.com overlap: one site's results would count for the other. */
function overlaps(a: string, b: string): boolean {
  return a === b || a.endsWith(`.${b}`) || b.endsWith(`.${a}`)
}

/** A problem with the addresses, before anything is sent (the server checks again). A field
 *  is only called "not an address" once the user has left it (`shown`), not mid-typing. */
function formProblem(site: string, competitors: string[], shown: (f: Field) => boolean): string | null {
  const ours = siteHost(site)
  if (site.trim() && !ours && shown('site')) return `“${site.trim()}” isn’t a website address. Try something like example.com.`
  const entries = competitors.map((c, i) => ({ c: c.trim(), i, host: siteHost(c) })).filter((e) => e.c)
  const bad = entries.find((e) => !e.host && shown(e.i))
  if (bad) return `“${bad.c}” isn’t a website address.`
  const hosts = entries.map((e) => e.host).filter((h): h is string => !!h)
  const clash = ours ? hosts.find((h) => overlaps(h, ours)) : undefined
  if (ours && clash) return clash === ours ? `${ours} is your own site. Remove it from the competitors.` : `${clash} is part of ${ours} (or the other way round). Compare separate sites.`
  if (new Set(hosts).size < hosts.length) return 'The same competitor is listed twice.'
  return null
}

export function NewGap({
  health,
  onStarted,
  prefill,
}: {
  health: Health | null
  onStarted: () => void
  prefill?: { site?: string; competitors?: string[] }
}) {
  const [defaults, setDefaults] = useState<GapDefaults | null>(null)
  const [settings, setSettings] = useState<GapSettingsIn | null>(null)
  const [site, setSite] = useState(prefill?.site ?? '')
  const [competitors, setCompetitors] = useState<string[]>(
    prefill?.competitors?.length ? prefill.competitors : ['', ''],
  )
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [left, setLeft] = useState<Set<Field>>(new Set())  // fields the user has moved out of
  const leave = (f: Field) => setLeft((prev) => new Set(prev).add(f))

  useEffect(() => {
    api.gapDefaults()
      .then((d) => {
        setDefaults(d)
        setSettings(d.settings)
        setCompetitors((prev) => prev.slice(0, d.max_competitors))  // a prefill can list more
      })
      .catch(() => setError('Can’t reach the server. Start the backend, then reload this page.'))
  }, [])

  const max = defaults?.max_competitors ?? 4
  const filled = competitors.filter((c) => c.trim())
  const problem = formProblem(site, competitors, (f) => left.has(f))
  const blocking = formProblem(site, competitors, () => true)
  const missing = health?.missing_for_keyword_gap ?? []
  const canStart = !!settings && !!siteHost(site) && filled.length > 0 && !blocking && !busy && missing.length === 0
  const update = (patch: Partial<GapSettingsIn>) => settings && setSettings({ ...settings, ...patch })
  const setCompetitor = (i: number, value: string) => setCompetitors(competitors.map((c, j) => (j === i ? value : c)))

  async function start() {
    if (!settings) return
    setBusy(true)
    setError(null)
    try {
      const { id } = await api.startGap(site.trim(), filled.map((c) => c.trim()), settings)
      onStarted()
      go({ page: 'gap', id })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <header className="page-head">
        <h1>Find your keyword gaps</h1>
        <p>See which Google searches your competitors show up for and you don’t, and which ones to target first.</p>
      </header>

      {missing.length > 0 && (
        <Alert tone="bad">
          <strong>One more setup step.</strong> Add {missing.map((k, i) => (
            <span key={k}>{i > 0 && ' and '}<code>{KEY_NAMES[k] ?? k}</code></span>
          ))} to the <code>.env</code> file, then reload this page.
        </Alert>
      )}

      <section className="card">
        <div className="card-body">
          <div className="field">
            <label className="field-label" htmlFor="gap-site">Your website</label>
            <div className="domain-row">
              <DomainDot index={0} />
              <input
                id="gap-site"
                className="input"
                type="text"
                inputMode="url"
                autoComplete="url"
                placeholder="emitii.com"
                value={site}
                onChange={(e) => setSite(e.target.value)}
                onBlur={() => leave('site')}
              />
            </div>
            <span className="field-hint">The whole site is compared, so the homepage address is enough.</span>
          </div>

          <fieldset className="field fieldset">
            <legend className="field-label">Competitors</legend>
            <div className="domain-list">
              {competitors.map((c, i) => (
                <div className="domain-row" key={i}>
                  <DomainDot index={i + 1} />
                  <input
                    className="input"
                    type="text"
                    inputMode="url"
                    aria-label={`Competitor ${i + 1}`}
                    placeholder={['moxo.com', 'clinked.com', 'copilot.com', 'huddle.com'][i]}
                    value={c}
                    onChange={(e) => setCompetitor(i, e.target.value)}
                    onBlur={() => leave(i)}
                  />
                  {competitors.length > 1 && (
                    <button
                      type="button"
                      className="btn ghost"
                      aria-label={`Remove competitor ${i + 1}`}
                      onClick={() => {
                        setCompetitors(competitors.filter((_, j) => j !== i))
                        setLeft((prev) => new Set([...prev].filter((f) => f === 'site')))  // rows shift
                      }}
                    >
                      Remove
                    </button>
                  )}
                </div>
              ))}
            </div>
            {competitors.length < max && (
              <div>
                <button type="button" className="link" onClick={() => setCompetitors([...competitors, ''])}>
                  + Add a competitor
                </button>
              </div>
            )}
            <span className="field-hint">
              Up to {max}. Pick sites that sell what you sell and already get visitors from Google.
            </span>
          </fieldset>

          {problem && <Alert tone="warn">{problem}</Alert>}

          <hr className="divider" />

          {settings && defaults && (
            <>
              <div className="field">
                <label className="field-label" htmlFor="gap-country">Where are your customers?</label>
                <select id="gap-country" className="select" value={settings.country} onChange={(e) => update({ country: e.target.value })}>
                  {defaults.countries.map((c) => <option key={c} value={c}>{COUNTRY_NAMES[c] ?? c}</option>)}
                </select>
                <span className="field-hint">We check the Google results people see in this country.</span>
              </div>

              <details className="more">
                <summary>More options</summary>
                <div className="more-body two-col">
                  <div className="field">
                    <label className="field-label" htmlFor="gap-depth">How deep to look</label>
                    <select id="gap-depth" className="select" value={settings.depth} onChange={(e) => update({ depth: Number(e.target.value) })}>
                      {defaults.depths.map((d) => <option key={d} value={d}>{DEPTH_LABELS[d] ?? `First ${d / 10} pages`}</option>)}
                    </select>
                  </div>
                  <div className="field">
                    <label className="field-label" htmlFor="gap-keywords">Keywords to check</label>
                    <select id="gap-keywords" className="select" value={settings.keywords} onChange={(e) => update({ keywords: Number(e.target.value) })}>
                      {defaults.keyword_options.map((k) => <option key={k} value={k}>Up to {k}</option>)}
                    </select>
                  </div>
                </div>
              </details>
            </>
          )}
        </div>

        <div className="card-foot">
          <span className="cta-note">
            {error ? (
              <span className="text-bad">{error}</span>
            ) : settings ? (
              <span className="credit-note">
                About 1 to 3 minutes. Uses up to {maxCredits(settings.keywords, settings.depth)} Serper credits
                (fewer when results are cached today) and under a cent of AI.
              </span>
            ) : null}
          </span>
          <button type="button" className="btn primary large" disabled={!canStart} onClick={start}>
            {busy ? 'Starting…' : 'Find keyword gaps'}
          </button>
        </div>
      </section>
    </div>
  )
}
