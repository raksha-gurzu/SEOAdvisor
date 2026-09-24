"""Keyword data provider: volume, difficulty, intent, autocomplete, ranked keywords.

Difficulty comes from DataForSEO only (CLAUDE.md rule 7).
"""

from typing import Any, Protocol

from pydantic import BaseModel

from seo_engine.config import Secrets, Settings
from seo_engine.providers.base import CostSink, DailyCache, no_cost
from seo_engine.providers.dataforseo import DataForSEOClient, location_code

BULK_LIMIT = 700  # keyword_overview accepts up to 700 keywords per task


class KeywordMetrics(BaseModel):
    keyword: str
    volume: int = 0
    difficulty: int | None = None  # None = DataForSEO has no score
    intent: str = "unknown"


class RankedKeyword(KeywordMetrics):
    rank: int
    url: str = ""


class KeywordProvider(Protocol):
    def metrics(self, keywords: list[str], country: str) -> list[KeywordMetrics]: ...
    def autocomplete(self, phrase: str, country: str) -> list[str]: ...
    def suggestions(self, phrase: str, country: str, limit: int) -> list[KeywordMetrics]: ...
    def ranked_keywords(self, target: str, country: str, limit: int) -> list[RankedKeyword]: ...


def _metrics_from(data: dict[str, Any]) -> KeywordMetrics:
    info = data.get("keyword_info") or {}
    props = data.get("keyword_properties") or {}
    intent = data.get("search_intent_info") or {}
    return KeywordMetrics(
        keyword=data.get("keyword", ""),
        volume=int(info.get("search_volume") or 0),
        difficulty=props.get("keyword_difficulty"),
        intent=intent.get("main_intent") or "unknown",
    )


def normalise(keyword: str) -> str:
    return " ".join(keyword.lower().split())


class DataForSEOKeywords:
    LABS = "dataforseo_labs/google"

    def __init__(
        self,
        client: DataForSEOClient,
        cache: DailyCache,
        settings: Settings,
        cost_sink: CostSink = no_cost,
    ) -> None:
        self.client = client
        self.cache = cache
        self.settings = settings
        self.cost_sink = cost_sink

    @classmethod
    def from_env(cls, settings: Settings, cost_sink: CostSink = no_cost) -> "DataForSEOKeywords":
        secrets = Secrets()
        client = DataForSEOClient(
            secrets.dataforseo_login, secrets.dataforseo_password.get_secret_value()
        )
        return cls(client, DailyCache(settings.cache_dir), settings, cost_sink)

    def _call(self, namespace: str, endpoint: str, task: dict[str, Any]) -> dict[str, Any]:
        cached = self.cache.get(namespace, task)
        if cached is None:
            cached, cost = self.client.post(endpoint, task)
            self.cost_sink(cost, f"dataforseo.{namespace}")
            self.cache.set(namespace, task, cached)
        return cached

    def _base(self, country: str) -> dict[str, Any]:
        return {"location_code": location_code(country), "language_code": self.settings.language}

    def metrics(self, keywords: list[str], country: str) -> list[KeywordMetrics]:
        """Volume, difficulty and intent for many keywords in as few calls as possible.

        Keywords DataForSEO has no data for come back with volume 0.
        """
        wanted = list(dict.fromkeys(normalise(k) for k in keywords if k.strip()))
        found: dict[str, KeywordMetrics] = {}
        for start in range(0, len(wanted), BULK_LIMIT):
            chunk = sorted(wanted[start : start + BULK_LIMIT])
            task = {**self._base(country), "keywords": chunk}
            result = self._call("keyword_overview", f"{self.LABS}/keyword_overview/live", task)
            for item in result.get("items") or []:
                m = _metrics_from(item)
                found[normalise(m.keyword)] = m
        return [found.get(k, KeywordMetrics(keyword=k)) for k in wanted]

    def autocomplete(self, phrase: str, country: str) -> list[str]:
        task = {**self._base(country), "keyword": phrase}
        result = self._call("autocomplete", "serp/google/autocomplete/live/advanced", task)
        out = [i["suggestion"] for i in result.get("items") or [] if i.get("suggestion")]
        return list(dict.fromkeys(out))

    def suggestions(self, phrase: str, country: str, limit: int = 50) -> list[KeywordMetrics]:
        task = {**self._base(country), "keyword": phrase, "limit": limit}
        result = self._call("keyword_suggestions", f"{self.LABS}/keyword_suggestions/live", task)
        return [_metrics_from(item) for item in result.get("items") or []]

    def ranked_keywords(self, target: str, country: str, limit: int = 100) -> list[RankedKeyword]:
        """Phrases a domain or single page (absolute URL) ranks for."""
        task = {**self._base(country), "target": target, "limit": limit}
        result = self._call("ranked_keywords", f"{self.LABS}/ranked_keywords/live", task)
        out: list[RankedKeyword] = []
        for item in result.get("items") or []:
            m = _metrics_from(item.get("keyword_data") or {})
            serp = (item.get("ranked_serp_element") or {}).get("serp_item") or {}
            out.append(
                RankedKeyword(
                    **m.model_dump(), rank=serp.get("rank_group") or 0, url=serp.get("url") or ""
                )
            )
        return out
