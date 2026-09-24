"""Run settings, tunable thresholds and secrets.

Every depth, cost and behaviour knob lives here (CLAUDE.md rule 9). Values marked
"tune" in docs/ARCHITECTURE.md are starting points to calibrate on the eval set.
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr
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
    headless_fallback: bool = True
    cache_dir: Path = PROJECT_ROOT / "cache"
    models: ModelSettings = Field(default_factory=ModelSettings)
    thresholds: Thresholds = Field(default_factory=Thresholds)


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
