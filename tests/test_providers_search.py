import httpx
import respx

from conftest import load_json
from seo_engine.providers.dataforseo import BASE_URL, DataForSEOClient
from seo_engine.providers.search import DataForSEOSearch

LIVE = f"{BASE_URL}serp/google/organic/live/advanced"


def _provider(settings, cache, run) -> DataForSEOSearch:
    return DataForSEOSearch(DataForSEOClient("l", "p"), cache, settings, cost_sink=run.add_cost)


@respx.mock
def test_top_parses_items_features_and_questions(settings, cache, run) -> None:
    respx.post(LIVE).mock(
        return_value=httpx.Response(200, json=load_json("dataforseo/serp_live.json"))
    )
    serp = _provider(settings, cache, run).top("client project workspace", "US", 10)
    assert len(serp.items) == 10
    assert serp.items[0].rank == 1 and serp.items[0].page_type == "forum"
    assert serp.items[1].page_type == "product"  # root URL
    assert serp.items[2].page_type == "listicle"
    assert serp.items[4].page_type == "video"
    assert {"people_also_ask", "video", "related_searches"} <= set(serp.features)
    assert "How much does a client portal cost?" in serp.people_also_ask
    assert "client portal free" in serp.related_searches
    assert run.cost_usd == 0.002


@respx.mock
def test_second_identical_call_same_day_is_free(settings, cache, run) -> None:
    route = respx.post(LIVE).mock(
        return_value=httpx.Response(200, json=load_json("dataforseo/serp_live.json"))
    )
    provider = _provider(settings, cache, run)
    first = provider.top("client project workspace", "US", 20)
    second = provider.top("client project workspace", "US", 20)
    assert first == second
    assert route.call_count == 1
    assert run.cost_usd == 0.002 and len(run.costs) == 1


@respx.mock
def test_retries_on_server_error(settings, cache, run, monkeypatch) -> None:
    monkeypatch.setattr("seo_engine.providers.base.time.sleep", lambda s: None)
    route = respx.post(LIVE).mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json=load_json("dataforseo/serp_live.json")),
        ]
    )
    serp = _provider(settings, cache, run).top("client project workspace", "US", 10)
    assert route.call_count == 2 and serp.items
