import { useEffect, useState, type FormEvent } from 'react'
import { api } from '../api'
import { EXAMPLE_PAGE } from '../example'
import { COUNTRY_NAMES, hostOf, wordCount } from '../format'
import { go } from '../router'
import type { Defaults, Health, RunSettings, SiteStrength } from '../types'
import { Alert, GlobeIcon, TextIcon } from './ui'

type Source = 'website' | 'text'

const STRENGTHS: { value: SiteStrength; label: string; hint: string }[] = [
  { value: 'new', label: 'New', hint: 'Launched recently or few other sites link to it' },
  { value: 'growing', label: 'Growing', hint: 'Some regular visitors and links' },
  { value: 'established', label: 'Established', hint: 'Well known, many sites link to it' },
]
const KEY_NAMES: Record<string, string> = { deepseek: 'DEEPSEEK_API_KEY', gemini: 'GEMINI_API_KEY' }

export function NewRun({ health, onStarted }: { health: Health | null; onStarted: () => void }) {
  const [source, setSource] = useState<Source>('website')
  const [defaults, setDefaults] = useState<Defaults | null>(null)
  const [settings, setSettings] = useState<RunSettings | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Website option
  const [url, setUrl] = useState('')
  const [fetching, setFetching] = useState(false)
  const [fetched, setFetched] = useState<{ url: string; text: string } | null>(null)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [reviewOpen, setReviewOpen] = useState(false)

  // Paste option
  const [pasted, setPasted] = useState('')

  useEffect(() => {
    api.defaults()
      .then((d) => { setDefaults(d); setSettings(d.settings) })
      .catch(() => setError('Can’t reach the server. Start the backend, then reload this page.'))
  }, [])

  const text = source === 'website' ? fetched?.text ?? '' : pasted
  const words = wordCount(text)
  const minWords = defaults?.min_words ?? 50
  const missing = health?.missing_for_free_mode ?? []
  const canStart = !!settings && words >= minWords && !busy && missing.length === 0
  const update = (patch: Partial<RunSettings>) => settings && setSettings({ ...settings, ...patch })

  async function fetchPage(e: FormEvent) {
    e.preventDefault()
    if (!url.trim()) return
    setFetching(true)
    setFetchError(null)
    setFetched(null)
    try {
      const page = await api.extract(url)
      setFetched({ url: page.url, text: page.text })
      setReviewOpen(false)
    } catch (err) {
      setFetchError((err as Error).message)
    } finally {
      setFetching(false)
    }
  }

  async function start() {
    if (!settings) return
    setBusy(true)
    setError(null)
    try {
      const { id } = await api.startRun(text, settings, source === 'website' ? fetched?.url ?? null : null)
      onStarted()
      go({ page: 'run', id })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <header className="page-head">
        <h1>Create an SEO brief</h1>
        <p>Find the Google searches your page can win, and exactly what to change on it to get there.</p>
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
            <span className="field-label">What should we analyse?</span>
            <div className="source-tabs" role="tablist" aria-label="Page source">
              <button type="button" role="tab" id="tab-website" aria-selected={source === 'website'} className="source-tab" onClick={() => setSource('website')}>
                <GlobeIcon />
                <div>
                  <strong>A live website</strong>
                  <span>We read the page for you</span>
                </div>
              </button>
              <button type="button" role="tab" id="tab-text" aria-selected={source === 'text'} className="source-tab" onClick={() => setSource('text')}>
                <TextIcon />
                <div>
                  <strong>Text I paste</strong>
                  <span>For a product that isn’t live yet</span>
                </div>
              </button>
            </div>
          </div>

          {source === 'website' ? (
            <div className="field" role="tabpanel" aria-labelledby="tab-website">
              <label className="field-label" htmlFor="page-url">Page address</label>
              <form className="url-row" onSubmit={fetchPage}>
                <input
                  id="page-url"
                  className="input"
                  type="text"
                  inputMode="url"
                  autoComplete="url"
                  placeholder="emitii.com"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                />
                <button type="submit" className="btn" disabled={!url.trim() || fetching}>
                  {fetching ? 'Reading page…' : 'Read page'}
                </button>
              </form>
              {!fetched && !fetchError && (
                <span className="field-hint">Use the exact page you want to rank, such as your homepage or a product page.</span>
              )}
              {fetchError && <Alert tone="bad">{fetchError}</Alert>}
              {fetched && (
                <>
                  <div className="fetched">
                    <span className="text-good" aria-hidden="true">✓</span>
                    <span>Found <strong>{wordCount(fetched.text).toLocaleString()} words</strong> on {hostOf(fetched.url)}</span>
                    <button type="button" className="link" onClick={() => setReviewOpen(!reviewOpen)} aria-expanded={reviewOpen}>
                      {reviewOpen ? 'Hide text' : 'Review text'}
                    </button>
                  </div>
                  {reviewOpen && (
                    <div className="field">
                      <textarea
                        id="fetched-text"
                        className="textarea"
                        aria-label="Text read from the page"
                        value={fetched.text}
                        onChange={(e) => setFetched({ ...fetched, text: e.target.value })}
                      />
                      <span className="field-hint">
                        Delete anything visitors wouldn’t read as page copy, like menu labels or sample text inside product screenshots.
                      </span>
                    </div>
                  )}
                </>
              )}
            </div>
          ) : (
            <div className="field" role="tabpanel" aria-labelledby="tab-text">
              <label className="field-label" htmlFor="page-text">Page text</label>
              <textarea
                id="page-text"
                className="textarea"
                value={pasted}
                onChange={(e) => setPasted(e.target.value)}
                placeholder="Paste the copy you plan to publish: headline, what the product does, features, pricing, FAQs…"
              />
              <div className="two-col">
                <span className="field-hint">
                  {pasted ? null : <>No copy yet? <button type="button" className="link" onClick={() => setPasted(EXAMPLE_PAGE)}>Try an example</button></>}
                </span>
                <span className={`word-count ${words > 0 && words < minWords ? 'text-bad' : ''}`}>
                  {words.toLocaleString()} words{words > 0 && words < minWords ? ` · at least ${minWords} needed` : ''}
                </span>
              </div>
            </div>
          )}

          <hr className="divider" />

          {settings && defaults && (
            <>
              <div className="field">
                <label className="field-label" htmlFor="country">Where are your customers?</label>
                <select id="country" className="select" value={settings.country} onChange={(e) => update({ country: e.target.value })}>
                  {defaults.countries.map((c) => <option key={c} value={c}>{COUNTRY_NAMES[c] ?? c}</option>)}
                </select>
                <span className="field-hint">We study the Google results people see in this country.</span>
              </div>

              <fieldset className="field fieldset">
                <legend className="field-label">How established is your website?</legend>
                <div className="strength-options">
                  {STRENGTHS.map((s) => (
                    <label key={s.value} className="option-card">
                      <input type="radio" name="strength" id={`strength-${s.value}`} checked={settings.site_strength === s.value} onChange={() => update({ site_strength: s.value })} />
                      <strong>{s.label}</strong>
                      <span>{s.hint}</span>
                    </label>
                  ))}
                </div>
                <span className="field-hint">Newer sites get searches with less competition, so they can realistically rank.</span>
              </fieldset>

              <details className="more">
                <summary>More options</summary>
                <div className="more-body two-col">
                  <div className="field">
                    <label className="field-label" htmlFor="phrases">Searches to target</label>
                    <select id="phrases" className="select" value={settings.phrases_per_run} onChange={(e) => update({ phrases_per_run: Number(e.target.value) })}>
                      {[1, 2, 3].map((n) => <option key={n} value={n}>{n}</option>)}
                    </select>
                  </div>
                  <div className="field">
                    <label className="field-label" htmlFor="pages">Google results to study</label>
                    <select id="pages" className="select" value={settings.pages_per_phrase} onChange={(e) => update({ pages_per_phrase: Number(e.target.value) as 10 | 20 })}>
                      <option value={10}>Top 10</option>
                      <option value={20}>Top 20</option>
                    </select>
                  </div>
                </div>
              </details>
            </>
          )}
        </div>

        <div className="card-foot">
          <span className="cta-note">
            {error ? <span className="text-bad">{error}</span> : 'Takes about 2 minutes. Costs a few cents in AI usage.'}
          </span>
          <button type="button" className="btn primary large" disabled={!canStart} onClick={start}>
            {busy ? 'Starting…' : 'Create brief'}
          </button>
        </div>
      </section>
    </div>
  )
}
