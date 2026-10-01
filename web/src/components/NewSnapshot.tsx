import { useEffect, useState } from 'react'
import { api } from '../api'
import { COUNTRY_NAMES, maxCredits, siteHost } from '../format'
import { go } from '../router'
import type { Health, SnapshotDefaults, SnapshotSettingsIn } from '../types'
import { Alert } from './ui'

const KEY_NAMES: Record<string, string> = {
  deepseek: 'DEEPSEEK_API_KEY',
  serper: 'SERPER_API_KEY',
  openpagerank: 'OPENPAGERANK_API_KEY',
  crux: 'CRUX_API_KEY',
  bing: 'BING_WEBMASTER_API_KEY',
}
const OPTIONAL_TEXT: Record<string, string> = {
  serper: 'Google positions',
  openpagerank: 'the link score',
  crux: 'speed for real visitors',
  bing: 'search numbers and visits',
}

export function NewSnapshot({ health, onStarted }: { health: Health | null; onStarted: () => void }) {
  const [defaults, setDefaults] = useState<SnapshotDefaults | null>(null)
  const [settings, setSettings] = useState<SnapshotSettingsIn | null>(null)
  const [site, setSite] = useState('')
  const [left, setLeft] = useState(false) // the user has moved out of the field
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.snapshotDefaults()
      .then((d) => { setDefaults(d); setSettings(d.settings) })
      .catch(() => setError('Can’t reach the server. Start the backend, then reload this page.'))
  }, [])

  const host = siteHost(site)
  const bad = site.trim() && !host && left
  const missing = health?.missing_for_site_snapshot ?? []
  const optional = health?.optional_for_site_snapshot ?? []
  const canStart = !!settings && !!host && !busy && missing.length === 0
  const update = (patch: Partial<SnapshotSettingsIn>) => settings && setSettings({ ...settings, ...patch })

  async function start() {
    if (!settings) return
    setBusy(true)
    setError(null)
    try {
      const { id } = await api.startSnapshot(site.trim(), settings)
      onStarted()
      go({ page: 'snap', id })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <header className="page-head">
        <h1>Take a site snapshot</h1>
        <p>One page about one website: how strong it is, where it shows on Google, its competitors and its technical basics.</p>
      </header>

      {missing.length > 0 && (
        <Alert tone="bad">
          <strong>One more setup step.</strong> Add <code>{KEY_NAMES[missing[0]] ?? missing[0]}</code> to the <code>.env</code> file, then reload this page.
        </Alert>
      )}

      <section className="card">
        <div className="card-body">
          <form className="field" onSubmit={(e) => { e.preventDefault(); if (canStart) start() }}>
            <label className="field-label" htmlFor="snap-site">Website</label>
            <input
              id="snap-site"
              className="input"
              type="text"
              inputMode="url"
              autoComplete="url"
              placeholder="gurzu.com"
              value={site}
              onChange={(e) => setSite(e.target.value)}
              onBlur={() => setLeft(true)}
              aria-invalid={bad ? true : undefined}
              aria-describedby="snap-site-hint"
            />
            <span className="field-hint" id="snap-site-hint">The whole site is read, so the homepage address is enough.</span>
          </form>
          {bad && <Alert tone="warn">“{site.trim()}” isn’t a website address. Try something like example.com.</Alert>}

          {settings && defaults && (
            <>
              <div className="field">
                <label className="field-label" htmlFor="snap-country">Where are the site’s customers?</label>
                <select id="snap-country" className="select" value={settings.country} onChange={(e) => update({ country: e.target.value })}>
                  {defaults.countries.map((c) => <option key={c} value={c}>{COUNTRY_NAMES[c] ?? c}</option>)}
                </select>
                <span className="field-hint">We check the Google results people see in this country.</span>
              </div>
              <details className="more">
                <summary>More options</summary>
                <div className="more-body">
                  <div className="field">
                    <label className="field-label" htmlFor="snap-keywords">Searches to check</label>
                    <select id="snap-keywords" className="select" value={settings.keywords} onChange={(e) => update({ keywords: Number(e.target.value) })}>
                      {defaults.keyword_options.map((k) => <option key={k} value={k}>Up to {k}</option>)}
                    </select>
                  </div>
                </div>
              </details>
            </>
          )}

          {optional.length > 0 && missing.length === 0 && (
            <p className="muted small">
              Not set up: {optional.map((k) => OPTIONAL_TEXT[k] ?? k).join(', ')}. Those parts of the snapshot will say so.
            </p>
          )}
        </div>

        <div className="card-foot">
          <span className="cta-note">
            {error ? (
              <span className="text-bad">{error}</span>
            ) : settings && defaults ? (
              <span className="credit-note">
                About 1 minute. Uses up to {maxCredits(settings.keywords, defaults.depth)} Serper credits (fewer when results are cached today)
                and under a cent of AI.
              </span>
            ) : null}
          </span>
          <button type="button" className="btn primary large" disabled={!canStart} onClick={start}>
            {busy ? 'Starting…' : 'Take snapshot'}
          </button>
        </div>
      </section>
    </div>
  )
}
