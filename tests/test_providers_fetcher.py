import httpx
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
