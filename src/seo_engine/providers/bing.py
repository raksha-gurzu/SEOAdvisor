"""Demand data from the free Bing Webmaster Tools keyword API.

Numbers are Bing impressions, not Google volume: good for comparing phrases, not as
absolute Google demand. Difficulty is never taken from here (computed from the SERP).
"""

import re
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from seo_engine.concurrency import pmap
from seo_engine.config import Secrets
from seo_engine.providers.autocomplete import GoogleAutocomplete, norm
from seo_engine.providers.base import DailyCache, request_with_retry
from seo_engine.providers.keywords import KeywordMetrics, RankedKeyword

BING_URL = "https://ssl.bing.com/webmaster/api.svc/json/"
WEEKS_PER_MONTH = 52 / 12


MS_DATE = re.compile(r"/Date\((-?\d+)")  # WCF JSON date: "/Date(1790380800000)/"


def row_date(row: dict[str, Any]) -> date | None:
    match = MS_DATE.match(str(row.get("Date") or ""))
    return datetime.fromtimestamp(int(match.group(1)) / 1000, UTC).date() if match else None


def monthly_from_weekly(rows: list[dict[str, Any]], today: date, weeks: int = 12) -> int:
    """Strict-match impressions over the `weeks` weeks up to `today`, as a monthly figure.

    Bing leaves out weeks with no impressions, so the total is divided by the length of the
    window, not by the number of rows returned (one row of 1 impression is ~0/month, not 4).
    Trade-off: a Bing outage week also counts as 0 (live 28 Sep 2026: week of 22 Aug missing
    for a ~500/week phrase), under-counting by 1/weeks; averaging rows over-counted rare
    phrases 4-10x instead.
    """
    start = today - timedelta(weeks=weeks)
    total = sum(
        int(r.get("Impressions") or 0)
        for r in rows
        if (d := row_date(r)) is not None and start < d <= today
    )
    return round(total / weeks * WEEKS_PER_MONTH)


class BingError(RuntimeError):
    """A Bing API failure. The message never contains the API key (it travels in the URL)."""


class BingThrottled(BingError):
    """Bing's undocumented rate limit: HTTP 400 with "ThrottleUser" (live, 29 Sep 2026)."""


THROTTLE_WAITS_S = (5.0, 20.0)  # back-off before giving up on a throttled call


class BingKeywords:
    """KeywordProvider for free mode. Without an API key every volume is 0 (autocomplete
    remains the demand signal). When Bing throttles, `metrics` returns 0 for the keywords it
    could not measure and lists them in `unmeasured`, so callers can show "not measured".
    """

    def __init__(
        self,
        api_key: str,
        cache: DailyCache,
        autocomplete: GoogleAutocomplete,
        language: str = "en",
        workers: int = 4,
        client: httpx.Client | None = None,
        today: date | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_key = api_key
        self.cache = cache
        self.autocomplete_provider = autocomplete
        self.language = language
        self.workers = workers
        self.http = client or httpx.Client(base_url=BING_URL, timeout=30.0)
        self.today = today or date.today()
        self.sleep = sleep
        self.throttled = False  # once throttled, stop calling for the rest of this run
        self.unmeasured: set[str] = set()

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
            cached = self._call(method, params)
            self.cache.set(f"bing_{method}", params, cached)
        return cached

    def _call(self, method: str, params: dict[str, str]) -> list[dict[str, Any]]:
        for wait in (*THROTTLE_WAITS_S, None):
            if self.throttled:
                raise BingThrottled("Bing keyword API limit reached (ThrottleUser)")
            try:
                resp = request_with_retry(
                    self.http,
                    "GET",
                    method,
                    params={**params, "apikey": self.api_key},
                    sleep=self.sleep,
                )
                return resp.json().get("d") or []
            except httpx.HTTPStatusError as exc:
                body = exc.response.text[:200].replace(self.api_key, "<key>")
                if "ThrottleUser" not in body:
                    raise BingError(
                        f"Bing {method}: HTTP {exc.response.status_code} {body}"
                    ) from None
            except httpx.TransportError as exc:
                raise BingError(f"Bing {method}: {type(exc).__name__}") from None
            if wait is None:
                self.throttled = True
            else:
                self.sleep(wait)
        raise BingThrottled("Bing keyword API limit reached (ThrottleUser)")

    def _locale(self, country: str) -> dict[str, str]:
        return {"country": country.lower(), "language": f"{self.language}-{country.upper()}"}

    def metrics(self, keywords: list[str], country: str) -> list[KeywordMetrics]:
        wanted = list(dict.fromkeys(norm(k) for k in keywords if k.strip()))
        if not self.api_key:
            return [KeywordMetrics(keyword=k) for k in wanted]

        def one(k: str) -> KeywordMetrics:
            try:
                rows = self._get("GetKeywordStats", {"q": k, **self._locale(country)})
            except BingError:  # the limit, or any other Bing failure: "not measured", not 0
                self.unmeasured.add(k)
                return KeywordMetrics(keyword=k)
            return KeywordMetrics(keyword=k, volume=monthly_from_weekly(rows, self.today))

        return pmap(one, wanted, self.workers)

    def autocomplete(self, phrase: str, country: str) -> list[str]:
        return self.autocomplete_provider.suggest(phrase, country)

    def suggestions(self, phrase: str, country: str, limit: int = 50) -> list[KeywordMetrics]:
        """Bing related keywords over the last 3 months, as monthly impressions."""
        if not self.api_key:
            return []
        start = self.today - timedelta(days=91)
        try:
            rows = self._related(phrase, country, start)
        except BingError:
            return []
        out = [
            KeywordMetrics(
                keyword=norm(r["Query"]), volume=round(int(r.get("Impressions") or 0) / 3)
            )
            for r in rows
            if r.get("Query")
        ]
        return sorted(out, key=lambda m: -m.volume)[:limit]

    def _related(self, phrase: str, country: str, start: date) -> list[dict[str, Any]]:
        return self._get(
            "GetRelatedKeywords",
            {
                "q": norm(phrase),
                **self._locale(country),
                "startDate": start.isoformat(),
                "endDate": self.today.isoformat(),
            },
        )

    def ranked_keywords(self, target: str, country: str, limit: int = 100) -> list[RankedKeyword]:
        return []  # no free source; free mode uses related keywords and autocomplete instead
