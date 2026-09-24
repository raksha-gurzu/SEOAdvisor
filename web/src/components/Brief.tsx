import type { ReactNode } from 'react'
import { competition, demandText, draftToMarkdown, hostOf, intentText, topicCoverage, verdict } from '../format'
import type { Brief, ContentDraft, Details, Run, SnippetCheck } from '../types'
import { Alert, CopyButton, Disclosure, Pill } from './ui'

export function ActionPlan({ brief, run, details }: { brief: Brief; run: Run; details: Details | null }) {
  const missing = brief.must_cover.filter((t) => t.ours_passages === 0)
  const present = brief.must_cover.filter((t) => t.ours_passages > 0)
  const main = brief.phrases[0]

  const todos: string[] = [`Aim the page at “${main.text}”, starting with the new title.`]
  if (missing.length) todos.push(`Add ${missing.length} topic${missing.length > 1 ? 's' : ''} that most top pages cover.`)
  if (brief.gaps.length) todos.push(`Answer ${brief.gaps.length} question${brief.gaps.length > 1 ? 's' : ''} searchers ask that competitors skip.`)
  if (brief.draft) todos.push(`Use the suggested content as your starting draft${brief.draft.placeholders.length ? `, and fill in the ${brief.draft.placeholders.length} highlighted facts` : ''}.`)

  return (
    <div className="plan">
      <Summary brief={brief} run={run} todos={todos} />

      <Step n={1} title="Target these searches" why="Searches people really make, where your page has a fair chance to rank.">
        <div className="phrase-list">
          {brief.phrases.map((p, i) => {
            const c = competition(p.difficulty)
            const also = p.cluster.filter((x) => x !== p.text)
            return (
              <div key={p.text} className={`phrase ${i === 0 ? 'primary' : ''}`}>
                <div className="phrase-top">
                  <span className="phrase-text">{p.text}</span>
                  {i === 0 && <Pill tone="brand">Main search</Pill>}
                </div>
                <div className="phrase-facts">
                  <Pill tone={c.tone}>{c.label}</Pill>
                  <Pill>{demandText(p)}</Pill>
                  <Pill>{intentText(p.intent)}</Pill>
                </div>
                {also.length > 0 && <p className="phrase-also">Also helps with: {also.join(', ')}</p>}
              </div>
            )
          })}
        </div>
      </Step>

      <Step n={2} title="Update your title and description" why="This is what people see on Google before they decide to click.">
        <SnippetPreview brief={brief} site={hostOf(run.source_url)} url={run.source_url} snippets={details?.snippets ?? []} />
      </Step>

      <Step
        n={3}
        title="Add these missing topics"
        why="Most pages that rank for your searches cover these. Your page doesn’t mention them yet."
      >
        {missing.length === 0 ? (
          <p className="empty-good"><span className="text-good" aria-hidden="true">✓</span> Your page already covers every must-have topic.</p>
        ) : (
          <ul className="topic-list">
            {missing.map((t) => (
              <li key={t.topic}>
                <span className="topic-name">{t.topic}</span>
                <span className="topic-meta">
                  <span className="mini-bar" aria-hidden="true"><span style={{ width: `${(t.covered_by / t.total) * 100}%` }} /></span>
                  {t.covered_by} of {t.total} top pages cover this
                </span>
              </li>
            ))}
          </ul>
        )}
        {present.length > 0 && (
          <Disclosure summary={`Already on your page (${present.length})`}>
            <ul className="topic-list">
              {present.map((t) => (
                <li key={t.topic}>
                  <span className="topic-name">{t.topic}</span>
                  <span className="topic-meta">Mentioned {t.ours_passages} time{t.ours_passages > 1 ? 's' : ''}</span>
                </li>
              ))}
            </ul>
          </Disclosure>
        )}
        {details && details.stuffing_warnings.length > 0 && (
          <Alert tone="warn">
            <strong>Don’t overdo it.</strong> Your page repeats some topics more than almost any top page does. See Details for which ones.
          </Alert>
        )}
      </Step>

      <Step n={4} title="Answer questions others don’t" why="People search for these, but almost no competing page answers them. A short, honest answer can set you apart.">
        {brief.gaps.length === 0 ? (
          <p className="muted">No clear unanswered questions this time.</p>
        ) : (
          <ul className="question-list">
            {brief.gaps.map((g) => (
              <li key={g.topic}>
                <span className="q" aria-hidden="true">?</span>
                <div>
                  <strong>{g.topic}</strong>
                  <span>{gapSource(g.evidence)} · {g.covered_by === 0 ? 'no top page answers it' : `only ${g.covered_by} top page${g.covered_by > 1 ? 's' : ''} answer it`}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
        <p className="muted small">You write the answers; the brief never makes up facts about your product.</p>
      </Step>

      <Step
        n={5}
        title="Suggested page outline"
        why="A heading structure that works the searches and new topics into your page."
        action={<CopyButton text={brief.headings.map((h, i) => `${i === 0 ? 'H1' : 'H2'}: ${h}`).join('\n')} label="Copy outline" />}
      >
        <ol className="outline">
          {brief.headings.map((h, i) => (
            <li key={`${i}-${h}`} className={i === 0 ? 'h1' : 'h2'}>
              <span className="lvl">{i === 0 ? 'Main heading' : 'Section'}</span>
              {h}
            </li>
          ))}
        </ol>
      </Step>

      {brief.draft && <DraftStep draft={brief.draft} />}
    </div>
  )
}

function DraftStep({ draft }: { draft: ContentDraft }) {
  const failing = draft.checks.filter((c) => !c.ok && c.label !== 'Facts to fill in')
  return (
    <Step
      n={6}
      title="Suggested content"
      why="A full draft of your page, written to SEO standards from the facts on your page. Edit it in your own voice before publishing."
      action={<CopyButton text={draftToMarkdown(draft)} label="Copy content" />}
    >
      <div className="checks-inline">
        {draft.checks.filter((c) => c.label !== 'Facts to fill in').map((c) => (
          <Pill key={c.label} tone={c.ok ? 'good' : 'warn'}>{c.ok ? '✓ ' : ''}{c.label}</Pill>
        ))}
        <Pill>{draft.word_count.toLocaleString()} words</Pill>
      </div>
      {draft.placeholders.length > 0 && (
        <Alert tone="warn">
          <strong>{draft.placeholders.length} fact{draft.placeholders.length > 1 ? 's' : ''} to fill in.</strong> The draft never guesses details it can’t find on your page. Replace each <mark className="ph">highlighted</mark> item with the real information.
        </Alert>
      )}
      {failing.length > 0 && (
        <p className="muted small">Worth a look: {failing.map((c) => `${c.label.toLowerCase()}${c.detail ? ` (${c.detail})` : ''}`).join('; ')}.</p>
      )}
      <article className="draft">
        <h1>{withPlaceholders(draft.h1)}</h1>
        <p>{withPlaceholders(draft.intro)}</p>
        {draft.sections.map((s) => (
          <section key={s.heading}>
            <h2>{withPlaceholders(s.heading)}</h2>
            <DraftBody text={s.body} />
          </section>
        ))}
        {draft.faq.length > 0 && (
          <section>
            <h2>Frequently asked questions</h2>
            {draft.faq.map((f) => (
              <div key={f.question} className="faq">
                <h3>{withPlaceholders(f.question)}</h3>
                <p>{withPlaceholders(f.answer)}</p>
              </div>
            ))}
          </section>
        )}
        {draft.cta && <p className="draft-cta">{withPlaceholders(draft.cta)}</p>}
      </article>
    </Step>
  )
}

/** Paragraphs split on blank lines; blocks of "- " lines become bullet lists. */
function DraftBody({ text }: { text: string }) {
  const blocks = text.trim().split(/\n\s*\n/)
  return (
    <>
      {blocks.map((block, i) => {
        const lines = block.split('\n').map((l) => l.trim()).filter(Boolean)
        if (lines.length && lines.every((l) => /^[-*•] /.test(l))) {
          return <ul key={i}>{lines.map((l) => <li key={l}>{withPlaceholders(l.slice(2))}</li>)}</ul>
        }
        return <p key={i}>{withPlaceholders(lines.join(' '))}</p>
      })}
    </>
  )
}

function withPlaceholders(text: string): ReactNode {
  return text.split(/(\[ADD:[^\]]*\])/).map((part, i) =>
    part.startsWith('[ADD:') ? <mark key={i} className="ph">{part}</mark> : part,
  )
}

function Summary({ brief, run, todos }: { brief: Brief; run: Run; todos: string[] }) {
  const v = verdict(brief.score)
  const { covered, total } = topicCoverage(run.coverage)
  const r = 54
  const circ = 2 * Math.PI * r
  return (
    <section className="card">
      <div className="summary">
        <div className="ring" role="img" aria-label={`Score ${brief.score} out of 100: ${v.label}`}>
          <svg viewBox="0 0 132 132">
            <circle className="ring-track" cx="66" cy="66" r={r} fill="none" strokeWidth="12" />
            <circle
              className={`ring-fill ${v.tone}`}
              cx="66" cy="66" r={r} fill="none" strokeWidth="12" strokeLinecap="round"
              strokeDasharray={circ} strokeDashoffset={circ * (1 - brief.score / 100)}
            />
          </svg>
          <div className="ring-label">
            <span className="ring-number">{brief.score}</span>
            <span className="ring-of">out of 100</span>
          </div>
        </div>
        <div className="summary-text">
          <div><Pill tone={v.tone}>{v.label}</Pill></div>
          <h2>Your page covers {covered} of {total} key topics that top-ranking pages share.</h2>
          {brief.intent_flag && (
            <Alert tone="warn"><strong>Heads up:</strong> {brief.intent_flag} New words alone may not be enough.</Alert>
          )}
          <p>What to do first:</p>
          <ul className="todo">{todos.map((t) => <li key={t}>{t}</li>)}</ul>
        </div>
      </div>
    </section>
  )
}

function Step({ n, title, why, action, children }: { n: number; title: string; why: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="card step-card" aria-labelledby={`step-${n}`}>
      <div className="card-body">
        <div className="step-head">
          <span className="step-num" aria-hidden="true">{n}</span>
          <div>
            <h2 id={`step-${n}`}>{title}</h2>
            <p>{why}</p>
          </div>
          {action}
        </div>
        <div className="step-content">{children}</div>
      </div>
    </section>
  )
}

function SnippetPreview({ brief, site, url, snippets }: { brief: Brief; site: string | null; url: string | null; snippets: SnippetCheck[] }) {
  const [best, ...others] = brief.titles
  const check = snippets.find((s) => s.title === best)
  const fits = check ? check.title_ok : true
  const descOk = brief.description.length <= 158
  return (
    <>
      <div className="serp" aria-label="Preview of your Google result">
        <div className="serp-site">
          <span className="serp-icon" aria-hidden="true">{(site ?? 'Y')[0].toUpperCase()}</span>
          <div>
            <div className="serp-name">{site ?? 'Your site'}</div>
            <div className="serp-url">{url ?? 'https://your-site.com'}</div>
          </div>
        </div>
        <div className="serp-title">{best}</div>
        <p className="serp-desc">{brief.description}</p>
      </div>
      <div className="checks-inline">
        <Pill tone={fits ? 'good' : 'bad'}>{fits ? '✓ Title fits on Google' : 'Title too long, Google will cut it'}</Pill>
        <Pill tone={descOk ? 'good' : 'warn'}>{descOk ? '✓ Description length is good' : 'Description will be cut short'}</Pill>
        {brief.checklist.phrase_in_title && <Pill tone="good">✓ Includes the main search</Pill>}
      </div>
      <div className="copy-row">
        <div className="copy-text"><span className="copy-label">Title</span>{best}</div>
        <CopyButton text={best} />
      </div>
      <div className="copy-row desc">
        <div className="copy-text"><span className="copy-label">Description</span>{brief.description}</div>
        <CopyButton text={brief.description} />
      </div>
      {others.length > 0 && (
        <Disclosure summary={`${others.length} other title idea${others.length > 1 ? 's' : ''}`}>
          <ul className="alt-titles">
            {others.map((t) => (
              <li key={t} className="copy-row">
                <span className="copy-text">{t}</span>
                <CopyButton text={t} />
              </li>
            ))}
          </ul>
        </Disclosure>
      )}
    </>
  )
}

function gapSource(evidence: string): string {
  const source = evidence.split(': ')[0]
  if (source === 'People Also Ask') return 'Asked on Google (“People also ask”)'
  if (source === 'Google autocomplete') return 'Suggested by Google search'
  return 'Searched on Google'
}
