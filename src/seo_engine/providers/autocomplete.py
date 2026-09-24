"""Google autocomplete via the public suggest endpoint (keyless, unofficial). Cached by day.

Google only suggests phrases people actually search, so a phrase that autocompletes to
itself is demand evidence in free mode.
"""

import httpx

from seo_engine.providers.base import DailyCache, request_with_retry

SUGGEST_URL = "https://suggestqueries.google.com/complete/search"


def norm(text: str) -> str:
    return " ".join(text.lower().split())


class GoogleAutocomplete:
    def __init__(
        self, cache: DailyCache, language: str = "en", client: httpx.Client | None = None
    ) -> None:
        self.cache = cache
        self.language = language
        self.http = client or httpx.Client(timeout=15.0, headers={"User-Agent": "Mozilla/5.0"})

    def suggest(self, phrase: str, country: str) -> list[str]:
        params = {
            "client": "firefox",
            "hl": self.language,
            "gl": country.lower(),
            "q": norm(phrase),
        }
        cached = self.cache.get("google_suggest", params)
        if cached is None:
            data = request_with_retry(self.http, "GET", SUGGEST_URL, params=params).json()
            cached = [s for s in (data[1] if len(data) > 1 else []) if isinstance(s, str)]
            self.cache.set("google_suggest", params, cached)
        return list(dict.fromkeys(norm(s) for s in cached))

    def is_searched(self, phrase: str, country: str) -> bool:
        return norm(phrase) in self.suggest(phrase, country)

    def variants(
        self, seed: str, country: str, prefixes: list[str], suffixes: list[str]
    ) -> list[str]:
        """Suggestions for "what is <seed>", "<seed> vs" and similar question patterns."""
        out: list[str] = []
        for q in [f"{p} {seed}" for p in prefixes] + [f"{seed} {s}" for s in suffixes]:
            out += self.suggest(q, country)
        return list(dict.fromkeys(out))
