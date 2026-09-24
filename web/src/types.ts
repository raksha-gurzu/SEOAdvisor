// Mirrors the Pydantic models served by the FastAPI backend (src/seo_engine).

export type Bucket = 'must' | 'worth' | 'rare' | 'noise'
export type RunStatus = 'queued' | 'running' | 'done' | 'failed'
export type StepStatus = 'pending' | 'running' | 'done' | 'failed'
export type SiteStrength = 'new' | 'growing' | 'established'
export type DataMode = 'free' | 'dataforseo'

export interface Phrase {
  text: string
  volume: number
  volume_source: string
  difficulty: number
  difficulty_source: string
  intent: string
  cluster: string[]
  reason: string
}

export interface TopicCount {
  topic: string
  covered_by: number
  total: number
  ours_passages: number
  bucket: Bucket
}

export interface Gap {
  topic: string
  covered_by: number
  evidence: string
}

export interface ContentDraft {
  h1: string
  intro: string
  sections: { heading: string; body: string }[]
  faq: { question: string; answer: string }[]
  cta: string
  word_count: number
  placeholders: string[]
  checks: { label: string; ok: boolean; detail: string }[]
}

export interface Brief {
  phrases: Phrase[]
  titles: string[]
  description: string
  must_cover: TopicCount[]
  gaps: Gap[]
  headings: string[]
  intent_flag: string | null
  score: number
  score_arithmetic: string
  checklist: Record<string, boolean>
  draft: ContentDraft | null
}

export interface CompetitorPage {
  url: string
  source: string
  page_type: string
  headings: string[]
  topics: string[]
}

export interface RunSettings {
  country: string
  site_strength: SiteStrength
  phrases_per_run: number
  pages_per_phrase: 10 | 20
  data_mode: DataMode
}

export interface Run {
  page_text: string
  source_url: string | null
  settings: RunSettings & Record<string, unknown>
  phrases: Phrase[]
  competitors: CompetitorPage[]
  coverage: TopicCount[]
  gaps: Gap[]
  brief: Brief | null
  cost_usd: number
  costs: { label: string; usd: number }[]
  notes: string[]
}

export interface Step {
  name: string
  label: string
  status: StepStatus
  detail: string
  started_at: string | null
  finished_at: string | null
}

export interface Candidate {
  keyword: string
  sources: string[]
  volume: number
  in_autocomplete: boolean | null
  difficulty: number | null
  intent: string
  fit: number
  kept: boolean
  reason: string
}

export interface Cluster {
  head: string
  members: string[]
  total_volume: number
  difficulty: number
  fit: number
  demand: number
  winnability: number
  score: number
  weak_spots: string[]
}

export interface SerpItem {
  rank: number
  url: string
  domain: string
  title: string
  page_type: string
}

export interface SerpResults {
  phrase: string
  source: string
  items: SerpItem[]
  features: string[]
  people_also_ask: string[]
  related_searches: string[]
}

export interface SnippetCheck {
  title: string
  title_px: number
  title_chars: number
  description_chars: number
  title_ok: boolean
  description_ok: boolean
  reasons: string[]
}

export interface Details {
  candidates: Candidate[]
  clusters: Cluster[]
  serps: SerpResults[]
  intent: { mix: Record<string, number>; dominant: string | null; dominant_share: number; verdict: string; flag: string | null } | null
  ours_page_type: string
  ours_topics: string[]
  dropped: { url: string; rank: number; reason: string }[]
  type_mix: Record<string, number>
  topic_details: { topic: string; members: string[]; competitor_passages: number[]; noise_reason: string; stuffing: boolean }[]
  stuffing_warnings: string[]
  snippets: SnippetCheck[]
  rewrites: number
}

export interface RunRecord {
  id: string
  created_at: string
  updated_at: string
  status: RunStatus
  error: string | null
  steps: Step[]
  run: Run
  details: Details | null
}

export interface RunSummary {
  id: string
  created_at: string
  status: RunStatus
  title: string
  score: number | null
  cost_usd: number
}

export interface Health {
  keys: Record<string, boolean>
  ready_free_mode: boolean
  missing_for_free_mode: string[]
}

export interface Defaults {
  settings: RunSettings
  countries: string[]
  min_words: number
}
