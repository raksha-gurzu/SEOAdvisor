"""Thin DataForSEO v3 client shared by the search and keyword providers."""

from typing import Any

import httpx

from seo_engine.providers.base import request_with_retry

BASE_URL = "https://api.dataforseo.com/v3/"

# ISO country -> DataForSEO location_code. Extend as needed.
LOCATION_CODES: dict[str, int] = {
    "US": 2840,
    "GB": 2826,
    "CA": 2124,
    "AU": 2036,
    "IN": 2356,
    "NP": 2524,
    "DE": 2276,
    "FR": 2250,
    "NZ": 2554,
    "IE": 2372,
    "SG": 2702,
}


class DataForSEOError(RuntimeError):
    pass


def location_code(country: str) -> int:
    try:
        return LOCATION_CODES[country.upper()]
    except KeyError as exc:
        raise DataForSEOError(f"No DataForSEO location code for country {country!r}") from exc


class DataForSEOClient:
    def __init__(self, login: str, password: str, client: httpx.Client | None = None) -> None:
        if not login or not password:
            raise DataForSEOError("DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD are not set in .env")
        self.http = client or httpx.Client(
            base_url=BASE_URL, auth=(login, password), timeout=httpx.Timeout(60.0)
        )

    def post(self, endpoint: str, task: dict[str, Any]) -> tuple[dict[str, Any], float]:
        """POST one task; return (first result object, cost in USD)."""
        response = request_with_retry(self.http, "POST", endpoint, json=[task])
        body = response.json()
        if body.get("status_code") != 20000:
            raise DataForSEOError(f"{endpoint}: {body.get('status_message')}")
        task_out = body["tasks"][0]
        if task_out.get("status_code") != 20000:
            raise DataForSEOError(f"{endpoint}: {task_out.get('status_message')}")
        results = task_out.get("result") or [{}]
        return results[0] or {}, float(task_out.get("cost") or body.get("cost") or 0.0)
