"""Keyword Gap step 3: where each domain ranks on Google (docs/KEYWORD-GAP-PLAN.md Step 3).

One search per keyword to `GapSettings.depth` (top 20 by default, 2 pages). A domain that is
not in the results seen is "not in top N", never "does not rank" (R2). Positions are one
snapshot; Google reorders a few places between requests (R11).
"""

import threading
from collections.abc import Callable

import httpx
from pydantic import BaseModel

from seo_engine.concurrency import pmap
from seo_engine.config import GapSettings
from seo_engine.page_types import owns
from seo_engine.providers.search import SearchProvider, SearchUnavailable, SerpItem


class DomainPosition(BaseModel):
    position: int | None = None  # None: not in the results checked
    url: str = ""  # the domain's best-ranking page


class KeywordRanking(BaseModel):
    keyword: str
    positions: dict[str, DomainPosition]  # every domain of the analysis, ours first
    results_seen: int  # organic results read (the depth, or fewer when Google has fewer)
    results: list[SerpItem]  # for row details, difficulty, intent and clustering
    features: list[str] = []
    people_also_ask: list[str] = []
    related_searches: list[str] = []

    def competitor_ranks(self, competitors: list[str]) -> bool:
        return any(
            self.positions[d].position is not None for d in competitors if d in self.positions
        )


class RankCheck(BaseModel):
    rankings: list[KeywordRanking]
    not_checked: list[str] = []  # search unavailable (credits out) or failed
    unavailable: bool = False  # the search provider stopped (credits out), not one failure
    notes: list[str] = []


def best_position(items: list[SerpItem], domain: str) -> DomainPosition:
    """The domain's highest result; subdomains count (blog.moxo.com is moxo.com)."""
    for item in sorted(items, key=lambda i: i.rank):
        if owns(item.domain, domain):
            return DomainPosition(position=item.rank, url=item.url)
    return DomainPosition()


def check_ranks(
    keywords: list[str],
    domains: list[str],
    s: GapSettings,
    search: SearchProvider,
    progress: Callable[[int, int], None] | None = None,
) -> RankCheck:
    """`domains[0]` is our site. Paging skips page 2 when every domain is on page 1.
    `progress(done, total)` is called after each keyword, for "Checking Google 34/60"."""
    stop = frozenset(domains)
    done = [0]
    lock = threading.Lock()

    def tick() -> None:
        if progress:
            with lock:
                done[0] += 1
                progress(done[0], len(keywords))

    unavailable = threading.Event()  # credits ran out: skip the rest instead of failing each
    reasons: dict[str, str] = {}

    def one(keyword: str) -> KeywordRanking | None:
        try:
            return search_one(keyword)
        finally:
            tick()

    def search_one(keyword: str) -> KeywordRanking | None:
        if unavailable.is_set():
            return None
        try:
            serp = search.top(keyword, s.base.country, s.depth, stop_domains=stop)
        except SearchUnavailable as exc:
            unavailable.set()
            reasons.setdefault("unavailable", str(exc))
            return None
        except httpx.HTTPError as exc:  # one failed search is a note, not a failed analysis
            reasons.setdefault("error", type(exc).__name__)
            return None
        return KeywordRanking(
            keyword=keyword,
            positions={d: best_position(serp.items, d) for d in domains},
            results_seen=len(serp.items),
            results=serp.items,
            features=serp.features,
            people_also_ask=serp.people_also_ask,
            related_searches=serp.related_searches,
        )

    out = pmap(one, keywords, s.base.concurrency)
    rankings = [r for r in out if r is not None]
    missed = [k for k, r in zip(keywords, out, strict=True) if r is None]
    notes: list[str] = []
    if "unavailable" in reasons:
        notes.append(
            f"Google results stopped after {len(rankings)} of {len(keywords)} keywords "
            f"({reasons['unavailable']}). Add Serper credits or run again tomorrow."
        )
    if "error" in reasons:
        notes.append(f"some searches failed ({reasons['error']}); those keywords were skipped")
    if empty := sum(1 for r in rankings if r.results_seen == 0):
        notes.append(f"{empty} keyword(s) returned no Google results")
    return RankCheck(
        rankings=rankings,
        not_checked=missed,
        unavailable="unavailable" in reasons,
        notes=notes,
    )
