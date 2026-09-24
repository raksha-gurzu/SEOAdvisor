"""seo_competitor_analysis: filter, fetch, clean and read competitor pages (§5.2, node 2-3).

Filters run in order: authority outliers, wrong format, intent/business model, length
outliers, domain diversity. Every dropped page carries its reason.
"""

import statistics
from collections import Counter
from typing import Literal

from pydantic import BaseModel, Field

from seo_engine.concurrency import pmap
from seo_engine.config import Settings
from seo_engine.deps import Deps
from seo_engine.models import Page
from seo_engine.page_types import domain_of, guess_page_type
from seo_engine.providers.fetcher import FetchedPage
from seo_engine.providers.llm import LLMProvider
from seo_engine.providers.search import SerpItem, SerpResults
from seo_engine.text import truncate_words
from seo_engine.tools.keyword_research import url_key

WRONG_FORMAT = {"forum", "video", "login", "pdf"}
OURS_URL = "ours"

PAGE_READER_SYSTEM = """You read one web page for an SEO analysis. Return:
- page_type: the kind of page (listicle, guide, product, category, comparison, tool, forum,
  video, news). A product or service landing page is "product".
- topics: 5 to 25 distinct subtopics the page actually covers, as short noun phrases of 1 to 6
  words (e.g. "file sharing with clients", "pricing per seat"). Name the idea, not the brand.
  Skip navigation, cookie, newsletter and footer boilerplate.
- questions: up to 10 searcher questions the page answers, phrased as a searcher would ask.
Only list what is on the page. Do not add anything the page does not say."""


class PageReading(BaseModel):
    page_type: Literal[
        "listicle", "guide", "product", "category", "comparison", "tool", "forum", "video", "news"
    ]
    topics: list[str] = Field(min_length=1)
    questions: list[str] = []


class Dropped(BaseModel):
    url: str
    rank: int
    reason: str


class CompetitorAnalysis(BaseModel):
    ours: Page
    ours_questions: list[str] = []
    kept: list[Page]
    dropped: list[Dropped]
    type_mix: dict[str, int]
    read_types: list[str] = []  # page type of every page read, in rank order (intent, §5.4)
    notes: list[str] = []


def read_page(
    llm: LLMProvider, text: str, title: str, headings: list[str], max_words: int
) -> PageReading:
    user = (
        f"TITLE: {title}\nHEADINGS:\n"
        + "\n".join(f"- {h}" for h in headings[:60])
        + f"\n\nTEXT:\n{truncate_words(text, max_words)}"
    )
    return llm.structured(PAGE_READER_SYSTEM, user, PageReading, tier="bulk")


def pool_results(serps: list[SerpResults]) -> list[SerpItem]:
    """Merge results of several phrases, one entry per URL at its best rank."""
    best: dict[str, SerpItem] = {}
    for serp in serps:
        for item in serp.items:
            key = url_key(item.url)
            if key not in best or item.rank < best[key].rank:
                best[key] = item
    return sorted(best.values(), key=lambda i: (i.rank, i.url))


def is_authority(domain: str, authority: list[str]) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in authority)


def choose_types(types: list[str], our_type: str, minimum: int) -> tuple[set[str], str | None]:
    """Filter 3: keep our page type if enough exist, else add the dominant types until the
    pool is big enough. Returns (types to keep, note)."""
    mix = Counter(types)
    if mix[our_type] >= minimum:
        return {our_type}, None
    keep: set[str] = {our_type} if mix[our_type] else set()
    total = mix[our_type]
    for kind, count in mix.most_common():
        if total >= minimum:
            break
        if kind not in keep:
            keep.add(kind)
            total += count
    dominant = mix.most_common(1)[0][0] if mix else None
    note = (
        f"only {mix[our_type]} {our_type} page(s) among competitors; kept "
        f"{', '.join(sorted(keep))} (dominant: {dominant})"
    )
    return keep, note


def competitor_analysis(
    deps: Deps, serps: list[SerpResults], page_text: str, settings: Settings
) -> CompetitorAnalysis:
    t = settings.thresholds
    dropped: list[Dropped] = []
    notes: list[str] = []

    # Our own page: type and topics from the same reader.
    ours_reading = read_page(deps.llm, page_text, "", [], t.llm_page_words)
    ours = Page(
        url=OURS_URL,
        source="input",
        page_type=ours_reading.page_type,
        text=page_text,
        headings=[],
        topics=ours_reading.topics,
    )

    # Filters 1 and 2 on the SERP data alone (no fetch cost).
    candidates: list[SerpItem] = []
    for item in pool_results(serps):
        domain = domain_of(item.url)
        if is_authority(domain, t.authority_domains):
            dropped.append(
                Dropped(url=item.url, rank=item.rank, reason=f"authority outlier ({domain})")
            )
        elif item.page_type in WRONG_FORMAT:
            dropped.append(
                Dropped(url=item.url, rank=item.rank, reason=f"wrong format ({item.page_type})")
            )
        else:
            candidates.append(item)

    # Fetch and read in parallel.
    fetched = pmap(deps.fetcher.fetch, [c.url for c in candidates], settings.concurrency)
    readable: list[tuple[SerpItem, FetchedPage]] = []
    for item, page in zip(candidates, fetched, strict=True):
        if page.ok:
            readable.append((item, page))
        else:
            dropped.append(
                Dropped(url=item.url, rank=item.rank, reason=f"fetch {page.status}: {page.reason}")
            )

    readings = pmap(
        lambda ip: read_page(deps.llm, ip[1].text, ip[1].title, ip[1].headings, t.llm_page_words),
        readable,
        settings.concurrency,
    )
    pages: list[tuple[SerpItem, Page, int]] = []
    for (item, fp), reading in zip(readable, readings, strict=True):
        rule_type = guess_page_type(item.url, fp.title or item.title, fp.schema_type)
        page_type = rule_type if rule_type != "unknown" else reading.page_type
        if page_type in WRONG_FORMAT:
            dropped.append(
                Dropped(url=item.url, rank=item.rank, reason=f"wrong format ({page_type})")
            )
            continue
        pages.append(
            (
                item,
                Page(
                    url=item.url,
                    source=f"google#{item.rank}",
                    page_type=page_type,
                    text=fp.text,
                    headings=fp.headings,
                    topics=reading.topics,
                ),
                fp.word_count,
            )
        )
    type_mix = dict(Counter(p.page_type for _, p, _ in pages).most_common())
    read_types = [p.page_type for _, p, _ in sorted(pages, key=lambda x: x[0].rank)]

    # Filter 3: intent / business model.
    keep_types, note = choose_types(
        [p.page_type for _, p, _ in pages], ours.page_type, t.competitors_min
    )
    if note:
        notes.append(note)
    survivors = []
    for item, page, words in pages:
        if page.page_type in keep_types:
            survivors.append((item, page, words))
        else:
            dropped.append(
                Dropped(
                    url=item.url, rank=item.rank, reason=f"different page type ({page.page_type})"
                )
            )

    # Filter 4: length outliers against the median.
    if survivors:
        median = statistics.median(w for _, _, w in survivors)
        lo, hi = median * t.length_ratio_min, median * t.length_ratio_max
        in_range = []
        for item, page, words in survivors:
            if lo <= words <= hi:
                in_range.append((item, page, words))
            else:
                dropped.append(
                    Dropped(
                        url=item.url,
                        rank=item.rank,
                        reason=f"length outlier ({words} words; median {median:.0f})",
                    )
                )
        survivors = in_range

    # Filter 5: domain diversity, then cap.
    per_domain: Counter[str] = Counter()
    kept: list[Page] = []
    for item, page, _ in survivors:
        domain = domain_of(item.url)
        if per_domain[domain] >= t.max_pages_per_domain:
            dropped.append(
                Dropped(
                    url=item.url,
                    rank=item.rank,
                    reason=f"domain limit ({t.max_pages_per_domain} per domain)",
                )
            )
        elif len(kept) >= t.competitors_max:
            dropped.append(
                Dropped(
                    url=item.url, rank=item.rank, reason=f"over the {t.competitors_max}-page cap"
                )
            )
        else:
            per_domain[domain] += 1
            kept.append(page)

    domains = {domain_of(p.url) for p in kept}
    if len(kept) < t.competitors_min:
        notes.append(
            f"only {len(kept)} competitor page(s) kept "
            f"(target {t.competitors_min} to {t.competitors_max})"
        )
    if len(domains) < t.competitors_min_domains:
        notes.append(
            f"only {len(domains)} distinct domain(s) (target >= {t.competitors_min_domains})"
        )

    return CompetitorAnalysis(
        ours=ours,
        ours_questions=ours_reading.questions,
        kept=kept,
        dropped=sorted(dropped, key=lambda d: d.rank),
        type_mix=type_mix,
        read_types=read_types,
        notes=notes,
    )
