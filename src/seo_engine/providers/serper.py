"""Google results from Serper.dev (free: 2,500 one-time queries). Cached by day.

Since September 2025 Google returns 10 results per request, whatever `num` asks for (live
test 28 Sep 2026: `num: 20` gave 10 results for 1 credit). Deeper results come page by page:
1 credit per page of 10, positions restarting at 1 on each page (docs/KEYWORD-GAP-PLAN.md R1,
R4, R5).
"""

import math
import threading
from typing import Any

import httpx

from seo_engine.config import Secrets
from seo_engine.page_types import domain_of, guess_page_type, owns
from seo_engine.providers.base import DailyCache, request_with_retry
from seo_engine.providers.search import SearchUnavailable, SerpItem, SerpResults

SERPER_URL = "https://google.serper.dev/"
PAGE_SIZE = 10
FEATURE_KEYS = {
    "answerBox": "featured_snippet",
    "knowledgeGraph": "knowledge_graph",
    "peopleAlsoAsk": "people_also_ask",
    "relatedSearches": "related_searches",
    "topStories": "top_stories",
    "videos": "video",
    "images": "images",
    "places": "local_pack",
    "shopping": "shopping",
}


def page_items(data: dict[str, Any], page: int) -> list[SerpItem]:
    """Organic results of one page, ranked from the top of the whole results list."""
    offset = (page - 1) * PAGE_SIZE
    return [
        SerpItem(
            rank=offset + int(o.get("position") or i),
            url=o["link"],
            domain=domain_of(o["link"]),
            title=o.get("title") or "",
            description=o.get("snippet") or "",
            page_type=guess_page_type(o["link"], o.get("title") or ""),
        )
        for i, o in enumerate(data.get("organic") or [], 1)
        if o.get("link")
    ]


def parse_serper(data: dict[str, Any], phrase: str, country: str, n: int) -> SerpResults:
    """One page of results (page 1)."""
    return parse_serper_pages([data], phrase, country, n)


def parse_serper_pages(
    pages: list[dict[str, Any]], phrase: str, country: str, n: int
) -> SerpResults:
    """Pages 1..k joined into one ranked list. SERP features, People Also Ask and related
    searches come from page 1, where Google shows them."""
    items: list[SerpItem] = []
    seen: set[str] = set()
    for number, data in enumerate(pages, 1):
        for item in page_items(data, number):
            if item.url not in seen:  # a result can repeat on the next page
                seen.add(item.url)
                items.append(item)
    first = pages[0] if pages else {}
    return SerpResults(
        phrase=phrase,
        country=country,
        source="google",
        items=items[:n],
        features=[f for k, f in FEATURE_KEYS.items() if first.get(k)],
        people_also_ask=[
            q["question"] for q in first.get("peopleAlsoAsk") or [] if q.get("question")
        ],
        related_searches=[r["query"] for r in first.get("relatedSearches") or [] if r.get("query")],
    )


class SerperSearch:
    def __init__(
        self,
        api_key: str,
        cache: DailyCache,
        language: str = "en",
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.cache = cache
        self.language = language
        self.http = client or httpx.Client(
            base_url=SERPER_URL, timeout=30.0, headers={"X-API-KEY": api_key}
        )
        self.credits_used = 0  # credits spent by this instance (cached pages cost nothing)
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls, cache: DailyCache, language: str = "en") -> "SerperSearch":
        return cls(Secrets().serper_api_key.get_secret_value(), cache, language)

    def _page(self, phrase: str, country: str, page: int) -> dict[str, Any]:
        body: dict[str, Any] = {
            "q": phrase,
            "gl": country.lower(),
            "hl": self.language,
            "num": PAGE_SIZE,
        }
        if page > 1:
            body["page"] = page  # page 1 keeps its old cache key
        cached = self.cache.get("serper", body)
        if cached is None:
            if not self.api_key:
                raise SearchUnavailable("SERPER_API_KEY not set")
            try:
                resp = request_with_retry(self.http, "POST", "search", json=body)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (400, 401, 402, 403, 429):
                    raise SearchUnavailable(
                        f"HTTP {exc.response.status_code}: {exc.response.text[:120]}"
                    ) from exc
                raise
            cached = resp.json()
            with self._lock:
                self.credits_used += int(cached.get("credits") or 1)
            self.cache.set("serper", body, cached)
        return cached

    def top(
        self, phrase: str, country: str, n: int, stop_domains: frozenset[str] = frozenset()
    ) -> SerpResults:
        """Top n results, fetched page by page. Paging stops at an empty page, or once every
        domain in `stop_domains` has appeared (the rest of the list cannot change that)."""
        pages: list[dict[str, Any]] = []
        for page in range(1, math.ceil(n / PAGE_SIZE) + 1):
            data = self._page(phrase, country, page)
            if page > 1 and not data.get("organic"):
                break
            pages.append(data)
            if not data.get("organic"):
                break
            if stop_domains:
                found = {i.domain for p, d in enumerate(pages, 1) for i in page_items(d, p)}
                if all(any(owns(f, t) for f in found) for t in stop_domains):
                    break
        return parse_serper_pages(pages, phrase, country, n)
