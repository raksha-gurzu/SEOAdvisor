"""Site Snapshot pipeline (snapshot_pipeline.py), offline with fakes."""

import threading

import httpx
import pytest

from seo_engine.snapshot_pipeline import (
    SNAPSHOT_STEPS,
    SnapshotError,
    SnapshotRun,
    run_snapshot,
)
from snapshot_fakes import (
    HOME,
    OURS,
    FakeDates,
    FakeLink,
    FakeProber,
    FakeSpeed,
    WaitingReader,
    snapshot_deps,
)


def run(**deps_over) -> tuple[SnapshotRun, list[tuple[str, str, str]]]:
    r = SnapshotRun(site="ours.com")
    steps: list[tuple[str, str, str]] = []
    run_snapshot(r, snapshot_deps(**deps_over), lambda n, st, d: steps.append((n, st, d)))
    return r, steps


def test_a_full_snapshot() -> None:
    r, steps = run()
    res = r.result
    assert [s for s, st, _ in steps if st == "done"] == [n for n, _ in SNAPSHOT_STEPS]
    assert res.domain == "ours.com" and res.home == HOME
    # Keywords: 3 checked (the brand keyword "ours pricing" is never checked), 2 in the top 20.
    assert [(k.keyword, k.position) for k in res.keywords] == [
        ("client portal software", 2),
        ("client workspace software", 12),
        ("secure client portal", None),
    ]
    assert (res.keywords_checked, res.keywords_found) == (3, 2)
    assert [(g.label, g.count) for g in res.groups] == [
        ("1-3", 1),
        ("4-10", 0),
        ("11-20", 1),
        ("not in top 20", 1),
    ]
    # Visits: Bing x US ratio x click rate at the position; all 3 have Bing numbers.
    assert res.visits_keywords == 3 and res.visits is not None and res.visits > 0
    assert res.top_pages[0].url == "https://ours.com/portal"
    assert res.top_pages[0].keywords == ["client portal software"]
    # Competitors on page 1 for 2 or more keywords: moxo.com and rival.io.
    assert {c.domain for c in res.competitors} == {"moxo.com", "rival.io"}
    # Facts and checks.
    assert res.facts.link.score == 2.5 and res.facts.majestic.ref_subnets == 12
    assert res.facts.tranco_rank == 250_000 and res.facts.dates.registered.year == 2019
    assert [(v.metric, v.status) for v in res.vitals] == [
        ("largest_contentful_paint", "good"),
        ("interaction_to_next_paint", "needs work"),
        ("cumulative_layout_shift", "poor"),
    ]
    assert res.checks is not None and res.checks.count("pass") == 10
    assert res.sitemap_urls == 3 and res.sitemap_files == 1
    assert r.credits_used == 6


def test_speed_is_asked_for_the_address_the_site_settles_on() -> None:
    speed = FakeSpeed()
    run(speed=speed)
    assert speed.asked == ["https://www.ours.com"]  # CrUX has no data for a redirecting origin


def test_page_bodies_are_not_stored_with_the_run() -> None:
    r, _ = run()
    assert r.probe.homepage.body == "" and r.probe.robots.body == ""
    assert "<html" not in r.model_dump_json()


def test_facts_run_at_the_same_time_as_the_main_steps() -> None:
    started = threading.Event()
    reader = WaitingReader([OURS], started)
    run(reader=reader, dates=FakeDates(started=started))
    assert reader.saw_facts_start  # a fact lookup began before the site was read


def test_without_serper_the_facts_still_show() -> None:
    r, steps = run(search=None)
    assert r.ranks is None and r.result.keywords == []
    assert "Google positions need SERPER_API_KEY in .env." in r.notes
    assert r.result.facts.link.score == 2.5 and r.result.checks is not None
    assert ("google", "done", "0 keywords, 6 credits") in steps


def test_an_unreadable_site_still_gets_facts_and_checks() -> None:
    r, _ = run(reader=snapshot_deps().reader.__class__([]))  # reads nothing
    assert r.discovery is None and r.result.keywords == []
    assert any(n.startswith("Couldn't read any page of ours.com") for n in r.notes)
    assert r.result.facts.dates is not None and r.result.checks is not None


def test_no_keyword_with_demand_is_a_note() -> None:
    from fakes import FakeAutocomplete, FakeKeywords

    r, _ = run(keywords=FakeKeywords({}), autocomplete=FakeAutocomplete(set()))
    assert "No keyword with search demand was found for this site's pages." in r.notes
    assert r.result.facts.link is not None


def test_failing_fact_sources_become_notes() -> None:
    class BrokenMajestic:
        def lookup(self, domain, exact=False):
            raise httpx.ConnectError("down")

    r, _ = run(
        majestic=BrokenMajestic(), link=FakeLink(status="error"), prober=FakeProber(fail=True)
    )
    facts = r.result.facts
    assert facts.majestic is None and not facts.majestic_read
    assert "Majestic Million failed (ConnectError)" in r.notes
    assert "link score: Open PageRank: HTTP 401 (invalid key)" in r.notes
    assert "technical checks failed (RuntimeError)" in r.notes
    assert r.result.checks is None and r.result.keywords  # the rest still works


def test_not_in_the_majestic_list_is_not_an_error() -> None:
    from seo_engine.providers.majestic import DictMajestic

    r, _ = run(majestic=DictMajestic([]))
    assert r.result.facts.majestic is None and r.result.facts.majestic_read


def test_a_bad_address_is_the_only_hard_error() -> None:
    with pytest.raises(SnapshotError, match="Enter a website address"):
        run_snapshot(SnapshotRun(site="not a site"), snapshot_deps())


def test_the_llm_cost_sink_is_the_run(tmp_path, monkeypatch) -> None:
    """snapshot_deps_from_env must hand run.add_cost to the paid LLM (CLAUDE.md rule 5)."""
    from seo_engine.config import GapSettings, Settings, SnapshotSettings
    from seo_engine.providers import llm as llm_module
    from seo_engine.snapshot_pipeline import snapshot_deps_from_env

    sinks = []
    monkeypatch.setattr(
        llm_module.DeepSeekLLM,
        "from_env",
        classmethod(lambda cls, models, sink: sinks.append(sink) or cls.__new__(cls)),
    )
    gap = GapSettings(base=Settings(cache_dir=tmp_path), keywords=30, second_pass_keywords=0)
    r = SnapshotRun(site="ours.com", settings=SnapshotSettings(gap=gap))
    snapshot_deps_from_env(r)
    assert sinks == [r.add_cost]
    sinks[0](0.0021, "deepseek")
    sinks[0](0.0004, "deepseek")
    assert r.cost_usd == 0.0025 and len(r.costs) == 2


def test_visits_are_the_exact_sum() -> None:
    r, _ = run()
    # Bing x (86.01 / 8.99) rounded: 900 -> 8611, 40 -> 383, 5 -> 48 Google searches.
    # x click rate: #2 = 0.1036 -> 892; #12 = 0.0046 (capped curve) -> 2; not ranked -> 0.
    assert [k.visits for k in r.result.keywords] == [892, 2, 0]
    assert r.result.visits == 894


def test_a_broken_local_list_is_a_note_not_a_failed_snapshot() -> None:
    import sqlite3

    class BrokenMajestic:
        def lookup(self, domain, exact=False):
            raise sqlite3.OperationalError("database or disk is full")

    class BrokenTranco:
        def rank(self, domain, exact=False):
            raise ValueError("bad zip")

    r, _ = run(majestic=BrokenMajestic(), ranks=BrokenTranco())
    assert "Majestic Million failed (OperationalError)" in r.notes
    assert "Tranco list failed (ValueError)" in r.notes
    assert not r.result.facts.majestic_read and not r.result.facts.tranco_read
    # Difficulty also needs the list: it becomes unknown, and the keywords still show.
    assert "difficulty unknown: the Tranco list could not be read (ValueError)" in r.notes
    assert len(r.result.keywords) == 3
    assert {k.difficulty for k in r.result.keywords} == {None}


def test_a_link_lookup_that_raises_is_a_note() -> None:
    r, _ = run(link=FakeLink(status="raise"))
    assert r.result.facts.link is None and "link score failed (KeyError)" in r.notes


def test_speed_is_still_asked_when_the_probe_fails() -> None:
    speed = FakeSpeed()
    r, _ = run(prober=FakeProber(fail=True), speed=speed)
    assert speed.asked == ["https://ours.com"]  # the typed domain, since no home is known
    assert r.result.facts.speed is not None and r.result.checks is None
    assert r.result.home == "https://ours.com/"


def test_a_speed_error_is_a_note() -> None:
    from seo_engine.providers.crux import Speed

    class Failing:
        def speed(self, origin, form_factor="PHONE"):
            return Speed(origin=origin, status="error", note="CrUX: HTTP 403")

    r, _ = run(speed=Failing())
    assert "speed: CrUX: HTTP 403" in r.notes


def test_a_fact_that_never_answers_does_not_hold_the_snapshot() -> None:
    import time

    from seo_engine.config import SnapshotSettings

    r = SnapshotRun(site="ours.com", settings=SnapshotSettings(facts_deadline_s=0.3))
    t0 = time.monotonic()
    run_snapshot(r, snapshot_deps(dates=FakeDates(delay_s=3)))
    assert time.monotonic() - t0 < 2  # did not wait for the 3 s lookup
    assert "site dates: no answer within the time limit" in r.notes
    assert r.result.facts.dates is None and r.result.facts.link is not None


def test_a_subdomain_never_gets_its_parent_sites_numbers() -> None:
    from seo_engine.providers.majestic import DictMajestic, MajesticEntry
    from seo_engine.providers.tranco import DictRanks

    entry = MajesticEntry(domain="ours.com", global_rank=1, ref_subnets=9, ref_ips=9)
    r = SnapshotRun(site="blog.ours.com")
    run_snapshot(r, snapshot_deps(majestic=DictMajestic([entry]), ranks=DictRanks({"ours.com": 5})))
    facts = r.result.facts
    assert facts.majestic is None and facts.majestic_read  # "not in the list", not ours.com's
    assert facts.tranco_rank is None and facts.tranco_read
