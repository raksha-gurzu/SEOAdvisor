"""Keyword Gap step 5: categories and the keywords to add (docs/KEYWORD-GAP-PLAN.md §5.5-5.7).

Categories use Semrush's published rules (G1); "ranks" means inside the results checked.
The "top keywords to add" order is the owner's (29 Sep 2026, after D11): business fit, then
competitor proof, then easier difficulty; Bing searches only break ties. All plain code.
"""

from collections import defaultdict
from typing import Literal

from pydantic import BaseModel

from seo_engine.config import GapSettings
from seo_engine.page_types import owns
from seo_engine.tools.keyword_metrics import GapMetrics, KeywordRow
from seo_engine.tools.rank_check import RankCheck
from seo_engine.tools.site_keywords import GapKeyword, KeywordDiscovery

Category = Literal["shared", "missing", "weak", "strong", "untapped", "unique"]
CATEGORIES: tuple[Category, ...] = ("shared", "missing", "weak", "strong", "untapped", "unique")
TO_ADD: tuple[Category, ...] = ("missing", "weak", "untapped")


class GapRow(KeywordRow):
    """One keyword of the table: its metrics plus positions and gap categories."""

    categories: list[Category]
    positions: dict[str, int | None]  # per domain, ours first; None = not in the results checked
    urls: dict[str, str]  # per domain: its best-ranking page ("" when not ranking)
    pages: dict[str, str]  # per domain: the page that targets the keyword (from discovery)
    sources: list[str]
    business_fit: int | None
    proof: float  # sum of competitors' click rates at their positions
    traffic_lift: int | None  # visits/month if we reached the best competitor; None: unknown


class Opportunity(BaseModel):
    keyword: str
    category: Category  # missing, weak or untapped (the first that applies)
    reason: str
    business_fit: int | None
    proof: float
    difficulty: int | None
    difficulty_band: str | None
    traffic_lift: int | None
    best_competitor: str
    best_position: int
    best_url: str


class CompetitorKeyword(BaseModel):
    keyword: str
    position: int
    url: str
    visits: int | None


class CompetitorPanel(BaseModel):
    domain: str
    keywords_ranked: int
    visits_known: int  # sum of estimated visits where Bing had numbers
    top: list[CompetitorKeyword]


class SuggestedCompetitor(BaseModel):
    domain: str
    keywords: int  # good-fit keywords where it is on page 1
    best_position: int
    examples: list[str]


class KeywordGapResult(BaseModel):
    domains: list[str]  # ours first
    rows: list[GapRow]  # every checked keyword; no categories when no site ranks
    counts: dict[Category, int]
    top: list[Opportunity]
    competitors: list[CompetitorPanel]
    unranked: list[str]  # checked, but no domain is in the results checked
    brand_keywords: list[GapKeyword]  # listed, never checked (step 2)
    suggested_competitors: list[SuggestedCompetitor] = []  # who really ranks (plan G13)
    notes: list[str] = []


UGC_TYPES = {"forum", "video"}


def suggest_competitors(
    checked: RankCheck, fit: dict[str, int | None], domains: list[str], s: GapSettings
) -> list[SuggestedCompetitor]:
    """Sites on page 1 for your good-fit keywords that you did not enter (plan G13): the
    competitors Google actually shows. Forums, videos and big platforms or directories
    (`not_competitors`) are left out; they are not businesses you compete with."""
    found: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for r in checked.rankings:
        f = fit.get(r.keyword)
        if f is not None and f < s.min_business_fit:
            continue
        seen: set[str] = set()
        for item in r.results[:10]:
            d = item.domain.removeprefix("www.")
            if (
                d in seen
                or item.page_type in UGC_TYPES
                or any(owns(d, x) for x in domains)
                or any(owns(d, x) for x in s.not_competitors)
            ):
                continue
            seen.add(d)
            found[d].append((item.rank, r.keyword))
    ranked = sorted(found.items(), key=lambda kv: (-len(kv[1]), min(p for p, _ in kv[1]), kv[0]))
    return [
        SuggestedCompetitor(
            domain=d,
            keywords=len(hits),
            best_position=min(p for p, _ in hits),
            examples=[k for _, k in sorted(hits)[:3]],
        )
        for d, hits in ranked
        if len(hits) >= s.suggest_min_keywords
    ][: s.suggest_competitors]


def categories(ours: int | None, competitors: list[int | None]) -> list[Category]:
    """Semrush Keyword Gap rules (G1). Categories overlap, as in Semrush."""
    ranked = [p for p in competitors if p is not None]
    out: list[Category] = []
    if ours is not None and competitors and len(ranked) == len(competitors):
        out.append("shared")
    if ours is None and competitors and len(ranked) == len(competitors):
        out.append("missing")
    if ours is not None and ranked and all(p < ours for p in ranked):
        out.append("weak")
    if ours is not None and ranked and all(ours < p for p in ranked):
        out.append("strong")
    if ours is None and ranked:
        out.append("untapped")
    if ours is not None and not ranked:
        out.append("unique")
    return out


def reason(row: GapRow, category: Category, ours: str, competitors: list[str]) -> str:
    ranked = sorted(
        ((d, p) for d in competitors if (p := row.positions[d]) is not None), key=lambda x: x[1]
    )
    listed = ", ".join(f"{d} #{p}" for d, p in ranked)
    text = f"{len(ranked)} of {len(competitors)} competitors rank: {listed}"
    if category == "weak":
        text += f"; you rank #{row.positions[ours]}"
    if row.traffic_lift:
        text += f"; about {row.traffic_lift} more visits a month at #{ranked[0][1]}"
    return text


def keyword_gap(
    discovery: KeywordDiscovery,
    checked: RankCheck,
    metrics: GapMetrics,
    domains: list[str],
    s: GapSettings,
) -> KeywordGapResult:
    ours, competitors = domains[0], domains[1:]
    found = {k.keyword: k for k in discovery.keywords}
    by_kw = {r.keyword: r for r in checked.rankings}
    rows: list[GapRow] = []
    unranked: list[str] = []
    for m in metrics.rows:
        r, k = by_kw[m.keyword], found[m.keyword]
        positions = {d: r.positions[d].position for d in domains}
        cats = categories(positions[ours], [positions[d] for d in competitors])
        if not any(p is not None for p in positions.values()):
            unranked.append(m.keyword)  # kept as a row (no categories): Bing numbers, CSV
        comp = [p for d in competitors if (p := positions[d]) is not None]
        lift = None
        if m.google_estimate is not None and comp:
            gain = s.ctr_at(min(comp)) - s.ctr_at(positions[ours])
            lift = max(0, round(m.google_estimate * gain))
        rows.append(
            GapRow(
                **m.model_dump(),
                categories=cats,
                positions=positions,
                urls={d: r.positions[d].url for d in domains},
                pages=k.pages,
                sources=k.sources,
                business_fit=k.business_fit,
                proof=round(sum(s.ctr_at(p) for p in comp), 4),
                traffic_lift=lift,
            )
        )

    def sort_key(row: GapRow) -> tuple:
        fit = row.business_fit if row.business_fit is not None else s.min_business_fit
        hard = row.difficulty if row.difficulty is not None else 101
        return (-fit, -row.proof, hard, -(row.bing_searches or 0), row.keyword)

    gaps = [row for row in rows if any(c in TO_ADD for c in row.categories)]
    candidates = [
        row for row in gaps if row.business_fit is None or row.business_fit >= s.min_business_fit
    ]
    top: list[Opportunity] = []
    for row in sorted(candidates, key=sort_key)[: s.top_opportunities]:
        category = next(c for c in TO_ADD if c in row.categories)
        best = min(competitors, key=lambda d: row.positions[d] or 10_000)
        top.append(
            Opportunity(
                keyword=row.keyword,
                category=category,
                reason=reason(row, category, ours, competitors),
                business_fit=row.business_fit,
                proof=row.proof,
                difficulty=row.difficulty,
                difficulty_band=row.difficulty_band,
                traffic_lift=row.traffic_lift,
                best_competitor=best,
                best_position=row.positions[best] or 0,
                best_url=row.urls[best],
            )
        )

    panels: list[CompetitorPanel] = []
    for d in competitors:
        mine = [row for row in rows if row.positions[d] is not None]
        mine.sort(key=lambda row: (-(row.visits.get(d) or 0), row.positions[d], row.keyword))
        panels.append(
            CompetitorPanel(
                domain=d,
                keywords_ranked=len(mine),
                visits_known=sum(row.visits.get(d) or 0 for row in mine),
                top=[
                    CompetitorKeyword(
                        keyword=row.keyword,
                        position=row.positions[d] or 0,
                        url=row.urls[d],
                        visits=row.visits.get(d),
                    )
                    for row in mine[: s.top_opportunities]
                ],
            )
        )

    notes = list(metrics.notes)
    if unranked:
        notes.append(
            f"{len(unranked)} checked keyword(s): none of the sites is on the first "
            + (f"{pages} pages" if (pages := -(-s.depth // 10)) > 1 else "page")
        )
    if gaps and not candidates:
        notes.append(f"{len(gaps)} gap keyword(s), but none fits the business well enough to add")
    return KeywordGapResult(
        domains=domains,
        rows=rows,
        counts={c: sum(1 for row in rows if c in row.categories) for c in CATEGORIES},
        top=top,
        competitors=panels,
        unranked=unranked,
        brand_keywords=discovery.brand_keywords,
        suggested_competitors=suggest_competitors(
            checked, {k.keyword: k.business_fit for k in discovery.keywords}, domains, s
        ),
        notes=notes,
    )
