"""Site reader for Keyword Gap: picks a site's key pages and reads their titles and headings.

Order (docs/KEYWORD-GAP-PLAN.md Step 1, G6): robots.txt `Sitemap:` lines, then the common
paths, then homepage links when the sitemap gives too few pages. Every fetch goes through
`HttpFetcher`, so robots.txt (RFC 9309) and the daily cache apply to sitemaps and pages alike.
"""

import re
import threading
from collections import defaultdict
from collections.abc import Callable
from typing import Literal
from urllib.parse import urljoin, urlparse

import httpx
from lxml import etree
from lxml import html as lxml_html
from pydantic import BaseModel

from seo_engine.concurrency import pmap
from seo_engine.config import GapSettings
from seo_engine.page_types import domain_of, owns
from seo_engine.providers.base import DailyCache, TooLarge, bounded_get, gunzip_capped
from seo_engine.providers.fetcher import FetchStatus, HttpFetcher, render_headless

Render = Callable[[str, str, float], str]  # (url, user agent, timeout) -> HTML

COMMON_PATHS = ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml")
# Child sitemaps in an index: pages that sell first, posts last, never tags or media.
CHILD_FIRST = re.compile(r"page|product|service|solution|feature|landing|pricing", re.I)
CHILD_LAST = re.compile(r"post|blog|news|article", re.I)
# Whole words only: dropping is costly ("format" must not drop "information-sitemap.xml").
CHILD_SKIP = re.compile(
    r"(?<![a-z])(tags?|authors?|attachments?|images?|videos?|media|formats?|users)(?![a-z])",
    re.I,
)
PAGINATION = re.compile(r"/page/\d+(/|$)")
# Search-engine ownership files (live: gurzu.com lists google385b42146547b16e.html).
VERIFICATION_FILE = re.compile(
    r"/(google[0-9a-f]{8,}\.html|yandex_[0-9a-f]+\.html|bingsiteauth\.xml)$"
)
LANG_PREFIX = re.compile(r"^[a-z]{2}(?:[-_][a-z]{2,4})?$")


def xml_parser() -> etree.XMLParser:
    """A new parser per call: lxml parser objects must not be shared between threads."""
    return etree.XMLParser(resolve_entities=False, no_network=True, recover=True, huge_tree=False)


SiteSource = Literal["sitemap", "sitemap+links", "links", "none"]


class SitemapEntry(BaseModel):
    url: str
    lastmod: str = ""


class ParsedSitemap(BaseModel):
    kind: Literal["urlset", "index", "invalid"]
    entries: list[SitemapEntry] = []


class SitePage(BaseModel):
    url: str
    status: FetchStatus
    title: str = ""
    headings: list[str] = []
    snippet: str = ""  # first words of the main text
    word_count: int = 0


class SiteSample(BaseModel):
    """What the keyword step sees of one site."""

    domain: str  # "gurzu.com"
    origin: str  # "https://gurzu.com"
    source: SiteSource = "none"
    sitemaps: list[str] = []  # sitemap files read
    urls_found: int = 0  # usable page URLs before sampling
    sitemap_urls: int = 0  # distinct pages of this domain the sitemap files list, before skipping
    sitemap_capped: bool = False  # more sitemap files were listed than `max_sitemap_files` read
    pages: list[SitePage] = []
    notes: list[str] = []


def site_origin(raw: str) -> tuple[str, str]:
    """("gurzu.com", "https://gurzu.com") from "gurzu.com", "http://www.gurzu.com/x" etc."""
    url = raw.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    if not host or "." not in host:
        raise ValueError(f"not a website address: {raw!r}")
    return host.removeprefix("www."), f"https://{host}"


def parse_sitemap(content: bytes, max_bytes: int = 10_000_000) -> ParsedSitemap:
    """A sitemap or sitemap index (sitemaps.org). Gzip is unpacked up to `max_bytes` (the
    sitemaps.org limit), so a small .gz cannot unpack to gigabytes; XXE is off."""
    if content[:2] == b"\x1f\x8b":
        try:
            content = gunzip_capped(content, max_bytes)
        except (TooLarge, OSError, EOFError, ValueError):
            return ParsedSitemap(kind="invalid")
    try:
        root = etree.fromstring(content, xml_parser())
    except etree.XMLSyntaxError:
        return ParsedSitemap(kind="invalid")
    if root is None:
        return ParsedSitemap(kind="invalid")
    kind = etree.QName(root).localname
    if kind not in ("urlset", "sitemapindex"):
        return ParsedSitemap(kind="invalid")
    child = "url" if kind == "urlset" else "sitemap"
    entries: list[SitemapEntry] = []
    for node in root.xpath(f"./*[local-name()='{child}']"):
        loc = "".join(node.xpath("./*[local-name()='loc']/text()")).strip()
        lastmod = "".join(node.xpath("./*[local-name()='lastmod']/text()")).strip()
        if loc:
            entries.append(SitemapEntry(url=loc, lastmod=lastmod))
    return ParsedSitemap(kind="urlset" if kind == "urlset" else "index", entries=entries)


def child_order(urls: list[str]) -> list[str]:
    """Child sitemaps of an index, most useful first; tag/author/media sitemaps dropped."""
    kept = [u for u in urls if not CHILD_SKIP.search(urlparse(u).path)]

    def rank(u: str) -> int:
        path = urlparse(u).path
        return 0 if CHILD_FIRST.search(path) else 2 if CHILD_LAST.search(path) else 1

    return sorted(kept, key=rank)  # stable: keeps the site's own order within a rank


def segments(url: str) -> list[str]:
    return [s for s in urlparse(url).path.lower().split("/") if s]


def skip_reason(url: str, domain: str, s: GapSettings) -> str | None:
    """Why a sitemap URL is not a page worth reading, or None to keep it."""
    parts = urlparse(url)
    path = parts.path.lower()
    if parts.scheme not in ("http", "https") or domain_of(url) != domain:
        return "other site"
    if parts.query:
        return "query string"
    if "http:" in path or "https:" in path:
        return "broken link"  # e.g. gurzu.com/https:/calendly.com/... in a live sitemap
    if path.endswith(tuple(s.skip_extensions)) or VERIFICATION_FILE.search(path):
        return "not a web page"
    if PAGINATION.search(path):
        return "pagination"
    segs = segments(url)
    if len(segs) == 1 and segs[0] in s.listing_sections:
        return "list page"
    for seg in segs:
        if (
            seg in s.skip_segments
            or seg.startswith(tuple(s.skip_prefixes))
            or any(c in seg for c in s.skip_contains)
        ):
            return f"skipped section '{seg}'"
    return None


def page_key(url: str) -> str:
    """Identity for de-duplication only: www/non-www, http/https, /x and /x/ and #fragments
    are one page (live: moxo.com lists www URLs). Pages are fetched at their own URL."""
    parts = urlparse(url)
    host = (parts.hostname or "").removeprefix("www.")
    return f"{host}{parts.path.rstrip('/') or '/'}"


def without_fragment(url: str) -> str:
    return url.split("#", 1)[0]


def other_languages(urls: list[str], language: str) -> set[str]:
    """First path segments that are other-language versions ("de", "pt-br").

    Only when a site shows 2 or more language prefixes, so a section called /ai/ or /it/ on
    a one-language site is kept.
    """
    prefixes = {seg[0] for u in urls if (seg := segments(u)) and LANG_PREFIX.match(seg[0])}
    if len(prefixes) < 2:
        return set()
    return {p for p in prefixes if p.split("-")[0].split("_")[0] != language.lower()}


def select_pages(entries: list[SitemapEntry], home: str | None, n: int) -> list[str]:
    """Up to n URLs spread across site sections, `home` first (None: leave it out).

    Round-robin over sections (first path segment; one-segment pages share a "top" section),
    smallest sections first, so 267 blog posts cannot crowd out 13 service pages. Within a
    section: shorter paths first, then the newest lastmod. URLs keep their own form.
    """
    groups: dict[str, list[SitemapEntry]] = defaultdict(list)
    seen: set[str] = {page_key(home)} if home else set()
    for e in entries:
        key = page_key(e.url)
        if key in seen or (home is None and segments(e.url) == []):
            continue
        seen.add(key)
        url = without_fragment(e.url)
        segs = segments(url)
        groups["" if len(segs) <= 1 else segs[0]].append(e.model_copy(update={"url": url}))
    for items in groups.values():
        items.sort(key=lambda e: e.lastmod, reverse=True)
        items.sort(key=lambda e: len(segments(e.url)))  # stable: newest first within a depth
    order = sorted(groups, key=lambda g: (g != "", len(groups[g]), g))
    picked = [home] if home else []
    while len(picked) < n and any(groups[g] for g in order):
        for g in order:
            if groups[g] and len(picked) < n:
                picked.append(groups[g].pop(0).url)
    return picked[:n]


def page_links(html: str, base: str) -> list[str]:
    """Absolute link targets in page order, duplicates removed."""
    try:
        tree = lxml_html.fromstring(html)
    except (etree.ParserError, ValueError):
        return []
    out = [urljoin(base, h.strip()) for h in tree.xpath("//a/@href") if h.strip()]
    return list(dict.fromkeys(u.split("#")[0] for u in out if u.startswith(("http", "/"))))


def limited(render: Render, workers: int) -> Render:
    """At most `workers` headless browsers at a time: five small sites read in parallel could
    otherwise start about 20 Chrome processes."""
    gate = threading.BoundedSemaphore(workers)

    def run(url: str, user_agent: str, timeout_s: float) -> str:
        with gate:
            return render(url, user_agent, timeout_s)

    return run


def uses_browser(s: GapSettings) -> bool:
    return s.links_headless_below > 0 or s.small_site_headless_pages > 0


class SiteReader:
    def __init__(
        self,
        settings: GapSettings,
        fetcher: HttpFetcher,
        cache: DailyCache,
        render: Render | None = None,
    ) -> None:
        self.s = settings
        self.fetcher = fetcher  # no browser: fast for large sites
        self.cache = cache
        self.render = limited(render, settings.browser_workers) if render else None
        self._rendering: HttpFetcher | None = None

    @classmethod
    def from_settings(cls, settings: GapSettings, cache: DailyCache | None = None) -> "SiteReader":
        base = settings.base.model_copy(
            update={"headless_fallback": settings.site_headless_fallback}
        )
        cache = cache or DailyCache(base.cache_dir)
        render = render_headless if uses_browser(settings) else None
        return cls(settings, HttpFetcher(base, cache), cache, render)

    def rendering_fetcher(self) -> HttpFetcher:
        """Fetcher with the browser fallback, for small sites. Shares the HTTP client and cache."""
        if self._rendering is None:
            base = self.s.base.model_copy(update={"headless_fallback": True})
            self._rendering = HttpFetcher(base, self.cache, self.fetcher.http, render=self.render)
        return self._rendering

    def _get(self, url: str) -> tuple[bytes | None, bool]:
        """(raw bytes of a robots-allowed URL or None, whether the outcome may be cached).

        Size and time are capped while downloading. Only lasting answers are cached (200, 4xx,
        a robots.txt Disallow, too large): a timeout, a 5xx or an unreachable robots.txt may
        work later the same day.
        """
        if not self.fetcher.allowed(url):
            return None, not self.fetcher.robots_unreachable(url)
        try:
            got = bounded_get(
                self.fetcher.http, url, self.s.max_sitemap_bytes, self.s.base.fetch_deadline_s
            )
        except httpx.HTTPError:
            return None, False
        if got.status >= 500 or got.status == 429:
            return None, False
        if got.status != 200 or got.too_large:
            return None, True
        return got.content, True

    def _sitemap(self, url: str) -> ParsedSitemap:
        cached = self.cache.get("sitemap", url)
        if cached is not None:
            return ParsedSitemap.model_validate(cached)
        content, cacheable = self._get(url)
        if content:
            parsed = parse_sitemap(content, self.s.max_sitemap_bytes)
        else:
            parsed = ParsedSitemap(kind="invalid")
        if cacheable:
            self.cache.set("sitemap", url, parsed.model_dump())
        return parsed

    def sitemap_entries(self, origin: str) -> tuple[list[SitemapEntry], list[str], bool]:
        """Page entries from the site's sitemaps, the sitemap files that were read, and whether
        files were left unread at the `max_sitemap_files` cap.

        Only sitemaps on the site's own domain are fetched: robots.txt and sitemap indexes are
        written by the site, and could otherwise point the server anywhere. At most
        `max_sitemap_files` requests are made, whatever their outcome.
        """
        domain = domain_of(origin)
        own = lambda u: urlparse(u).scheme in ("http", "https") and owns(domain_of(u), domain)  # noqa: E731
        listed = [u for u in self.fetcher.robots(origin + "/").sitemaps if own(u)]
        from_robots = bool(listed)
        common = [origin + p for p in COMMON_PATHS]
        queue = listed if from_robots else list(common)
        read: list[str] = []
        entries: list[SitemapEntry] = []
        seen: set[str] = set()
        attempts = 0
        while queue and attempts < self.s.max_sitemap_files:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            attempts += 1
            parsed = self._sitemap(url)
            if parsed.kind == "invalid":
                continue
            read.append(url)
            if url in common:
                # The common paths are alternatives: once one of them is a sitemap (a page list
                # or an index), the others are not needed. Children of an index are all read.
                queue = [u for u in queue if u not in common]
            if parsed.kind == "index":
                children = [c for c in child_order([e.url for e in parsed.entries]) if own(c)]
                queue = children[: self.s.max_sitemap_files] + queue
            else:
                entries += parsed.entries
        capped = any(u not in seen for u in queue if u not in common)
        return entries, read, capped

    def homepage_links(self, home: str, domain: str) -> list[SitemapEntry]:
        """Links on the homepage; rendered in the browser when the HTML has too few."""
        cached = self.cache.get("site_links", home)
        if cached is None:
            content, cacheable = self._get(home)
            cached = page_links(content.decode("utf-8", "replace"), home) if content else []
            own = {page_key(u) for u in cached if domain_of(u) == domain} - {page_key(home)}
            if content and self.render and len(own) < self.s.links_headless_below:
                try:
                    html = self.render(home, self.s.base.user_agent, self.s.base.fetch_timeout_s)
                    cached = list(dict.fromkeys(cached + page_links(html, home)))
                except Exception:  # the browser is best effort; keep the plain links
                    pass
            if cacheable:
                self.cache.set("site_links", home, cached)
        return [SitemapEntry(url=u) for u in cached]

    def _page(self, url: str, fetcher: HttpFetcher | None = None) -> SitePage:
        page = (fetcher or self.fetcher).fetch(url)
        return SitePage(
            url=url,
            status=page.status,
            title=page.title,
            headings=page.headings[: self.s.headings_per_page],
            snippet=" ".join(page.text.split()[: self.s.snippet_words]),
            word_count=page.word_count,
        )

    def read(self, site: str) -> SiteSample:
        domain, origin = site_origin(site)
        sample = SiteSample(domain=domain, origin=origin)
        entries, sample.sitemaps, sample.sitemap_capped = self.sitemap_entries(origin)
        # The site's own homepage URL (live: moxo.com lists https://www.moxo.com/).
        home = next(
            (
                without_fragment(e.url)
                for e in entries
                if page_key(e.url) == page_key(origin + "/") and domain_of(e.url) == domain
            ),
            origin + "/",
        )
        sample.origin = home.rstrip("/")
        sample.sitemap_urls = len({page_key(e.url) for e in entries if domain_of(e.url) == domain})
        source: SiteSource = "sitemap" if entries else "none"
        usable = self._usable(entries, domain, sample)
        if len(usable) < self.s.pages_per_site:
            links = self._usable(self.homepage_links(home, domain), domain, sample, quiet=True)
            known = {page_key(e.url) for e in usable}
            extra = [e for e in links if page_key(e.url) not in known]
            if extra:
                usable += extra
                source = "sitemap+links" if source == "sitemap" else "links"
        sample.source = source
        home_ok = self.fetcher.allowed(home)
        sample.urls_found = len(
            {page_key(e.url) for e in usable} | ({page_key(home)} if home_ok else set())
        )
        urls = select_pages(usable, home if home_ok else None, self.s.pages_per_site)
        small = self.render is not None and len(urls) <= self.s.small_site_headless_pages
        fetcher = self.rendering_fetcher() if small else self.fetcher
        pages = pmap(lambda u: self._page(u, fetcher), urls, self.s.site_fetch_workers)
        sample.pages = [p for p in pages if p.title or p.headings]
        dropped = len(pages) - len(sample.pages)
        if dropped:
            sample.notes.append(f"{dropped} page(s) had no title or headings")
        if not sample.pages:
            sample.notes.append("no readable pages: check the address, robots.txt or sitemap")
        return sample

    def _usable(
        self, entries: list[SitemapEntry], domain: str, sample: SiteSample, quiet: bool = False
    ) -> list[SitemapEntry]:
        languages = other_languages([e.url for e in entries], self.s.base.language)
        kept: list[SitemapEntry] = []
        skipped: dict[str, int] = defaultdict(int)
        for e in entries:
            reason = skip_reason(e.url, domain, self.s)
            if reason is None and (segs := segments(e.url)) and segs[0] in languages:
                reason = "other language"
            if reason is None and not self.fetcher.allowed(e.url):
                reason = "blocked by robots.txt"
            if reason:
                skipped[reason] += 1
            else:
                kept.append(e)
        if skipped and not quiet:
            summary = ", ".join(f"{n} {r}" for r, n in sorted(skipped.items(), key=lambda x: -x[1]))
            sample.notes.append(f"sitemap URLs skipped: {summary}")
        return kept
