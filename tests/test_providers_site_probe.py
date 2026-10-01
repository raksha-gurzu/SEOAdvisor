"""The raw probe behind the technical checks (providers/site_probe.py). No live calls."""

import httpx
import pytest
import respx

from seo_engine.providers.site_probe import SiteProber, home_of, variant_urls

HOME = "https://www.site.com/"
PAGE = "<html><head><title>Site</title></head><body>Hi</body></html>"


def mock_site(robots: httpx.Response | None = None) -> dict[str, respx.Route]:
    return {
        "bare_https": respx.get("https://site.com/").mock(
            return_value=httpx.Response(301, headers={"Location": HOME})
        ),
        "home": respx.get(HOME).mock(
            return_value=httpx.Response(
                200,
                text=PAGE,
                headers={
                    "content-type": "text/html; charset=utf-8",
                    "X-Robots-Tag": "noarchive",
                    "Link": '<https://www.site.com/>; rel="canonical"',
                },
            )
        ),
        "bare_http": respx.get("http://site.com/").mock(
            return_value=httpx.Response(308, headers={"Location": "https://site.com/"})
        ),
        "www_http": respx.get("http://www.site.com/").mock(
            side_effect=httpx.ConnectError("refused")
        ),
        "robots": respx.get("https://www.site.com/robots.txt").mock(
            return_value=robots or httpx.Response(200, text="User-agent: *\nAllow: /\n")
        ),
    }


@respx.mock
def test_probe_records_every_hop_and_the_headers(settings) -> None:
    mock_site()
    got = SiteProber(settings).probe_site("www.site.com")
    assert [p.url for p in got.variants] == variant_urls("site.com")
    bare_http = got.variants[2]
    assert [(h.url, h.status) for h in bare_http.hops] == [
        ("http://site.com/", 308),
        ("https://site.com/", 301),
    ]
    assert bare_http.final_url == HOME and bare_http.ok
    assert got.variants[3].error == "ConnectError" and not got.variants[3].ok
    assert got.home == HOME
    assert got.homepage.body == PAGE
    assert got.homepage.x_robots_tags == ["noarchive"]
    assert "canonical" in got.homepage.link_header
    assert got.variants[0].body == ""  # variant probes never download the page


@respx.mock
def test_robots_that_block_us_mean_no_homepage_download(settings) -> None:
    routes = mock_site(httpx.Response(200, text="User-agent: *\nDisallow: /\n"))
    got = SiteProber(settings).probe_site("site.com")
    assert got.robots_blocks_us and got.homepage is None
    assert routes["home"].call_count == 3  # the 3 address probes that end there; no page download


@respx.mock
def test_when_robots_allow_us_the_homepage_is_downloaded_once_more(settings) -> None:
    routes = mock_site()
    SiteProber(settings).probe_site("site.com")
    assert routes["home"].call_count == 4


@respx.mock
def test_nothing_answers(settings) -> None:
    for url in variant_urls("site.com"):
        respx.get(url).mock(side_effect=httpx.ConnectError("down"))
    got = SiteProber(settings).probe_site("site.com")
    assert got.home == "" and got.robots is None and got.homepage is None


@respx.mock
def test_redirect_loop_is_an_error_not_a_crash(settings) -> None:
    respx.get("https://loop.com/").mock(
        return_value=httpx.Response(302, headers={"Location": "https://loop.com/"})
    )
    got = SiteProber(settings).probe("https://loop.com/")
    assert got.error == "too many redirects"


@respx.mock
def test_a_redirect_to_a_private_address_is_blocked(settings, monkeypatch) -> None:
    monkeypatch.setattr(
        "seo_engine.providers.base.address_check", lambda url: "10.0.0.5" not in url
    )
    respx.get("https://site.com/").mock(
        return_value=httpx.Response(302, headers={"Location": "http://10.0.0.5/admin"})
    )
    private = respx.get("http://10.0.0.5/admin").mock(
        return_value=httpx.Response(200, text="secret")
    )
    got = SiteProber(settings).probe("https://site.com/", body=True)
    assert got.error == "not a public address" and private.call_count == 0


@respx.mock
def test_body_over_the_cap_is_not_kept(settings) -> None:
    respx.get("https://big.com/").mock(return_value=httpx.Response(200, content=b"x" * 5000))
    got = SiteProber(settings).probe("https://big.com/", body=True, max_bytes=1000)
    assert got.too_large and got.body == ""


def test_home_is_the_first_address_that_answers_200() -> None:
    from seo_engine.providers.site_probe import Probe

    probes = [
        Probe(url="a", error="x"),
        Probe(url="b", status=200, final_url="https://b/"),
        Probe(url="c", status=200, final_url="https://c/"),
    ]
    assert home_of(probes) == "https://b/"
    assert home_of([Probe(url="a", status=500, final_url="https://a/")]) == ""


# --- review round (Step 6): robots.txt follows the page fetcher's rules --------------------


@pytest.mark.parametrize(
    "robots",
    [
        httpx.Response(503),
        httpx.Response(429),
        httpx.Response(403),  # we are stricter than the RFC here, as the page fetcher is
    ],
)
@respx.mock
def test_an_unreadable_or_refused_robots_txt_means_we_do_not_read_the_homepage(
    settings, robots
) -> None:
    routes = mock_site(robots)
    got = SiteProber(settings).probe_site("site.com")
    assert got.robots_blocks_us and got.homepage is None
    assert routes["home"].call_count == 3  # the address probes only


@respx.mock
def test_robots_rules_use_our_robots_name(settings) -> None:
    rules = f"User-agent: {settings.robots_token}\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
    mock_site(httpx.Response(200, text=rules))
    assert SiteProber(settings).probe_site("site.com").robots_blocks_us


@respx.mock
def test_a_large_robots_txt_keeps_its_start(settings) -> None:
    from seo_engine.providers.fetcher import ROBOTS_MAX_BYTES

    big = "User-agent: *\nDisallow: /private/\n" + "# padding\n" * (ROBOTS_MAX_BYTES // 8)
    mock_site(httpx.Response(200, text=big))
    got = SiteProber(settings).probe_site("site.com")
    assert got.robots.too_large and got.robots.body.startswith("User-agent: *")
    assert len(got.robots.body.encode()) <= ROBOTS_MAX_BYTES
    assert got.robots_blocks_us  # over the cap: like the page fetcher, we do not read the site
