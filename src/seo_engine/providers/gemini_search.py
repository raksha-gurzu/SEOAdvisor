"""Google results via Gemini grounding with Google Search (free tier ~500 requests/day).

Returns the pages Gemini cited while searching, in citation order. It is not the ranked
organic list, has no People Also Ask, and titles are often just the domain. Only the phrase
is sent to Google, never our page text.
"""

from typing import Any

import httpx

from seo_engine.config import ModelSettings, Secrets
from seo_engine.page_types import domain_of, guess_page_type
from seo_engine.providers.base import CostSink, DailyCache, no_cost, request_with_retry
from seo_engine.providers.embeddings import GEMINI_URL
from seo_engine.providers.search import SearchUnavailable, SerpItem, SerpResults

PROMPT = (
    'Search Google for "{phrase}" as a searcher in country {country} would. Name at least 10 '
    "different web pages from different sites that rank for it, most relevant first, one line "
    "each, and cite every page."
)
REDIRECT_HOST = "vertexaisearch.cloud.google.com"


def grounding_chunks(data: dict[str, Any]) -> tuple[list[tuple[str, str]], list[str]]:
    """(uri, title) pairs and the search queries from a generateContent response."""
    candidates = data.get("candidates") or [{}]
    meta = candidates[0].get("groundingMetadata") or {}
    chunks = [
        (c["web"]["uri"], c["web"].get("title") or "")
        for c in meta.get("groundingChunks") or []
        if (c.get("web") or {}).get("uri")
    ]
    return chunks, list(meta.get("webSearchQueries") or [])


class GeminiGroundedSearch:
    def __init__(
        self,
        models: ModelSettings,
        api_key: str,
        cache: DailyCache,
        cost_sink: CostSink = no_cost,
        client: httpx.Client | None = None,
        resolver: httpx.Client | None = None,
    ) -> None:
        self.models = models
        self.api_key = api_key
        self.cache = cache
        self.cost_sink = cost_sink
        self.http = client or httpx.Client(
            base_url=GEMINI_URL, timeout=90.0, headers={"x-goog-api-key": api_key}
        )
        self.resolver = resolver or httpx.Client(follow_redirects=False, timeout=15.0)

    @classmethod
    def from_env(
        cls, models: ModelSettings, cache: DailyCache, cost_sink: CostSink = no_cost
    ) -> "GeminiGroundedSearch":
        return cls(models, Secrets().gemini_api_key.get_secret_value(), cache, cost_sink)

    def resolve(self, uri: str) -> str:
        """Grounding URIs are Google redirects; follow one hop to the real page URL."""
        if REDIRECT_HOST not in uri:
            return uri
        try:
            resp = self.resolver.get(uri)
        except httpx.HTTPError:
            return uri
        return resp.headers.get("location") or uri

    def top(self, phrase: str, country: str, n: int) -> SerpResults:
        key = [self.models.grounding_model, PROMPT, phrase, country]  # new prompt, new cache entry
        cached = self.cache.get("grounded", key)
        if cached is None:
            if not self.api_key:
                raise SearchUnavailable("GEMINI_API_KEY not set")
            body = {
                "contents": [{"parts": [{"text": PROMPT.format(phrase=phrase, country=country)}]}],
                "tools": [{"google_search": {}}],
            }
            try:
                resp = request_with_retry(
                    self.http,
                    "POST",
                    f"models/{self.models.grounding_model}:generateContent",
                    json=body,
                    attempts=2,
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (400, 401, 403, 429):
                    raise SearchUnavailable(f"HTTP {exc.response.status_code}") from exc
                raise
            self.cost_sink(
                self.models.grounding_price_per_request,
                f"gemini.grounding.{self.models.grounding_model}",
            )
            chunks, queries = grounding_chunks(resp.json())
            pages = [(self.resolve(uri), title) for uri, title in chunks]
            cached = {"pages": pages, "queries": queries}
            self.cache.set("grounded", key, cached)

        items: list[SerpItem] = []
        seen: set[str] = set()
        for url, title in cached["pages"]:
            if url in seen or REDIRECT_HOST in url:
                continue
            seen.add(url)
            items.append(
                SerpItem(
                    rank=len(items) + 1,
                    url=url,
                    domain=domain_of(url),
                    title=title,
                    page_type=guess_page_type(url, title),
                )
            )
        # Gemini's own search queries are useful demand evidence, kept as related searches.
        return SerpResults(
            phrase=phrase,
            country=country,
            source="gemini-grounding",
            items=items[:n],
            features=[],
            related_searches=cached["queries"],
        )
