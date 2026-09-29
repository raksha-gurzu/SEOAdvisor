import httpx
import pytest

from fakes import FakeSearch
from seo_engine.config import GapSettings, Settings
from seo_engine.page_types import owns
from seo_engine.providers.search import SearchUnavailable
from seo_engine.tools.rank_check import best_position, check_ranks

DOMAINS = ["ours.com", "moxo.com", "clinked.com"]
SERPS = {
    "client portal software": [
        ("https://www.moxo.com/portal", "product"),
        ("https://g2.com/categories/client-portal", "listicle"),
        ("https://clinked.com/features", "product"),
        ("https://blog.moxo.com/best-portals", "listicle"),  # moxo again, lower
        ("https://notmoxo.com/x", "product"),
    ],
    "agency crm": [("https://hubspot.com/crm", "product"), ("https://ours.com/crm", "product")],
    "no results": [],
}


def settings(**over) -> GapSettings:
    return GapSettings(base=Settings(concurrency=1), **over)


@pytest.mark.parametrize(
    ("domain", "target", "expected"),
    [
        ("moxo.com", "moxo.com", True),
        ("www.moxo.com", "moxo.com", True),
        ("blog.moxo.com", "moxo.com", True),
        ("moxo.com", "www.moxo.com", True),
        ("notmoxo.com", "moxo.com", False),
        ("moxo.com.evil.io", "moxo.com", False),
    ],
)
def test_owns(domain: str, target: str, expected: bool) -> None:
    assert owns(domain, target) is expected


def test_positions_per_domain() -> None:
    out = check_ranks(["client portal software"], DOMAINS, settings(), FakeSearch(SERPS))
    [r] = out.rankings
    assert list(r.positions) == DOMAINS  # ours first
    assert r.positions["ours.com"].position is None
    assert r.positions["moxo.com"].position == 1  # best of its two results
    assert r.positions["moxo.com"].url == "https://www.moxo.com/portal"
    assert r.positions["clinked.com"].position == 3
    assert r.results_seen == 5 and len(r.results) == 5


def test_best_position_ignores_lookalike_domains() -> None:
    items = FakeSearch(SERPS).top("client portal software", "US", 20).items
    assert best_position(items, "notmoxo.com").position == 5
    assert best_position(items, "hubspot.com").position is None


class RecordingSearch(FakeSearch):
    def __init__(self, serps, fail_after: int | None = None, error_on: str | None = None):
        super().__init__(serps)
        self.fail_after = fail_after
        self.error_on = error_on
        self.stop_seen: list[frozenset[str]] = []
        self.depths: list[int] = []

    def top(self, phrase, country, n, stop_domains=frozenset()):
        self.stop_seen.append(stop_domains)
        self.depths.append(n)
        if self.fail_after is not None and len(self.calls) >= self.fail_after:
            raise SearchUnavailable("HTTP 400: Not enough credits")
        if phrase == self.error_on:
            raise httpx.ReadTimeout("slow")
        return super().top(phrase, country, n, stop_domains)


def test_depth_and_stop_domains_are_passed_to_the_provider() -> None:
    search = RecordingSearch(SERPS)
    check_ranks(["agency crm"], DOMAINS, settings(depth=30), search)
    assert search.stop_seen == [frozenset(DOMAINS)]
    assert search.depths == [30]


def test_credits_running_out_keeps_results_and_lists_the_rest() -> None:
    keywords = ["client portal software", "agency crm", "no results", "extra"]
    search = RecordingSearch(SERPS, fail_after=2)
    out = check_ranks(keywords, DOMAINS, settings(), search)
    assert [r.keyword for r in out.rankings] == ["client portal software", "agency crm"]
    assert out.not_checked == ["no results", "extra"]
    assert len(search.calls) == 2  # after the first refusal, no more calls are made
    assert out.notes == [
        "Google results stopped after 2 of 4 keywords (HTTP 400: Not enough credits). "
        "Add Serper credits or run again tomorrow."
    ]


def test_one_failed_search_is_skipped_not_fatal() -> None:
    search = RecordingSearch(SERPS, error_on="agency crm")
    out = check_ranks(["client portal software", "agency crm"], DOMAINS, settings(), search)
    assert [r.keyword for r in out.rankings] == ["client portal software"]
    assert out.not_checked == ["agency crm"]
    assert "some searches failed (ReadTimeout); those keywords were skipped" in out.notes


def test_keyword_without_results_is_noted() -> None:
    out = check_ranks(["no results"], DOMAINS, settings(), FakeSearch(SERPS))
    assert out.rankings[0].results_seen == 0
    assert all(p.position is None for p in out.rankings[0].positions.values())
    assert "1 keyword(s) returned no Google results" in out.notes


def test_progress_is_reported_per_keyword() -> None:
    seen: list[tuple[int, int]] = []
    keywords = ["client portal software", "agency crm", "no results"]
    check_ranks(
        keywords, DOMAINS, settings(), FakeSearch(SERPS), progress=lambda d, t: seen.append((d, t))
    )
    assert seen == [(1, 3), (2, 3), (3, 3)]
