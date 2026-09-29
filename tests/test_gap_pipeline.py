import pytest

from fakes import FakeSearch
from gap_fakes import ANSWERS, SITES, deps, gap_run
from seo_engine.config import GapSettings
from seo_engine.gap_pipeline import GapError, GapRun, run_gap, validate_sites
from seo_engine.providers.search import SearchUnavailable


def test_pipeline_runs_every_step_in_order() -> None:
    steps: list[tuple[str, str, str]] = []
    run = gap_run()
    run_gap(run, deps(), lambda n, st, d: steps.append((n, st, d)))
    assert [(n, st) for n, st, _ in steps if st == "done"] == [
        ("sites", "done"),
        ("keywords", "done"),
        ("google", "done"),
        ("metrics", "done"),
        ("compare", "done"),
    ]
    google = [d for n, st, d in steps if n == "google" and st == "running"]
    assert google[0] == "0/5" and google[-1] == "5/5"  # live progress for the UI
    assert run.domains == ["ours.com", "moxo.com", "rival.io"]
    assert run.credits_used == 7
    assert run.result is not None
    top = [o.keyword for o in run.result.top]
    assert top[0] == "client portal software"  # both competitors rank; fit 3
    assert "agency crm" not in top  # we rank #1 above rival.io: strong, not a gap
    assert run.result.counts["strong"] == 1


@pytest.mark.parametrize(
    ("site", "competitors", "message"),
    [
        ("ours.com", [], "Add at least one competitor website."),
        ("ours.com", ["www.ours.com"], "ours.com is your own site"),
        (
            "ours.com",
            ["moxo.com", "https://www.moxo.com/x"],
            "The same competitor is listed twice.",
        ),
        ("ours.com", [f"c{i}.com" for i in range(5)], "Compare with at most 4 competitors."),
        ("localhost", ["moxo.com"], "not a website address"),
    ],
)
def test_validate_sites(site, competitors, message) -> None:
    with pytest.raises(GapError, match=message):
        validate_sites(site, competitors, 4)


def test_validate_sites_normalises() -> None:
    assert validate_sites(" https://www.Ours.com/pricing ", ["moxo.com", " "], 4) == [
        "ours.com",
        "moxo.com",
    ]


def test_unreadable_own_site_is_a_clear_error() -> None:
    with pytest.raises(GapError, match="Couldn't read any page of ours.com"):
        run_gap(gap_run(), deps(sites=SITES[1:]))


def test_unreadable_competitors_is_a_clear_error() -> None:
    with pytest.raises(GapError, match="Couldn't read any competitor's pages"):
        run_gap(gap_run(), deps(sites=SITES[:1]))


def test_no_keyword_with_demand_is_a_clear_error() -> None:
    answers = {d: {"pages": [{"page": 1, "keyword": "unsearched thing"}]} for d in ANSWERS}
    with pytest.raises(GapError, match="No keyword with search demand"):
        run_gap(gap_run(), deps(answers=answers))


class NoCredits(FakeSearch):
    def top(self, phrase, country, n, stop_domains=frozenset()):
        raise SearchUnavailable("HTTP 400: Not enough credits")


def test_no_credits_at_all_is_a_clear_error() -> None:
    with pytest.raises(GapError, match="Google results stopped after 0 of 5 keywords"):
        run_gap(gap_run(), deps(search=NoCredits({})))


def test_settings_travel_with_the_run() -> None:
    run = gap_run(settings=GapSettings(depth=30, keywords=40))
    assert GapRun.model_validate_json(run.model_dump_json()).settings.depth == 30


def test_overlapping_sites_are_rejected() -> None:
    with pytest.raises(GapError, match="gurzu.com and blog.gurzu.com overlap"):
        validate_sites("gurzu.com", ["blog.gurzu.com"], 4)
    with pytest.raises(GapError, match="overlap"):
        validate_sites("ours.com", ["moxo.com", "app.moxo.com"], 4)


def test_sites_are_read_at_the_address_as_typed() -> None:
    from gap_fakes import FakeReader

    reader = FakeReader(SITES)
    run = GapRun(site="https://www.ours.com/pricing", competitors=["moxo.com", "rival.io"])
    d = deps()
    d.reader = reader
    run_gap(run, d)
    assert reader.asked == ["https://www.ours.com", "https://moxo.com", "https://rival.io"]
    assert run.domains[0] == "ours.com"  # matching still uses the bare domain


def test_missing_serper_key_is_a_clear_error(monkeypatch, tmp_path) -> None:
    from seo_engine.config import Settings
    from seo_engine.gap_pipeline import gap_deps_from_env
    from seo_engine.providers.serper import SerperSearch

    monkeypatch.setattr(
        SerperSearch,
        "from_env",
        classmethod(lambda cls, cache, language="en": cls("", cache, language)),
    )
    run = gap_run(settings=GapSettings(base=Settings(cache_dir=tmp_path)))
    with pytest.raises(GapError, match="needs SERPER_API_KEY"):
        gap_deps_from_env(run)


def test_second_pass_keywords_are_checked_and_reported() -> None:
    from fakes import FakeSearch
    from gap_fakes import SERPS

    serps = {**SERPS, "client portal for lawyers": [("https://moxo.com/legal", "product")]}
    search = FakeSearch(serps, related={"client portal software": ["client portal for lawyers"]})
    d = deps(search=search, auto={"client portal for lawyers"})
    run = gap_run()
    run_gap(run, d)
    assert "client portal for lawyers" in search.calls
    row = next(r for r in run.result.rows if r.keyword == "client portal for lawyers")
    # moxo.com is #1; rival.io and ours.com are not on the pages checked
    assert row.sources == ["related search"]
    assert row.categories == ["untapped"]
    assert row.positions == {"ours.com": None, "moxo.com": 1, "rival.io": None}
    assert any(n.startswith("second pass: 1 of") for n in run.notes)


def test_second_pass_is_skipped_when_credits_ran_out() -> None:
    from fakes import FakeSearch
    from gap_fakes import SERPS

    class RunsOut(FakeSearch):
        def top(self, phrase, country, n, stop_domains=frozenset()):
            if len(self.calls) >= 3:
                raise SearchUnavailable("HTTP 400: Not enough credits")
            return super().top(phrase, country, n, stop_domains)

    search = RunsOut(SERPS, related={"client portal software": ["client portal for lawyers"]})
    run = gap_run()
    run_gap(run, deps(search=search, auto={"client portal for lawyers"}))
    assert "client portal for lawyers" not in search.calls
    assert not any(n.startswith("second pass") for n in run.notes)


def test_one_failed_search_does_not_skip_the_second_pass() -> None:
    import httpx

    from gap_fakes import SERPS

    class OneFails(FakeSearch):
        def top(self, phrase, country, n, stop_domains=frozenset()):
            if phrase == "agency crm":
                raise httpx.ReadTimeout("slow")
            return super().top(phrase, country, n, stop_domains)

    serps = {**SERPS, "client portal for lawyers": [("https://moxo.com/legal", "product")]}
    search = OneFails(serps, related={"client portal software": ["client portal for lawyers"]})
    run = gap_run()
    run_gap(run, deps(search=search, auto={"client portal for lawyers"}))
    assert run.ranks.not_checked and not run.ranks.unavailable
    assert "client portal for lawyers" in search.calls
    assert any(n.startswith("second pass: 1 of") for n in run.notes)
