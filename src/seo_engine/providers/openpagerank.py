"""Link score from Open PageRank (free key, 30,000 domains a month; docs/SITE-SNAPSHOT-PLAN.md F2).

A 0-10 score from the Common Crawl link graph, with an authority-weighted count of referring
domains and a monthly history (F18). It is a link measure from a third party: the UI names it
"Open PageRank", never an "authority score" (O4, O7).
"""

import time
from collections.abc import Callable
from datetime import date
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel

from seo_engine.config import Secrets
from seo_engine.providers.base import DailyCache, request_with_retry

OPR_URL = "https://openpagerank.keywordseverywhere.com/v1/domains/bulk"
SOURCE = "Open PageRank (Common Crawl link graph)"

FactStatus = Literal["ok", "not_found", "not_set_up", "error"]


class LinkScorePoint(BaseModel):
    month: date
    score: float
    estimated: bool = False  # Open PageRank fills some months by estimate


class LinkScore(BaseModel):
    domain: str
    status: FactStatus
    score: float | None = None  # 0-10
    rank: int | None = None  # global position by Open PageRank
    referring_domains: int | None = None  # authority-weighted count, not a raw link count
    history: list[LinkScorePoint] = []
    source: str = SOURCE
    note: str = ""


class LinkScoreProvider(Protocol):
    def score(self, domain: str) -> LinkScore: ...


def bare_domain(domain: str) -> str:
    return domain.strip().lower().removeprefix("www.").rstrip(".")


def parse_result(domain: str, item: dict[str, Any]) -> LinkScore:
    if not item.get("found"):
        return LinkScore(domain=domain, status="not_found", note="Open PageRank has no data")
    history = [
        LinkScorePoint(
            month=date.fromisoformat(p["date"]),
            score=float(p["open_page_rank"]),
            estimated=bool(p.get("estimated")),
        )
        for p in item.get("history") or []
        if p.get("open_page_rank") is not None
    ]
    return LinkScore(
        domain=domain,
        status="ok",
        score=item.get("open_page_rank"),
        rank=item.get("rank"),
        referring_domains=item.get("referring_domains"),
        history=sorted(history, key=lambda p: p.month),
    )


class OpenPageRank:
    """LinkScoreProvider. Without a key every answer is `not_set_up`, never an error."""

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
    def from_env(cls, cache: DailyCache, timeout_s: float = 20.0) -> "OpenPageRank":
        return cls(Secrets().openpagerank_api_key.get_secret_value(), cache, timeout_s=timeout_s)

    def score(self, domain: str) -> LinkScore:
        domain = bare_domain(domain)
        if not self.api_key:
            return LinkScore(domain=domain, status="not_set_up", note="no OPENPAGERANK_API_KEY")
        cached = self.cache.get("openpagerank", domain)
        if cached is not None:
            return LinkScore.model_validate(cached)
        try:
            resp = request_with_retry(
                self.http,
                "POST",
                OPR_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"domains": [domain], "include_history": True},
                sleep=self.sleep,
            )
            item = next(iter(resp.json().get("results") or []), {})
            result = parse_result(domain, item)
        except httpx.HTTPStatusError as exc:
            reason = "invalid key" if exc.response.status_code == 401 else "request failed"
            return LinkScore(
                domain=domain,
                status="error",
                note=f"Open PageRank: HTTP {exc.response.status_code} ({reason})",
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:  # network or bad data
            return LinkScore(
                domain=domain, status="error", note=f"Open PageRank: {type(exc).__name__}"
            )
        self.cache.set("openpagerank", domain, result.model_dump(mode="json"))
        return result
