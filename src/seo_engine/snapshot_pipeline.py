"""Site Snapshot fixed pipeline (docs/SITE-SNAPSHOT-PLAN.md §5.1, docs/ARCHITECTURE.md §14).

One site: read it, find the searches its pages target, check Google, measure, summarise.
Site facts (link score, popularity, speed, dates, technical checks) run in the background
from the start, so the slow Wayback lookup costs no waiting.

Only a bad address stops a snapshot. Anything else that fails (a site that cannot be read, no
keyword with demand, no Serper key or credits, a fact source that is down) becomes a note, and
the rest of the page still shows.
"""

import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from seo_engine.config import SnapshotSettings
from seo_engine.gap_pipeline import SiteReaderLike
from seo_engine.models import CostEntry
from seo_engine.providers.autocomplete import AutocompleteProvider, GoogleAutocomplete
from seo_engine.providers.base import DailyCache
from seo_engine.providers.bing import BingKeywords
from seo_engine.providers.crux import CruxSpeed, Speed, SpeedProvider
from seo_engine.providers.domain_age import DomainAge, DomainDatesProvider
from seo_engine.providers.keywords import KeywordProvider
from seo_engine.providers.llm import DailyCachedLLM, DeepSeekLLM, LLMProvider
from seo_engine.providers.majestic import MajesticLookup, MajesticMillion
from seo_engine.providers.openpagerank import LinkScoreProvider, OpenPageRank
from seo_engine.providers.search import SearchProvider
from seo_engine.providers.serper import SerperSearch
from seo_engine.providers.site_probe import SiteProbe, SiteProber, origin
from seo_engine.providers.sitemap import SiteReader, SiteSample, site_origin
from seo_engine.providers.tranco import RankLookup, TrancoRanks
from seo_engine.tools.keyword_metrics import GapMetrics, keyword_metrics
from seo_engine.tools.rank_check import RankCheck, check_ranks
from seo_engine.tools.site_checks import site_checks
from seo_engine.tools.site_keywords import KeywordDiscovery, discover_keywords
from seo_engine.tools.site_snapshot import SiteFacts, SnapshotResult, build_snapshot

SnapshotStepName = Literal["site", "keywords", "google", "facts", "summary"]
SNAPSHOT_STEPS: list[tuple[SnapshotStepName, str]] = [
    ("site", "Reading the website"),
    ("keywords", "Finding keywords"),
    ("google", "Checking Google positions"),
    ("facts", "Collecting site facts"),
    ("summary", "Building the snapshot"),
]
OnSnapshotStep = Callable[[SnapshotStepName, Literal["running", "done"], str], None]
_COST_LOCK = threading.Lock()


class SnapshotError(RuntimeError):
    """A problem the user can fix (the address), shown as written."""


class SnapshotRun(BaseModel):
    site: str  # as entered
    settings: SnapshotSettings = Field(default_factory=SnapshotSettings)
    domain: str = ""
    sample: SiteSample | None = None
    discovery: KeywordDiscovery | None = None
    ranks: RankCheck | None = None
    metrics: GapMetrics | None = None
    probe: SiteProbe | None = None
    result: SnapshotResult | None = None
    credits_used: int = 0
    cost_usd: float = 0.0
    costs: list[CostEntry] = []
    notes: list[str] = []

    def add_cost(self, usd: float, label: str = "") -> None:
        with _COST_LOCK:
            self.costs.append(CostEntry(label=label, usd=usd))
            self.cost_usd = round(self.cost_usd + usd, 6)


class Prober(Protocol):
    def probe_site(self, domain: str) -> SiteProbe: ...


@dataclass
class SnapshotDeps:
    reader: SiteReaderLike
    llm: LLMProvider
    keywords: KeywordProvider
    autocomplete: AutocompleteProvider
    search: SearchProvider | None  # None: no Serper key, so no Google positions
    ranks: RankLookup
    has_bing: bool
    link: LinkScoreProvider
    majestic: MajesticLookup
    speed: SpeedProvider
    dates: DomainDatesProvider
    prober: Prober
    credits_used: Callable[[], int] = field(default=lambda: 0)


def snapshot_origin(site: str) -> tuple[str, str]:
    """(domain, origin) or SnapshotError with a message for the user."""
    try:
        return site_origin(site)
    except ValueError as exc:
        raise SnapshotError(f"{exc}. Enter a website address like example.com.") from None


def strip_bodies(probe: SiteProbe) -> SiteProbe:
    return probe.model_copy(
        update={
            "robots": probe.robots.model_copy(update={"body": ""}) if probe.robots else None,
            "homepage": probe.homepage.model_copy(update={"body": ""}) if probe.homepage else None,
        }
    )


def _noop(step: SnapshotStepName, status: str, detail: str) -> None:
    pass


FACT_LABEL = {
    "probe": "technical checks",
    "link": "link score",
    "dates": "site dates",
    "majestic": "Majestic Million",
    "tranco": "Tranco list",
}


def _probe_then_speed(
    deps: SnapshotDeps, domain: str, s: SnapshotSettings
) -> tuple[SiteProbe | None, Speed | None, list[str]]:
    """The speed lookup needs the address the site settles on (CrUX has no data for an origin
    that redirects), so it runs after the probe; it still runs when the probe fails."""
    probe: SiteProbe | None = None
    speed: Speed | None = None
    notes: list[str] = []
    try:
        probe = deps.prober.probe_site(domain)
    except Exception as exc:  # a fact source must never stop the snapshot
        notes.append(f"technical checks failed ({type(exc).__name__})")
    home = origin(probe.home) if probe and probe.home else f"https://{domain}"
    try:
        speed = deps.speed.speed(home, s.crux_form_factor)
    except Exception as exc:  # same: never stop the snapshot
        notes.append(f"speed lookup failed ({type(exc).__name__})")
    return probe, speed, notes


def _collect_facts(
    futures: dict[str, Future], facts: SiteFacts, notes: list[str], deadline: float
) -> SiteProbe | None:
    """Wait for each fact until `deadline` (time.monotonic). A fact that fails or is late is a
    note; the snapshot goes on without it."""

    def wait(name: str) -> tuple[Any, bool]:
        try:
            return futures[name].result(timeout=max(0.0, deadline - time.monotonic())), True
        except FutureTimeout:
            notes.append(f"{FACT_LABEL[name]}: no answer within the time limit")
        except Exception as exc:  # any error, not only network errors (a broken local list)
            notes.append(f"{FACT_LABEL[name]} failed ({type(exc).__name__})")
        return None, False

    probe = None
    got, ok = wait("probe")
    if ok:
        probe, facts.speed, probe_notes = got
        notes += probe_notes
    facts.link = wait("link")[0]
    facts.dates = wait("dates")[0]
    facts.majestic, facts.majestic_read = wait("majestic")
    facts.tranco_rank, facts.tranco_read = wait("tranco")
    for label, fact in (("link score", facts.link), ("speed", facts.speed)):
        if fact is not None and fact.status == "error":
            notes.append(f"{label}: {fact.note}")
    if facts.dates:
        notes += facts.dates.notes
    return probe


def _metrics(run: SnapshotRun, deps: SnapshotDeps) -> GapMetrics:
    """Keyword numbers. Difficulty needs the Tranco list; when it cannot be read, difficulty
    becomes "Unknown" for every keyword (never a guess) and the rest still shows."""
    s = run.settings.gap
    try:
        metrics = keyword_metrics(
            run.discovery, run.ranks, [run.domain], s, deps.ranks, deps.has_bing
        )
    except Exception as exc:  # the list download or its local copy failed
        run.notes.append(
            f"difficulty unknown: the Tranco list could not be read ({type(exc).__name__})"
        )
        no_difficulty = s.model_copy(update={"difficulty_min_results": 10**6})
        metrics = keyword_metrics(
            run.discovery, run.ranks, [run.domain], no_difficulty, deps.ranks, deps.has_bing
        )
        metrics.notes = [n for n in metrics.notes if "no difficulty" not in n]
    run.notes += metrics.notes
    return metrics


def run_snapshot(run: SnapshotRun, deps: SnapshotDeps, on_step: OnSnapshotStep = _noop) -> None:
    """Fills `run` step by step. Raises SnapshotError only for a bad address."""
    s = run.settings
    domain, site_origin_url = snapshot_origin(run.site)
    run.domain = domain
    deadline = time.monotonic() + s.facts_deadline_s

    # Not a `with` block: leaving it would wait for a stuck source; shutdown(wait=False) won't.
    pool = ThreadPoolExecutor(max_workers=len(FACT_LABEL))
    try:
        futures: dict[str, Future] = {
            "probe": pool.submit(_probe_then_speed, deps, domain, s),
            "link": pool.submit(deps.link.score, domain),
            "dates": pool.submit(deps.dates.dates, domain),
            # Exact: a subdomain must not show its parent site's numbers (alice.github.io).
            "majestic": pool.submit(deps.majestic.lookup, domain, True),
            "tranco": pool.submit(deps.ranks.rank, domain, True),
        }

        on_step("site", "running", "")
        run.sample = deps.reader.read(site_origin_url)
        run.notes += run.sample.notes
        pages = len(run.sample.pages)
        if not pages:
            run.notes.append(
                f"Couldn't read any page of {domain}, so there are no keywords. The site may "
                "block automated reading in its robots.txt."
            )
        on_step("site", "done", f"{pages} pages")

        on_step("keywords", "running", "")
        if pages:
            run.discovery = discover_keywords(
                [run.sample], s.gap, deps.llm, deps.keywords, deps.autocomplete, deps.has_bing
            )
            run.notes += run.discovery.notes
        found = len(run.discovery.keywords) if run.discovery else 0
        if pages and not found:
            run.notes.append("No keyword with search demand was found for this site's pages.")
        on_step("keywords", "done", f"{found} keywords to check")

        on_step("google", "running", f"0/{found}")
        if found and deps.search is None:
            run.notes.append("Google positions need SERPER_API_KEY in .env.")
        elif found and deps.search is not None:
            run.ranks = check_ranks(
                [k.keyword for k in run.discovery.keywords],
                [domain],
                s.gap,
                deps.search,
                progress=lambda done, n: on_step("google", "running", f"{done}/{n}"),
            )
            run.notes += run.ranks.notes
            if run.ranks.rankings:
                run.metrics = _metrics(run, deps)
        run.credits_used = deps.credits_used()
        checked = len(run.ranks.rankings) if run.ranks else 0
        on_step("google", "done", f"{checked} keywords, {run.credits_used} credits")

        on_step("facts", "running", "")
        facts = SiteFacts()
        run.probe = _collect_facts(futures, facts, run.notes, deadline)
        on_step("facts", "done", "")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    on_step("summary", "running", "")
    checks = site_checks(run.probe, run.sample, s.gap.base.thresholds) if run.probe else None
    run.result = build_snapshot(
        domain,
        run.probe.home if run.probe and run.probe.home else run.sample.origin + "/",
        run.sample,
        run.discovery,
        run.ranks,
        run.metrics,
        facts,
        checks,
        s,
    )
    run.notes += [n for n in run.result.notes if n not in run.notes]
    if run.probe:  # the checks are done: do not store page bodies with the run
        run.probe = strip_bodies(run.probe)
    on_step(
        "summary",
        "done",
        f"{run.result.keywords_found} of {run.result.keywords_checked} keywords "
        f"in the top {s.gap.depth}",
    )


def snapshot_deps_from_env(run: SnapshotRun) -> SnapshotDeps:
    """Free-mode providers. Without SERPER_API_KEY the snapshot still shows the site facts."""
    s = run.settings
    base = s.gap.base
    cache = DailyCache(base.cache_dir)
    serper = SerperSearch.from_env(cache, base.language)
    autocomplete = GoogleAutocomplete(cache, base.language)
    bing = BingKeywords.from_env(cache, autocomplete, base.language)
    return SnapshotDeps(
        reader=SiteReader.from_settings(s.gap, cache),
        llm=DailyCachedLLM(DeepSeekLLM.from_env(base.models, run.add_cost), cache, base.models),
        keywords=bing,
        autocomplete=autocomplete,
        search=serper if serper.api_key else None,
        ranks=TrancoRanks(base.cache_dir),
        has_bing=bool(bing.api_key),
        link=OpenPageRank.from_env(cache, s.fact_timeout_s),
        majestic=MajesticMillion(
            base.cache_dir, s.majestic_max_age_days, timeout_s=s.majestic_download_timeout_s
        ),
        speed=CruxSpeed.from_env(cache, s.fact_timeout_s),
        dates=DomainAge(
            cache,
            base.user_agent,
            rdap_timeout_s=s.rdap_timeout_s,
            wayback_timeout_s=s.wayback_timeout_s,
        ),
        prober=SiteProber(base),
        credits_used=lambda: serper.credits_used,
    )
