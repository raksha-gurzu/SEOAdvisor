"""Google results provider (docs/ARCHITECTURE.md §4). Tools use `SearchProvider` only."""

import time
from typing import Any, Protocol

from pydantic import BaseModel

from seo_engine.config import Secrets, Settings
from seo_engine.page_types import guess_page_type
from seo_engine.providers.base import CostSink, DailyCache, no_cost
from seo_engine.providers.dataforseo import DataForSEOClient, DataForSEOError, location_code


class SerpItem(BaseModel):
    rank: int
    url: str
    domain: str
    title: str = ""
    description: str = ""
    page_type: str = "unknown"


class SerpResults(BaseModel):
    phrase: str
    country: str
    source: str = "google"  # "google" (ranked organic list) or "gemini-grounding" (cited pages)
    items: list[SerpItem]
    features: list[str] = []  # SERP feature types, e.g. "people_also_ask", "video"
    people_also_ask: list[str] = []
    related_searches: list[str] = []


class SearchProvider(Protocol):
    def top(self, phrase: str, country: str, n: int) -> SerpResults: ...


class SearchUnavailable(RuntimeError):
    """No key, no credits or quota used up: the next provider should take over."""


class FallbackSearch:
    """Try providers in order; move on when one is unavailable (free mode: Serper -> Gemini)."""

    def __init__(self, providers: list[SearchProvider]) -> None:
        self.providers = providers

    def top(self, phrase: str, country: str, n: int) -> SerpResults:
        reasons: list[str] = []
        for provider in self.providers:
            try:
                return provider.top(phrase, country, n)
            except SearchUnavailable as exc:
                reasons.append(f"{type(provider).__name__}: {exc}")
        raise SearchUnavailable("no search provider available; " + "; ".join(reasons))


def parse_serp(result: dict[str, Any], phrase: str, country: str, n: int) -> SerpResults:
    """Turn a DataForSEO organic/advanced result into `SerpResults`."""
    items: list[SerpItem] = []
    features: list[str] = []
    paa: list[str] = []
    related: list[str] = []
    for item in result.get("items") or []:
        kind = item.get("type", "")
        if kind == "organic":
            if len(items) < n:
                items.append(
                    SerpItem(
                        rank=item.get("rank_group") or len(items) + 1,
                        url=item["url"],
                        domain=item.get("domain", ""),
                        title=item.get("title") or "",
                        description=item.get("description") or "",
                        page_type=guess_page_type(item["url"], item.get("title") or ""),
                    )
                )
            continue
        if kind and kind not in features:
            features.append(kind)
        if kind == "people_also_ask":
            paa += [q["title"] for q in item.get("items") or [] if q.get("title")]
        elif kind in ("related_searches", "people_also_search"):
            related += [s for s in item.get("items") or [] if isinstance(s, str)]
    return SerpResults(
        phrase=phrase,
        country=country,
        items=items,
        features=features,
        people_also_ask=paa,
        related_searches=related,
    )


class DataForSEOSearch:
    """Google organic SERP via DataForSEO, cached by day, cost reported per paid call."""

    ORGANIC = "serp/google/organic"

    def __init__(
        self,
        client: DataForSEOClient,
        cache: DailyCache,
        settings: Settings,
        cost_sink: CostSink = no_cost,
        poll_s: float = 5.0,
    ) -> None:
        self.client = client
        self.cache = cache
        self.settings = settings
        self.cost_sink = cost_sink
        self.poll_s = poll_s

    @classmethod
    def from_env(cls, settings: Settings, cost_sink: CostSink = no_cost) -> "DataForSEOSearch":
        secrets = Secrets()
        client = DataForSEOClient(
            secrets.dataforseo_login, secrets.dataforseo_password.get_secret_value()
        )
        return cls(client, DailyCache(settings.cache_dir), settings, cost_sink)

    def top(self, phrase: str, country: str, n: int) -> SerpResults:
        depth = 10 if n <= 10 else 20 if n <= 20 else 100
        task = {
            "keyword": phrase,
            "location_code": location_code(country),
            "language_code": self.settings.language,
            "device": "desktop",
            "depth": depth,
        }
        cached = self.cache.get("serp", task)
        if cached is None:
            cached, cost = self._fetch(task)
            self.cost_sink(cost, "dataforseo.serp")
            self.cache.set("serp", task, cached)
        return parse_serp(cached, phrase, country, n)

    def _fetch(self, task: dict[str, Any]) -> tuple[dict[str, Any], float]:
        queue = self.settings.serp_queue
        if queue == "live":
            return self.client.post(f"{self.ORGANIC}/live/advanced", task)
        return self._fetch_queued(task, priority=2 if queue == "priority" else 1)

    def _fetch_queued(self, task: dict[str, Any], priority: int) -> tuple[dict[str, Any], float]:
        response = self.client.http.post(
            f"{self.ORGANIC}/task_post", json=[{**task, "priority": priority}]
        )
        response.raise_for_status()
        posted = response.json()["tasks"][0]
        if posted.get("status_code") not in (20000, 20100):
            raise DataForSEOError(f"task_post: {posted.get('status_message')}")
        task_id, cost = posted["id"], float(posted.get("cost") or 0.0)
        deadline = time.monotonic() + self.settings.time_budget_s
        while time.monotonic() < deadline:
            time.sleep(self.poll_s)
            got = self.client.http.get(f"{self.ORGANIC}/task_get/advanced/{task_id}")
            got.raise_for_status()
            out = got.json()["tasks"][0]
            if out.get("status_code") == 20000:
                return (out.get("result") or [{}])[0], cost
            if out.get("status_code") not in (40601, 40602):  # handed / in queue
                raise DataForSEOError(f"task_get: {out.get('status_message')}")
        raise DataForSEOError(f"SERP task {task_id} not ready within time budget")
