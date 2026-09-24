"""Demand data from the free Bing Webmaster Tools keyword API.

Numbers are Bing impressions, not Google volume: good for comparing phrases, not as
absolute Google demand. Difficulty is never taken from here (computed from the SERP).
"""

import statistics
from datetime import date, timedelta
from typing import Any

import httpx

from seo_engine.concurrency import pmap
from seo_engine.config import Secrets
from seo_engine.providers.autocomplete import GoogleAutocomplete, norm
from seo_engine.providers.base import DailyCache, request_with_retry
from seo_engine.providers.keywords import KeywordMetrics, RankedKeyword

BING_URL = "https://ssl.bing.com/webmaster/api.svc/json/"
WEEKS_PER_MONTH = 52 / 12


def monthly_from_weekly(rows: list[dict[str, Any]], weeks: int = 12) -> int:
    """Average of the most recent `weeks` weekly strict-match impressions, as a monthly figure."""
    recent = [int(r.get("Impressions") or 0) for r in rows][-weeks:]
    return round(statistics.fmean(recent) * WEEKS_PER_MONTH) if recent else 0


class BingKeywords:
    """KeywordProvider for free mode. Without an API key every volume is 0 (autocomplete
    remains the demand signal)."""

    def __init__(
        self,
        api_key: str,
        cache: DailyCache,
        autocomplete: GoogleAutocomplete,
        language: str = "en",
        workers: int = 4,
        client: httpx.Client | None = None,
        today: date | None = None,
    ) -> None:
        self.api_key = api_key
        self.cache = cache
        self.autocomplete_provider = autocomplete
        self.language = language
        self.workers = workers
        self.http = client or httpx.Client(base_url=BING_URL, timeout=30.0)
        self.today = today or date.today()

    @classmethod
    def from_env(
        cls,
        cache: DailyCache,
        autocomplete: GoogleAutocomplete,
        language: str = "en",
        workers: int = 4,
    ) -> "BingKeywords":
        key = Secrets().bing_webmaster_api_key.get_secret_value()
        return cls(key, cache, autocomplete, language, workers)

    def _get(self, method: str, params: dict[str, str]) -> list[dict[str, Any]]:
        cached = self.cache.get(f"bing_{method}", params)
        if cached is None:
            resp = request_with_retry(
                self.http, "GET", method, params={**params, "apikey": self.api_key}
            )
            cached = resp.json().get("d") or []
            self.cache.set(f"bing_{method}", params, cached)
        return cached

    def _locale(self, country: str) -> dict[str, str]:
        return {"country": country.lower(), "language": f"{self.language}-{country.upper()}"}

    def metrics(self, keywords: list[str], country: str) -> list[KeywordMetrics]:
        wanted = list(dict.fromkeys(norm(k) for k in keywords if k.strip()))
        if not self.api_key:
            return [KeywordMetrics(keyword=k) for k in wanted]

        def one(k: str) -> KeywordMetrics:
            rows = self._get("GetKeywordStats", {"q": k, **self._locale(country)})
            return KeywordMetrics(keyword=k, volume=monthly_from_weekly(rows))

        return pmap(one, wanted, self.workers)

    def autocomplete(self, phrase: str, country: str) -> list[str]:
        return self.autocomplete_provider.suggest(phrase, country)

    def suggestions(self, phrase: str, country: str, limit: int = 50) -> list[KeywordMetrics]:
        """Bing related keywords over the last 3 months, as monthly impressions."""
        if not self.api_key:
            return []
        start = self.today - timedelta(days=91)
        rows = self._get(
            "GetRelatedKeywords",
            {
                "q": norm(phrase),
                **self._locale(country),
                "startDate": start.isoformat(),
                "endDate": self.today.isoformat(),
            },
        )
        out = [
            KeywordMetrics(
                keyword=norm(r["Query"]), volume=round(int(r.get("Impressions") or 0) / 3)
            )
            for r in rows
            if r.get("Query")
        ]
        return sorted(out, key=lambda m: -m.volume)[:limit]

    def ranked_keywords(self, target: str, country: str, limit: int = 100) -> list[RankedKeyword]:
        return []  # no free source; free mode uses related keywords and autocomplete instead
