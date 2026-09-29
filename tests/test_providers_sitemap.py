import gzip
import re
from collections import Counter
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from conftest import FIXTURES
from seo_engine.config import GapSettings, Settings
from seo_engine.providers.base import DailyCache
from seo_engine.providers.fetcher import HttpFetcher
from seo_engine.providers.sitemap import (
    SitemapEntry,
    SiteReader,
    child_order,
    other_languages,
    page_key,
    page_links,
    parse_sitemap,
    select_pages,
    site_origin,
    skip_reason,
)

HTML = {"content-type": "text/html"}
XML = {"content-type": "application/xml"}
GURZU_XML = (FIXTURES / "sitemap/gurzu_sitemap.xml").read_bytes()  # live, 28 Sep 2026, trimmed
EMITII_XML = (FIXTURES / "sitemap/emitii_sitemap.xml").read_bytes()  # live, 28 Sep 2026
YOAST_INDEX = (FIXTURES / "sitemap/yoast_index.xml").read_bytes()  # live, 28 Sep 2026
GURZU_ROBOTS = (FIXTURES / "sitemap/gurzu_robots.txt").read_text()  # live, 28 Sep 2026
EMITII_ROBOTS = (
    "User-Agent: *\nAllow: /\nDisallow: /home\nDisallow: /signup\nDisallow: /api/\n"
    "Sitemap: https://emitii.com/sitemap.xml\n"
)


def page_html(title: str, words: int = 20) -> str:
    return (
        f"<html><head><title>{title}</title></head><body><h1>{title}</h1>"
        f"<p>{' '.join(['word'] * words)}</p></body></html>"
    )


def urlset(*paths: str, host: str = "https://s.com") -> bytes:
    locs = "".join(f"<url><loc>{host}{p}</loc></url>" for p in paths)
    return f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locs}</urlset>'.encode()


def reader(tmp_path: Path, render=None, **overrides) -> SiteReader:
    gap = GapSettings(base=Settings(cache_dir=tmp_path / "cache"), **overrides)
    cache = DailyCache(gap.base.cache_dir, today=lambda: date(2026, 9, 28))
    return SiteReader(gap, HttpFetcher(gap.base, cache, render=None), cache, render=render)


def serve_pages(host: str) -> respx.Route:
    """Every other page on `host` answers with a small page titled by its path."""
    return respx.get(url__regex=rf"^{re.escape(host)}/.*").mock(
        side_effect=lambda req: httpx.Response(200, text=page_html(req.url.path), headers=HTML)
    )


# --- pure functions ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("gurzu.com", ("gurzu.com", "https://gurzu.com")),
        ("  https://gurzu.com/services/ ", ("gurzu.com", "https://gurzu.com")),
        ("http://www.Gurzu.com/x?y=1", ("gurzu.com", "https://www.gurzu.com")),
        ("emitii.com.", ("emitii.com", "https://emitii.com")),
    ],
)
def test_site_origin(raw: str, expected: tuple[str, str]) -> None:
    assert site_origin(raw) == expected


@pytest.mark.parametrize("raw", ["", "localhost", "https://", "not a site"])
def test_site_origin_rejects_non_sites(raw: str) -> None:
    with pytest.raises(ValueError):
        site_origin(raw)


def test_parse_real_urlset() -> None:
    parsed = parse_sitemap(GURZU_XML)
    assert parsed.kind == "urlset" and len(parsed.entries) == 112
    assert parsed.entries[0].url == "https://gurzu.com/articles/bug-reporting-template/"
    assert parsed.entries[0].lastmod.startswith("2020-06-08")


def test_parse_real_index_and_gzip() -> None:
    index = parse_sitemap(YOAST_INDEX)
    assert index.kind == "index" and len(index.entries) == 21
    assert parse_sitemap(gzip.compress(EMITII_XML)).entries == parse_sitemap(EMITII_XML).entries


@pytest.mark.parametrize(
    "content",
    [b"", b"not xml", b"<html><body>404</body></html>", b"\x1f\x8bbroken gzip", b"<rss/>"],
)
def test_parse_invalid_content(content: bytes) -> None:
    assert parse_sitemap(content).kind == "invalid"


def test_parse_does_not_resolve_external_entities() -> None:
    xxe = (
        b'<?xml version="1.0"?><!DOCTYPE u [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
        b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        b"<url><loc>https://s.com/&x;</loc></url></urlset>"
    )
    for entry in parse_sitemap(xxe).entries:
        assert "root:" not in entry.url


def test_child_order_real_index() -> None:
    urls = [e.url for e in parse_sitemap(YOAST_INDEX).entries]
    names = [u.rsplit("/", 1)[-1] for u in child_order(urls)]
    assert names[:3] == ["page-sitemap.xml", "product-sitemap.xml", "yoast_feature-sitemap.xml"]
    assert names[-2:] == ["wpkb-article-sitemap.xml", "yoast_developer_blog-sitemap.xml"]
    assert not {"post_tag-sitemap.xml", "video-sitemap.xml", "yoast_videos-sitemap.xml"} & set(
        names
    )


def test_child_skip_matches_whole_words_only() -> None:
    urls = [
        "https://a.com/information-sitemap.xml",
        "https://a.com/user-guide-sitemap.xml",
        "https://a.com/wp-sitemap-users-1.xml",
        "https://a.com/wp-sitemap-taxonomies-post_format-1.xml",
    ]
    assert child_order(urls) == urls[:2]


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("https://gurzu.com/https:/calendly.com/gurzu/meeting", "broken link"),  # live sitemap
        ("https://gurzu.com/blog?page=2", "query string"),
        ("https://gurzu.com/deck.pdf", "not a web page"),
        ("https://gurzu.com/google385b42146547b16e.html", "not a web page"),  # live sitemap
        ("https://gurzu.com/yandex_2f1c9a.html", "not a web page"),
        ("https://gurzu.com/blog/page/3/", "pagination"),
        ("https://gurzu.com/tag/rails/", "skipped section 'tag'"),
        ("https://gurzu.com/blog/", "list page"),  # live: gave "tech blog" (F25)
        ("https://gurzu.com/articles", "list page"),
        ("https://gurzu.com/Success-Stories/", "list page"),
        ("https://gurzu.com/blog/category/rails/", "skipped section 'category'"),
        ("https://gurzu.com/privacy-policy", "skipped section 'privacy-policy'"),
        (
            "https://gurzu.com/design-ebook-downloaded-thank-you/",
            "skipped section 'design-ebook-downloaded-thank-you'",
        ),
        ("https://emitii.com/login", "other site"),
        ("https://blog.gurzu.com/post", "other site"),
        ("ftp://gurzu.com/file", "other site"),
    ],
)
def test_skip_reason(url: str, reason: str) -> None:
    assert skip_reason(url, "gurzu.com", GapSettings()) == reason


@pytest.mark.parametrize(
    "url",
    [
        "https://gurzu.com/services/web-development/",
        "https://www.gurzu.com/pricing",
        "https://gurzu.com/accounting-software",  # "account" is a whole-segment rule only
        "https://gurzu.com/cartography",
        "https://gurzu.com/blog/shift-left-testing/",  # a post under a list page is kept
        "https://gurzu.com/success-stories/hamrotrips/",
        "https://gurzu.com/services/",  # a service hub is what the site sells: kept
        "https://gurzu.com/business-solutions/",
        "https://gurzu.com/blogging-platform",  # whole-segment match only
    ],
)
def test_skip_reason_keeps_real_pages(url: str) -> None:
    assert skip_reason(url, "gurzu.com", GapSettings()) is None


def test_page_key_treats_url_variants_as_one_page() -> None:
    same = [
        "https://gurzu.com/services",
        "https://gurzu.com/services/",
        "https://www.Gurzu.com/services/#top",
        "http://gurzu.com/services",
    ]
    assert {page_key(u) for u in same} == {"gurzu.com/services"}
    assert page_key("https://gurzu.com") == page_key("https://www.gurzu.com/") == "gurzu.com/"
    assert page_key("https://blog.gurzu.com/") != page_key("https://gurzu.com/")


def test_other_languages_only_on_multilingual_sites() -> None:
    one = ["https://a.com/ai/agents", "https://a.com/pricing"]
    assert other_languages(one, "en") == set()
    many = ["https://a.com/de/preise", "https://a.com/fr/prix", "https://a.com/en/pricing"]
    assert other_languages(many + ["https://a.com/pt-br/precos"], "en") == {"de", "fr", "pt-br"}


def test_select_pages_spreads_across_sections() -> None:
    s = GapSettings()
    entries = [
        e for e in parse_sitemap(GURZU_XML).entries if skip_reason(e.url, "gurzu.com", s) is None
    ]
    picked = select_pages(entries, "https://gurzu.com/", 30)
    sections = Counter(u.split("/")[3] for u in picked[1:])
    assert picked[0] == "https://gurzu.com/"
    listed = {e.url for e in entries}
    assert set(picked[1:]) <= listed  # the sitemap's own URLs: no redirect per page
    assert len(picked) == len(set(picked)) == 30
    assert sections["services"] >= 4 and sections["solutions"] >= 4
    assert sections["blog"] <= 6  # 40 blog posts in the fixture cannot crowd the rest out
    assert not any("calendly" in u for u in picked)


def test_select_pages_small_site_and_no_home() -> None:
    entries = [SitemapEntry(url=f"https://s.com{p}") for p in ("/", "/a", "/a/", "/b#x")]
    assert select_pages(entries, "https://s.com/", 30) == [
        "https://s.com/",
        "https://s.com/a",
        "https://s.com/b",
    ]
    assert select_pages(entries, None, 30) == ["https://s.com/a", "https://s.com/b"]


def test_select_pages_www_and_bare_host_are_one_page() -> None:
    # Live moxo.com: the origin was https://moxo.com, the sitemap lists https://www.moxo.com/.
    entries = [SitemapEntry(url=u) for u in ("https://www.moxo.com/", "https://www.moxo.com/a")]
    assert select_pages(entries, "https://www.moxo.com/", 30) == [
        "https://www.moxo.com/",
        "https://www.moxo.com/a",
    ]
    entries.append(SitemapEntry(url="https://moxo.com/a/"))
    assert select_pages(entries, "https://moxo.com/", 30) == [
        "https://moxo.com/",
        "https://www.moxo.com/a",
    ]


def test_select_pages_prefers_short_paths_then_newest() -> None:
    entries = [
        SitemapEntry(url="https://s.com/docs/a/deep/page", lastmod="2026-09-01"),
        SitemapEntry(url="https://s.com/docs/old", lastmod="2024-01-01"),
        SitemapEntry(url="https://s.com/docs/new", lastmod="2026-01-01"),
    ]
    assert select_pages(entries, None, 4) == [
        "https://s.com/docs/new",
        "https://s.com/docs/old",
        "https://s.com/docs/a/deep/page",
    ]


def test_page_links() -> None:
    html = (
        '<a href="/pricing">p</a><a href="https://s.com/pricing#faq">p</a>'
        '<a href="features">f</a><a href="mailto:x@s.com">m</a><a href="  ">e</a>'
    )
    assert page_links(html, "https://s.com/") == [
        "https://s.com/pricing",
        "https://s.com/features",
    ]
    assert page_links("", "https://s.com/") == []


# --- full reads (mocked HTTP, recorded sitemaps) ----------------------------------------


@respx.mock
def test_read_gurzu_live_sitemap_and_robots(tmp_path: Path) -> None:
    respx.get("https://gurzu.com/robots.txt").mock(
        return_value=httpx.Response(200, text=GURZU_ROBOTS)
    )
    respx.get("https://gurzu.com/sitemap.xml").mock(
        return_value=httpx.Response(200, content=GURZU_XML, headers=XML)
    )
    index_route = respx.get("https://gurzu.com/sitemap_index.xml").mock(
        return_value=httpx.Response(404)
    )
    serve_pages("https://gurzu.com")
    sample = reader(tmp_path).read("https://gurzu.com/services/")
    assert sample.source == "sitemap"
    assert sample.sitemaps == ["https://gurzu.com/sitemap.xml"]
    assert sample.sitemap_urls == 111  # distinct pages in the file (112 <loc>, one twice)
    assert not sample.sitemap_capped
    assert index_route.call_count == 0  # robots.txt names the sitemap; no guessing
    assert len(sample.pages) == 30 and sample.pages[0].url == "https://gurzu.com/"
    assert sample.pages[1].title and sample.pages[1].headings
    # The trimmed live fixture keeps 2 of the 3 broken calendly entries, 2 Google verification
    # files, 2 thank-you pages, and /admin/ and /services/rails-maintenance/, which the site's
    # own robots.txt disallows. The 5 list pages are /articles/, /success-stories/,
    # /community/, /podcast/ and /resources/ (their posts are kept).
    assert sample.notes[0] == (
        "sitemap URLs skipped: 5 list page, 2 broken link, 2 blocked by robots.txt, "
        "2 not a web page, "
        "1 skipped section 'design-ebook-downloaded-thank-you', 1 skipped section 'thankyou'"
    )


@respx.mock
def test_read_emitii_adds_homepage_links_to_a_tiny_sitemap(tmp_path: Path) -> None:
    respx.get("https://emitii.com/robots.txt").mock(
        return_value=httpx.Response(200, text=EMITII_ROBOTS)
    )
    respx.get("https://emitii.com/sitemap.xml").mock(
        return_value=httpx.Response(200, content=EMITII_XML, headers=XML)
    )
    home = (
        "<html><head><title>Emitii</title></head><body><h1>Client workspace</h1>"
        '<a href="/features">F</a><a href="/pricing">P</a>'
        '<a href="/signup">S</a><a href="/home">H</a>'
        '<a href="https://twitter.com/emitii">T</a><a href="/terms">T</a></body></html>'
    )
    respx.get("https://emitii.com/").mock(return_value=httpx.Response(200, text=home, headers=HTML))
    signup = respx.get("https://emitii.com/signup").mock(return_value=httpx.Response(200))
    serve_pages("https://emitii.com")
    sample = reader(tmp_path).read("emitii.com")
    urls = [p.url for p in sample.pages]
    assert sample.source == "sitemap+links"
    assert urls[0] == "https://emitii.com/"
    assert {"https://emitii.com/contact", "https://emitii.com/features"} <= set(urls)
    assert "https://emitii.com/pricing" in urls
    assert not {"https://emitii.com/login", "https://emitii.com/signup"} & set(urls)
    assert not any("home" in u or "terms" in u or "twitter" in u for u in urls)
    assert signup.call_count == 0  # robots.txt disallows it
    assert sample.urls_found == 4  # contact + features + pricing + the listed homepage


@respx.mock
def test_read_index_reads_useful_children_first_within_the_file_limit(tmp_path: Path) -> None:
    robots = "User-agent: *\nAllow: /\nSitemap: https://yoast.com/sitemap_index.xml\n"
    respx.get("https://yoast.com/robots.txt").mock(return_value=httpx.Response(200, text=robots))
    respx.get("https://yoast.com/sitemap_index.xml").mock(
        return_value=httpx.Response(200, content=YOAST_INDEX, headers=XML)
    )
    page = respx.get("https://yoast.com/page-sitemap.xml").mock(
        return_value=httpx.Response(200, content=urlset("/about", host="https://yoast.com"))
    )
    product = respx.get("https://yoast.com/product-sitemap.xml").mock(
        return_value=httpx.Response(200, content=urlset("/plugins/seo", host="https://yoast.com"))
    )
    tag = respx.get("https://yoast.com/post_tag-sitemap.xml").mock(return_value=httpx.Response(200))
    post = respx.get("https://yoast.com/post-sitemap.xml").mock(return_value=httpx.Response(200))
    serve_pages("https://yoast.com")
    sample = reader(tmp_path, max_sitemap_files=3).read("yoast.com")
    assert sample.sitemaps == [
        "https://yoast.com/sitemap_index.xml",
        "https://yoast.com/page-sitemap.xml",
        "https://yoast.com/product-sitemap.xml",
    ]
    assert page.call_count == product.call_count == 1
    assert tag.call_count == post.call_count == 0
    assert {"https://yoast.com/about", "https://yoast.com/plugins/seo"} <= {
        p.url for p in sample.pages
    }


@respx.mock
def test_read_gzipped_sitemap_from_robots(tmp_path: Path) -> None:
    robots = "User-agent: *\nSitemap: https://s.com/sitemap.xml.gz\n"
    respx.get("https://s.com/robots.txt").mock(return_value=httpx.Response(200, text=robots))
    respx.get("https://s.com/sitemap.xml.gz").mock(
        return_value=httpx.Response(200, content=gzip.compress(urlset("/pricing", "/features")))
    )
    serve_pages("https://s.com")
    sample = reader(tmp_path).read("s.com")
    assert sample.sitemaps == ["https://s.com/sitemap.xml.gz"]
    assert [p.url for p in sample.pages] == [
        "https://s.com/",
        "https://s.com/pricing",
        "https://s.com/features",
    ]


@respx.mock
def test_read_without_sitemap_uses_homepage_links(tmp_path: Path) -> None:
    respx.get("https://s.com/robots.txt").mock(return_value=httpx.Response(404))
    for path in ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml"):
        respx.get(f"https://s.com{path}").mock(return_value=httpx.Response(404))
    home = page_html("Home") + '<a href="/services">S</a><a href="/about">A</a>'
    respx.get("https://s.com/").mock(return_value=httpx.Response(200, text=home, headers=HTML))
    serve_pages("https://s.com")
    sample = reader(tmp_path).read("s.com")
    assert sample.source == "links" and sample.sitemaps == []
    assert {p.url for p in sample.pages} == {
        "https://s.com/",
        "https://s.com/services",
        "https://s.com/about",
    }


@respx.mock
def test_sitemap_that_is_really_an_html_page_is_ignored(tmp_path: Path) -> None:
    respx.get("https://s.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://s.com/sitemap.xml").mock(
        return_value=httpx.Response(200, text=page_html("Not found"), headers=HTML)
    )
    for path in ("/sitemap_index.xml", "/wp-sitemap.xml"):
        respx.get(f"https://s.com{path}").mock(return_value=httpx.Response(404))
    serve_pages("https://s.com")
    sample = reader(tmp_path).read("s.com")
    assert sample.sitemaps == [] and sample.source == "none"
    assert [p.url for p in sample.pages] == ["https://s.com/"]


@respx.mock
def test_oversized_sitemap_is_skipped(tmp_path: Path) -> None:
    respx.get("https://s.com/robots.txt").mock(
        return_value=httpx.Response(200, text="Sitemap: https://s.com/big.xml\n")
    )
    respx.get("https://s.com/big.xml").mock(
        return_value=httpx.Response(200, content=urlset("/a", "/b"))
    )
    serve_pages("https://s.com")
    sample = reader(tmp_path, max_sitemap_bytes=50).read("s.com")
    assert sample.sitemaps == []


@respx.mock
def test_unreachable_robots_reads_nothing(tmp_path: Path) -> None:
    respx.get("https://down.com/robots.txt").mock(return_value=httpx.Response(503))
    pages = serve_pages("https://down.com")
    sample = reader(tmp_path).read("down.com")
    assert sample.pages == [] and sample.source == "none"
    assert any("no readable pages" in n for n in sample.notes)
    assert pages.call_count == 0


@respx.mock
def test_pages_without_title_or_headings_are_dropped(tmp_path: Path) -> None:
    respx.get("https://s.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://s.com/sitemap.xml").mock(
        return_value=httpx.Response(200, content=urlset("/blank"))
    )
    respx.get("https://s.com/blank").mock(
        return_value=httpx.Response(200, text="<html><body></body></html>", headers=HTML)
    )
    respx.get("https://s.com/").mock(
        return_value=httpx.Response(200, text=page_html("Home"), headers=HTML)
    )
    sample = reader(tmp_path).read("s.com")
    assert [p.url for p in sample.pages] == ["https://s.com/"]
    assert "1 page(s) had no title or headings" in sample.notes


@respx.mock
def test_second_read_same_day_makes_no_page_or_sitemap_requests(tmp_path: Path) -> None:
    respx.get("https://s.com/robots.txt").mock(return_value=httpx.Response(404))
    sitemap = respx.get("https://s.com/sitemap.xml").mock(
        return_value=httpx.Response(200, content=urlset("/a", "/b"))
    )
    pages = serve_pages("https://s.com")
    r = reader(tmp_path)
    first = r.read("s.com")
    calls = (sitemap.call_count, pages.call_count)
    assert r.read("s.com") == first
    assert (sitemap.call_count, pages.call_count) == calls


def test_snippet_is_cut_to_the_setting(tmp_path: Path) -> None:
    with respx.mock:
        respx.get("https://s.com/robots.txt").mock(return_value=httpx.Response(404))
        respx.get("https://s.com/sitemap.xml").mock(return_value=httpx.Response(404))
        respx.get("https://s.com/sitemap_index.xml").mock(return_value=httpx.Response(404))
        respx.get("https://s.com/wp-sitemap.xml").mock(return_value=httpx.Response(404))
        respx.get("https://s.com/").mock(
            return_value=httpx.Response(200, text=page_html("Home", words=400), headers=HTML)
        )
        sample = reader(tmp_path, snippet_words=10).read("s.com")
    assert len(sample.pages[0].snippet.split()) == 10


@respx.mock
def test_common_paths_are_tried_in_order_when_robots_lists_none(tmp_path: Path) -> None:
    respx.get("https://s.com/robots.txt").mock(return_value=httpx.Response(200, text="Allow: /"))
    first = respx.get("https://s.com/sitemap.xml").mock(return_value=httpx.Response(404))
    second = respx.get("https://s.com/sitemap_index.xml").mock(
        return_value=httpx.Response(200, content=urlset("/pricing"))
    )
    third = respx.get("https://s.com/wp-sitemap.xml").mock(return_value=httpx.Response(200))
    serve_pages("https://s.com")
    sample = reader(tmp_path).read("s.com")
    assert sample.sitemaps == ["https://s.com/sitemap_index.xml"]
    assert (first.call_count, second.call_count, third.call_count) == (1, 1, 0)


@respx.mock
def test_read_uses_the_sitemap_homepage_host(tmp_path: Path) -> None:
    robots = "User-agent: *\nSitemap: https://www.moxo.com/sitemap.xml\n"
    respx.get("https://moxo.com/robots.txt").mock(return_value=httpx.Response(200, text=robots))
    respx.get("https://www.moxo.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://www.moxo.com/sitemap.xml").mock(
        return_value=httpx.Response(
            200, content=urlset("/", "/pricing", host="https://www.moxo.com")
        )
    )
    bare_home = respx.get("https://moxo.com/").mock(return_value=httpx.Response(200))
    serve_pages("https://www.moxo.com")
    sample = reader(tmp_path).read("moxo.com")
    assert sample.origin == "https://www.moxo.com"
    assert [p.url for p in sample.pages] == [
        "https://www.moxo.com/",
        "https://www.moxo.com/pricing",
    ]
    assert bare_home.call_count == 0
    assert sample.urls_found == 2


def js_site(robots: str = "User-agent: *\nSitemap: https://app.com/sitemap.xml\n") -> None:
    """A JavaScript site like emitii.com: the HTML has no links, the sitemap lists 2 pages."""
    respx.get("https://app.com/robots.txt").mock(return_value=httpx.Response(200, text=robots))
    respx.get("https://app.com/sitemap.xml").mock(
        return_value=httpx.Response(200, content=urlset("/", "/contact", host="https://app.com"))
    )
    shell = '<html><head><title>App</title></head><body><div id="root"></div></body></html>'
    respx.get(url__regex=r"^https://app\.com/.*").mock(
        return_value=httpx.Response(200, text=shell, headers=HTML)
    )


RENDERED = (
    "<html><head><title>App</title></head><body><h1>Client workspace</h1>"
    '<a href="/contact">C</a><a href="/demo/agency">D</a><a href="/demo/studio">D</a>'
    "<p>" + " ".join(["word"] * 200) + "</p></body></html>"
)


@respx.mock
def test_js_homepage_is_rendered_for_links_and_small_site_pages(tmp_path: Path) -> None:
    js_site()
    calls: list[str] = []

    def render(url: str, agent: str, timeout: float) -> str:
        calls.append(url)
        return RENDERED

    sample = reader(tmp_path, render=render).read("app.com")
    urls = [p.url for p in sample.pages]
    assert sample.source == "sitemap+links"
    assert set(urls) == {
        "https://app.com/",
        "https://app.com/contact",
        "https://app.com/demo/agency",
        "https://app.com/demo/studio",
    }
    assert sample.pages[0].headings == ["Client workspace"]  # rendered, not the empty shell
    assert calls.count("https://app.com/") == 2  # once for links, once for the page itself


@respx.mock
def test_no_browser_when_the_html_already_has_links(tmp_path: Path) -> None:
    respx.get("https://s.com/robots.txt").mock(return_value=httpx.Response(404))
    for path in ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml"):
        respx.get(f"https://s.com{path}").mock(return_value=httpx.Response(404))
    links = "".join(f'<a href="/p{i}">x</a>' for i in range(40))
    respx.get("https://s.com/").mock(
        return_value=httpx.Response(200, text=page_html("Home", 200) + links, headers=HTML)
    )
    serve_pages("https://s.com")

    def render(*_: object) -> str:
        raise AssertionError("the browser must not start")

    sample = reader(tmp_path, render=render).read("s.com")
    assert len(sample.pages) == 30  # large site: no per-page browser either


@respx.mock
def test_browser_failure_keeps_the_plain_result(tmp_path: Path) -> None:
    js_site()

    def render(*_: object) -> str:
        raise RuntimeError("chrome missing")

    sample = reader(tmp_path, render=render).read("app.com")
    assert {p.url for p in sample.pages} == {"https://app.com/", "https://app.com/contact"}


@respx.mock
def test_browser_settings_can_be_switched_off(tmp_path: Path) -> None:
    js_site()
    calls: list[str] = []
    sample = reader(
        tmp_path,
        render=lambda url, *_: calls.append(url) or RENDERED,
        links_headless_below=0,
        small_site_headless_pages=0,
    ).read("app.com")
    assert calls == []
    assert len(sample.pages) == 2


def index(*locs: str) -> bytes:
    items = "".join(f"<sitemap><loc>{u}</loc></sitemap>" for u in locs)
    return f'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</sitemapindex>'.encode()


@respx.mock
def test_sitemaps_on_other_hosts_are_never_requested(tmp_path: Path) -> None:
    robots = "Sitemap: http://10.0.0.5:8080/admin.xml\nSitemap: https://s.com/index.xml\n"
    respx.get("https://s.com/robots.txt").mock(return_value=httpx.Response(200, text=robots))
    respx.get("https://s.com/index.xml").mock(
        return_value=httpx.Response(
            200, content=index("http://169.254.169.254/meta.xml", "https://s.com/pages.xml")
        )
    )
    respx.get("https://s.com/pages.xml").mock(
        return_value=httpx.Response(200, content=urlset("/a"))
    )
    private = respx.route(url__regex=r"^https?://(10\.0\.0\.5|169\.254\.169\.254)").mock(
        return_value=httpx.Response(200)
    )
    serve_pages("https://s.com")
    sample = reader(tmp_path).read("s.com")
    assert private.call_count == 0
    assert sample.sitemaps == ["https://s.com/index.xml", "https://s.com/pages.xml"]


@respx.mock
def test_sitemap_requests_are_capped_even_when_they_fail(tmp_path: Path) -> None:
    children = [f"https://s.com/child-{i}.xml" for i in range(50)]
    robots = "Sitemap: https://s.com/index.xml\n"
    respx.get("https://s.com/robots.txt").mock(return_value=httpx.Response(200, text=robots))
    respx.get("https://s.com/index.xml").mock(
        return_value=httpx.Response(200, content=index(*children))
    )
    failing = respx.get(url__regex=r"^https://s\.com/child-\d+\.xml$").mock(
        return_value=httpx.Response(404)
    )
    serve_pages("https://s.com")
    reader(tmp_path, max_sitemap_files=8).read("s.com")
    assert failing.call_count == 7  # 8 attempts: the index, then 7 children


@respx.mock
def test_an_index_found_at_a_common_path_has_all_its_children_read(tmp_path: Path) -> None:
    respx.get("https://s.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://s.com/sitemap.xml").mock(return_value=httpx.Response(404))
    respx.get("https://s.com/sitemap_index.xml").mock(
        return_value=httpx.Response(
            200,
            content=index("https://s.com/page-sitemap.xml", "https://s.com/product-sitemap.xml"),
        )
    )
    respx.get("https://s.com/page-sitemap.xml").mock(
        return_value=httpx.Response(200, content=urlset("/about"))
    )
    respx.get("https://s.com/product-sitemap.xml").mock(
        return_value=httpx.Response(200, content=urlset("/plans"))
    )
    wp = respx.get("https://s.com/wp-sitemap.xml").mock(return_value=httpx.Response(200))
    serve_pages("https://s.com")
    sample = reader(tmp_path).read("s.com")
    assert {p.url for p in sample.pages} >= {"https://s.com/about", "https://s.com/plans"}
    assert wp.call_count == 0  # a working common path makes the others unnecessary


@respx.mock
def test_a_failed_sitemap_is_tried_again_the_same_day(tmp_path: Path) -> None:
    respx.get("https://s.com/robots.txt").mock(
        return_value=httpx.Response(200, text="Sitemap: https://s.com/sitemap.xml\n")
    )
    sitemap = respx.get("https://s.com/sitemap.xml").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, content=urlset("/a"))]
    )
    serve_pages("https://s.com")
    assert reader(tmp_path).read("s.com").sitemaps == []
    assert reader(tmp_path).read("s.com").sitemaps == ["https://s.com/sitemap.xml"]
    assert sitemap.call_count == 2


@respx.mock
def test_a_gzip_bomb_sitemap_is_rejected(tmp_path: Path) -> None:
    bomb = gzip.compress(urlset(*[f"/p{i}" for i in range(2000)]))
    respx.get("https://s.com/robots.txt").mock(
        return_value=httpx.Response(200, text="Sitemap: https://s.com/s.xml.gz\n")
    )
    respx.get("https://s.com/s.xml.gz").mock(return_value=httpx.Response(200, content=bomb))
    serve_pages("https://s.com")
    assert len(bomb) < 10_000
    sample = reader(tmp_path, max_sitemap_bytes=10_000).read("s.com")  # unpacks to ~60 KB
    assert sample.sitemaps == []


@respx.mock
def test_the_address_is_read_as_typed(tmp_path: Path) -> None:
    respx.get("https://www.w.com/robots.txt").mock(return_value=httpx.Response(404))
    for path in ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml"):
        respx.get(f"https://www.w.com{path}").mock(return_value=httpx.Response(404))
    bare = respx.get(url__regex=r"^https://w\.com/").mock(side_effect=httpx.ConnectError("no apex"))
    serve_pages("https://www.w.com")
    sample = reader(tmp_path).read("https://www.w.com")
    assert sample.domain == "w.com" and [p.url for p in sample.pages] == ["https://www.w.com/"]
    assert bare.call_count == 0


def test_headless_browsers_are_limited() -> None:
    import threading
    import time

    from seo_engine.concurrency import pmap
    from seo_engine.providers.sitemap import limited

    running, peak, lock = [0], [0], threading.Lock()

    def render(url: str, agent: str, timeout: float) -> str:
        with lock:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        time.sleep(0.02)
        with lock:
            running[0] -= 1
        return "<html></html>"

    gated = limited(render, 2)
    pmap(lambda u: gated(u, "agent", 1.0), [f"https://s{i}.com/" for i in range(12)], 8)
    assert peak[0] == 2
