"""Site Snapshot summary (docs/SITE-SNAPSHOT-PLAN.md §5.2). Plain code over data already
fetched: no requests, no LLM (CLAUDE.md rule 1).

Numbers are always a sample: the keywords we found and checked, never the site's total
(plan F1). Visits exist only where Bing measured a keyword (Keyword Gap D11); the sum says how
many keywords it covers.
"""

from collections import defaultdict

from pydantic import BaseModel

from seo_engine.config import SnapshotSettings
from seo_engine.providers.crux import Speed
from seo_engine.providers.domain_age import DomainDates
from seo_engine.providers.majestic import MajesticEntry
from seo_engine.providers.openpagerank import LinkScore
from seo_engine.providers.sitemap import SiteSample
from seo_engine.tools.keyword_gap import SuggestedCompetitor, suggest_competitors
from seo_engine.tools.keyword_metrics import GapMetrics
from seo_engine.tools.rank_check import RankCheck
from seo_engine.tools.site_checks import SiteChecks
from seo_engine.tools.site_keywords import KeywordDiscovery


class SiteFacts(BaseModel):
    """Facts from outside sources. Each can be missing; each missing one has a reason."""

    link: LinkScore | None = None
    majestic: MajesticEntry | None = None  # None: not in the top one million (or not read)
    majestic_read: bool = False  # False when the list could not be read at all
    tranco_rank: int | None = None
    tranco_read: bool = False
    speed: Speed | None = None
    dates: DomainDates | None = None


class VitalResult(BaseModel):
    metric: str
    p75: float
    status: str  # good, needs work, poor (plan F16)


class SnapshotKeyword(BaseModel):
    keyword: str
    position: int | None  # None: not in the results checked
    url: str  # our ranking page, or the page that targets it when not ranked
    ranked: bool
    bing_searches: int | None
    bing_status: str
    google_estimate: int | None
    visits: int | None  # None: no Bing number, so no estimate
    difficulty: int | None
    difficulty_band: str | None
    intent: str
    features: list[str]


class PositionGroup(BaseModel):
    label: str  # "1-3", "4-10", "11-20", "not in top 20"
    low: int | None
    high: int | None
    count: int


class TopPage(BaseModel):
    url: str
    visits: int | None  # sum over its keywords with a Bing number; None when none has one
    keywords: list[str]
    best_position: int


class SnapshotResult(BaseModel):
    domain: str
    home: str
    facts: SiteFacts
    vitals: list[VitalResult]
    sitemap_urls: int
    sitemap_files: int
    sitemap_capped: bool = False  # more sitemap files than we read: the count is a minimum
    keywords_checked: int
    keywords_found: int  # in the top `depth`
    depth: int
    visits: int | None
    visits_keywords: int  # keywords with a Bing number, behind `visits`
    groups: list[PositionGroup]
    keywords: list[SnapshotKeyword]
    top_pages: list[TopPage]
    competitors: list[SuggestedCompetitor]
    checks: SiteChecks | None
    notes: list[str] = []


def vital_results(speed: Speed | None, s: SnapshotSettings) -> list[VitalResult]:
    if speed is None or speed.status != "ok":
        return []
    return [
        VitalResult(metric=m, p75=v, status=s.vital_status(m, v))
        for m, v in speed.p75.items()
        if m in s.vitals
    ]


def snapshot_keywords(
    discovery: KeywordDiscovery | None,
    checked: RankCheck | None,
    metrics: GapMetrics | None,
    domain: str,
) -> list[SnapshotKeyword]:
    if discovery is None or checked is None or metrics is None:
        return []
    targets = {k.keyword: k.pages.get(domain, "") for k in discovery.keywords}
    rows = {r.keyword: r for r in metrics.rows}
    out: list[SnapshotKeyword] = []
    for r in checked.rankings:
        m = rows.get(r.keyword)
        pos = r.positions.get(domain)
        if m is None or pos is None:
            continue
        out.append(
            SnapshotKeyword(
                keyword=r.keyword,
                position=pos.position,
                url=pos.url or targets.get(r.keyword, ""),
                ranked=pos.position is not None,
                bing_searches=m.bing_searches,
                bing_status=m.bing_status,
                google_estimate=m.google_estimate,
                visits=m.visits.get(domain),
                difficulty=m.difficulty,
                difficulty_band=m.difficulty_band,
                intent=m.intent,
                features=m.features,
            )
        )
    # Ranked first (best position first), then the most searched.
    out.sort(
        key=lambda k: (k.position is None, k.position or 0, -(k.bing_searches or 0), k.keyword)
    )
    return out


def position_groups(keywords: list[SnapshotKeyword], s: SnapshotSettings) -> list[PositionGroup]:
    groups = [
        PositionGroup(
            label=f"{lo}-{hi}",
            low=lo,
            high=hi,
            count=sum(1 for k in keywords if k.position is not None and lo <= k.position <= hi),
        )
        for lo, hi in s.position_groups
    ]
    last = s.position_groups[-1][1] if s.position_groups else s.gap.depth
    outside = sum(1 for k in keywords if k.position is None or k.position > last)
    groups.append(PositionGroup(label=f"not in top {last}", low=None, high=None, count=outside))
    return groups


def top_pages(keywords: list[SnapshotKeyword], limit: int) -> list[TopPage]:
    """Pages that rank for at least one checked keyword, by estimated visits, then by how many
    keywords they rank for, then by best position."""
    by_url: dict[str, list[SnapshotKeyword]] = defaultdict(list)
    for k in keywords:
        if k.ranked and k.url:
            by_url[k.url].append(k)
    pages = []
    for url, ks in by_url.items():
        measured = [k.visits for k in ks if k.visits is not None]
        pages.append(
            TopPage(
                url=url,
                visits=sum(measured) if measured else None,
                keywords=[k.keyword for k in sorted(ks, key=lambda k: k.position or 0)],
                best_position=min(k.position or 0 for k in ks),
            )
        )
    pages.sort(
        key=lambda p: (p.visits is None, -(p.visits or 0), -len(p.keywords), p.best_position, p.url)
    )
    return pages[:limit]


def build_snapshot(
    domain: str,
    home: str,
    sample: SiteSample | None,
    discovery: KeywordDiscovery | None,
    checked: RankCheck | None,
    metrics: GapMetrics | None,
    facts: SiteFacts,
    checks: SiteChecks | None,
    s: SnapshotSettings,
) -> SnapshotResult:
    keywords = snapshot_keywords(discovery, checked, metrics, domain)
    measured = [k.visits for k in keywords if k.visits is not None]
    fit = {k.keyword: k.business_fit for k in discovery.keywords} if discovery else {}
    competitors = suggest_competitors(checked, fit, [domain], s.gap) if checked else []
    notes: list[str] = []
    if keywords and not measured:
        notes.append("Bing has no search numbers for these keywords, so there is no visit estimate")
    return SnapshotResult(
        domain=domain,
        home=home,
        facts=facts,
        vitals=vital_results(facts.speed, s),
        sitemap_urls=sample.sitemap_urls if sample else 0,
        sitemap_files=len(sample.sitemaps) if sample else 0,
        sitemap_capped=sample.sitemap_capped if sample else False,
        keywords_checked=len(keywords),
        keywords_found=sum(1 for k in keywords if k.ranked),
        depth=s.gap.depth,
        visits=sum(measured) if measured else None,
        visits_keywords=len(measured),
        groups=position_groups(keywords, s),
        keywords=keywords,
        top_pages=top_pages(keywords, s.top_pages),
        competitors=competitors,
        checks=checks,
        notes=notes,
    )
