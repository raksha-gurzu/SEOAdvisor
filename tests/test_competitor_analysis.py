from fakes import FakeEmbed, FakeFetcher, FakeLLM, FakeSearch
from seo_engine.deps import Deps
from seo_engine.providers.fetcher import FetchedPage
from seo_engine.tools.competitor_analysis import choose_types, competitor_analysis

PRODUCT_TEXT = "client portal file sharing approvals " * 60  # 300 words


def _page(url: str, words: int = 300, title: str = "Client portal") -> FetchedPage:
    text = " ".join(("client portal file sharing approvals " * (words // 5 + 1)).split()[:words])
    return FetchedPage(
        url=url,
        status="ok",
        title=title,
        text=text,
        headings=["Features"],
        word_count=words,
        method="httpx",
    )


SERP = [
    ("https://www.g2.com/categories/client-portal", "category"),  # authority
    ("https://www.reddit.com/r/agency/1", "forum"),  # wrong format
    ("https://p1.com/", "product"),
    ("https://p2.com/", "product"),
    ("https://p2.com/features", "product"),
    ("https://p2.com/pricing", "product"),  # 3rd page on p2.com
    ("https://p3.com/", "product"),
    ("https://p4.com/", "product"),
    ("https://blog.com/best-client-portals", "listicle"),  # different type
    ("https://huge.com/", "product"),  # length outlier
    ("https://blocked.com/", "product"),  # fetch fails
]


def _deps() -> Deps:
    pages = {u: _page(u) for u, _ in SERP}
    pages["https://huge.com/"] = _page("https://huge.com/", words=5000)
    pages["https://blocked.com/"] = FetchedPage(
        url="https://blocked.com/", status="robots_blocked", reason="disallowed by robots.txt"
    )
    pages["https://blog.com/best-client-portals"] = _page(
        "https://blog.com/best-client-portals", title="12 Best Client Portals"
    )

    def reader(system: str, user: str) -> dict:
        kind = "listicle" if "12 Best" in user else "product"
        return {
            "page_type": kind,
            "topics": ["file sharing", "client approvals"],
            "questions": ["what is a client portal?"],
        }

    return Deps(
        search=FakeSearch({"client portal": SERP}),
        keywords=None,  # type: ignore[arg-type]
        fetcher=FakeFetcher(pages),
        llm=FakeLLM({"PageReading": reader}),
        embed=FakeEmbed(),
    )


def test_filters_in_order_with_reasons(settings) -> None:
    deps = _deps()
    serp = deps.search.top("client portal", "US", 20)
    out = competitor_analysis(deps, [serp], PRODUCT_TEXT, settings)

    reasons = {d.url: d.reason for d in out.dropped}
    assert reasons["https://www.g2.com/categories/client-portal"].startswith("authority outlier")
    assert reasons["https://www.reddit.com/r/agency/1"] == "wrong format (forum)"
    assert reasons["https://blocked.com/"].startswith("fetch robots_blocked")
    assert reasons["https://blog.com/best-client-portals"] == "different page type (listicle)"
    assert reasons["https://huge.com/"].startswith("length outlier")
    assert reasons["https://p2.com/pricing"].startswith("domain limit")

    kept = [p.url for p in out.kept]
    assert kept == [
        "https://p1.com/",
        "https://p2.com/",
        "https://p2.com/features",
        "https://p3.com/",
        "https://p4.com/",
    ]
    assert out.ours.page_type == "product" and out.ours.topics
    assert all(p.source.startswith("google#") and p.topics for p in out.kept)
    assert len(out.kept) + len(out.dropped) == len(SERP)
    assert out.notes == []


def test_choose_types_falls_back_to_dominant() -> None:
    keep, note = choose_types(["listicle"] * 6 + ["product"] * 2, "product", 5)
    assert keep == {"product", "listicle"} and note and "dominant: listicle" in note
    keep, note = choose_types(["product"] * 5 + ["listicle"] * 3, "product", 5)
    assert keep == {"product"} and note is None
