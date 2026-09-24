"""Page fetcher: httpx + trafilatura, robots.txt check, length check, headless fallback."""

import json
from collections.abc import Callable
from typing import Literal, Protocol
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura
from lxml import etree
from lxml import html as lxml_html
from pydantic import BaseModel

from seo_engine.config import Settings
from seo_engine.providers.base import DailyCache

FetchStatus = Literal["ok", "too_short", "robots_blocked", "http_error", "not_html"]


class FetchedPage(BaseModel):
    url: str
    status: FetchStatus
    title: str = ""
    text: str = ""
    headings: list[str] = []
    word_count: int = 0
    schema_type: str = ""
    method: Literal["httpx", "headless", "none"] = "none"
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class PageFetcher(Protocol):
    def fetch(self, url: str) -> FetchedPage: ...


def _schema_type(tree: etree._Element) -> str:
    """First schema.org @type found in JSON-LD, or ""."""
    for node in tree.xpath('//script[@type="application/ld+json"]/text()'):
        try:
            data = json.loads(node)
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            obj = stack.pop(0)
            if not isinstance(obj, dict):
                continue
            kind = obj.get("@type")
            if isinstance(kind, list):
                kind = kind[0] if kind else None
            if isinstance(kind, str) and kind not in (
                "WebSite",
                "Organization",
                "BreadcrumbList",
                "WebPage",
                "SiteNavigationElement",
            ):
                return kind
            stack += obj.get("@graph") or []
    return ""


DROP_TAGS = ("script", "style", "noscript", "svg", "template", "iframe", "nav", "footer", "form")
BLOCK_TAGS = (
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "li",
    "blockquote",
    "dt",
    "dd",
    "figcaption",
    "td",
    "th",
    "summary",
)
BOILERPLATE = ("cookie", "consent", "gdpr", "newsletter", "navbar", "menu", "breadcrumb")


def visible_text(html: str) -> tuple[str, list[str]]:
    """Every visible heading, paragraph and list item, in page order, one per line.

    For landing pages, where article extractors keep only one section. Drops scripts,
    navigation, footers, forms and cookie/newsletter blocks.
    """
    try:
        tree = lxml_html.fromstring(html)
    except (etree.ParserError, ValueError):
        return "", []
    for el in tree.xpath("//" + " | //".join(DROP_TAGS)):
        el.drop_tree()
    for el in tree.xpath('//*[@role="navigation" or @role="contentinfo" or @aria-hidden="true"]'):
        el.drop_tree()
    for el in tree.xpath("//*[@id or @class]"):
        marker = f"{el.get('id', '')} {el.get('class', '')}".lower()
        if any(b in marker for b in BOILERPLATE) and el.getparent() is not None:
            el.drop_tree()
    lines: list[str] = []
    headings: list[str] = []
    seen: set[str] = set()
    for el in tree.iter(*BLOCK_TAGS):
        if any(child.tag in BLOCK_TAGS for child in el.iterdescendants()):
            continue  # the inner block will be emitted on its own
        line = " ".join(el.text_content().split())
        if not line or line in seen:
            continue
        seen.add(line)
        lines.append(line)
        if el.tag in ("h1", "h2", "h3"):
            headings.append(line)
    return "\n".join(lines), headings


def tidy(text: str) -> str:
    """Strip each line and collapse runs of blank lines."""
    out: list[str] = []
    for line in (ln.strip() for ln in text.splitlines()):
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip()


def extract(url: str, html: str) -> tuple[str, str, list[str], str]:
    """Return (title, main text, headings, schema type) from raw HTML."""
    text = (
        trafilatura.extract(
            html, url=url, include_comments=False, include_tables=True, favor_recall=True
        )
        or ""
    )
    xml = trafilatura.extract(
        html,
        url=url,
        output_format="xml",
        include_comments=False,
        favor_recall=True,
        include_formatting=True,
    )
    headings: list[str] = []
    if xml:
        root = etree.fromstring(xml.encode("utf-8"))
        headings = [" ".join("".join(h.itertext()).split()) for h in root.iter("head")]
    try:
        tree = lxml_html.fromstring(html)
    except (etree.ParserError, ValueError):
        return "", text, headings, ""
    if not headings:
        headings = [" ".join(h.text_content().split()) for h in tree.xpath("//h1|//h2|//h3")]
    title = " ".join((tree.findtext(".//title") or "").split())
    return title, text, [h for h in headings if h], _schema_type(tree)


def _render_headless(url: str, user_agent: str, timeout_s: float) -> str:
    from playwright.sync_api import sync_playwright  # optional extra: pip install -e ".[browser]"

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:  # Playwright's own Chromium not downloaded: use installed Google Chrome
            browser = p.chromium.launch(channel="chrome")
        try:
            page = browser.new_page(user_agent=user_agent)
            page.goto(url, wait_until="networkidle", timeout=int(timeout_s * 1000))
            return page.content()
        finally:
            browser.close()


class HttpFetcher:
    """Fetches competitor pages politely. Cached by (url, day)."""

    def __init__(
        self,
        settings: Settings,
        cache: DailyCache | None = None,
        client: httpx.Client | None = None,
        render: Callable[[str, str, float], str] | None = _render_headless,
    ) -> None:
        self.settings = settings
        self.cache = cache or DailyCache(settings.cache_dir)
        self.http = client or httpx.Client(
            follow_redirects=True,
            timeout=settings.fetch_timeout_s,
            headers={"User-Agent": settings.user_agent, "Accept-Language": "en"},
        )
        self.render = render if settings.headless_fallback else None
        self._robots: dict[str, RobotFileParser | None] = {}

    def allowed(self, url: str) -> bool:
        parts = urlparse(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser: RobotFileParser | None = RobotFileParser()
            try:
                resp = self.http.get(urljoin(origin, "/robots.txt"))
                if resp.status_code in (401, 403):
                    parser.disallow_all = True  # type: ignore[union-attr]
                elif resp.status_code >= 400:
                    parser = None  # no robots.txt: everything allowed
                else:
                    parser.parse(resp.text.splitlines())  # type: ignore[union-attr]
            except httpx.HTTPError:
                parser = None
            self._robots[origin] = parser
        parser = self._robots[origin]
        return parser is None or parser.can_fetch(self.settings.robots_token, url)

    def fetch(self, url: str) -> FetchedPage:
        cached = self.cache.get("fetch", url)
        if cached is not None:
            return FetchedPage.model_validate(cached)
        page = self._fetch(url)
        if page.status in ("ok", "robots_blocked", "not_html"):  # too_short may work on a retry
            self.cache.set("fetch", url, page.model_dump())
        return page

    def _fetch(self, url: str) -> FetchedPage:
        if not self.allowed(url):
            return FetchedPage(url=url, status="robots_blocked", reason="disallowed by robots.txt")
        try:
            resp = self.http.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            return self._fallback(url, f"http error: {exc}")
        if "html" not in resp.headers.get("content-type", "html"):
            return FetchedPage(
                url=url,
                status="not_html",
                reason=f"content-type {resp.headers.get('content-type')}",
            )
        page = self._build(url, resp.text, "httpx")
        if page.ok:
            return page
        return self._fallback(url, page.reason, page)

    def _build(self, url: str, html: str, method: Literal["httpx", "headless"]) -> FetchedPage:
        title, text, headings, schema = extract(url, html)
        text = tidy(text)
        min_words = self.settings.thresholds.min_clean_words
        if len(text.split()) < min_words:  # landing pages: article extraction keeps too little
            full, full_headings = visible_text(html)
            if len(full.split()) > len(text.split()):
                text, headings = full, full_headings or headings
        words = len(text.split())
        status: FetchStatus = (
            "ok" if words >= self.settings.thresholds.min_clean_words else "too_short"
        )
        reason = "" if status == "ok" else f"only {words} words of main text"
        return FetchedPage(
            url=url,
            status=status,
            title=title,
            text=text,
            headings=headings,
            word_count=words,
            schema_type=schema,
            method=method,
            reason=reason,
        )

    def _fallback(self, url: str, reason: str, first: FetchedPage | None = None) -> FetchedPage:
        if self.render is None:
            return first or FetchedPage(url=url, status="http_error", reason=reason)
        try:
            html = self.render(url, self.settings.user_agent, self.settings.fetch_timeout_s)
        except Exception as exc:  # headless is best effort; keep the first result
            note = f"{reason}; headless failed: {type(exc).__name__}"
            if first:
                return first.model_copy(update={"reason": note})
            return FetchedPage(url=url, status="http_error", reason=note)
        page = self._build(url, html, "headless")
        if page.ok or first is None or page.word_count > first.word_count:
            return page
        return first
