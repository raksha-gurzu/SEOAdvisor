"""Free-mode providers: Serper, Gemini grounding, Google autocomplete, Bing, Tranco.

Fixtures follow each vendor's documented response shape (synthetic until recorded live).
"""

import io
import json
import zipfile
from datetime import date, timedelta

import httpx
import pytest
import respx

from seo_engine.config import ModelSettings, Thresholds
from seo_engine.difficulty import computed_difficulty, intent_from_types
from seo_engine.providers.autocomplete import SUGGEST_URL, GoogleAutocomplete
from seo_engine.providers.bing import (
    BING_URL,
    BingError,
    BingKeywords,
    monthly_from_weekly,
    row_date,
)
from seo_engine.providers.embeddings import GEMINI_URL
from seo_engine.providers.gemini_search import GeminiGroundedSearch
from seo_engine.providers.search import FallbackSearch, SearchUnavailable, SerpItem, SerpResults
from seo_engine.providers.serper import SERPER_URL, SerperSearch
from seo_engine.providers.tranco import TRANCO_URL, DictRanks, TrancoRanks

SERPER_BODY = {
    "searchParameters": {"q": "client portal", "gl": "us"},
    "organic": [
        {
            "title": "Client Portal Software",
            "link": "https://clientportal.io/",
            "position": 1,
            "snippet": "...",
        },
        {
            "title": "12 Best Client Portals (2026)",
            "link": "https://acme.com/blog/best-client-portals",
            "position": 2,
        },
        {"title": "r/agency", "link": "https://www.reddit.com/r/agency/1", "position": 3},
    ],
    "peopleAlsoAsk": [{"question": "What is a client portal?", "snippet": "..."}],
    "relatedSearches": [{"query": "client portal free"}],
    "videos": [{"title": "x"}],
    "credits": 1,
}


@respx.mock
def test_serper_parses_and_caches(cache) -> None:
    route = respx.post(f"{SERPER_URL}search").mock(
        return_value=httpx.Response(200, json=SERPER_BODY)
    )
    search = SerperSearch("key", cache)
    serp = search.top("client portal", "US", 10)
    assert [i.page_type for i in serp.items] == ["product", "listicle", "forum"]
    assert serp.people_also_ask == ["What is a client portal?"]
    assert serp.related_searches == ["client portal free"]
    assert {"people_also_ask", "related_searches", "video"} <= set(serp.features)
    search.top("client portal", "US", 10)
    assert route.call_count == 1


GROUNDED = {
    "candidates": [
        {
            "content": {"parts": [{"text": "..."}]},
            "groundingMetadata": {
                "webSearchQueries": ["client portal software", "best client portal"],
                "groundingChunks": [
                    {
                        "web": {
                            "uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AAA",
                            "title": "clientportal.io",
                        }
                    },
                    {
                        "web": {
                            "uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/BBB",
                            "title": "reddit.com",
                        }
                    },
                ],
            },
        }
    ]
}


@respx.mock
def test_fallback_to_gemini_grounding_when_serper_out_of_credits(cache, run) -> None:
    respx.post(f"{SERPER_URL}search").mock(
        return_value=httpx.Response(403, json={"message": "Not enough credits"})
    )
    respx.post(f"{GEMINI_URL}models/gemini-2.5-flash:generateContent").mock(
        return_value=httpx.Response(200, json=GROUNDED)
    )
    respx.get("https://vertexaisearch.cloud.google.com/grounding-api-redirect/AAA").mock(
        return_value=httpx.Response(302, headers={"location": "https://clientportal.io/"})
    )
    respx.get("https://vertexaisearch.cloud.google.com/grounding-api-redirect/BBB").mock(
        return_value=httpx.Response(302, headers={"location": "https://www.reddit.com/r/agency/1"})
    )

    search = FallbackSearch(
        [
            SerperSearch("key", cache),
            GeminiGroundedSearch(ModelSettings(), "gkey", cache, cost_sink=run.add_cost),
        ]
    )
    serp = search.top("client portal", "US", 10)
    assert serp.source == "gemini-grounding"
    assert [i.url for i in serp.items] == [
        "https://clientportal.io/",
        "https://www.reddit.com/r/agency/1",
    ]
    assert serp.items[1].page_type == "forum"
    assert serp.related_searches == ["client portal software", "best client portal"]
    assert run.cost_usd == 0.0  # free tier


def test_fallback_raises_when_nothing_available(cache) -> None:
    search = FallbackSearch(
        [SerperSearch("", cache), GeminiGroundedSearch(ModelSettings(), "", cache)]
    )
    with pytest.raises(SearchUnavailable, match="SERPER_API_KEY"):
        search.top("x", "US", 10)


@respx.mock
def test_autocomplete_demand_and_variants(cache) -> None:
    def reply(request: httpx.Request) -> httpx.Response:
        q = request.url.params["q"]
        table = {
            "client portal": ["client portal", "client portal login", "client portal app"],
            "what is client portal": ["what is a client portal"],
            "client portal vs": ["client portal vs extranet"],
        }
        return httpx.Response(200, json=[q, table.get(q, []), [], {}])

    respx.get(SUGGEST_URL).mock(side_effect=reply)
    ac = GoogleAutocomplete(cache)
    assert ac.is_searched("Client  Portal", "US")
    assert not ac.is_searched("purple client portal", "US")
    assert ac.variants("client portal", "US", ["what is"], ["vs"]) == [
        "what is a client portal",
        "client portal vs extranet",
    ]


TODAY = date(2026, 9, 28)
EPOCH = date(1970, 1, 1)


def weekly_rows(impressions: list[int], last: date = date(2026, 9, 26)) -> list[dict]:
    """Rows shaped like the live API: one per week with impressions, oldest first."""
    n = len(impressions)
    return [
        {
            "__type": "KeywordStats:#Microsoft.Bing.Webmaster.Api",
            "Query": "client portal",
            "Impressions": imp,
            "BroadImpressions": imp * 10,
            "Date": f"/Date({(last - timedelta(weeks=n - 1 - i) - EPOCH).days * 86_400_000})/",
        }
        for i, imp in enumerate(impressions)
    ]


def test_bing_row_date_parses_wcf_dates() -> None:
    assert row_date({"Date": "/Date(1790380800000)/"}) == date(2026, 9, 26)
    assert row_date({"Date": "garbage"}) is None
    assert row_date({}) is None


def test_bing_monthly_from_full_weeks() -> None:
    assert monthly_from_weekly(weekly_rows([10] * 12), TODAY) == 43  # 10/week * 52/12
    assert monthly_from_weekly([], TODAY) == 0


def test_bing_missing_weeks_count_as_zero() -> None:
    # Live 28 Sep 2026: "client portal software" came back as one row of 1 impression.
    assert monthly_from_weekly(weekly_rows([1]), TODAY) == 0  # was 4 when averaging rows
    sparse = weekly_rows([12, 12, 12], last=date(2026, 9, 12))
    assert monthly_from_weekly(sparse, TODAY) == 13  # 36 in 12 weeks, not 52/month


def test_bing_only_counts_the_last_12_weeks() -> None:
    rows = weekly_rows([1000] * 13 + [10] * 12)  # 25 weeks, as the live API returns
    assert monthly_from_weekly(rows, TODAY) == 43
    assert monthly_from_weekly(rows, TODAY, weeks=4) == 43
    future = weekly_rows([500], last=date(2026, 10, 3))
    assert monthly_from_weekly(future, TODAY) == 0


@respx.mock
def test_bing_metrics_and_related(cache) -> None:
    respx.get(f"{BING_URL}GetKeywordStats").mock(
        return_value=httpx.Response(
            200,
            json={"d": weekly_rows([30] * 12, last=date(2026, 9, 19))},
        )
    )
    respx.get(f"{BING_URL}GetRelatedKeywords").mock(
        return_value=httpx.Response(
            200,
            json={
                "d": [
                    {
                        "Query": "Client Portal Software",
                        "Impressions": 300,
                        "BroadImpressions": 900,
                    },
                    {"Query": "client portal app", "Impressions": 60, "BroadImpressions": 100},
                ]
            },
        )
    )
    bing = BingKeywords("key", cache, GoogleAutocomplete(cache), today=date(2026, 9, 24))
    [m] = bing.metrics(["client portal"], "US")
    assert m.volume == 130 and m.difficulty is None
    related = bing.suggestions("client portal", "US")
    assert [(r.keyword, r.volume) for r in related] == [
        ("client portal software", 100),
        ("client portal app", 20),
    ]
    assert bing.ranked_keywords("https://x.com", "US") == []


def test_bing_without_key_returns_zero_volume(cache) -> None:
    bing = BingKeywords("", cache, GoogleAutocomplete(cache))
    assert [m.volume for m in bing.metrics(["a", "b"], "US")] == [0, 0]
    assert bing.suggestions("a", "US") == []


@respx.mock
def test_tranco_download_and_parent_domain_lookup(tmp_path) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("top-1m.csv", "1,google.com\n2,hubspot.com\n3,example.co.uk\n")
    route = respx.get(TRANCO_URL).mock(return_value=httpx.Response(200, content=buf.getvalue()))
    ranks = TrancoRanks(tmp_path)
    assert ranks.rank("blog.hubspot.com") == 2
    assert ranks.rank("www.example.co.uk") == 3
    assert ranks.rank("tiny-agency.io") is None
    assert TrancoRanks(tmp_path).rank("google.com") == 1  # reuses the SQLite file
    assert route.call_count == 1


def test_computed_difficulty_and_intent() -> None:
    def item(url: str, kind: str = "product") -> SerpItem:
        return SerpItem(rank=1, url=url, domain=url.split("/")[2], page_type=kind)

    serp = SerpResults(
        phrase="x",
        country="US",
        items=[
            item("https://big.com/"),  # rank 500    -> 1.0
            item("https://mid.com/"),  # rank 50,000 -> 0.55
            item("https://tiny.io/"),  # unlisted    -> 0.1
            item("https://www.reddit.com/r/x", "forum"),  # UGC -> 0.1
        ],
    )
    ranks = DictRanks({"big.com": 500, "mid.com": 50_000, "reddit.com": 20})
    d = computed_difficulty(serp, ranks, Thresholds())
    assert d.strengths == [1.0, 0.55, 0.1, 0.1]
    assert d.score == 44 and d.small_sites == 1
    assert intent_from_types(["guide", "guide", "product"]) == "informational"
    assert intent_from_types(["unknown"]) == "unknown"


THROTTLED = httpx.Response(400, json={"ErrorCode": 4, "Message": "ERROR!!! ThrottleUser"})
SECRET = "k3y-that-must-never-leak"


def bing_with(cache, sleeps: list[float]) -> BingKeywords:
    return BingKeywords(
        SECRET, cache, GoogleAutocomplete(cache), today=TODAY, sleep=sleeps.append, workers=1
    )


@respx.mock
def test_bing_throttle_backs_off_then_recovers(cache) -> None:
    respx.get(f"{BING_URL}GetKeywordStats").mock(
        side_effect=[THROTTLED, httpx.Response(200, json={"d": weekly_rows([10] * 12)})]
    )
    sleeps: list[float] = []
    bing = bing_with(cache, sleeps)
    [m] = bing.metrics(["client portal"], "US")
    assert m.volume == 43 and bing.unmeasured == set()
    assert sleeps == [5.0]


@respx.mock
def test_bing_persistent_throttle_marks_keywords_unmeasured(cache) -> None:
    route = respx.get(f"{BING_URL}GetKeywordStats").mock(return_value=THROTTLED)
    sleeps: list[float] = []
    bing = bing_with(cache, sleeps)
    out = bing.metrics(["client portal", "client portal software", "agency crm"], "US")
    assert [m.volume for m in out] == [0, 0, 0]
    assert bing.unmeasured == {"client portal", "client portal software", "agency crm"}
    assert sleeps == [5.0, 20.0] and route.call_count == 3  # later keywords make no calls
    related = respx.get(f"{BING_URL}GetRelatedKeywords").mock(return_value=THROTTLED)
    assert bing.suggestions("client portal", "US") == [] and related.call_count == 0


@respx.mock
def test_bing_throttle_is_not_cached(cache) -> None:
    respx.get(f"{BING_URL}GetKeywordStats").mock(
        side_effect=[THROTTLED, THROTTLED, THROTTLED, httpx.Response(200, json={"d": []})]
    )
    bing_with(cache, []).metrics(["client portal"], "US")
    fresh = bing_with(cache, [])  # a later run the same day tries again
    assert fresh.metrics(["client portal"], "US")[0].volume == 0
    assert fresh.unmeasured == set()


@respx.mock
def test_bing_errors_never_contain_the_api_key(cache) -> None:
    respx.get(f"{BING_URL}GetKeywordStats").mock(
        return_value=httpx.Response(400, text=f"bad request for apikey={SECRET}")
    )
    bing = bing_with(cache, [])
    with pytest.raises(BingError) as err:
        bing._get("GetKeywordStats", {"q": "client portal"})
    assert SECRET not in str(err.value) and "<key>" in str(err.value)
    assert err.value.__cause__ is None and err.value.__suppress_context__
    # metrics() turns the failure into "not measured" instead of failing the analysis
    assert bing.metrics(["client portal"], "US")[0].volume == 0
    assert bing.unmeasured == {"client portal"}


@respx.mock
def test_bing_transport_error_never_contains_the_api_key(cache) -> None:
    respx.get(f"{BING_URL}GetKeywordStats").mock(side_effect=httpx.ConnectError("refused"))
    respx.get(f"{BING_URL}GetRelatedKeywords").mock(side_effect=httpx.ConnectError("refused"))
    bing = bing_with(cache, [])
    with pytest.raises(BingError) as err:
        bing._get("GetKeywordStats", {"q": "client portal"})
    assert SECRET not in str(err.value) and "ConnectError" in str(err.value)
    assert bing.suggestions("client portal", "US") == []


def serper_page(urls: list[str], **extra) -> dict:
    """A Serper page: positions restart at 1 on every page (live test, 28 Sep 2026)."""
    organic = [{"title": u, "link": u, "position": i} for i, u in enumerate(urls, 1)]
    return {"organic": organic, "credits": 1, **extra}


def serper_pages(pages: dict[int, dict]):
    """respx side effect answering by the `page` field (absent = page 1)."""
    calls: list[dict] = []

    def reply(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(200, json=pages.get(body.get("page", 1), {"organic": []}))

    return reply, calls


PAGE_1 = serper_page(
    [f"https://p1-{i}.com/" for i in range(1, 11)],
    peopleAlsoAsk=[{"question": "What is a client portal?"}],
    videos=[{}],
)
PAGE_2 = serper_page(["https://p1-10.com/"] + [f"https://p2-{i}.com/" for i in range(2, 11)])


@respx.mock
def test_serper_pages_to_depth_with_absolute_ranks(cache) -> None:
    reply, calls = serper_pages({1: PAGE_1, 2: PAGE_2})
    respx.post(f"{SERPER_URL}search").mock(side_effect=reply)
    search = SerperSearch("key", cache)
    serp = search.top("client portal", "US", 20)
    assert [c.get("page") for c in calls] == [None, 2]  # page 1 keeps its old cache key
    assert all(c["num"] == 10 for c in calls)
    ranks = {i.url: i.rank for i in serp.items}
    assert ranks["https://p1-1.com/"] == 1 and ranks["https://p2-2.com/"] == 12
    assert ranks["https://p1-10.com/"] == 10  # repeated on page 2: kept once, first rank
    assert len(serp.items) == 19
    assert serp.people_also_ask == ["What is a client portal?"]  # from page 1
    assert "video" in serp.features
    assert search.credits_used == 2


@respx.mock
def test_serper_depth_10_is_one_request(cache) -> None:
    reply, calls = serper_pages({1: PAGE_1, 2: PAGE_2})
    respx.post(f"{SERPER_URL}search").mock(side_effect=reply)
    assert len(SerperSearch("key", cache).top("client portal", "US", 10).items) == 10
    assert len(calls) == 1


@respx.mock
def test_serper_stops_at_an_empty_page(cache) -> None:
    reply, calls = serper_pages({1: PAGE_1})
    respx.post(f"{SERPER_URL}search").mock(side_effect=reply)
    serp = SerperSearch("key", cache).top("client portal", "US", 50)
    assert len(calls) == 2 and len(serp.items) == 10


@respx.mock
def test_serper_skips_page_2_when_every_domain_is_on_page_1(cache) -> None:
    reply, calls = serper_pages({1: PAGE_1, 2: PAGE_2})
    respx.post(f"{SERPER_URL}search").mock(side_effect=reply)
    search = SerperSearch("key", cache)
    search.top("client portal", "US", 20, stop_domains=frozenset({"p1-1.com", "p1-3.com"}))
    assert len(calls) == 1
    search.top("client portal", "US", 20, stop_domains=frozenset({"p1-1.com", "ours.com"}))
    assert len(calls) == 2  # ours.com not on page 1: page 2 is needed


@respx.mock
def test_serper_counts_only_credits_it_spends(cache) -> None:
    reply, calls = serper_pages({1: PAGE_1, 2: PAGE_2})
    respx.post(f"{SERPER_URL}search").mock(side_effect=reply)
    search = SerperSearch("key", cache)
    search.top("client portal", "US", 20)
    search.top("client portal", "US", 20)  # same day: from the cache
    assert search.credits_used == 2 and len(calls) == 2


def test_fallback_search_still_accepts_providers_without_stop_domains() -> None:
    class OldStyle:  # a provider written before stop_domains existed
        def top(self, phrase: str, country: str, n: int) -> SerpResults:
            return SerpResults(phrase=phrase, country=country, items=[])

    assert FallbackSearch([OldStyle()]).top("client portal", "US", 10).phrase == "client portal"


@pytest.mark.parametrize(
    ("url", "redirect"),
    [
        ("https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc", True),
        ("https://example.com/vertexaisearch.cloud.google.com/page", False),  # only in the path
        ("https://vertexaisearch.cloud.google.com.evil.example/x", False),
    ],
)
def test_grounding_redirect_is_matched_by_host(url: str, redirect: bool) -> None:
    from seo_engine.providers.gemini_search import is_redirect

    assert is_redirect(url) is redirect
