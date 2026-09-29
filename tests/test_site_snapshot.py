"""Site Snapshot summary (tools/site_snapshot.py): pure code."""

from seo_engine.config import GapSettings, SnapshotSettings
from seo_engine.providers.crux import Speed
from seo_engine.tools.site_snapshot import (
    SnapshotKeyword,
    position_groups,
    top_pages,
    vital_results,
)


def kw(
    keyword: str, position: int | None, url: str = "https://s.com/a", visits: int | None = None
) -> SnapshotKeyword:
    return SnapshotKeyword(
        keyword=keyword,
        position=position,
        url=url,
        ranked=position is not None,
        bing_searches=None,
        bing_status="too_low",
        google_estimate=None,
        visits=visits,
        difficulty=None,
        difficulty_band=None,
        intent="commercial",
        features=[],
    )


def test_position_groups_cover_every_keyword() -> None:
    ks = [kw("a", 1), kw("b", 3), kw("c", 4), kw("d", 10), kw("e", 11), kw("f", 20), kw("g", None)]
    got = [(g.label, g.count) for g in position_groups(ks, SnapshotSettings())]
    assert got == [("1-3", 2), ("4-10", 2), ("11-20", 2), ("not in top 20", 1)]
    assert sum(c for _, c in got) == len(ks)


def test_position_groups_follow_the_settings() -> None:
    s = SnapshotSettings(
        gap=GapSettings(keywords=30, depth=30, second_pass_keywords=0),
        position_groups=[(1, 10), (11, 30)],
    )
    got = [(g.label, g.count) for g in position_groups([kw("a", 25), kw("b", None)], s)]
    assert got == [("1-10", 0), ("11-30", 1), ("not in top 30", 1)]


def test_top_pages_order_and_unknown_visits() -> None:
    ks = [
        kw("a", 5, "https://s.com/x", visits=40),
        kw("b", 2, "https://s.com/x", visits=None),  # no Bing number: not counted as 0
        kw("c", 1, "https://s.com/y", visits=90),
        kw("d", 3, "https://s.com/z"),
        kw("e", 8, "https://s.com/z"),
        kw("f", None, "https://s.com/w", visits=0),  # not ranked: not a top page
    ]
    pages = top_pages(ks, 10)
    assert [(p.url, p.visits, p.keywords, p.best_position) for p in pages] == [
        ("https://s.com/y", 90, ["c"], 1),
        ("https://s.com/x", 40, ["b", "a"], 2),
        ("https://s.com/z", None, ["d", "e"], 3),  # no measured visits: after the measured ones
    ]
    assert len(top_pages(ks, 1)) == 1


def test_vitals_only_when_there_is_data() -> None:
    s = SnapshotSettings()
    assert vital_results(None, s) == []
    assert vital_results(Speed(origin="o", status="no_data"), s) == []
    got = vital_results(
        Speed(
            origin="o",
            status="ok",
            p75={"largest_contentful_paint": 4200, "first_contentful_paint": 900},
        ),
        s,
    )
    assert [(v.metric, v.status) for v in got] == [
        ("largest_contentful_paint", "poor")
    ]  # FCP is not a Core Web Vital


def test_snapshot_csv_escapes_formulas() -> None:
    from seo_engine.snapshot_pipeline import SnapshotRun
    from seo_engine.snapshot_report import snapshot_csv
    from seo_engine.tools.site_snapshot import SiteFacts, SnapshotResult

    result = SnapshotResult(
        domain="s.com", home="https://s.com/", facts=SiteFacts(), vitals=[], sitemap_urls=0,
        sitemap_files=0, keywords_checked=1, keywords_found=1, depth=20, visits=None,
        visits_keywords=0, groups=[], keywords=[kw("=HYPERLINK(1)", 4, "https://s.com/x")],
        top_pages=[], competitors=[], checks=None,
    )  # fmt: skip
    text = snapshot_csv(SnapshotRun(site="s.com", result=result))
    assert text.splitlines()[1].startswith("'=HYPERLINK(1),4,https://s.com/x")
