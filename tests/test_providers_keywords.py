import json

import httpx
import respx

from conftest import load_json
from seo_engine.providers.dataforseo import BASE_URL, DataForSEOClient
from seo_engine.providers.keywords import DataForSEOKeywords

LABS = f"{BASE_URL}dataforseo_labs/google/"


def _provider(settings, cache, run) -> DataForSEOKeywords:
    return DataForSEOKeywords(DataForSEOClient("l", "p"), cache, settings, cost_sink=run.add_cost)


@respx.mock
def test_metrics_bulk_one_call_for_30_candidates(settings, cache, run) -> None:
    route = respx.post(f"{LABS}keyword_overview/live").mock(
        return_value=httpx.Response(200, json=load_json("dataforseo/keyword_overview.json"))
    )
    candidates = ["Client Portal", "client  project workspace", "client workspace"] + [
        f"filler phrase {i}" for i in range(27)
    ]
    out = _provider(settings, cache, run).metrics(candidates, "US")
    assert route.call_count == 1
    sent = json.loads(route.calls[0].request.content)[0]
    assert len(sent["keywords"]) == 30 and sent["location_code"] == 2840
    by = {m.keyword: m for m in out}
    assert by["client portal"].volume == 8100 and by["client portal"].difficulty == 48
    assert by["client project workspace"].intent == "commercial"
    assert by["filler phrase 3"].volume == 0 and by["filler phrase 3"].difficulty is None
    assert run.cost_usd == 0.0101


@respx.mock
def test_autocomplete_dedupes(settings, cache, run) -> None:
    respx.post(f"{BASE_URL}serp/google/autocomplete/live/advanced").mock(
        return_value=httpx.Response(200, json=load_json("dataforseo/autocomplete.json"))
    )
    out = _provider(settings, cache, run).autocomplete("client workspace", "US")
    assert out == ["client workspace", "client workspace app", "client workspace software"]


@respx.mock
def test_ranked_keywords_and_suggestions(settings, cache, run) -> None:
    respx.post(f"{LABS}ranked_keywords/live").mock(
        return_value=httpx.Response(200, json=load_json("dataforseo/ranked_keywords.json"))
    )
    respx.post(f"{LABS}keyword_suggestions/live").mock(
        return_value=httpx.Response(200, json=load_json("dataforseo/keyword_suggestions.json"))
    )
    provider = _provider(settings, cache, run)
    ranked = provider.ranked_keywords("https://clientportal.io/", "US")
    assert ranked[0].keyword == "client portal software" and ranked[0].rank == 4
    sugg = provider.suggestions("client workspace", "US")
    assert [s.keyword for s in sugg] == ["client workspace software", "shared client workspace"]
    assert len(run.costs) == 2
