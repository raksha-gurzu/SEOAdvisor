"""Page fetcher: httpx + trafilatura, robots.txt check, length check, headless fallback."""

import json
from collections.abc import Callable
from typing import Literal, Protocol
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
from lxml import etree
from lxml import html as lxml_html
from protego import Protego
from pydantic import BaseModel

from seo_engine.config import Settings
from seo_engine.providers.base import (
    BlockedAddress,
    DailyCache,
    bounded_get,
    decode_body,
    public_client,
)

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


RENDER_MAX_BYTES = 10_000_000  # per resource the browser asks for


DEAD_PROXY = "http://127.0.0.1:9"  # discard port: nothing listens there


def render_headless(url: str, user_agent: str, timeout_s: float) -> str:
    """Render a JavaScript page in headless Chromium without giving the browser network access.

    Every request the page makes (the document, scripts, redirects, popups) is served by our own
    client (`public_client`): the same address guard, the same pinned connection, the same size
    limit. Playwright's own interception misses redirect hops, so the browser must never fetch
    by itself. Service workers and WebSockets are blocked; only GET and HEAD are served.
    """
    from playwright.sync_api import Route, sync_playwright  # optional: pip install -e ".[browser]"

    client = public_client(
        follow_redirects=True,
        timeout=timeout_s,
        headers={"User-Agent": user_agent, "Accept-Language": "en"},
    )

    def serve(route: Route) -> None:
        request = route.request
        if request.method not in ("GET", "HEAD"):
            route.abort()
            return
        try:
            got = bounded_get(client, request.url, RENDER_MAX_BYTES, timeout_s)
        except httpx.HTTPError:
            route.abort()
            return
        if got.too_large:
            route.abort()
            return
        headers = {"content-type": got.content_type} if got.content_type else {}
        route.fulfill(status=got.status, headers=headers, body=got.content)

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:  # Playwright's own Chromium not downloaded: use installed Google Chrome
            browser = p.chromium.launch(channel="chrome")
        try:
            context = browser.new_context(
                user_agent=user_agent,
                service_workers="block",
                # Routed requests never reach this proxy. Anything that skips routing (a
                # <link rel=preconnect> opens a bare TCP connection) goes to a dead port
                # instead of the host; "<-loopback>" removes Chromium's localhost exception.
                proxy={"server": DEAD_PROXY, "bypass": "<-loopback>"},
            )
            context.route("**/*", serve)  # the whole context: popups too
            # A handler that never calls connect_to_server() leaves the socket mocked: no
            # network. (Calling ws.close() in here deadlocks the sync API; seen offline.)
            context.route_web_socket("**/*", lambda ws: None)
            page = context.new_page()
            page.goto(url, wait_until="networkidle", timeout=int(timeout_s * 1000))
            return page.content()
        finally:
            browser.close()
            client.close()


DISALLOW_ALL = "User-agent: *\nDisallow: /"


def robots_body(status: int | None, text: str, too_large: bool) -> tuple[str, bool]:
    """(the rules we follow, robots.txt was unreachable) for a robots.txt answer. Shared by the
    page fetcher and the Site Snapshot probe, so both read sites under the same rules.

    - No answer, 5xx, 429 or over the size cap: disallow everything, and it is temporary
      (RFC 9309 §2.3.1.4).
    - 401/403: disallow everything. The RFC allows crawling here; we choose to be stricter.
    - Other 4xx (404, 410): no rules, allow everything.
    """
    if status is None or status >= 500 or status == 429 or too_large:
        return DISALLOW_ALL, True
    if status in (401, 403):
        return DISALLOW_ALL, False
    if status >= 400:
        return "", False
    return text, False


ROBOTS_MAX_BYTES = 512_000  # RFC 9309 §2.5: parse at least the first 500 KiB


class HttpFetcher:
    """Fetches competitor pages politely. Cached by (url, day)."""

    def __init__(
        self,
        settings: Settings,
        cache: DailyCache | None = None,
        client: httpx.Client | None = None,
        render: Callable[[str, str, float], str] | None = render_headless,
    ) -> None:
        self.settings = settings
        self.cache = cache or DailyCache(settings.cache_dir)
        self.http = client or public_client(
            follow_redirects=True,
            timeout=settings.fetch_timeout_s,
            headers={"User-Agent": settings.user_agent, "Accept-Language": "en"},
        )
        self.render = render if settings.headless_fallback else None
        self._robots: dict[str, Protego] = {}
        self._unreachable: set[str] = set()  # origins whose robots.txt could not be read

    @staticmethod
    def _origin(url: str) -> str:
        parts = urlparse(url)
        return f"{parts.scheme}://{parts.netloc}"

    def robots(self, url: str) -> Protego:
        """The site's robots.txt rules (RFC 9309), fetched once per origin per fetcher.

        - 5xx, 429 or no connection: robots.txt is unreachable, so everything is disallowed
          (RFC 9309 §2.3.1.4). This is temporary: pages blocked for this reason are not cached.
        - 401/403: disallow everything. The RFC allows crawling here; we choose to be stricter.
        - Other 4xx (404, 410): no rules, allow everything.
        """
        origin = self._origin(url)
        if origin not in self._robots:
            try:
                got = bounded_get(
                    self.http,
                    urljoin(origin, "/robots.txt"),
                    ROBOTS_MAX_BYTES,
                    self.settings.fetch_deadline_s,
                )
                text = "" if got.too_large else decode_body(got.content, got.charset)
                body, unreachable = robots_body(got.status, text, got.too_large)
            except httpx.HTTPError:
                body, unreachable = robots_body(None, "", False)
            if unreachable:
                self._unreachable.add(origin)
            self._robots[origin] = Protego.parse(body)
        return self._robots[origin]

    def robots_unreachable(self, url: str) -> bool:
        return self._origin(url) in self._unreachable

    def allowed(self, url: str) -> bool:
        return self.robots(url).can_fetch(url, self.settings.robots_token)

    def fetch(self, url: str) -> FetchedPage:
        cached = self.cache.get("fetch", url)
        if cached is not None:
            page = FetchedPage.model_validate(cached)
            # A too_short cached by a fetcher without headless deserves a headless retry here.
            if page.status != "too_short" or self.render is None:
                return page
        page = self._fetch(url)
        # too_short may work on a retry with the headless browser; without one it cannot.
        final = ("ok", "robots_blocked", "not_html") + (
            ("too_short",) if self.render is None else ()
        )
        # A block caused by an unreachable robots.txt is temporary: never keep it for the day.
        temporary = page.status == "robots_blocked" and self.robots_unreachable(url)
        if page.status in final and not temporary:
            self.cache.set("fetch", url, page.model_dump())
        return page

    def _fetch(self, url: str) -> FetchedPage:
        if not self.allowed(url):
            reason = (
                "robots.txt could not be read"
                if self.robots_unreachable(url)
                else "disallowed by robots.txt"
            )
            return FetchedPage(url=url, status="robots_blocked", reason=reason)
        try:
            got = bounded_get(
                self.http, url, self.settings.max_page_bytes, self.settings.fetch_deadline_s
            )
        except BlockedAddress as exc:  # never retry a blocked address in the browser
            return FetchedPage(url=url, status="http_error", reason=str(exc))
        except httpx.HTTPError as exc:
            if "not a public address" in str(exc):  # blocked when connecting (pinned backend)
                return FetchedPage(url=url, status="http_error", reason=str(exc))
            return self._fallback(url, f"http error: {exc}")
        if got.status >= 400:
            return self._fallback(url, f"http error: HTTP {got.status}")
        if got.too_large:
            return FetchedPage(url=url, status="not_html", reason="page larger than the size cap")
        if "html" not in (got.content_type or "html"):
            return FetchedPage(
                url=url, status="not_html", reason=f"content-type {got.content_type}"
            )
        html = decode_body(got.content, got.charset)
        page = self._build(url, html, "httpx")
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
