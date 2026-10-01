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
  missing_for_keyword_gap: string[]
  missing_for_site_snapshot: string[]
  optional_for_site_snapshot: string[]
}

export interface Defaults {
  settings: RunSettings
  countries: string[]
  min_words: number
}

// ——— Keyword gap (src/seo_engine/gap_pipeline.py and tools/) ———

export type GapCategory = 'shared' | 'missing' | 'weak' | 'strong' | 'untapped' | 'unique'
export type BingStatus = 'measured' | 'too_low' | 'not_measured' | 'no_key'

export interface GapSettingsIn {
  country: string
  depth: number
  keywords: number
}

export interface GapDefaults {
  settings: GapSettingsIn
  countries: string[]
  max_competitors: number
  depths: number[]
  keyword_options: number[]
}

export interface SitePage {
  url: string
  status: string
  title: string
  headings: string[]
  word_count: number
}

export interface SiteSample {
  domain: string
  origin: string
  source: 'sitemap' | 'sitemap+links' | 'links' | 'none'
  sitemaps: string[]
  urls_found: number
  sitemap_urls: number
  sitemap_capped: boolean
  pages: SitePage[]
  notes: string[]
}

export interface GapKeyword {
  keyword: string
  sources: string[]
  pages: Record<string, string>
  bing_searches: number | null
  autocomplete: boolean | null
  brand_of: string | null
  business_fit: number | null
}

export interface KeywordDiscovery {
  keywords: GapKeyword[]
  brand_keywords: GapKeyword[]
  candidates: number
  no_demand: number
  not_checked: number
  no_fit: number
  ours_no_demand: string[]
  notes: string[]
}

export interface SerpItem {
  rank: number
  url: string
  domain: string
  title: string
  description: string
  page_type: string
}

export interface KeywordRanking {
  keyword: string
  positions: Record<string, { position: number | null; url: string }>
  results_seen: number
  results: SerpItem[]
  features: string[]
  people_also_ask: string[]
  related_searches: string[]
}

export interface GapRow {
  keyword: string
  bing_searches: number | null
  bing_status: BingStatus
  autocomplete: boolean | null
  google_estimate: number | null
  visits: Record<string, number | null>
  difficulty: number | null
  difficulty_band: 'low' | 'medium' | 'high' | null
  intent: string
  features: string[]
  cluster: string
  categories: GapCategory[]
  positions: Record<string, number | null>
  urls: Record<string, string>
  pages: Record<string, string>
  sources: string[]
  business_fit: number | null
  proof: number
  traffic_lift: number | null
}

export interface Opportunity {
  keyword: string
  category: GapCategory
  reason: string
  business_fit: number | null
  proof: number
  difficulty: number | null
  difficulty_band: string | null
  traffic_lift: number | null
  best_competitor: string
  best_position: number
  best_url: string
}

export interface CompetitorPanel {
  domain: string
  keywords_ranked: number
  visits_known: number
  top: { keyword: string; position: number; url: string; visits: number | null }[]
}

export interface KeywordGapResult {
  domains: string[]
  rows: GapRow[]
  counts: Record<GapCategory, number>
  top: Opportunity[]
  competitors: CompetitorPanel[]
  unranked: string[]
  brand_keywords: GapKeyword[]
  suggested_competitors: { domain: string; keywords: number; best_position: number; examples: string[] }[]
  notes: string[]
}

export interface GapRun {
  site: string
  competitors: string[]
  settings: { base: { country: string }; depth: number; keywords: number; max_competitors: number; pages_per_site: number }
  domains: string[]
  sites: SiteSample[]
  discovery: KeywordDiscovery | null
  ranks: { rankings: KeywordRanking[]; not_checked: string[]; notes: string[] } | null
  result: KeywordGapResult | null
  google_per_bing: number | null
  ctr_source: string
  shares_source: string
  credits_used: number
  cost_usd: number
  notes: string[]
}

export interface GapRecord {
  id: string
  created_at: string
  updated_at: string
  status: RunStatus
  error: string | null
  steps: Step[]
  run: GapRun
}

export interface GapSummary {
  id: string
  created_at: string
  status: RunStatus
  title: string
  to_add: number | null
  credits_used: number
  cost_usd: number
}

// ——— Site Snapshot (docs/SITE-SNAPSHOT-PLAN.md) ———

export type FactStatus = 'ok' | 'not_found' | 'not_set_up' | 'error'
export type CheckStatus = 'pass' | 'warn' | 'fail' | 'unknown'

export interface SnapshotSettingsIn {
  country: string
  keywords: number
}

export interface SnapshotDefaults {
  settings: SnapshotSettingsIn
  countries: string[]
  keyword_options: number[]
  depth: number
}

export interface LinkScore {
  domain: string
  status: FactStatus
  score: number | null
  rank: number | null
  referring_domains: number | null
  history: { month: string; score: number; estimated: boolean }[]
  source: string
  note: string
}

export interface Speed {
  origin: string
  status: 'ok' | 'no_data' | 'not_set_up' | 'error'
  form_factor: string
  p75: Record<string, number>
  first_day: string | null
  last_day: string | null
  note: string
}

export interface DomainDates {
  domain: string
  registered: string | null
  registered_via: string
  registered_domain: string
  first_seen: string | null
  first_seen_url: string
  notes: string[]
}

export interface SiteFacts {
  link: LinkScore | null
  majestic: { domain: string; global_rank: number; ref_subnets: number; ref_ips: number } | null
  majestic_read: boolean
  tranco_rank: number | null
  tranco_read: boolean
  speed: Speed | null
  dates: DomainDates | null
}

export interface SnapshotKeyword {
  keyword: string
  position: number | null
  url: string
  ranked: boolean
  bing_searches: number | null
  bing_status: BingStatus
  google_estimate: number | null
  visits: number | null
  difficulty: number | null
  difficulty_band: 'low' | 'medium' | 'high' | null
  intent: string
  features: string[]
}

export interface SiteCheck {
  key: string
  label: string
  status: CheckStatus
  detail: string
}

export interface SnapshotResult {
  domain: string
  home: string
  facts: SiteFacts
  vitals: { metric: string; p75: number; status: string }[]
  sitemap_urls: number
  sitemap_files: number
  sitemap_capped: boolean
  keywords_checked: number
  keywords_found: number
  depth: number
  visits: number | null
  visits_keywords: number
  groups: { label: string; low: number | null; high: number | null; count: number }[]
  keywords: SnapshotKeyword[]
  top_pages: { url: string; visits: number | null; keywords: string[]; best_position: number }[]
  competitors: { domain: string; keywords: number; best_position: number; examples: string[] }[]
  checks: { home: string; checks: SiteCheck[] } | null
  notes: string[]
}

export interface SnapshotRun {
  site: string
  settings: { gap: { keywords: number; depth: number; base: { country: string } } }
  domain: string
  sample: SiteSample | null
  ranks: { rankings: KeywordRanking[]; not_checked: string[] } | null
  result: SnapshotResult | null
  credits_used: number
  cost_usd: number
  notes: string[]
}

export interface SnapshotRecord {
  id: string
  created_at: string
  updated_at: string
  status: RunStatus
  error: string | null
  steps: Step[]
  run: SnapshotRun
}

export interface SnapshotSummary {
  id: string
  created_at: string
  status: RunStatus
  title: string
  found: number | null
  checked: number | null
  credits_used: number
  cost_usd: number
}
