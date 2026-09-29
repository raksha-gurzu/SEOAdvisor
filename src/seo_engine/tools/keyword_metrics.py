"""Keyword Gap step 4: numbers for each checked keyword (docs/KEYWORD-GAP-PLAN.md §5.3, §5.4).

Plain code over data already fetched (rule 1): no extra searches or credits. Visits exist only
where Bing measured the keyword; everywhere else they are None ("too low to measure on Bing"),
never 0 (owner decision after D11).
"""

from typing import Literal

from pydantic import BaseModel

from seo_engine.config import GapSettings
from seo_engine.difficulty import computed_difficulty, intent_from_types
from seo_engine.providers.search import SerpResults
from seo_engine.providers.tranco import RankLookup
from seo_engine.tools.keyword_research import url_key
from seo_engine.tools.rank_check import KeywordRanking, RankCheck
from seo_engine.tools.site_keywords import GapKeyword, KeywordDiscovery

BingStatus = Literal["measured", "too_low", "not_measured", "no_key"]
Band = Literal["low", "medium", "high"]


class KeywordRow(BaseModel):
    keyword: str
    bing_searches: int | None  # per month; None unless measured
    bing_status: BingStatus
    autocomplete: bool | None
    google_estimate: int | None  # rough: Bing x country ratio; None when Bing has no number
    visits: dict[str, int | None]  # per domain; None when there is no Google estimate
    difficulty: int | None  # 0-100 from the top 10 (difficulty.py); None: too few results
    difficulty_band: Band | None
    intent: str
    features: list[str]
    cluster: str  # lead keyword of its group (itself when alone)


class GapMetrics(BaseModel):
    rows: list[KeywordRow]
    google_per_bing: float | None  # the ratio used, for the "how we calculate" note
    ctr_source: str
    shares_source: str = ""
    notes: list[str] = []


def bing_status(k: GapKeyword, has_bing: bool) -> BingStatus:
    if not has_bing:
        return "no_key"
    if k.bing_searches is None:
        return "not_measured"  # Bing limit (D12)
    return "measured" if k.bing_searches > 0 else "too_low"


def band(difficulty: int | None, s: GapSettings) -> Band | None:
    if difficulty is None:
        return None
    if difficulty <= s.difficulty_low_max:
        return "low"
    return "medium" if difficulty <= s.difficulty_medium_max else "high"


def clusters(rankings: list[KeywordRanking], order: list[str], min_shared: int) -> dict[str, str]:
    """keyword -> lead keyword. Head-based: a keyword joins the first lead whose top 10 shares
    at least `min_shared` URLs with its own (G11); leads are taken in `order`."""
    top10 = {r.keyword: {url_key(i.url) for i in r.results[:10]} for r in rankings}
    leads: list[str] = []
    out: dict[str, str] = {}
    for kw in order:
        if kw not in top10:
            continue
        lead = next((h for h in leads if len(top10[h] & top10[kw]) >= min_shared), None)
        if lead is None:
            leads.append(kw)
            lead = kw
        out[kw] = lead
    return out


def keyword_metrics(
    discovery: KeywordDiscovery,
    checked: RankCheck,
    domains: list[str],
    s: GapSettings,
    site_ranks: RankLookup,
    has_bing: bool,
) -> GapMetrics:
    found = {k.keyword: k for k in discovery.keywords}
    ratio = s.google_per_bing(s.base.country)
    # Leads: better-fitting, better-measured keywords first, then discovery order.
    order = sorted(
        (r.keyword for r in checked.rankings),
        key=lambda kw: (-(found[kw].business_fit or 0), -(found[kw].bing_searches or 0)),
    )
    groups = clusters(checked.rankings, order, s.cluster_min_shared_urls)
    rows: list[KeywordRow] = []
    for r in checked.rankings:
        k = found[r.keyword]
        status = bing_status(k, has_bing)
        estimate = (
            round(k.bing_searches * ratio)
            if status == "measured" and k.bing_searches and ratio
            else None
        )
        top10 = r.results[:10]
        difficulty = None
        if len(top10) >= s.difficulty_min_results:
            serp = SerpResults(phrase=r.keyword, country=s.base.country, items=top10)
            difficulty = computed_difficulty(serp, site_ranks, s.base.thresholds).score
        rows.append(
            KeywordRow(
                keyword=r.keyword,
                bing_searches=k.bing_searches if status == "measured" else None,
                bing_status=status,
                autocomplete=k.autocomplete,
                google_estimate=estimate,
                visits={
                    d: None if estimate is None else round(estimate * s.ctr_at(p.position))
                    for d, p in r.positions.items()
                },
                difficulty=difficulty,
                difficulty_band=band(difficulty, s),
                intent=intent_from_types([i.page_type for i in top10]),
                features=r.features,
                cluster=groups.get(r.keyword, r.keyword),
            )
        )
    notes: list[str] = []
    if ratio is None and s.google_estimate:
        notes.append(f"no search-share data for {s.base.country}: no Google estimate or visits")
    measured = sum(1 for row in rows if row.bing_status == "measured")
    if rows and measured < len(rows):
        notes.append(
            f"visits shown for {measured} of {len(rows)} keywords; "
            "Bing has no numbers for the others"
        )
    if few := sum(1 for row in rows if row.difficulty is None):
        notes.append(
            f"{few} keyword(s) had fewer than {s.difficulty_min_results} results: no difficulty"
        )
    return GapMetrics(
        rows=rows,
        google_per_bing=ratio,
        ctr_source=s.ctr_source,
        shares_source=s.search_shares_source,
        notes=notes,
    )
