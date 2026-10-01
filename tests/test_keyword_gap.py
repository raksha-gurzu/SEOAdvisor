"""Expected values are worked out by hand from docs/KEYWORD-GAP-PLAN.md §5.5-5.7."""

import pytest

from seo_engine.config import GapSettings, Settings
from seo_engine.providers.search import SerpItem
from seo_engine.providers.tranco import DictRanks
from seo_engine.tools.keyword_gap import categories, keyword_gap
from seo_engine.tools.keyword_metrics import keyword_metrics
from seo_engine.tools.rank_check import DomainPosition, KeywordRanking, RankCheck
from seo_engine.tools.site_keywords import GapKeyword, KeywordDiscovery

OURS, MOXO, CLINKED = "ours.com", "moxo.com", "clinked.com"
DOMAINS = [OURS, MOXO, CLINKED]


@pytest.mark.parametrize(
    ("ours", "competitors", "expected"),
    [
        (None, [3, 8], ["missing", "untapped"]),
        (None, [3, None], ["untapped"]),
        (15, [3, 8], ["shared", "weak"]),
        (2, [3, 8], ["shared", "strong"]),
        (5, [3, 8], ["shared"]),  # between them: neither weak nor strong
        (5, [3, None], ["weak"]),
        (2, [3, None], ["strong"]),
        (5, [None, None], ["unique"]),
        (None, [None, None], []),
    ],
)
def test_semrush_categories(ours, competitors, expected) -> None:
    assert categories(ours, competitors) == expected


# (keyword, business fit, Bing searches, positions: ours, moxo, clinked)
CASES = [
    ("client portal for agencies", 2, 0, (None, 3, 8)),  # missing + untapped
    ("agency crm", 3, 0, (None, 15, None)),  # untapped
    ("workflow tool", 2, 100, (12, 4, None)),  # weak
    ("our niche", 3, 0, (2, None, None)),  # unique
    ("off topic", 1, 0, (None, 1, None)),  # untapped, but fit 1
    ("nobody", 2, 0, (None, None, None)),  # no site on the first 2 pages
]


def build(cases=CASES, **over):
    s = GapSettings(base=Settings(), **over)
    keywords = [
        GapKeyword(
            keyword=k,
            sources=["page"],
            pages={MOXO: f"https://moxo.com/{i}"},
            bing_searches=bing,
            business_fit=fit,
        )
        for i, (k, fit, bing, _) in enumerate(cases)
    ]
    discovery = KeywordDiscovery(
        keywords=keywords, brand_keywords=[], candidates=6, no_demand=0, not_checked=0
    )
    rankings = [
        KeywordRanking(
            keyword=k,
            positions={
                d: DomainPosition(position=p, url=f"https://{d}/{k.replace(' ', '-')}" if p else "")
                for d, p in zip(DOMAINS, pos, strict=True)
            },
            results_seen=10,
            results=[
                SerpItem(rank=i, url=f"https://s{i}.com/", domain=f"s{i}.com") for i in range(1, 11)
            ],
        )
        for k, _, _, pos in cases
    ]
    checked = RankCheck(rankings=rankings)
    metrics = keyword_metrics(discovery, checked, DOMAINS, s, DictRanks({}), has_bing=True)
    return keyword_gap(discovery, checked, metrics, DOMAINS, s)


def test_counts_rows_and_unranked() -> None:
    out = build()
    assert out.unranked == ["nobody"]
    nobody = next(r for r in out.rows if r.keyword == "nobody")
    assert nobody.categories == [] and nobody.proof == 0
    assert out.counts == {
        "shared": 0,
        "missing": 1,
        "weak": 1,
        "strong": 0,
        "untapped": 3,
        "unique": 1,
    }
    assert "1 checked keyword(s): none of the sites is on the first 2 pages" in out.notes


def test_top_keywords_order_fit_then_proof() -> None:
    out = build()
    # fit 3 first ("agency crm"); among fit 2, proof 0.0389 + 0.0046 = 0.0435 beats 0.0171.
    # "our niche" is unique (not a gap); "off topic" has fit 1.
    assert [o.keyword for o in out.top] == [
        "agency crm",
        "client portal for agencies",
        "workflow tool",
    ]
    by_kw = {o.keyword: o for o in out.top}
    assert by_kw["client portal for agencies"].proof == 0.0435
    assert by_kw["client portal for agencies"].category == "missing"
    assert by_kw["client portal for agencies"].best_competitor == MOXO
    assert (
        by_kw["client portal for agencies"].best_url
        == "https://moxo.com/client-portal-for-agencies"
    )
    assert by_kw["agency crm"].category == "untapped"


def test_reasons_and_traffic_lift_by_hand() -> None:
    by_kw = {o.keyword: o for o in build().top}
    assert by_kw["client portal for agencies"].reason == (
        "2 of 2 competitors rank: moxo.com #3, clinked.com #8"
    )
    # Google estimate round(100 x 9.567) = 957; lift = 957 x (CTR #4 0.0171 - CTR #12 0.0046)
    # = 957 x 0.0125 = 11.96 -> 12
    workflow = by_kw["workflow tool"]
    assert workflow.category == "weak" and workflow.traffic_lift == 12
    assert workflow.reason == (
        "1 of 2 competitors rank: moxo.com #4; you rank #12; about 12 more visits a month at #4"
    )
    assert by_kw["agency crm"].traffic_lift is None  # no Bing number: unknown, not 0


def test_competitor_panels_by_visits_then_position() -> None:
    out = build()
    moxo, clinked = out.competitors
    assert moxo.domain == MOXO and moxo.keywords_ranked == 4
    # only "workflow tool" has visits: 957 x CTR #4 0.0171 = 16.4 -> 16; then by position
    assert [(k.keyword, k.position, k.visits) for k in moxo.top] == [
        ("workflow tool", 4, 16),
        ("off topic", 1, None),
        ("client portal for agencies", 3, None),
        ("agency crm", 15, None),
    ]
    assert moxo.visits_known == 16
    assert [k.keyword for k in clinked.top] == ["client portal for agencies"]


def test_row_carries_positions_pages_and_metrics() -> None:
    row = next(r for r in build().rows if r.keyword == "workflow tool")
    assert row.positions == {OURS: 12, MOXO: 4, CLINKED: None}
    assert row.urls[CLINKED] == "" and row.urls[MOXO].startswith("https://moxo.com/")
    assert row.pages == {MOXO: "https://moxo.com/2"}
    assert row.google_estimate == 957 and row.categories == ["weak"]


def test_note_when_gaps_exist_but_none_fits() -> None:
    cases = [("off topic", 1, 0, (None, 1, None)), ("also off", 1, 0, (None, None, 5))]
    out = build(cases)
    assert out.top == []
    assert "2 gap keyword(s), but none fits the business well enough to add" in out.notes


def test_unknown_fit_is_treated_as_the_minimum_not_dropped() -> None:
    cases = [("unjudged", None, 0, (None, 2, None)), ("judged", 3, 0, (None, 9, None))]
    assert [o.keyword for o in build(cases).top] == ["judged", "unjudged"]


def gap_with(spec, **over):
    """Rows built directly: (keyword, fit, bing, difficulty, (ours, moxo, clinked))."""
    from seo_engine.tools.keyword_metrics import GapMetrics, KeywordRow, band

    s = GapSettings(**over)
    discovery = KeywordDiscovery(
        keywords=[
            GapKeyword(keyword=k, sources=["page"], bing_searches=b, business_fit=f)
            for k, f, b, _, _ in spec
        ],
        brand_keywords=[],
        candidates=len(spec),
        no_demand=0,
        not_checked=0,
    )
    rankings = [
        KeywordRanking(
            keyword=k,
            positions={d: DomainPosition(position=p) for d, p in zip(DOMAINS, pos, strict=True)},
            results_seen=10,
            results=[],
        )
        for k, _, _, _, pos in spec
    ]
    rows = [
        KeywordRow(
            keyword=k,
            bing_searches=b or None,
            bing_status="measured" if b else "too_low",
            autocomplete=None,
            google_estimate=None,
            visits=dict.fromkeys(DOMAINS),
            difficulty=diff,
            difficulty_band=band(diff, s),
            intent="commercial",
            features=[],
            cluster=k,
        )
        for k, _, b, diff, _ in spec
    ]
    metrics = GapMetrics(rows=rows, google_per_bing=None, ctr_source="")
    return keyword_gap(discovery, RankCheck(rankings=rankings), metrics, DOMAINS, s)


def test_ties_are_broken_by_difficulty_then_bing_searches() -> None:
    same = (None, 3, None)  # equal fit and equal competitor proof for every row
    out = gap_with(
        [
            ("hard", 2, 0, 60, same),
            ("easy", 2, 0, 20, same),
            ("easy popular", 2, 500, 40, same),
            ("easy quiet", 2, 10, 40, same),
        ]
    )
    assert [o.keyword for o in out.top] == ["easy", "easy popular", "easy quiet", "hard"]


def test_top_keywords_are_limited() -> None:
    spec = [(f"k{i:02}", 2, 0, 30, (None, 3, None)) for i in range(15)]
    assert len(gap_with(spec).top) == 10
    assert len(gap_with(spec, top_opportunities=4).top) == 4


@pytest.mark.parametrize(
    ("depth", "words"), [(10, "first page"), (20, "first 2 pages"), (30, "first 3 pages")]
)
def test_the_no_site_note_follows_the_depth(depth: int, words: str) -> None:
    out = gap_with([("nobody", 2, 0, 30, (None, None, None))], depth=depth)
    assert f"1 checked keyword(s): none of the sites is on the {words}" in out.notes


def test_suggested_competitors_are_the_businesses_google_shows() -> None:
    from seo_engine.tools.keyword_gap import suggest_competitors

    def result(domain: str, rank: int, page_type: str = "product") -> SerpItem:
        return SerpItem(rank=rank, url=f"https://{domain}/x", domain=domain, page_type=page_type)

    def kr(keyword: str, items: list[SerpItem]) -> KeywordRanking:
        return KeywordRanking(keyword=keyword, positions={}, results_seen=len(items), results=items)

    checked = RankCheck(
        rankings=[
            kr(
                "k1",
                [
                    result("rival.co", 2),
                    result("www.reddit.com", 1, "forum"),
                    result("blog.ours.com", 3),
                    result("g2.com", 4),
                ],
            ),
            kr(
                "k2",
                [
                    result("www.rival.co", 5),
                    result("other.io", 1),
                    result("youtube.com", 2, "video"),
                ],
            ),
            kr("k3", [result("other.io", 1)]),
            kr("off", [result("unrelated.net", 1), result("unrelated.net", 2)]),
        ]
    )
    fit = {"k1": 3, "k2": 2, "k3": 2, "off": 1}  # "off" is a poor fit: its results do not count
    out = suggest_competitors(checked, fit, DOMAINS, GapSettings())
    assert [(c.domain, c.keywords, c.best_position) for c in out] == [
        ("other.io", 2, 1),
        ("rival.co", 2, 2),
    ]
    assert out[1].examples == ["k1", "k2"]
    assert suggest_competitors(checked, fit, DOMAINS, GapSettings(suggest_min_keywords=3)) == []
