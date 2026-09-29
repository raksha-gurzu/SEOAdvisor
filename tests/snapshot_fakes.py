"""Shared fake world for the Site Snapshot tests: ours.com from the Keyword Gap fakes, with
Google results where it ranks, and fake site-fact providers."""

import threading
from datetime import date

from fakes import FakeAutocomplete, FakeKeywords, FakeSearch
from gap_fakes import ANSWERS, SITES, VOLUMES, FakeReader, llm_for
from seo_engine.providers.crux import Speed
from seo_engine.providers.domain_age import DomainDates
from seo_engine.providers.majestic import DictMajestic, MajesticEntry
from seo_engine.providers.openpagerank import LinkScore, LinkScorePoint
from seo_engine.providers.site_probe import Hop, Probe, SiteProbe
from seo_engine.providers.tranco import DictRanks
from seo_engine.snapshot_pipeline import SnapshotDeps

OURS = SITES[0].model_copy(
    update={"source": "sitemap", "sitemaps": ["https://ours.com/sitemap.xml"], "sitemap_urls": 3}
)
HOME = "https://www.ours.com/"


# ours.com targets: client workspace software, client portal software, secure client portal.
def filler(prefix: str, n: int) -> list[tuple[str, str]]:
    """Sites that show for one keyword only, so they are never suggested as competitors."""
    return [(f"https://{prefix}{i}.com/", "product") for i in range(n)]


SERPS = {
    "client portal software": [
        ("https://moxo.com/portal", "product"),
        ("https://ours.com/portal", "product"),  # #2
        ("https://rival.io/portal", "product"),
        *filler("a", 7),
    ],
    "client workspace software": [
        *filler("b", 11),
        ("https://ours.com/", "product"),  # #12, page 2
    ],
    "secure client portal": [
        ("https://moxo.com/security", "product"),
        ("https://rival.io/secure", "product"),
        *filler("c", 8),
    ],  # ours.com not in the top 20
}
AUTO = {"client workspace software", "client portal software", "secure client portal"}

PAGE = """<html><head><title>Ours: the client workspace for agencies that ship on time</title>
<meta name="description" content="Ours gives agencies one calm place for client files, approvals
and updates. Start free today and bring every client project together.">
<link rel="canonical" href="https://www.ours.com/"></head><body>Hi</body></html>"""


class FakeLink:
    def __init__(self, status: str = "ok") -> None:
        self.status = status
        self.asked: list[str] = []

    def score(self, domain: str) -> LinkScore:
        self.asked.append(domain)
        if self.status == "raise":
            raise KeyError("date")  # a malformed answer that slipped through
        if self.status == "error":
            return LinkScore(
                domain=domain, status="error", note="Open PageRank: HTTP 401 (invalid key)"
            )
        if self.status != "ok":
            return LinkScore(domain=domain, status=self.status)
        return LinkScore(
            domain=domain,
            status="ok",
            score=2.5,
            rank=1_000_000,
            referring_domains=20,
            history=[
                LinkScorePoint(month=date(2026, 8, 1), score=2.4),
                LinkScorePoint(month=date(2026, 9, 1), score=2.5),
            ],
        )


class FakeSpeed:
    def __init__(self) -> None:
        self.asked: list[str] = []

    def speed(self, origin: str, form_factor: str = "PHONE") -> Speed:
        self.asked.append(origin)
        return Speed(
            origin=origin,
            status="ok",
            p75={
                "largest_contentful_paint": 2100,
                "interaction_to_next_paint": 320,
                "cumulative_layout_shift": 0.3,
            },
        )


class FakeDates:
    def __init__(self, started: threading.Event | None = None, delay_s: float = 0.0) -> None:
        self.started = started  # set when the lookup begins
        self.delay_s = delay_s

    def dates(self, domain: str) -> DomainDates:
        if self.started is not None:
            self.started.set()
        if self.delay_s:
            threading.Event().wait(self.delay_s)
        return DomainDates(domain=domain, registered=date(2019, 1, 2), first_seen=date(2018, 5, 6))


class FakeProber:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def probe_site(self, domain: str) -> SiteProbe:
        if self.fail:
            raise RuntimeError("probe broke")
        moved = [Hop(url=f"https://{domain}/", status=301)]
        return SiteProbe(
            domain=domain,
            variants=[
                Probe(url=f"https://{domain}/", status=200, final_url=HOME, hops=moved),
                Probe(url=HOME, status=200, final_url=HOME),
                Probe(url=f"http://{domain}/", status=200, final_url=HOME, hops=moved),
                Probe(url=f"http://www.{domain}/", status=200, final_url=HOME, hops=moved),
            ],
            home=HOME,
            robots=Probe(
                url=HOME + "robots.txt",
                status=200,
                final_url=HOME + "robots.txt",
                body="User-agent: *\nAllow: /\n",
            ),
            homepage=Probe(url=HOME, status=200, final_url=HOME, body=PAGE),
        )


class WaitingReader(FakeReader):
    """Reads only after a fact lookup has started. If the facts ran after the reader, one
    after the other, `started` would never be set and `saw_facts_start` stays False."""

    def __init__(self, sites, started: threading.Event) -> None:
        super().__init__(sites)
        self.started = started
        self.saw_facts_start = False

    def read(self, site: str):
        self.saw_facts_start = self.started.wait(timeout=5)
        return super().read(site)


MAJESTIC = DictMajestic(
    [MajesticEntry(domain="ours.com", global_rank=900_000, ref_subnets=12, ref_ips=15)]
)


def snapshot_deps(**over) -> SnapshotDeps:
    values = dict(
        reader=FakeReader([OURS]),
        llm=llm_for(ANSWERS),
        keywords=FakeKeywords(VOLUMES),
        autocomplete=FakeAutocomplete(AUTO),
        search=FakeSearch(SERPS),
        ranks=DictRanks({"ours.com": 250_000}),
        has_bing=True,
        link=FakeLink(),
        majestic=MAJESTIC,
        speed=FakeSpeed(),
        dates=FakeDates(),
        prober=FakeProber(),
        credits_used=lambda: 6,
    )
    values.update(over)
    return SnapshotDeps(**values)
