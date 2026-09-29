"""Site Snapshot providers: link score, Majestic Million, CrUX speed, domain dates.
Recorded answers (tests/fixtures/site_facts/); no live calls."""

import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from conftest import load_json, load_text
from seo_engine.providers.crux import CRUX_URL, CruxSpeed, parse_record
from seo_engine.providers.domain_age import (
    RDAP_BOOTSTRAP_URL,
    WAYBACK_CDX_URL,
    DomainAge,
    first_capture,
    rdap_servers,
    registration_date,
)
from seo_engine.providers.majestic import (
    MAJESTIC_URL,
    DictMajestic,
    MajesticEntry,
    MajesticMillion,
    parse_rows,
)
from seo_engine.providers.openpagerank import OPR_URL, OpenPageRank

F = "site_facts/"
UA = "test-agent"


def no_sleep(_: float) -> None:
    pass


# --- Open PageRank -----------------------------------------------------------------------


@respx.mock
def test_link_score_from_the_recorded_answer(cache) -> None:
    route = respx.post(OPR_URL).mock(
        return_value=httpx.Response(200, json=load_json(F + "opr_gurzu.json"))
    )
    got = OpenPageRank("opr_live_test", cache).score("www.Gurzu.com")
    assert got.status == "ok" and got.domain == "gurzu.com"
    assert (got.score, got.rank, got.referring_domains) == (1.78, 2634099, 13)
    assert got.history[0].month == date(2020, 5, 1) and got.history[0].score == 0.41
    assert got.history[-1].month == date(2026, 9, 1) and got.history[-1].score == 1.78
    sent = route.calls[0].request
    assert sent.headers["Authorization"] == "Bearer opr_live_test"
    assert json.loads(sent.content) == {"domains": ["gurzu.com"], "include_history": True}


@respx.mock
def test_link_score_is_cached_for_the_day(cache) -> None:
    route = respx.post(OPR_URL).mock(
        return_value=httpx.Response(200, json=load_json(F + "opr_gurzu.json"))
    )
    opr = OpenPageRank("opr_live_test", cache)
    assert opr.score("gurzu.com") == opr.score("gurzu.com")
    assert route.call_count == 1


@respx.mock
def test_unknown_domain_is_not_found(cache) -> None:
    body = load_json(F + "opr_gurzu.json")
    body["results"] = body["results"][1:]  # the recorded unknown domain
    respx.post(OPR_URL).mock(return_value=httpx.Response(200, json=body))
    got = OpenPageRank("opr_live_test", cache).score("no-such-domain-xyz123.com")
    assert got.status == "not_found" and got.score is None


def test_no_key_means_not_set_up_and_no_request(cache) -> None:
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post(OPR_URL)
        got = OpenPageRank("", cache).score("gurzu.com")
    assert got.status == "not_set_up" and route.call_count == 0


@respx.mock
def test_invalid_key_is_an_error_that_is_not_cached(cache) -> None:
    route = respx.post(OPR_URL).mock(
        return_value=httpx.Response(401, text=load_text(F + "opr_invalid_key.json"))
    )
    opr = OpenPageRank("opr_live_bad", cache, sleep=no_sleep)
    got = opr.score("gurzu.com")
    assert got.status == "error" and "invalid key" in got.note
    assert "opr_live_bad" not in got.note
    opr.score("gurzu.com")
    assert route.call_count == 2  # a fixed key must work the same day


@respx.mock
def test_network_error_is_an_error_not_an_exception(cache) -> None:
    respx.post(OPR_URL).mock(side_effect=httpx.ConnectError("down"))
    got = OpenPageRank("opr_live_test", cache, sleep=no_sleep).score("gurzu.com")
    assert got.status == "error" and "ConnectError" in got.note


# --- Majestic Million ----------------------------------------------------------------------

CSV = (
    "GlobalRank,TldRank,Domain,TLD,RefSubNets,RefIPs,IDN_Domain,IDN_TLD,"
    "PrevGlobalRank,PrevTldRank,PrevRefSubNets,PrevRefIPs\n"
    "10,10,github.com,com,254817,640820,github.com,com,10,10,254777,640682\n"
    "578712,254725,lftechnology.com,com,338,1536,lftechnology.com,com,1,1,337,1490\n"
    "bad,row,broken.com,com,x,y,,,,,,\n"
)


def test_csv_rows_are_read_by_header_name_and_bad_rows_skipped() -> None:
    rows = list(parse_rows(iter(CSV.splitlines())))
    assert rows == [("github.com", 10, 254817, 640820), ("lftechnology.com", 578712, 338, 1536)]


@respx.mock
def test_majestic_download_and_lookup(tmp_path: Path) -> None:
    route = respx.get(MAJESTIC_URL).mock(return_value=httpx.Response(200, text=CSV))
    mm = MajesticMillion(tmp_path)
    got = mm.lookup("blog.lftechnology.com")  # a subdomain counts as its domain
    assert got == MajesticEntry(
        domain="lftechnology.com", global_rank=578712, ref_subnets=338, ref_ips=1536
    )
    assert mm.lookup("gurzu.com") is None  # not in the top one million
    assert MajesticMillion(tmp_path).lookup("github.com").ref_subnets == 254817
    assert route.call_count == 1  # the second reader uses the stored copy


@respx.mock
def test_a_failed_refresh_keeps_the_old_list(tmp_path: Path) -> None:
    respx.get(MAJESTIC_URL).mock(return_value=httpx.Response(200, text=CSV))
    MajesticMillion(tmp_path).lookup("github.com")
    respx.get(MAJESTIC_URL).mock(return_value=httpx.Response(200, text="<html>error</html>"))
    stale = MajesticMillion(tmp_path, max_age_days=0)  # forces a refresh, which gets no rows
    assert stale.lookup("github.com").ref_subnets == 254817  # last copy used, no error
    assert not list((tmp_path / "majestic").glob("*.tmp"))  # nothing half-written left behind


@respx.mock
def test_a_failed_first_download_raises(tmp_path: Path) -> None:
    respx.get(MAJESTIC_URL).mock(return_value=httpx.Response(200, text="<html>error</html>"))
    with pytest.raises(ValueError, match="no rows"):
        MajesticMillion(tmp_path).lookup("github.com")
    assert not list((tmp_path / "majestic").glob("*.tmp"))


@respx.mock
def test_two_readers_download_once(tmp_path: Path) -> None:
    import threading

    route = respx.get(MAJESTIC_URL).mock(return_value=httpx.Response(200, text=CSV))
    readers = [MajesticMillion(tmp_path) for _ in range(4)]  # as in parallel snapshot runs
    threads = [threading.Thread(target=r.lookup, args=("github.com",)) for r in readers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert route.call_count == 1


def test_exact_lookup_never_borrows_the_parent_domain() -> None:
    entry = MajesticEntry(domain="github.io", global_rank=50, ref_subnets=300_000, ref_ips=1)
    mm = DictMajestic([entry])
    assert mm.lookup("alice.github.io") == entry  # difficulty: a subdomain counts as its domain
    assert mm.lookup("alice.github.io", exact=True) is None  # snapshot: never github.io's data
    assert mm.lookup("www.github.io", exact=True) == entry  # www is the same site


def test_dict_majestic_for_tests() -> None:
    entry = MajesticEntry(domain="a.com", global_rank=5, ref_subnets=9, ref_ips=12)
    assert DictMajestic([entry]).lookup("www.a.com") == entry


# --- CrUX ----------------------------------------------------------------------------------


def test_crux_record_parsing() -> None:
    got = parse_record("https://www.example.com", "PHONE", load_json(F + "crux_record.json"))
    assert got.status == "ok"
    assert got.p75 == {
        "largest_contentful_paint": 2063.0,
        "interaction_to_next_paint": 250.0,
        "cumulative_layout_shift": 0.05,  # sent as a string
    }
    assert (got.first_day, got.last_day) == (date(2026, 8, 30), date(2026, 9, 26))


@respx.mock
def test_crux_sends_the_key_in_a_header_not_the_url(cache) -> None:
    route = respx.post(CRUX_URL).mock(
        return_value=httpx.Response(200, json=load_json(F + "crux_record.json"))
    )
    got = CruxSpeed("secret-key", cache).speed("https://www.example.com/")
    sent = route.calls[0].request
    assert "secret-key" not in str(sent.url)
    assert sent.headers["X-Goog-Api-Key"] == "secret-key"
    assert json.loads(sent.content)["origin"] == "https://www.example.com"
    assert got.status == "ok"


@respx.mock
def test_crux_404_means_no_data_and_is_cached(cache) -> None:
    route = respx.post(CRUX_URL).mock(
        return_value=httpx.Response(
            404, json={"error": {"code": 404, "message": "chrome ux report data not found"}}
        )
    )
    crux = CruxSpeed("k", cache)
    got = crux.speed("https://gurzu.com")
    assert got.status == "no_data" and "not enough Chrome visitors" in got.note
    crux.speed("https://gurzu.com")
    assert route.call_count == 1


@respx.mock
def test_crux_other_errors_are_not_cached(cache) -> None:
    route = respx.post(CRUX_URL).mock(return_value=httpx.Response(403, json={}))
    crux = CruxSpeed("k", cache, sleep=no_sleep)
    assert crux.speed("https://gurzu.com").status == "error"
    crux.speed("https://gurzu.com")
    assert route.call_count == 2


def test_crux_without_a_key_is_not_set_up(cache) -> None:
    assert CruxSpeed("", cache).speed("https://gurzu.com").status == "not_set_up"


# --- Domain dates ------------------------------------------------------------------------


def test_rdap_servers_from_the_bootstrap_file() -> None:
    servers = rdap_servers(load_json(F + "rdap_bootstrap.json"))
    assert servers["com"] == "https://rdap.verisign.com/com/v1/"
    assert "io" not in servers  # not in the IANA list (F10)


def test_registration_and_first_capture_parsing() -> None:
    assert registration_date(load_json(F + "rdap_gurzu.json")) == date(2018, 10, 13)
    assert registration_date({"events": [{"eventAction": "expiration"}]}) is None
    rows = json.loads(load_text(F + "wayback_gurzu.json"))
    assert first_capture(rows) == (date(2017, 5, 20), "http://gurzu.com:80/")
    assert first_capture([]) is None


def mock_dates(rdap: httpx.Response, wayback: httpx.Response):
    respx.get(RDAP_BOOTSTRAP_URL).mock(
        return_value=httpx.Response(200, json=load_json(F + "rdap_bootstrap.json"))
    )
    rdap_route = respx.get(url__startswith="https://rdap.verisign.com/com/v1/domain/").mock(
        return_value=rdap
    )
    wb_route = respx.get(url__startswith=WAYBACK_CDX_URL).mock(return_value=wayback)
    return rdap_route, wb_route


@respx.mock
def test_both_dates_are_kept_when_they_differ(cache) -> None:
    rdap, wb = mock_dates(
        httpx.Response(200, json=load_json(F + "rdap_gurzu.json")),
        httpx.Response(200, text=load_text(F + "wayback_gurzu.json")),
    )
    got = DomainAge(cache, UA).dates("www.gurzu.com")
    assert got.registered == date(2018, 10, 13)  # the current registration
    assert got.first_seen == date(2017, 5, 20)  # older: a capture before it (F15)
    assert got.registered_via == "https://rdap.verisign.com/com/v1/"
    assert got.notes == []
    assert str(rdap.calls[0].request.url).endswith("/domain/gurzu.com")
    assert wb.calls[0].request.url.params["url"] == "gurzu.com"
    assert rdap.calls[0].request.headers["User-Agent"] == UA
    DomainAge(cache, UA).dates("gurzu.com")
    assert (rdap.call_count, wb.call_count) == (1, 1)  # cached for the day


@respx.mock
def test_tld_without_rdap_and_no_capture_are_notes(cache) -> None:
    mock_dates(httpx.Response(404), httpx.Response(200, text="[]\n"))
    got = DomainAge(cache, UA).dates("emitii.io")
    assert got.registered is None and got.first_seen is None
    assert got.notes == [
        "registration date: .io has no public RDAP service",
        "first seen online: no Wayback capture",
    ]


@respx.mock
def test_subdomain_falls_back_to_its_domain(cache) -> None:
    respx.get(RDAP_BOOTSTRAP_URL).mock(
        return_value=httpx.Response(200, json=load_json(F + "rdap_bootstrap.json"))
    )
    base = "https://rdap.verisign.com/com/v1/domain/"
    sub = respx.get(base + "blog.gurzu.com").mock(return_value=httpx.Response(404))
    main = respx.get(base + "gurzu.com").mock(
        return_value=httpx.Response(200, json=load_json(F + "rdap_gurzu.json"))
    )
    respx.get(url__startswith=WAYBACK_CDX_URL).mock(return_value=httpx.Response(200, text="[]"))
    got = DomainAge(cache, UA).dates("blog.gurzu.com")
    assert got.registered == date(2018, 10, 13)
    assert got.registered_domain == "gurzu.com"  # the date belongs to the registered name
    assert (sub.call_count, main.call_count) == (1, 1)


@respx.mock
def test_wayback_rate_limit_is_a_note_and_not_cached(cache) -> None:
    _, wb = mock_dates(
        httpx.Response(200, json=load_json(F + "rdap_gurzu.json")), httpx.Response(429)
    )
    age = DomainAge(cache, UA)
    got = age.dates("gurzu.com")
    assert got.registered == date(2018, 10, 13) and got.first_seen is None
    assert got.notes == ["first seen online: Wayback unavailable (HTTPStatusError)"]
    age.dates("gurzu.com")
    assert wb.call_count == 2  # tried again: a temporary block must not last the day


@respx.mock
def test_rdap_server_error_is_a_note(cache) -> None:
    mock_dates(httpx.Response(503), httpx.Response(200, text="[]"))
    got = DomainAge(cache, UA).dates("gurzu.com")
    assert got.registered is None
    assert "registration date: RDAP HTTP 503" in got.notes


def test_domain_dates_never_reach_a_private_address(cache, monkeypatch) -> None:
    """A hostile bootstrap file could name a private RDAP server: the guard blocks it."""
    monkeypatch.setattr(
        "seo_engine.providers.base.address_check", lambda url: "10.0.0.5" not in url
    )
    with respx.mock(assert_all_called=False) as mock:
        mock.get(RDAP_BOOTSTRAP_URL).mock(
            return_value=httpx.Response(
                200, json={"services": [[["com"], ["https://10.0.0.5/rdap/"]]]}
            )
        )
        private = mock.get(url__startswith="https://10.0.0.5/")
        mock.get(url__startswith=WAYBACK_CDX_URL).mock(return_value=httpx.Response(200, text="[]"))
        got = DomainAge(cache, UA).dates("gurzu.com")
    assert private.call_count == 0
    assert got.registered is None and "BlockedAddress" in got.notes[0]
