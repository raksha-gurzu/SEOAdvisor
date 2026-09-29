"""Expected numbers are worked out by hand from docs/KEYWORD-GAP-PLAN.md §5.3-5.4."""

import pytest

from seo_engine.config import GapSettings, Settings
from seo_engine.providers.search import SerpItem
from seo_engine.providers.tranco import DictRanks
from seo_engine.tools.keyword_metrics import band, clusters, keyword_metrics
from seo_engine.tools.rank_check import DomainPosition, KeywordRanking, RankCheck
from seo_engine.tools.site_keywords import GapKeyword, KeywordDiscovery

DOMAINS = ["ours.com", "moxo.com"]
US_RATIO = 86.01 / 8.99  # 9.567...


def item(rank: int, domain: str, page_type: str = "listicle", path: str = "") -> SerpItem:
    return SerpItem(rank=rank, url=f"https://{domain}/{path}", domain=domain, page_type=page_type)


def ranking(
    keyword: str, items: list[SerpItem], positions: dict[str, int | None]
) -> KeywordRanking:
    return KeywordRanking(
        keyword=keyword,
        positions={d: DomainPosition(position=p) for d, p in positions.items()},
        results_seen=len(items),
        results=items,
        features=["people_also_ask"],
    )


# Top 10 for the difficulty case: 2 very strong sites (Tranco <= 1,000 -> 1.0),
# 4 small sites (unlisted -> 0.1), 4 mid sites (Tranco <= 100,000 -> 0.55).
# Mean = (2 x 1.0 + 4 x 0.1 + 4 x 0.55) / 10 = 0.46 -> difficulty 46 -> "medium".
TOP10 = (
    [item(1, "big1.com"), item(2, "big2.com")]
    + [item(3 + i, f"small{i}.com") for i in range(4)]
    + [item(7 + i, f"mid{i}.com") for i in range(4)]
)
RANKS = DictRanks({"big1.com": 500, "big2.com": 900, **{f"mid{i}.com": 50_000 for i in range(4)}})


def run(keywords: list[GapKeyword], rankings: list[KeywordRanking], has_bing=True, **over):
    s = GapSettings(base=Settings(**over.pop("base", {})), **over)
    discovery = KeywordDiscovery(
        keywords=keywords, brand_keywords=[], candidates=len(keywords), no_demand=0, not_checked=0
    )
    return keyword_metrics(discovery, RankCheck(rankings=rankings), DOMAINS, s, RANKS, has_bing)


def gk(keyword: str, bing: int | None, fit: int | None = 2) -> GapKeyword:
    return GapKeyword(keyword=keyword, sources=["page"], bing_searches=bing, business_fit=fit)


def test_google_estimate_and_visits_by_hand() -> None:
    out = run(
        [gk("secure file sharing", 134)],
        [ranking("secure file sharing", TOP10, {"ours.com": 12, "moxo.com": 1})],
    )
    [row] = out.rows
    assert out.google_per_bing == pytest.approx(US_RATIO)
    assert row.bing_status == "measured" and row.bing_searches == 134
    assert row.google_estimate == 1282  # round(134 x 9.567) = round(1281.99)
    assert row.visits == {"ours.com": 6, "moxo.com": 257}  # 1282 x 0.0046; 1282 x 0.2002


def test_not_in_top_20_is_zero_visits_when_there_is_an_estimate() -> None:
    out = run([gk("k", 100)], [ranking("k", TOP10, {"ours.com": None, "moxo.com": 3})])
    assert out.rows[0].visits == {"ours.com": 0, "moxo.com": 37}  # round(957 x 0.0389)


@pytest.mark.parametrize(
    ("bing", "has_bing", "status"),
    [(0, True, "too_low"), (None, True, "not_measured"), (None, False, "no_key")],
)
def test_no_bing_number_means_no_visits_never_zero(bing, has_bing, status) -> None:
    out = run([gk("k", bing)], [ranking("k", TOP10, {"ours.com": 2, "moxo.com": 1})], has_bing)
    [row] = out.rows
    assert row.bing_status == status
    assert row.bing_searches is None and row.google_estimate is None
    assert row.visits == {"ours.com": None, "moxo.com": None}
    assert "visits shown for 0 of 1 keywords; Bing has no numbers for the others" in out.notes


def test_country_without_share_data_has_no_estimate() -> None:
    out = run([gk("k", 100)], [ranking("k", TOP10, {"ours.com": 1})], base={"country": "BR"})
    assert out.rows[0].google_estimate is None and out.google_per_bing is None
    assert "no search-share data for BR: no Google estimate or visits" in out.notes


def test_difficulty_band_and_intent_by_hand() -> None:
    out = run([gk("k", 0)], [ranking("k", TOP10, {"ours.com": None})])
    [row] = out.rows
    assert row.difficulty == 46 and row.difficulty_band == "medium"
    assert row.intent == "commercial"  # listicles in the top 10 (difficulty.INTENT_BY_TYPE)
    assert row.features == ["people_also_ask"]


def test_too_few_results_gives_no_difficulty() -> None:
    out = run([gk("k", 0)], [ranking("k", TOP10[:7], {"ours.com": None})])
    assert out.rows[0].difficulty is None and out.rows[0].difficulty_band is None
    assert "1 keyword(s) had fewer than 8 results: no difficulty" in out.notes


@pytest.mark.parametrize(
    ("difficulty", "expected"),
    [(None, None), (0, "low"), (30, "low"), (31, "medium"), (55, "medium"), (56, "high")],
)
def test_band_edges(difficulty, expected) -> None:
    assert band(difficulty, GapSettings()) == expected


def test_clusters_are_head_based() -> None:
    def urls(*paths: str) -> list[SerpItem]:
        return [item(i, "x.com", path=p) for i, p in enumerate(paths, 1)]

    rankings = [
        ranking("lead", urls("a", "b", "c", "d"), {}),
        ranking("joins lead", urls("a", "b", "c", "z"), {}),  # 3 shared with lead
        ranking("near joiner", urls("b", "c", "z", "y"), {}),  # 3 with joiner, 2 with lead
        ranking("alone", urls("q", "r", "s"), {}),
    ]
    order = ["lead", "joins lead", "near joiner", "alone"]
    groups = clusters(rankings, order, 3)
    assert groups == {
        "lead": "lead",
        "joins lead": "lead",
        "near joiner": "near joiner",  # no chaining through "joins lead"
        "alone": "alone",
    }


def test_cluster_lead_is_the_best_fitting_keyword() -> None:
    same = TOP10
    out = run(
        [gk("weak fit", 0, fit=1), gk("strong fit", 0, fit=3)],
        [ranking("weak fit", same, {}), ranking("strong fit", same, {})],
    )
    assert {r.keyword: r.cluster for r in out.rows} == {
        "weak fit": "strong fit",
        "strong fit": "strong fit",
    }
