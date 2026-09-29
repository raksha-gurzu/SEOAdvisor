"""Keyword Gap fixed pipeline (docs/ARCHITECTURE.md §13): read sites, find keywords, check
Google, measure, compare. Serves the API; every step reports progress for the UI."""

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from seo_engine.concurrency import pmap
from seo_engine.config import GapSettings
from seo_engine.models import CostEntry
from seo_engine.page_types import owns
from seo_engine.providers.autocomplete import AutocompleteProvider, GoogleAutocomplete
from seo_engine.providers.base import DailyCache
from seo_engine.providers.bing import BingKeywords
from seo_engine.providers.keywords import KeywordProvider
from seo_engine.providers.llm import DailyCachedLLM, DeepSeekLLM, LLMProvider
from seo_engine.providers.search import SearchProvider
from seo_engine.providers.serper import SerperSearch
from seo_engine.providers.sitemap import SiteReader, SiteSample, site_origin
from seo_engine.providers.tranco import RankLookup, TrancoRanks
from seo_engine.tools.keyword_gap import KeywordGapResult, keyword_gap
from seo_engine.tools.keyword_metrics import keyword_metrics
from seo_engine.tools.rank_check import RankCheck, check_ranks
from seo_engine.tools.site_keywords import KeywordDiscovery, discover_keywords, second_pass

GapStepName = Literal["sites", "keywords", "google", "metrics", "compare"]
GAP_STEPS: list[tuple[GapStepName, str]] = [
    ("sites", "Reading the websites"),
    ("keywords", "Finding keywords"),
    ("google", "Checking Google positions"),
    ("metrics", "Measuring keywords"),
    ("compare", "Comparing the sites"),
]
OnGapStep = Callable[[GapStepName, Literal["running", "done"], str], None]
_COST_LOCK = threading.Lock()


class GapError(RuntimeError):
    """A problem the user can fix (address, robots.txt, no demand), shown as written."""


class GapRun(BaseModel):
    site: str  # our site as entered
    competitors: list[str]
    settings: GapSettings = Field(default_factory=GapSettings)
    domains: list[str] = []  # ours first, as read
    sites: list[SiteSample] = []
    discovery: KeywordDiscovery | None = None
    ranks: RankCheck | None = None
    result: KeywordGapResult | None = None
    google_per_bing: float | None = None
    ctr_source: str = ""
    shares_source: str = ""  # where the Bing-to-Google ratio comes from
    credits_used: int = 0  # Serper credits (cached pages cost nothing)
    cost_usd: float = 0.0  # paid calls (LLM)
    costs: list[CostEntry] = []
    notes: list[str] = []

    def add_cost(self, usd: float, label: str = "") -> None:
        with _COST_LOCK:
            self.costs.append(CostEntry(label=label, usd=usd))
            self.cost_usd = round(self.cost_usd + usd, 6)


class SiteReaderLike(Protocol):
    def read(self, site: str) -> SiteSample: ...


@dataclass
class GapDeps:
    reader: SiteReaderLike
    llm: LLMProvider
    keywords: KeywordProvider
    autocomplete: AutocompleteProvider
    search: SearchProvider
    ranks: RankLookup
    has_bing: bool
    credits_used: Callable[[], int] = field(default=lambda: 0)


def site_origins(site: str, competitors: list[str], max_competitors: int) -> list[tuple[str, str]]:
    """(domain, origin) for every site, ours first. The domain has no "www." (for matching
    results); the origin keeps the host as typed (for fetching: some sites have no bare-domain
    address). Raises GapError with a message for the user."""
    try:
        ours = site_origin(site)
        theirs = [site_origin(c) for c in competitors if c.strip()]
    except ValueError as exc:
        raise GapError(f"{exc}. Enter a website address like example.com.") from None
    if not theirs:
        raise GapError("Add at least one competitor website.")
    if len(theirs) > max_competitors:
        raise GapError(f"Compare with at most {max_competitors} competitors.")
    domains = [ours[0]] + [d for d, _ in theirs]
    if ours[0] in domains[1:]:
        raise GapError(f"{ours[0]} is your own site; remove it from the competitors.")
    if len(set(domains[1:])) < len(domains) - 1:
        raise GapError("The same competitor is listed twice.")
    for i, a in enumerate(domains):
        for b in domains[i + 1 :]:
            if owns(a, b) or owns(b, a):  # blog.x.com's results would count for x.com too
                raise GapError(
                    f"{a} and {b} overlap (one is part of the other); compare separate sites."
                )
    return [ours, *theirs]


def validate_sites(site: str, competitors: list[str], max_competitors: int) -> list[str]:
    """Domains in order, ours first (see site_origins)."""
    return [d for d, _ in site_origins(site, competitors, max_competitors)]


def _noop(step: GapStepName, status: str, detail: str) -> None:
    pass


def run_gap(run: GapRun, deps: GapDeps, on_step: OnGapStep = _noop) -> None:
    """Fills `run` step by step. Raises GapError when the analysis cannot give an answer."""
    s = run.settings
    origins = [o for _, o in site_origins(run.site, run.competitors, s.max_competitors)]

    on_step("sites", "running", f"0 of {len(origins)} sites")
    run.sites = pmap(deps.reader.read, origins, len(origins))
    run.domains = [x.domain for x in run.sites]
    for x in run.sites:
        run.notes += [f"{x.domain}: {n}" for n in x.notes]
    if not run.sites[0].pages:
        raise GapError(
            f"Couldn't read any page of {run.domains[0]}. Check the address; the site may "
            "block automated reading in its robots.txt."
        )
    if not any(x.pages for x in run.sites[1:]):
        raise GapError("Couldn't read any competitor's pages. Check the addresses.")
    pages = sum(len(x.pages) for x in run.sites)
    on_step("sites", "done", f"{pages} pages from {len(run.sites)} sites")

    on_step("keywords", "running", "")
    run.discovery = discover_keywords(
        run.sites, s, deps.llm, deps.keywords, deps.autocomplete, deps.has_bing
    )
    run.notes += run.discovery.notes
    if not run.discovery.keywords:
        raise GapError(
            "No keyword with search demand fits your site. Try competitors closer to your business."
        )
    on_step(
        "keywords",
        "done",
        f"{len(run.discovery.keywords)} keywords to check (from {run.discovery.candidates})",
    )

    total = len(run.discovery.keywords)
    on_step("google", "running", f"0/{total}")
    run.ranks = check_ranks(
        [k.keyword for k in run.discovery.keywords],
        run.domains,
        s,
        deps.search,
        progress=lambda done, n: on_step("google", "running", f"{done}/{n}"),
    )
    run.notes += run.ranks.notes
    if not run.ranks.rankings:
        raise GapError(run.ranks.notes[0] if run.ranks.notes else "No Google results came back.")

    # Second pass (plan G13): related searches where competitors are proven to rank. Skipped
    # when the first pass ran out of Google credits; one failed search does not stop it.
    if not run.ranks.unavailable:
        extra, notes = second_pass(
            run.discovery,
            run.ranks.rankings,
            run.domains[1:],
            run.sites[0],
            s,
            deps.llm,
            deps.keywords,
            deps.autocomplete,
            deps.has_bing,
        )
        run.notes += notes
        if extra:
            more = check_ranks(
                [k.keyword for k in extra],
                run.domains,
                s,
                deps.search,
                progress=lambda done, n: on_step(
                    "google", "running", f"{total + done}/{total + n}"
                ),
            )
            run.discovery.keywords += extra
            run.ranks.rankings += more.rankings
            run.ranks.not_checked += more.not_checked
            run.ranks.unavailable = run.ranks.unavailable or more.unavailable
            run.notes += more.notes
            total += len(extra)
    run.credits_used = deps.credits_used()
    on_step(
        "google",
        "done",
        f"{len(run.ranks.rankings)} of {total} keywords, {run.credits_used} credits",
    )

    on_step("metrics", "running", "")
    metrics = keyword_metrics(run.discovery, run.ranks, run.domains, s, deps.ranks, deps.has_bing)
    run.google_per_bing, run.ctr_source = metrics.google_per_bing, metrics.ctr_source
    run.shares_source = metrics.shares_source
    on_step("metrics", "done", f"{len(metrics.rows)} keywords")

    on_step("compare", "running", "")
    run.result = keyword_gap(run.discovery, run.ranks, metrics, run.domains, s)
    run.notes += [n for n in run.result.notes if n not in run.notes]
    on_step("compare", "done", f"{len(run.result.top)} keywords to add")


def gap_deps_from_env(run: GapRun) -> GapDeps:
    """Free-mode providers; Serper is required (Gemini grounding has no positions)."""
    base = run.settings.base
    cache = DailyCache(base.cache_dir)
    serper = SerperSearch.from_env(cache, base.language)
    if not serper.api_key:
        raise GapError("Keyword Gap needs SERPER_API_KEY in .env (Google positions).")
    autocomplete = GoogleAutocomplete(cache, base.language)
    bing = BingKeywords.from_env(cache, autocomplete, base.language)
    return GapDeps(
        reader=SiteReader.from_settings(run.settings, cache),
        llm=DailyCachedLLM(DeepSeekLLM.from_env(base.models, run.add_cost), cache, base.models),
        keywords=bing,
        autocomplete=autocomplete,
        search=serper,
        ranks=TrancoRanks(base.cache_dir),
        has_bing=bool(bing.api_key),
        credits_used=lambda: serper.credits_used,
    )
