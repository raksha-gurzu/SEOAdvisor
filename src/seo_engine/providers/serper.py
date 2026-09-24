"""Google results from Serper.dev (free: 2,500 one-time queries). Cached by day."""

from typing import Any

import httpx

from seo_engine.config import Secrets
from seo_engine.page_types import domain_of, guess_page_type
from seo_engine.providers.base import DailyCache, request_with_retry
from seo_engine.providers.search import SearchUnavailable, SerpItem, SerpResults

SERPER_URL = "https://google.serper.dev/"
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


def parse_serper(data: dict[str, Any], phrase: str, country: str, n: int) -> SerpResults:
    items = [
        SerpItem(
            rank=int(o.get("position") or i),
            url=o["link"],
            domain=domain_of(o["link"]),
            title=o.get("title") or "",
            description=o.get("snippet") or "",
            page_type=guess_page_type(o["link"], o.get("title") or ""),
        )
        for i, o in enumerate(data.get("organic") or [], 1)
        if o.get("link")
    ][:n]
    return SerpResults(
        phrase=phrase,
        country=country,
        source="google",
        items=items,
        features=[f for k, f in FEATURE_KEYS.items() if data.get(k)],
        people_also_ask=[
            q["question"] for q in data.get("peopleAlsoAsk") or [] if q.get("question")
        ],
        related_searches=[r["query"] for r in data.get("relatedSearches") or [] if r.get("query")],
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

    @classmethod
    def from_env(cls, cache: DailyCache, language: str = "en") -> "SerperSearch":
        return cls(Secrets().serper_api_key.get_secret_value(), cache, language)

    def top(self, phrase: str, country: str, n: int) -> SerpResults:
        body = {
            "q": phrase,
            "gl": country.lower(),
            "hl": self.language,
            "num": 10 if n <= 10 else 20,
        }
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
            self.cache.set("serper", body, cached)
        return parse_serper(cached, phrase, country, n)
