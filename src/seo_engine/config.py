"""Run settings, tunable thresholds and secrets.

Every depth, cost and behaviour knob lives here (CLAUDE.md rule 9). Values marked
"tune" in docs/ARCHITECTURE.md are starting points to calibrate on the eval set.
"""

from itertools import pairwise
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SiteStrength = Literal["new", "growing", "established"]

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Thresholds(BaseModel):
    """Algorithm thresholds from docs/ARCHITECTURE.md §5 (all "tune")."""

    # §5.1 phrase discovery
    min_volume: int = 50  # DataForSEO mode: Google monthly volume
    min_bing_impressions: int = 10  # free mode: Bing monthly impressions
    autocomplete_counts_as_demand: bool = True  # free mode: in Google autocomplete = searched
    question_prefixes: list[str] = ["what is", "how to", "best"]
    question_suffixes: list[str] = ["vs", "for"]
    # free-mode difficulty (§5.1): Tranco rank ceiling -> site strength; unlisted -> last value
    tranco_strength: list[tuple[int, float]] = [
        (1_000, 1.0),
        (10_000, 0.8),
        (100_000, 0.55),
        (1_000_000, 0.3),
    ]
    unlisted_strength: float = 0.1
    ugc_strength: float = 0.1  # forums and user-generated pages, whatever the domain
    small_site_min_count: int = 2  # this many unlisted domains in the top 10 = weak spot
    weak_spot_small_site_bonus: float = 0.05
    difficulty_ceiling: dict[SiteStrength, int] = {"new": 30, "growing": 45, "established": 60}
    cluster_min_shared_urls: int = 3
    cluster_top_n: int = 10
    seed_phrases_min: int = 15
    seed_phrases_max: int = 20
    page_phrases_top_n: int = 10  # KeyBERT-style phrases from the page text
    mmr_diversity: float = 0.5
    seeds_to_expand: int = 3  # best seeds used for borrow-the-map and autocomplete
    borrow_pages_per_seed: int = 3
    ranked_keywords_limit: int = 100
    suggestions_limit: int = 50
    cluster_max_candidates: int = 20  # candidates that get a SERP call for clustering
    weak_spot_forum_bonus: float = 0.10
    weak_spot_stale_bonus: float = 0.05
    stale_years: int = 2  # a year in a top-10 title this many years old or more is stale
    llm_page_words: int = 3000  # page text sent to an LLM is cut to this many words

    # §5.2 competitor filtering
    competitors_min: int = 5
    competitors_max: int = 10
    competitors_min_domains: int = 3
    max_pages_per_domain: int = 2
    length_ratio_min: float = 0.3
    length_ratio_max: float = 3.0
    authority_domains: list[str] = [
        "wikipedia.org",
        "amazon.com",
        "youtube.com",
        "g2.com",
        "capterra.com",
        "trustpilot.com",
        "forbes.com",
        "nytimes.com",
        "linkedin.com",
        "facebook.com",
    ]

    # §5.3 gap detection
    # Calibrated on Gemini gemini-embedding-001 (SEMANTIC_SIMILARITY, 768 dims), 2026-09-24:
    # synonyms 0.91-0.95, different topics 0.79-0.87. Topic-vs-passage scores overlap
    # (matches 0.81-0.89, non-matches up to 0.84), so passage coverage is read by the LLM.
    topic_merge_similarity: float = 0.90
    passage_max_words: int = 120
    coverage_max_topics: int = 80  # topic groups labelled per page (most-listed first)
    max_open_questions: int = 15  # unmatched searcher questions checked as gap candidates
    must_cover_share: float = 0.6
    worth_covering_share: float = 0.2
    evidence_similarity: float = 0.88  # topic <-> PAA/related/ranked phrase match
    max_gaps: int = 8
    brief_max_must: int = 15  # must-cover topics shown in the brief (full list in run.coverage)
    # suggested draft (PRD §5.9)
    draft_min_words: int = 600
    draft_max_words: int = 1500
    draft_max_density: float = 2.5  # main phrase uses per 100 words before it reads as stuffing

    # §5.4 intent
    intent_clear_share: float = 0.6
    intent_mixed_share: float = 0.5

    # §5.5 scoring and checklist
    bm25_k: float = 1.2
    score_target_saturation: float = 0.77
    title_max_px: int = 600
    title_min_chars: int = 30
    title_font_px: int = 20  # Google desktop title: Arial 20px
    description_min_chars: int = 70
    description_max_chars: int = 158
    description_payoff_chars: int = 120
    stuffing_percentile: float = 0.9

    # fetcher
    min_clean_words: int = 150


class ModelSettings(BaseModel):
    """Model names per tier (docs/ARCHITECTURE.md §6); picked by bake-off."""

    judgment: str = "deepseek-reasoner"
    bulk: str = "deepseek-chat"
    checker: str = "deepseek-reasoner"
    embedding: str = "gemini-embedding-001"
    embedding_dims: int = 768
    temperature: float = 0.2
    deepseek_base_url: str = "https://api.deepseek.com"
    # USD per 1M tokens: (input cache miss, input cache hit, output). Verify against vendor
    # pricing pages before trusting run costs.
    llm_prices: dict[str, tuple[float, float, float]] = {
        "deepseek-chat": (0.28, 0.028, 0.42),
        "deepseek-reasoner": (0.28, 0.028, 0.42),
    }
    embedding_price_per_m: float = 0.15
    grounding_model: str = "gemini-2.5-flash"  # free-tier Google Search grounding
    grounding_price_per_request: float = 0.0  # free tier; set if billing is on


class Settings(BaseModel):
    """Per-run settings (docs/PRD.md §7, docs/ARCHITECTURE.md §9)."""

    # "free": Serper free credits -> Gemini grounding, Bing + autocomplete demand, computed
    # difficulty; only LLM calls cost money. "dataforseo": paid DataForSEO for all SEO data.
    data_mode: Literal["free", "dataforseo"] = "free"
    phrases_per_run: int = 3
    phrase_selection: Literal["auto", "approval"] = "auto"
    pages_per_phrase: int = 20
    country: str = "US"
    language: str = "en"
    site_strength: SiteStrength = "new"
    surfaces: list[str] = ["google"]
    pool_mode: Literal["google", "merged", "per_surface"] = "google"
    ai_engines: int = 2
    ai_samples_per_engine: int = 30
    time_budget_s: int = 300
    cost_budget_usd: float | None = None  # set after phase 1
    serp_queue: Literal["standard", "priority", "live"] = "live"
    concurrency: int = 8
    user_agent: str = "Mozilla/5.0 (compatible; GurzuSEOEngine/0.1; +https://gurzu.com)"
    robots_token: str = "GurzuSEOEngine"
    fetch_timeout_s: float = 20.0
    fetch_deadline_s: float = 60.0  # whole download; fetch_timeout_s is per read
    max_page_bytes: int = 10_000_000  # larger pages are skipped, never held in memory
    headless_fallback: bool = True
    cache_dir: Path = PROJECT_ROOT / "cache"
    models: ModelSettings = Field(default_factory=ModelSettings)
    thresholds: Thresholds = Field(default_factory=Thresholds)


class GapSettings(BaseModel):
    """Keyword Gap run settings (docs/KEYWORD-GAP-PLAN.md §5). Research ids (R1, T2, D3...)
    point to the plan's research tables, which cite the sources."""

    # Shared plumbing (cache, fetcher, models, Tranco thresholds, country) comes from `base`.
    base: Settings = Field(default_factory=Settings)
    max_competitors: int = Field(4, ge=1, le=4)  # you + 4, as in Semrush
    pages_per_site: int = Field(30, ge=5, le=100)
    keywords: int = Field(60, ge=10, le=100)  # keywords whose Google positions are checked
    # Google returns 10 results per request since Sep 2025 (R1): depth costs depth/10 requests.
    depth: int = Field(20, ge=10, le=100, multiple_of=10)

    # Organic CTR by position 1..N, as published. Code caps each value at the one above it
    # (the source shows 11-19 above 7-10). Refresh quarterly (T2).
    ctr_by_position: list[float] = [
        0.2002, 0.1036, 0.0389, 0.0171, 0.0108, 0.0073, 0.0046, 0.0047, 0.0054, 0.0058,
        0.0067, 0.0070, 0.0082, 0.0088, 0.0080, 0.0067, 0.0064, 0.0055, 0.0052, 0.0027,
    ]  # fmt: skip
    ctr_source: str = "Advanced Web Ranking, Google US desktop, all SERPs, July 2026"

    # Rough Google searches = Bing searches x (Google share / Bing share) (D3, D4).
    google_estimate: bool = True
    # StatCounter, all platforms, August 2026: country -> (Google %, Bing %).
    search_shares: dict[str, tuple[float, float]] = {
        "US": (86.01, 8.99),
        "GB": (91.75, 5.66),
        "CA": (85.6, 9.61),
        "AU": (87.53, 9.45),
        "IN": (97.71, 1.26),
        "NP": (96.3, 2.74),
        "DE": (88.41, 5.88),
        "FR": (88.67, 5.17),
        "NZ": (88.31, 8.22),
        "IE": (93.97, 3.55),
        "SG": (92.57, 3.66),
    }
    search_shares_source: str = "StatCounter search engine market share, all platforms, Aug 2026"

    # Top keywords to add (§5.7)
    min_business_fit: int = Field(2, ge=0, le=3)  # Ahrefs business potential rubric (G3)
    # Difficulty bands, same cut-offs as the brief UI (web/src/format.ts competition()).
    difficulty_low_max: int = 30
    difficulty_medium_max: int = 55
    cluster_min_shared_urls: int = 3  # Keyword Insights default (G11)
    difficulty_min_results: int = 8  # fewer top-10 results: no difficulty (REVIEW.md M1)
    top_opportunities: int = 10
    depth_options: list[int] = [10, 20, 30, 50]  # offered in the form; 1 Serper credit per 10
    keyword_options: list[int] = [30, 60, 100]

    # Site reader (providers/sitemap.py, G6)
    max_sitemap_files: int = 8  # sitemap files read per site, index files included
    # Per sitemap file. The protocol allows 50 MB, but up to 5 sites are read in parallel and
    # we only pick a few dozen pages; 10 MB is still about 50,000 short URLs.
    max_sitemap_bytes: int = 10_000_000
    site_fetch_workers: int = 4  # parallel page fetches per site (polite)
    site_headless_fallback: bool = False  # a browser per short page is too slow for 30 pages
    # JavaScript sites (live: emitii.com has no links without a browser). The homepage is
    # rendered when its HTML has fewer same-site links than this; 0 turns it off.
    links_headless_below: int = 3
    # Sites with this many pages or fewer are read with the browser fallback per page.
    small_site_headless_pages: int = 8
    browser_workers: int = 2  # headless browsers running at the same time

    # Keyword discovery (tools/site_keywords.py). Demand gate = the brief's rule:
    # base.thresholds.min_bing_impressions or Google autocomplete.
    alternatives_per_page: int = Field(2, ge=0, le=5)  # extra phrases the LLM may give a page
    keyword_max_words: int = 7
    related_seeds_per_site: int = 2  # best phrases per site expanded with Bing related keywords
    demand_checks_max: int = 250  # candidates checked for demand (autocomplete + Bing calls)
    # A "brand" word in more than this share of candidates is a generic word, not a brand
    # (a site called workspace.com must not mark every "workspace" keyword as branded).
    brand_generic_share: float = 0.3
    fit_batch_size: int = 100  # keywords per business-fit LLM call
    # Keywords below min_business_fit fill spare slots only if at least this fit.
    # 1 (owner, 29 Sep 2026) uses every slot; min_business_fit saves credits instead.
    fill_min_fit: int = Field(1, ge=1, le=3)
    keyword_max_chars: int = 80
    prompt_headings: int = 6  # headings per page sent to the keyword LLM
    prompt_text_words: int = 40  # first words per page sent to the keyword LLM
    fit_text_words: int = 20  # first words per page when the LLM judges business fit
    demand_workers: int = 4  # parallel autocomplete and fit calls (polite)
    related_per_seed: int = 20  # Bing related keywords read per seed
    related_min_shared_words: int = 2  # live: 1 shared word let in "built for teams"
    brand_check_min_keywords: int = 10  # the common-word guard needs at least this many

    # Low yield (plan G13). Second pass: related searches from result pages where a
    # competitor ranks, checked on Google too (about 2 credits each; 0 turns it off).
    second_pass_keywords: int = Field(20, ge=0, le=60)
    # Suggested competitors: sites on page 1 for your good-fit keywords, apart from these
    # platforms, directories and forums (and anything they host).
    suggest_competitors: int = 5
    suggest_min_keywords: int = 2
    not_competitors: list[str] = [
        "wikipedia.org", "youtube.com", "reddit.com", "quora.com", "linkedin.com",
        "facebook.com", "instagram.com", "x.com", "twitter.com", "pinterest.com", "medium.com",
        "github.com", "stackoverflow.com", "amazon.com", "forbes.com", "nytimes.com",
        "g2.com", "capterra.com", "trustpilot.com", "getapp.com", "softwareadvice.com",
        "clutch.co", "goodfirms.co", "upwork.com", "fiverr.com", "indeed.com", "glassdoor.com",
        "google.com", "microsoft.com", "apple.com", "ibm.com",
        # developer communities and blog platforms (live, 29 Sep 2026: dev.to, geeksforgeeks)
        "dev.to", "geeksforgeeks.org", "w3schools.com", "freecodecamp.org", "hashnode.com",
        "tutorialspoint.com", "javatpoint.com", "substack.com", "wordpress.com", "blogspot.com",
    ]  # fmt: skip
    snippet_words: int = 60  # main text kept per page for the keyword LLM
    headings_per_page: int = 12  # headings kept per page for the keyword LLM
    # Pages that never target a search keyword. Whole path segments, then segment prefixes.
    skip_segments: list[str] = [
        "tag", "tags", "author", "authors", "login", "log-in", "signin", "sign-in", "signup",
        "sign-up", "register", "logout", "account", "my-account", "cart", "checkout", "basket",
        "wishlist", "search", "terms", "legal", "gdpr", "disclaimer", "imprint", "impressum",
        "data-deletion", "feed", "rss", "amp", "attachment", "404", "forgot-password",
        "reset-password", "unsubscribe", "category", "categories",
    ]  # fmt: skip
    # List pages: the index of a content section (/blog/, /articles/) names no search anyone
    # makes ("tech blog"); its posts are kept (Site Snapshot F25, owner decision Q5).
    listing_sections: list[str] = [
        "blog", "blogs", "articles", "news", "insights", "resources", "posts", "stories",
        "success-stories", "case-studies", "press", "events", "library", "knowledge-base",
        "learn", "guides", "updates", "podcast", "podcasts", "webinars", "community",
    ]  # fmt: skip
    skip_prefixes: list[str] = ["privacy", "terms-", "cookie", "wp-"]
    skip_contains: list[str] = ["thank-you", "thankyou"]  # "design-ebook-downloaded-thank-you"
    skip_extensions: list[str] = [
        ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".zip", ".mp4", ".mp3",
        ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".xml", ".txt", ".json", ".css", ".js",
    ]  # fmt: skip

    @field_validator("ctr_by_position")
    @classmethod
    def ctr_in_range(cls, v: list[float]) -> list[float]:
        if not v or any(not 0 <= c <= 1 for c in v):
            raise ValueError("ctr_by_position needs at least one value, each between 0 and 1")
        return v

    @field_validator("search_shares")
    @classmethod
    def shares_positive(cls, v: dict[str, tuple[float, float]]) -> dict[str, tuple[float, float]]:
        if any(g <= 0 or b <= 0 for g, b in v.values()):
            raise ValueError("search_shares values must be positive percentages")
        return {k.upper(): s for k, s in v.items()}

    def ctr_curve(self) -> list[float]:
        """CTR by position (index 0 = position 1), never above the position before it."""
        curve: list[float] = []
        for c in self.ctr_by_position:
            curve.append(min(c, curve[-1]) if curve else c)
        return curve

    def ctr_at(self, position: int | None) -> float:
        """0 when the page is not ranked or ranks below the published table."""
        curve = self.ctr_curve()
        if position is None or not 1 <= position <= len(curve):
            return 0.0
        return curve[position - 1]

    def google_per_bing(self, country: str) -> float | None:
        """None when the country has no share data or the estimate is switched off."""
        shares = self.search_shares.get(country.upper())
        if not self.google_estimate or shares is None:
            return None
        return shares[0] / shares[1]


class SnapshotSettings(BaseModel):
    """Site Snapshot settings (docs/SITE-SNAPSHOT-PLAN.md §5). Research ids (F7, O6...) point to
    the plan's research tables, which cite the sources."""

    # Steps 1-4 reuse the Keyword Gap code for one site. 30 keywords x depth 20 = about 60
    # Serper credits (owner decision Q1). No second pass: it needs competitors.
    gap: GapSettings = Field(
        default_factory=lambda: GapSettings(keywords=30, second_pass_keywords=0)
    )
    keyword_options: list[int] = [30, 60]

    # Position groups shown as bars (O6; our depth is 20, so no 21-50 group).
    position_groups: list[tuple[int, int]] = [(1, 3), (4, 10), (11, 20)]
    top_pages: int = Field(10, ge=1, le=50)

    # Site facts (F4, F10, F11). Majestic publishes daily; a week-old copy is close enough.
    majestic_max_age_days: int = Field(7, ge=1, le=60)
    rdap_timeout_s: float = 20.0
    fact_timeout_s: float = 20.0  # Open PageRank and CrUX, per request
    majestic_download_timeout_s: float = 120.0
    # The whole facts step, counted from the start of the snapshot. A source still busy after
    # this (a server that trickles its answer) becomes a note; the snapshot does not wait.
    facts_deadline_s: float = 150.0
    # The Wayback CDX server took 10 to 45 s per domain in live tests (29 Sep 2026); it runs
    # at the same time as the Google checks, so a long limit costs no waiting.
    wayback_timeout_s: float = 60.0

    # Core Web Vitals, 75th percentile (web.dev "Defining the Core Web Vitals thresholds"):
    # metric -> (good at or below, poor above).
    crux_form_factor: Literal["PHONE", "DESKTOP", "TABLET"] = "PHONE"
    vitals: dict[str, tuple[float, float]] = {
        "largest_contentful_paint": (2500, 4000),  # ms
        "interaction_to_next_paint": (200, 500),  # ms
        "cumulative_layout_shift": (0.1, 0.25),
    }

    @model_validator(mode="after")
    def _groups_fit_the_depth(self) -> "SnapshotSettings":
        groups = self.position_groups
        if any(a > b for a, b in groups) or any(b1 >= a2 for (_, b1), (a2, _) in pairwise(groups)):
            raise ValueError("position_groups must be ordered and must not overlap")
        if groups and groups[-1][1] > self.gap.depth:
            raise ValueError("the last position group goes deeper than the Google check")
        if self.gap.keywords not in self.keyword_options:
            raise ValueError(f"keywords must be one of {self.keyword_options}")
        return self

    def vital_status(self, metric: str, p75: float) -> Literal["good", "needs work", "poor"]:
        good, poor = self.vitals[metric]
        return "good" if p75 <= good else "poor" if p75 > poor else "needs work"


class Secrets(BaseSettings):
    """API keys, read from the environment or .env (never committed)."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    dataforseo_login: str = ""
    dataforseo_password: SecretStr = SecretStr("")
    deepseek_api_key: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")
    serper_api_key: SecretStr = SecretStr("")
    bing_webmaster_api_key: SecretStr = SecretStr("")
    openpagerank_api_key: SecretStr = SecretStr("")  # Site Snapshot link score (free)
    crux_api_key: SecretStr = SecretStr("")  # Chrome UX Report API (Site Snapshot speed; optional)
