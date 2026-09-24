from datetime import date

from fakes import FakeEmbed, FakeKeywords, FakeLLM, FakeSearch
from seo_engine.deps import Deps
from seo_engine.tools.keyword_research import (
    cluster_candidates,
    keyword_research,
    url_key,
    weak_spots,
)

PAGE = """Emitii is a client project workspace for agencies.
Share tasks, files and approvals with clients in one client workspace.
Clients see project progress without email threads.
Agencies invite clients to a shared workspace."""

SHARED = ["https://a.com/x", "https://b.com/y", "https://c.com/z"]


def _serp(urls: list[str], forum: bool = False) -> list[tuple[str, str]]:
    out = [(u, "product") for u in urls]
    if forum:
        out.append(("https://www.reddit.com/r/agency/1", "forum"))
    return out


def _deps(llm_fit_no: set[str] | None = None) -> tuple[Deps, FakeKeywords, FakeSearch, FakeLLM]:
    no = llm_fit_no or set()
    llm = FakeLLM(
        {
            "SeedPhrases": lambda s, u: {
                "phrases": [
                    "client project workspace",
                    "client workspace",
                    "client portal software",
                    "shared workspace for clients",
                    "free crm",
                ]
            },
            "FitVerdicts": lambda s, u: {
                "verdicts": [
                    {"phrase": line[2:], "fits": line[2:] not in no}
                    for line in u.split("PHRASES:\n")[1].splitlines()
                ]
            },
        }
    )
    keywords = FakeKeywords(
        {
            "client project workspace": (90, 12),
            "client workspace": (320, 22),
            "client workspace app": (140, 18),
            "client portal software": (2900, 48),  # above the "new" ceiling of 30
            "shared workspace for clients": (30, 10),  # below the volume floor
            "free crm": (9900, 25),
            "agency client portal": (480, 25),
        },
        autocomplete={"client workspace": ["client workspace app"]},
        ranked={"https://a.com/x": ["agency client portal"]},
    )
    search = FakeSearch(
        {
            "client workspace": _serp(SHARED + ["https://d.com/"], forum=True),
            "client project workspace": _serp(SHARED + ["https://e.com/"]),
            "client workspace app": _serp(["https://f.com/", "https://g.com/"]),
            "agency client portal": _serp(["https://h.com/", "https://a.com/x"]),
            "free crm": _serp(["https://crm.com/"]),
        }
    )
    deps = Deps(search=search, keywords=keywords, fetcher=None, llm=llm, embed=FakeEmbed())  # type: ignore[arg-type]
    return deps, keywords, search, llm


def test_research_filters_clusters_and_ranks(settings) -> None:
    settings = settings.model_copy(update={"data_mode": "dataforseo"})
    deps, keywords, search, llm = _deps(llm_fit_no={"free crm"})
    out = keyword_research(deps, PAGE, settings, today=date(2026, 9, 24))

    by = {c.keyword: c for c in out.candidates}
    assert by["client portal software"].reason.startswith("difficulty 48 > 30")
    assert by["shared workspace for clients"].reason.startswith("volume 30 < 50")
    assert by["free crm"].reason.startswith("LLM")
    assert "borrowed" in by["agency client portal"].sources
    assert "autocomplete" in by["client workspace app"].sources

    # No chosen phrase below the volume floor or above the difficulty ceiling.
    for p in out.phrases:
        assert p.volume >= 50 and p.difficulty <= 30

    # "client workspace" and "client project workspace" share 3 top-10 URLs -> one cluster.
    heads = {cl.head: cl for cl in out.clusters}
    assert heads["client workspace"].members == ["client workspace", "client project workspace"]
    assert heads["client workspace"].total_volume == 410
    assert "forum in top 10" in heads["client workspace"].weak_spots[0]
    assert "client project workspace" not in heads

    assert len(out.phrases) <= settings.phrases_per_run
    assert out.phrases[0].reason
    assert llm.calls == ["SeedPhrases", "FitVerdicts"]


def test_url_key_normalises() -> None:
    assert url_key("https://www.A.com/x/?utm=1#top") == url_key("http://a.com/x")


def test_cluster_is_head_based(settings) -> None:
    from seo_engine.providers.search import SerpItem, SerpResults
    from seo_engine.tools.keyword_research import Candidate

    def serp(urls: list[str]) -> SerpResults:
        return SerpResults(
            phrase="",
            country="US",
            items=[SerpItem(rank=i, url=u, domain="") for i, u in enumerate(urls, 1)],
        )

    serps = {
        "a": serp(["1", "2", "3", "4"]),
        "b": serp(["1", "2", "3", "9"]),  # shares 3 with a
        "c": serp(["4", "9", "8", "7"]),  # shares 1 with a, 1 with b: no chaining
    }
    cands = [
        Candidate(keyword=k, sources=[], volume=v) for k, v in [("a", 300), ("b", 200), ("c", 100)]
    ]
    groups = cluster_candidates(cands, serps, min_shared=3, top_n=10)
    assert [[c.keyword for c in g] for g in groups] == [["a", "b"], ["c"]]


def test_stale_titles_raise_winnability(settings) -> None:
    from seo_engine.providers.search import SerpItem, SerpResults

    serp = SerpResults(
        phrase="x",
        country="US",
        items=[
            SerpItem(rank=1, url="https://a.com", domain="a.com", title="Best tools 2022"),
            SerpItem(rank=2, url="https://b.com", domain="b.com", title="Best tools 2026"),
        ],
    )
    signals, bonus = weak_spots(serp, settings, date(2026, 9, 24))
    assert signals == ["1 stale page(s) in top 10"] and bonus == 0.05


def test_free_mode_uses_bing_autocomplete_and_computed_difficulty(settings) -> None:
    from fakes import FakeAutocomplete
    from seo_engine.providers.tranco import DictRanks

    assert settings.data_mode == "free"
    settings = settings.model_copy(update={"site_strength": "growing"})  # ceiling 45
    deps, keywords, search, llm = _deps()
    # Bing-like volumes: no difficulty from the provider.
    keywords.data = {
        "client workspace": (40, None),  # >= 10 Bing impressions
        "client project workspace": (0, None),  # only autocomplete demand
        "client portal software": (5, None),  # below floor, not in autocomplete -> dropped
        "free crm": (500, None),
    }
    deps.autocomplete = FakeAutocomplete(
        searched={"client project workspace"},
        variants=["what is a client workspace", "client workspace vs portal"],
    )
    # a.com and b.com are big sites; the rest are unlisted small sites.
    deps.ranks = DictRanks({"a.com": 500, "b.com": 5_000, "crm.com": 50})
    search.serps["free crm"] = [(f"https://crm{i}.com/", "product") for i in range(5)]
    deps.ranks.ranks.update({f"crm{i}.com": 100 for i in range(5)})  # all top-1k: hard

    out = keyword_research(deps, PAGE, settings, today=date(2026, 9, 24))
    by = {c.keyword: c for c in out.candidates}

    assert by["client portal software"].reason.startswith("no demand")
    assert by["free crm"].reason.startswith("difficulty 100 > 45")
    # a.com 1.0 + b.com 0.8 + c.com 0.1 + e.com 0.1 -> 50
    assert by["client project workspace"].reason.startswith("difficulty 50 > 45")
    assert by["client project workspace"].in_autocomplete is True

    head = next(p for p in out.phrases if p.text == "client workspace")
    assert head.volume_source == "bing" and head.difficulty_source == "computed"
    assert "Bing impressions/mo" in head.reason
    # top 10 of "client workspace": a.com 1.0, b.com 0.8, c.com/d.com 0.1, reddit forum 0.1
    assert head.difficulty == round(100 * (1.0 + 0.8 + 0.1 + 0.1 + 0.1) / 5)
    assert head.intent == "commercial"  # product pages dominate
    assert "what is a client workspace" in out.questions
    assert "client workspace" in out.serps
