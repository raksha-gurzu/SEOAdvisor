"""Free-mode providers: Serper, Gemini grounding, Google autocomplete, Bing, Tranco.

Fixtures follow each vendor's documented response shape (synthetic until recorded live).
"""

import io
import zipfile
from datetime import date

import httpx
import pytest
import respx

from seo_engine.config import ModelSettings, Thresholds
from seo_engine.difficulty import computed_difficulty, intent_from_types
from seo_engine.providers.autocomplete import SUGGEST_URL, GoogleAutocomplete
from seo_engine.providers.bing import BING_URL, BingKeywords, monthly_from_weekly
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


def test_bing_monthly_from_weekly() -> None:
    rows = [{"Impressions": 10}] * 12
    assert monthly_from_weekly(rows) == 43  # 10/week * 52/12
    assert monthly_from_weekly([]) == 0


@respx.mock
def test_bing_metrics_and_related(cache) -> None:
    respx.get(f"{BING_URL}GetKeywordStats").mock(
        return_value=httpx.Response(
            200,
            json={
                "d": [
                    {
                        "__type": "KeywordStats",
                        "Query": "client portal",
                        "Impressions": 30,
                        "BroadImpressions": 90,
                        "Date": "/Date(1720854000000)/",
                    }
                ]
                * 12
            },
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
