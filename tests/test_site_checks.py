"""Site Snapshot technical checks (tools/site_checks.py): pure code on recorded probe answers."""

import pytest

from seo_engine.providers.site_probe import Hop, Probe, SiteProbe
from seo_engine.providers.sitemap import SiteSample
from seo_engine.tools.site_checks import (
    canonical_from_link_header,
    read_tags,
    same_page,
    says_noindex,
    site_checks,
)

HOME = "https://www.site.com/"
GOOD_HTML = """<html><head>
<title>Site: software for agencies that want happier clients</title>
<meta name="description" content="Site helps agencies share files, approvals and updates with
clients in one calm place. Try it free for fourteen days, no card needed.">
<link rel="canonical" href="https://www.site.com/">
</head><body><h1>Site</h1></body></html>"""


def moved(url: str, to: str, status: int = 301) -> Probe:
    return Probe(url=url, status=200, final_url=to, hops=[Hop(url=url, status=status)])


def good_probe(html: str = GOOD_HTML, **home_fields) -> SiteProbe:
    return SiteProbe(
        domain="site.com",
        variants=[
            moved("https://site.com/", HOME),
            Probe(url=HOME, status=200, final_url=HOME),
            moved("http://site.com/", HOME),
            moved("http://www.site.com/", HOME),
        ],
        home=HOME,
        robots=Probe(
            url="https://www.site.com/robots.txt",
            status=200,
            final_url="x",
            body="User-agent: *\nDisallow: /admin/\n",
        ),
        homepage=Probe(url=HOME, status=200, final_url=HOME, body=html, **home_fields),
    )


SAMPLE = SiteSample(
    domain="site.com",
    origin="https://site.com",
    source="sitemap",
    sitemaps=["a.xml", "b.xml"],
    urls_found=40,
    sitemap_urls=48,
)


def results(probe: SiteProbe, sample: SiteSample | None = SAMPLE) -> dict[str, tuple[str, str]]:
    return {c.key: (c.status, c.detail) for c in site_checks(probe, sample).checks}


def test_a_healthy_site_passes_everything() -> None:
    got = results(good_probe())
    assert {k: s for k, (s, _) in got.items()} == {
        "https": "pass",
        "http_redirect": "pass",
        "one_address": "pass",
        "permanent_redirects": "pass",
        "robots": "pass",
        "sitemap": "pass",
        "indexable": "pass",
        "title": "pass",
        "description": "pass",
        "canonical": "pass",
    }
    assert got["sitemap"][1] == "48 page addresses listed in 2 sitemap files."
    assert got["one_address"][1] == "All working addresses lead to https://www.site.com/."


def test_http_only_site_fails_https() -> None:
    probe = good_probe()
    plain = Probe(url="http://site.com/", status=200, final_url="http://site.com/")
    probe = probe.model_copy(
        update={
            "home": "http://site.com/",
            "variants": [
                Probe(url="https://site.com/", error="ConnectError"),
                Probe(url=HOME, error="ConnectError"),
                plain,
                moved("http://www.site.com/", "http://site.com/"),
            ],
        }
    )
    got = results(probe)
    assert got["https"][0] == "fail" and got["http_redirect"][0] == "fail"


def test_two_addresses_that_both_show_the_site_are_a_warning() -> None:
    probe = good_probe()
    variants = list(probe.variants)
    variants[0] = Probe(
        url="https://site.com/", status=200, final_url="https://site.com/"
    )  # no redirect
    got = results(probe.model_copy(update={"variants": variants}))
    assert got["one_address"][0] == "warn"
    assert "https://site.com/" in got["one_address"][1] and HOME in got["one_address"][1]


def test_www_that_does_not_resolve_is_fine() -> None:
    probe = good_probe()
    variants = list(probe.variants)
    variants[3] = Probe(url="http://www.site.com/", error="ConnectError")
    status, detail = results(probe.model_copy(update={"variants": variants}))["one_address"]
    assert status == "pass" and "1 of 4 addresses did not answer" in detail


@pytest.mark.parametrize(
    ("code", "status"), [(301, "pass"), (308, "pass"), (302, "warn"), (307, "warn")]
)
def test_redirect_kinds(code: int, status: str) -> None:
    probe = good_probe()
    variants = list(probe.variants)
    variants[2] = moved("http://site.com/", HOME, code)
    assert (
        results(probe.model_copy(update={"variants": variants}))["permanent_redirects"][0] == status
    )


@pytest.mark.parametrize(
    ("robots", "status"),
    [
        (Probe(url="r", status=404), "pass"),
        (Probe(url="r", status=503), "warn"),
        (Probe(url="r", error="ReadTimeout"), "warn"),
        (Probe(url="r", status=200, body="User-agent: *\nDisallow: /\n"), "fail"),
        (
            Probe(
                url="r",
                status=200,
                body="User-agent: Googlebot\nDisallow: /\n\nUser-agent: *\nAllow: /\n",
            ),
            "fail",
        ),
        (Probe(url="r", status=200, body="User-agent: BadBot\nDisallow: /\n"), "pass"),
    ],
)
def test_robots_rules_are_read_for_googlebot(robots: Probe, status: str) -> None:
    assert results(good_probe().model_copy(update={"robots": robots}))["robots"][0] == status


def test_sitemap_states() -> None:
    links = SAMPLE.model_copy(update={"source": "links", "sitemaps": [], "sitemap_urls": 0})
    assert results(good_probe(), links)["sitemap"][0] == "warn"
    assert results(good_probe(), None)["sitemap"][0] == "unknown"
    # A small sitemap topped up with homepage links still is a sitemap (live: emitii.com).
    topped = SAMPLE.model_copy(
        update={"source": "sitemap+links", "sitemaps": ["s.xml"], "sitemap_urls": 10}
    )
    assert results(good_probe(), topped)["sitemap"] == (
        "pass",
        "10 page addresses listed in 1 sitemap file.",
    )
    empty = SAMPLE.model_copy(update={"source": "links", "sitemaps": ["s.xml"], "sitemap_urls": 0})
    assert results(good_probe(), empty)["sitemap"][0] == "warn"


@pytest.mark.parametrize(
    ("meta", "header", "noindex"),
    [
        ('<meta name="robots" content="noindex, follow">', "", True),
        ('<meta name="ROBOTS" content="none">', "", True),
        ('<meta name="googlebot" content="noindex">', "", True),
        ('<meta name="bingbot" content="noindex">', "", False),  # another crawler
        ("", "noindex", True),
        ("", "googlebot: noindex", True),
        ("", "otherbot: noindex, nofollow", False),
        ("", "unavailable_after: 25 Jun 2030 15:00:00 PST", False),
        ('<meta name="robots" content="index, follow">', "", False),
    ],
)
def test_noindex_in_meta_or_header(meta: str, header: str, noindex: bool) -> None:
    html = GOOD_HTML.replace("</head>", meta + "</head>")
    got = results(good_probe(html, x_robots_tags=[header] if header else []))["indexable"]
    assert got[0] == ("fail" if noindex else "pass")


def test_title_and_description_problems() -> None:
    html = "<html><head></head><body>x</body></html>"
    got = results(good_probe(html))
    assert got["title"][0] == "fail" and got["description"][0] == "warn"
    long = (
        "<html><head><title>"
        + "Very long homepage title " * 6
        + "</title><meta name='description' content='Too short.'></head></html>"
    )
    got = results(good_probe(long))
    assert got["title"][0] == "warn" and "Google will truncate it" in got["title"][1]
    assert got["description"] == ("warn", "10 characters; aim for 70 to 158.")


@pytest.mark.parametrize(
    ("tag", "status", "words"),
    [
        ("", "warn", "No canonical tag"),
        ('<link rel="canonical" href="/">', "pass", "itself"),  # relative, same page
        ('<link rel="canonical" href="https://www.site.com/other">', "warn", "not to the homepage"),
        ('<link rel="canonical" href="https://elsewhere.com/">', "warn", "another site"),
    ],
)
def test_canonical_tag(tag: str, status: str, words: str) -> None:
    html = GOOD_HTML.replace('<link rel="canonical" href="https://www.site.com/">', tag)
    got = results(good_probe(html))["canonical"]
    assert got[0] == status and words in got[1]


def test_canonical_in_the_link_header_counts() -> None:
    html = GOOD_HTML.replace('<link rel="canonical" href="https://www.site.com/">', "")
    got = results(good_probe(html, link_header='<https://www.site.com/>; rel="canonical"'))
    assert got["canonical"][0] == "pass"


def test_homepage_not_read_means_unknown_with_the_reason() -> None:
    probe = good_probe().model_copy(update={"homepage": None, "robots_blocks_us": True})
    got = results(probe)
    for key in ("indexable", "title", "description", "canonical"):
        assert got[key][0] == "unknown"
    assert got["title"][1] == "Robots.txt asks crawlers like ours not to read the homepage."


def test_nothing_answered() -> None:
    probe = SiteProbe(
        domain="site.com", variants=[Probe(url=u, error="ConnectError") for u in "abcd"]
    )
    got = results(probe, None)
    assert got["https"] == ("unknown", "No address of the site answered.")
    assert {got[k][0] for k in ("http_redirect", "one_address", "robots", "title")} == {"unknown"}


def test_helpers() -> None:
    assert same_page("https://Site.com", "https://site.com/")
    assert not same_page("https://site.com/?a=1", "https://site.com/")
    assert not same_page("http://site.com/", "https://site.com/")
    assert (
        canonical_from_link_header(
            '<https://a.com/x>; rel="preload", </y>; rel=canonical', "https://a.com/"
        )
        == "https://a.com/y"
    )
    assert canonical_from_link_header("", "https://a.com/") is None
    tags = read_tags(GOOD_HTML, HOME)
    assert tags.title.startswith("Site: software") and tags.canonical == HOME
    assert (
        tags.description.startswith("Site helps agencies share files")
        and "\n" not in tags.description
    )
    assert read_tags("", HOME) is None  # empty page: no crash, checks say "unknown"
    assert says_noindex(["googlebot: noindex"], header=True)


# --- review round (Step 6) ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("headers", "noindex"),
    [
        (["max-image-preview:large, noindex"], True),  # a rule with a value is not a crawler
        (["max-snippet: -1, noindex"], True),
        (["max-video-preview: 0, googlebot: noindex"], True),
        (["otherbot: nofollow", "noindex"], True),  # a new header starts again for all crawlers
        (["otherbot: noindex"], False),
        (["googlebot: max-snippet: 20, noindex"], True),
        (["unavailable_after: 2030-01-01", "none"], True),
    ],
)
def test_x_robots_tag_rules_with_values_and_several_headers(headers, noindex) -> None:
    assert says_noindex(headers, header=True) is noindex
    got = results(good_probe(x_robots_tags=headers))["indexable"]
    assert got[0] == ("fail" if noindex else "pass")


def test_a_page_with_an_xml_declaration_is_read() -> None:
    xhtml = '<?xml version="1.0" encoding="UTF-8"?>\n' + GOOD_HTML
    got = results(good_probe(xhtml))
    assert got["title"][0] == "pass" and got["canonical"][0] == "pass"
    noindex = xhtml.replace("</head>", '<meta name="robots" content="noindex"></head>')
    assert results(good_probe(noindex))["indexable"][0] == "fail"


def test_a_page_that_cannot_be_parsed_is_unknown_not_fail() -> None:
    got = results(good_probe("   "))  # whitespace only: lxml has nothing to parse
    assert {got[k][0] for k in ("indexable", "title", "description", "canonical")} == {"unknown"}


def test_a_bot_wall_is_unknown_not_a_failure() -> None:
    wall = [
        Probe(url=u, status=403, final_url="https://site.com/", hops=[Hop(url=u, status=301)])
        for u in (
            "https://site.com/",
            "https://www.site.com/",
            "http://site.com/",
            "http://www.site.com/",
        )
    ]
    probe = SiteProbe(domain="site.com", variants=wall)
    got = results(probe, None)
    assert got["https"][0] == "unknown" and "HTTP 403" in got["https"][1]
    assert got["http_redirect"] == (
        "pass",
        "http://site.com redirects to https://site.com/ (it answered HTTP 403).",
    )


@pytest.mark.parametrize(
    ("robots", "status", "words"),
    [
        (Probe(url="r", status=403), "pass", "treats that as no rules"),  # Google: 4xx = no rules
        (Probe(url="r", status=401), "pass", "treats that as no rules"),
        (Probe(url="r", status=429), "warn", "Google stops crawling"),
        (
            Probe(url="r", status=200, body="User-agent: *\nDisallow: /\n", too_large=True),
            "fail",
            "blocks Googlebot",
        ),  # too large: Google reads the first 500 KiB, which here blocks everything
        (
            Probe(url="r", status=200, body="User-agent: *\nAllow: /\n", too_large=True),
            "pass",
            "first 500 KiB",
        ),
    ],
)
def test_robots_answers_as_google_reads_them(robots: Probe, status: str, words: str) -> None:
    got = results(good_probe().model_copy(update={"robots": robots}))["robots"]
    assert got[0] == status and words in got[1]
