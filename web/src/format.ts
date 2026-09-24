import type { Brief, ContentDraft, Phrase, TopicCount } from './types'

export type Tone = 'good' | 'warn' | 'bad' | 'neutral'

export const COUNTRY_NAMES: Record<string, string> = {
  US: 'United States', GB: 'United Kingdom', CA: 'Canada', AU: 'Australia', IN: 'India',
  NP: 'Nepal', DE: 'Germany', FR: 'France', NZ: 'New Zealand', IE: 'Ireland', SG: 'Singapore',
}

export const CHECKLIST_LABELS: Record<string, string> = {
  phrase_in_title: 'Main search phrase is in the title',
  phrase_first_in_title: 'Title starts with the main phrase',
  title_width_ok: 'Title fits on Google without being cut',
  description_length_ok: 'Description is a good length',
  phrase_in_description_payoff: 'Description mentions the phrase early',
  phrase_in_h1: 'Main heading includes the phrase',
  intent_matches: 'Page type matches what Google shows',
  no_stuffing: 'No keyword stuffing',
}

export function checklistLabel(key: string): string {
  return CHECKLIST_LABELS[key] ?? key.replaceAll('_', ' ')
}

/** Difficulty (0–100) as a plain competition level. */
export function competition(difficulty: number): { label: string; tone: Tone } {
  if (difficulty <= 30) return { label: 'Low competition', tone: 'good' }
  if (difficulty <= 55) return { label: 'Medium competition', tone: 'warn' }
  return { label: 'High competition', tone: 'bad' }
}

export function intentText(intent: string): string {
  switch (intent) {
    case 'commercial': return 'People are comparing options'
    case 'transactional': return 'People are ready to sign up or buy'
    case 'informational': return 'People want to learn'
    case 'navigational': return 'People look for a specific site'
    default: return 'Mixed reasons for searching'
  }
}

export function demandText(p: Phrase): string {
  if (p.volume_source === 'autocomplete') return 'People search this on Google'
  if (p.volume_source === 'bing') return `About ${p.volume.toLocaleString()} searches a month (Bing)`
  return `About ${p.volume.toLocaleString()} searches a month`
}

export function verdict(score: number): { label: string; tone: Tone } {
  if (score >= 70) return { label: 'Strong', tone: 'good' }
  if (score >= 40) return { label: 'Getting there', tone: 'warn' }
  return { label: 'Needs work', tone: 'bad' }
}

/** Key topics = must-cover + worth-covering; covered = mentioned at least once on the page. */
export function topicCoverage(coverage: TopicCount[]): { covered: number; total: number } {
  const key = coverage.filter((c) => c.bucket === 'must' || c.bucket === 'worth')
  return { covered: key.filter((c) => c.ours_passages > 0).length, total: key.length }
}

export function hostOf(url: string | null): string | null {
  if (!url) return null
  try { return new URL(url).host.replace(/^www\./, '') } catch { return null }
}

export function usd(value: number): string {
  if (value === 0) return '$0'
  return value < 0.01 ? '< $0.01' : `$${value.toFixed(2)}`
}

export function relativeTime(iso: string): string {
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

export function duration(start: string | null, end: string | null): string {
  if (!start) return ''
  const ms = (end ? new Date(end) : new Date()).getTime() - new Date(start).getTime()
  const s = Math.max(0, Math.round(ms / 1000))
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`
}

export function wordCount(text: string): number {
  return text.trim() ? text.trim().split(/\s+/).length : 0
}

export function briefToMarkdown(brief: Brief, site: string | null): string {
  const lines: string[] = [`# SEO brief${site ? ` for ${site}` : ''}`, '']
  lines.push(`Score: ${brief.score}/100 (${verdict(brief.score).label})`, '')
  if (brief.intent_flag) lines.push(`> Page type warning: ${brief.intent_flag}`, '')
  lines.push('## 1. Target these searches', '')
  for (const p of brief.phrases) {
    lines.push(`- **${p.text}**: ${competition(p.difficulty).label.toLowerCase()}; ${demandText(p).toLowerCase()}`)
  }
  lines.push('', '## 2. Title and description', '', `Title: ${brief.titles[0]}`)
  brief.titles.slice(1).forEach((t) => lines.push(`Alternative: ${t}`))
  lines.push('', `Description: ${brief.description}`)
  lines.push('', '## 3. Topics to add', '')
  const missing = brief.must_cover.filter((t) => t.ours_passages === 0)
  for (const t of missing) lines.push(`- ${t.topic} (${t.covered_by} of ${t.total} top pages cover it)`)
  if (!missing.length) lines.push('- None: your page covers every must-have topic.')
  lines.push('', '## 4. Questions to answer', '')
  for (const g of brief.gaps) lines.push(`- ${g.topic}`)
  if (!brief.gaps.length) lines.push('- None found this time.')
  lines.push('', '## 5. Suggested outline', '')
  brief.headings.forEach((h, i) => lines.push(i === 0 ? `- H1: ${h}` : `  - H2: ${h}`))
  if (brief.draft) lines.push('', '## 6. Suggested content', '', draftToMarkdown(brief.draft))
  return lines.join('\n') + '\n'
}

/** The suggested draft as Markdown, ready to paste into a CMS or doc. */
export function draftToMarkdown(d: ContentDraft): string {
  const out = [`# ${d.h1}`, '', d.intro]
  for (const s of d.sections) out.push('', `## ${s.heading}`, '', s.body)
  if (d.faq.length) {
    out.push('', '## Frequently asked questions')
    for (const f of d.faq) out.push('', `### ${f.question}`, '', f.answer)
  }
  if (d.cta) out.push('', d.cta)
  return out.join('\n')
}
