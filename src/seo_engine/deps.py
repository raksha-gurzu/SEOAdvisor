"""Wires providers for one run, with every paid call reporting cost into the Run."""

from dataclasses import dataclass

from seo_engine.models import Run
from seo_engine.providers.autocomplete import GoogleAutocomplete
from seo_engine.providers.base import DailyCache
from seo_engine.providers.bing import BingKeywords
from seo_engine.providers.embeddings import EmbeddingProvider, GeminiEmbeddings
from seo_engine.providers.fetcher import HttpFetcher, PageFetcher
from seo_engine.providers.gemini_search import GeminiGroundedSearch
from seo_engine.providers.keywords import DataForSEOKeywords, KeywordProvider
from seo_engine.providers.llm import DeepSeekLLM, LLMProvider
from seo_engine.providers.search import DataForSEOSearch, FallbackSearch, SearchProvider
from seo_engine.providers.serper import SerperSearch
from seo_engine.providers.tranco import RankLookup, TrancoRanks


@dataclass
class Deps:
    search: SearchProvider
    keywords: KeywordProvider
    fetcher: PageFetcher
    llm: LLMProvider
    embed: EmbeddingProvider
    ranks: RankLookup | None = None  # free mode: site strength for computed difficulty
    autocomplete: GoogleAutocomplete | None = None  # free mode: demand + question variants


def from_env(run: Run) -> Deps:
    s = run.settings
    cache = DailyCache(s.cache_dir)
    llm = DeepSeekLLM.from_env(s.models, run.add_cost)
    embed = GeminiEmbeddings.from_env(s.models, cache, run.add_cost)
    fetcher = HttpFetcher(s, cache)
    if s.data_mode == "dataforseo":
        return Deps(
            search=DataForSEOSearch.from_env(s, run.add_cost),
            keywords=DataForSEOKeywords.from_env(s, run.add_cost),
            fetcher=fetcher,
            llm=llm,
            embed=embed,
        )
    autocomplete = GoogleAutocomplete(cache, s.language)
    return Deps(
        search=FallbackSearch(
            [
                SerperSearch.from_env(cache, s.language),
                GeminiGroundedSearch.from_env(s.models, cache, run.add_cost),
            ]
        ),
        keywords=BingKeywords.from_env(cache, autocomplete, s.language, workers=4),
        fetcher=fetcher,
        llm=llm,
        embed=embed,
        ranks=TrancoRanks(s.cache_dir),
        autocomplete=autocomplete,
    )
