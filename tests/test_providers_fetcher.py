import httpx
import pytest
import respx

from conftest import load_text
from seo_engine.providers.fetcher import HttpFetcher

HTML = {"content-type": "text/html"}


@respx.mock
def test_fetch_cleans_main_text_headings_and_schema(settings, cache) -> None:
    respx.get("https://moxo.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://moxo.com/blog/client-portal").mock(
        return_value=httpx.Response(200, text=load_text("html/article.html"), headers=HTML)
    )
    page = HttpFetcher(settings, cache, render=None).fetch("https://moxo.com/blog/client-portal")
    assert page.ok and page.method == "httpx"
    assert page.word_count >= 150
    assert "Copyright" not in page.text
    assert "Why agencies use one" in page.headings
    assert page.schema_type == "Article"
    assert page.title.startswith("What Is a Client Portal")


@respx.mock
def test_robots_disallow_is_respected(settings, cache) -> None:
    respx.get("https://blocked.com/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /")
    )
    page_route = respx.get("https://blocked.com/page").mock(return_value=httpx.Response(200))
    page = HttpFetcher(settings, cache, render=None).fetch("https://blocked.com/page")
    assert page.status == "robots_blocked"
    assert page_route.call_count == 0


@respx.mock
def test_short_page_falls_back_to_headless(settings, cache) -> None:
    respx.get("https://app.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://app.com/").mock(
        return_value=httpx.Response(200, text=load_text("html/js_shell.html"), headers=HTML)
    )
    rendered = load_text("html/article.html")
    fetcher = HttpFetcher(settings, cache, render=lambda url, ua, t: rendered)
    page = fetcher.fetch("https://app.com/")
    assert page.ok and page.method == "headless"


@respx.mock
def test_short_page_without_browser_reports_too_short(settings, cache) -> None:
    respx.get("https://app.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://app.com/").mock(
        return_value=httpx.Response(200, text=load_text("html/js_shell.html"), headers=HTML)
    )
    page = HttpFetcher(settings, cache, render=None).fetch("https://app.com/")
    assert page.status == "too_short" and "words" in page.reason


def test_visible_text_keeps_landing_page_copy_and_drops_chrome() -> None:
    from seo_engine.providers.fetcher import visible_text

    html = """<html><body>
      <nav><a>Home</a><a>Pricing</a></nav>
      <div class="cookie-banner"><p>We use cookies</p></div>
      <section><h1>One workspace for client projects</h1>
        <p>Share files and approvals with every client.</p>
        <ul><li>Tasks both sides can see</li><li>Tasks both sides can see</li></ul></section>
      <footer><p>© 2026 Emitii</p></footer><script>var x = 1;</script>
    </body></html>"""
    text, headings = visible_text(html)
    assert text.splitlines() == [
        "One workspace for client projects",
        "Share files and approvals with every client.",
        "Tasks both sides can see",
    ]
    assert headings == ["One workspace for client projects"]


# Live gurzu.com robots.txt (28 Sep 2026), trimmed. The stdlib parser allowed /admin/ here
# (first match "Allow: /") and ignored wildcards; RFC 9309 uses the longest match.
GURZU_ROBOTS = """User-agent: *
Allow: /
Disallow: /admin/
Disallow: /*?*
Disallow: /*.pdf$
Sitemap: https://gurzu.com/sitemap.xml
"""


@respx.mock
def test_robots_follow_rfc_9309_longest_match_and_wildcards(settings, cache) -> None:
    respx.get("https://gurzu.com/robots.txt").mock(
        return_value=httpx.Response(200, text=GURZU_ROBOTS)
    )
    fetcher = HttpFetcher(settings, cache, render=None)
    assert not fetcher.allowed("https://gurzu.com/admin/users")
    assert not fetcher.allowed("https://gurzu.com/blog?page=2")
    assert not fetcher.allowed("https://gurzu.com/deck.pdf")
    assert fetcher.allowed("https://gurzu.com/deck.pdf.html")
    assert fetcher.allowed("https://gurzu.com/services/")
    assert list(fetcher.robots("https://gurzu.com/").sitemaps) == ["https://gurzu.com/sitemap.xml"]


@respx.mock
def test_robots_group_for_our_user_agent_wins(settings, cache) -> None:
    respx.get("https://a.com/robots.txt").mock(
        return_value=httpx.Response(
            200,
            text="User-agent: GurzuSEOEngine\nDisallow: /private\n\nUser-agent: *\nDisallow: /\n",
        )
    )
    fetcher = HttpFetcher(settings, cache, render=None)
    assert fetcher.allowed("https://a.com/public")
    assert not fetcher.allowed("https://a.com/private/x")


@pytest.mark.parametrize(
    ("status", "allowed"), [(404, True), (410, True), (403, False), (503, False)]
)
@respx.mock
def test_robots_status_codes(settings, cache, status: int, allowed: bool) -> None:
    respx.get("https://s.com/robots.txt").mock(return_value=httpx.Response(status))
    assert HttpFetcher(settings, cache, render=None).allowed("https://s.com/page") is allowed


@respx.mock
def test_unreachable_robots_means_disallow(settings, cache) -> None:
    respx.get("https://down.com/robots.txt").mock(side_effect=httpx.ConnectError("refused"))
    page_route = respx.get("https://down.com/page").mock(return_value=httpx.Response(200))
    page = HttpFetcher(settings, cache, render=None).fetch("https://down.com/page")
    assert page.status == "robots_blocked"
    assert page_route.call_count == 0


@respx.mock
def test_robots_fetched_once_per_origin(settings, cache) -> None:
    route = respx.get("https://once.com/robots.txt").mock(return_value=httpx.Response(404))
    fetcher = HttpFetcher(settings, cache, render=None)
    for path in ("/a", "/b", "/c"):
        fetcher.allowed(f"https://once.com{path}")
    assert route.call_count == 1


SHORT_HTML = (
    "<html><head><title>Pricing</title></head><body><h1>Pricing</h1><p>Plans.</p></body></html>"
)


@respx.mock
def test_too_short_is_cached_when_no_headless_retry_is_possible(settings, cache) -> None:
    respx.get("https://s.com/robots.txt").mock(return_value=httpx.Response(404))
    route = respx.get("https://s.com/pricing").mock(
        return_value=httpx.Response(200, text=SHORT_HTML, headers=HTML)
    )
    fetcher = HttpFetcher(settings, cache, render=None)
    assert fetcher.fetch("https://s.com/pricing").status == "too_short"
    assert fetcher.fetch("https://s.com/pricing").title == "Pricing"
    assert route.call_count == 1


@respx.mock
def test_headless_fetcher_retries_a_too_short_cached_without_headless(settings, cache) -> None:
    respx.get("https://s.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://s.com/app").mock(
        return_value=httpx.Response(200, text=SHORT_HTML, headers=HTML)
    )
    HttpFetcher(settings, cache, render=None).fetch("https://s.com/app")  # caches too_short
    rendered = load_text("html/article.html")
    page = HttpFetcher(settings, cache, render=lambda *_: rendered).fetch("https://s.com/app")
    assert page.ok and page.method == "headless"


@respx.mock
def test_fetcher_never_follows_a_redirect_to_a_private_address(
    settings, cache, monkeypatch
) -> None:
    monkeypatch.setattr(
        "seo_engine.providers.base.address_check", lambda url: "10.0.0.5" not in url
    )
    respx.get("https://s.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://s.com/page").mock(
        return_value=httpx.Response(302, headers={"Location": "http://10.0.0.5/admin"})
    )
    private = respx.get("http://10.0.0.5/admin").mock(
        return_value=httpx.Response(200, text="secret")
    )
    rendered: list[str] = []
    fetcher = HttpFetcher(settings, cache, render=lambda u, a, t: rendered.append(u) or "")
    page = fetcher.fetch("https://s.com/page")
    assert page.status == "http_error" and "not a public address" in page.reason
    assert private.call_count == 0
    assert rendered == []  # a blocked address is never retried in the browser


@respx.mock
def test_a_block_from_the_pinned_backend_is_not_retried_in_the_browser(settings, cache) -> None:
    respx.get("https://s.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://s.com/page").mock(
        side_effect=httpx.ConnectError("blocked: s.com is not a public address")
    )
    rendered: list[str] = []
    fetcher = HttpFetcher(settings, cache, render=lambda u, a, t: rendered.append(u) or "")
    page = fetcher.fetch("https://s.com/page")
    assert page.status == "http_error" and rendered == []


@respx.mock
def test_an_unknown_charset_does_not_crash_the_fetch(settings, cache) -> None:
    respx.get("https://s.com/robots.txt").mock(return_value=httpx.Response(404))
    body = "<html><head><title>Caf\u00e9</title></head><body><main>"
    body += "<p>" + "Real words about the caf\u00e9 menu. " * 40 + "</p></main></body></html>"
    respx.get("https://s.com/page").mock(
        return_value=httpx.Response(
            200,
            content=body.encode(),
            headers={"content-type": "text/html; charset=no-such-charset"},
        )
    )
    page = HttpFetcher(settings, cache, render=None).fetch("https://s.com/page")
    assert page.ok and "café" in page.text


@respx.mock
def test_pages_over_the_size_cap_are_skipped(cache, tmp_path) -> None:
    from seo_engine.config import Settings

    small = Settings(cache_dir=tmp_path / "c", max_page_bytes=1000)
    respx.get("https://s.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://s.com/huge").mock(
        return_value=httpx.Response(200, text="<p>" + "x" * 5000 + "</p>", headers=HTML)
    )
    page = HttpFetcher(small, cache, render=None).fetch("https://s.com/huge")
    assert page.status == "not_html" and "size cap" in page.reason


@pytest.mark.parametrize("status", [429, 503])
@respx.mock
def test_blocks_from_an_unreachable_robots_txt_are_not_kept_for_the_day(
    settings, cache, status: int
) -> None:
    robots = respx.get("https://t.com/robots.txt").mock(
        side_effect=[httpx.Response(status), httpx.Response(404)]
    )
    respx.get("https://t.com/page").mock(
        return_value=httpx.Response(200, text=load_text("html/article.html"), headers=HTML)
    )
    first = HttpFetcher(settings, cache, render=None).fetch("https://t.com/page")
    assert first.status == "robots_blocked" and first.reason == "robots.txt could not be read"
    later = HttpFetcher(settings, cache, render=None).fetch("https://t.com/page")  # same day
    assert later.ok and robots.call_count == 2


@respx.mock
def test_a_real_disallow_is_kept_for_the_day(settings, cache) -> None:
    respx.get("https://d.com/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /")
    )
    first = HttpFetcher(settings, cache, render=None).fetch("https://d.com/page")
    assert first.reason == "disallowed by robots.txt"
    respx.get("https://d.com/robots.txt").mock(return_value=httpx.Response(404))
    assert (
        HttpFetcher(settings, cache, render=None).fetch("https://d.com/page").status
        == "robots_blocked"
    )


def test_the_browser_cannot_reach_a_blocked_address(monkeypatch) -> None:
    """Offline: a page on an allowed local server tries every way to reach a blocked one
    (links, redirects, fetch, beacon, WebSocket, popup, preconnect). The blocked server
    counts raw TCP connections, so even a connection that sends nothing is caught."""
    import socket
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    pytest.importorskip("playwright")
    from seo_engine.providers import base
    from seo_engine.providers.fetcher import render_headless

    hits: list[str] = []
    blocked = socket.socket()
    blocked.bind(("127.0.0.1", 0))
    blocked.listen(50)

    def count() -> None:
        while True:
            try:
                conn, _ = blocked.accept()
            except OSError:
                return
            hits.append("connection")
            conn.close()

    threading.Thread(target=count, daemon=True).start()
    b = f"127.0.0.1:{blocked.getsockname()[1]}"
    page = f"""<html><head><link rel="preconnect" href="http://{b}">
    <link rel="stylesheet" href="http://{b}/css"></head><body><main><p>hello</p>
    <img src="http://{b}/img"><iframe src="/redirect"></iframe><script src="/app.js"></script>
    <script>fetch("http://{b}/f").catch(() => {{}}); fetch("/redirect").catch(() => {{}});
    navigator.sendBeacon("http://{b}/beacon", "x"); new WebSocket("ws://{b}/ws");
    window.open("http://{b}/popup");</script></main></body></html>"""

    class Allowed(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", f"http://{b}/via-redirect")
                self.end_headers()
                return
            js = self.path == "/app.js"
            body = (
                b'document.body.insertAdjacentHTML("beforeend", "<p>from-js</p>")'
                if js
                else page.encode()
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript" if js else "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args) -> None:
            pass

    allowed = ThreadingHTTPServer(("127.0.0.1", 0), Allowed)
    threading.Thread(target=allowed.serve_forever, daemon=True).start()
    a_port = allowed.server_address[1]
    monkeypatch.setattr(base, "address_check", lambda url: f":{a_port}" in url)
    monkeypatch.setattr(
        base,
        "public_addresses",
        lambda host, port=None: ["127.0.0.1"] if port == a_port else [],
    )
    try:
        html = render_headless(f"http://127.0.0.1:{a_port}/", "test-agent", 10)
    except Exception as exc:  # no Chromium installed on this machine
        if "Executable doesn't exist" in str(exc) or "is not found" in str(exc):
            pytest.skip(f"no browser: {exc}")
        raise
    finally:
        allowed.shutdown()
    blocked.close()
    assert "hello" in html and "from-js" in html  # the page and its script still work
    assert hits == []
