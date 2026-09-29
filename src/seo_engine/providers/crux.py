"""Speed for real visitors from the Chrome UX Report API (free key; plan F7, F8, F16).

Values are the 75th percentile over a 28-day rolling window. Many small sites have no data:
the API then answers HTTP 404 "chrome ux report data not found", which is `no_data`, not an
error. It also has no data for an origin whose homepage redirects, so callers pass the
origin that served the homepage. Without `CRUX_API_KEY` every answer is `not_set_up` (Q2).
The key travels in a header, so it never appears in URLs or error messages.
CrUX data is CC BY 4.0: the UI shows `ATTRIBUTION`.
"""

import time
from collections.abc import Callable
from datetime import date
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel

from seo_engine.config import Secrets
from seo_engine.providers.base import DailyCache, request_with_retry

CRUX_URL = "https://chromeuxreport.googleapis.com/v1/records:queryRecord"
ATTRIBUTION = "Chrome UX Report, by Google, licensed under CC BY 4.0"
METRICS = ("largest_contentful_paint", "interaction_to_next_paint", "cumulative_layout_shift")

SpeedStatus = Literal["ok", "no_data", "not_set_up", "error"]


class Speed(BaseModel):
    origin: str
    status: SpeedStatus
    form_factor: str = "PHONE"
    p75: dict[str, float] = {}  # metric -> 75th percentile (ms, or a score for CLS)
    first_day: date | None = None
    last_day: date | None = None
    note: str = ""


class SpeedProvider(Protocol):
    def speed(self, origin: str, form_factor: str = "PHONE") -> Speed: ...


def api_date(d: dict[str, int] | None) -> date | None:
    try:
        return date(d["year"], d["month"], d["day"]) if d else None
    except (KeyError, TypeError, ValueError):
        return None


def parse_record(origin: str, form_factor: str, body: dict[str, Any]) -> Speed:
    record = body.get("record") or {}
    p75: dict[str, float] = {}
    for name in METRICS:
        value = ((record.get("metrics") or {}).get(name) or {}).get("percentiles", {}).get("p75")
        try:
            if value is not None:
                p75[name] = float(value)  # CLS comes as a string ("0.05")
        except (TypeError, ValueError):
            continue
    period = body.get("record", {}).get("collectionPeriod") or {}
    return Speed(
        origin=origin,
        status="ok" if p75 else "no_data",
        form_factor=form_factor,
        p75=p75,
        first_day=api_date(period.get("firstDate")),
        last_day=api_date(period.get("lastDate")),
        note="" if p75 else "no Core Web Vitals in the CrUX record",
    )


class CruxSpeed:
    def __init__(
        self,
        api_key: str,
        cache: DailyCache,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        timeout_s: float = 20.0,
    ) -> None:
        self.api_key = api_key
        self.cache = cache
        self.http = client or httpx.Client(timeout=timeout_s)
        self.sleep = sleep

    @classmethod
    def from_env(cls, cache: DailyCache, timeout_s: float = 20.0) -> "CruxSpeed":
        return cls(Secrets().crux_api_key.get_secret_value(), cache, timeout_s=timeout_s)

    def speed(self, origin: str, form_factor: str = "PHONE") -> Speed:
        origin = origin.rstrip("/").lower()
        if not self.api_key:
            return Speed(
                origin=origin, status="not_set_up", form_factor=form_factor, note="no CRUX_API_KEY"
            )
        key = [origin, form_factor]
        cached = self.cache.get("crux", key)
        if cached is not None:
            return Speed.model_validate(cached)
        try:
            resp = request_with_retry(
                self.http,
                "POST",
                CRUX_URL,
                headers={"X-Goog-Api-Key": self.api_key},
                json={"origin": origin, "formFactor": form_factor, "metrics": list(METRICS)},
                sleep=self.sleep,
            )
            result = parse_record(origin, form_factor, resp.json())
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                return Speed(
                    origin=origin,
                    status="error",
                    form_factor=form_factor,
                    note=f"CrUX: HTTP {exc.response.status_code}",
                )
            result = Speed(
                origin=origin,
                status="no_data",
                form_factor=form_factor,
                note="not enough Chrome visitors to measure",
            )
        except (httpx.HTTPError, ValueError) as exc:
            return Speed(
                origin=origin,
                status="error",
                form_factor=form_factor,
                note=f"CrUX: {type(exc).__name__}",
            )
        self.cache.set("crux", key, result.model_dump(mode="json"))
        return result
