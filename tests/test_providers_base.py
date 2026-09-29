import gzip
import json
import threading
from datetime import date

import httpcore
import httpx
import pytest

from seo_engine.providers import base
from seo_engine.providers.base import (
    DailyCache,
    PublicOnlyBackend,
    TooLarge,
    bounded_get,
    decode_body,
    gunzip_capped,
    ip_is_public,
    is_public_url,
    public_addresses,
    public_client,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/",
        "http://localhost/",
        "http://10.0.0.5/",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://0.0.0.0/",
        "http://[::1]/",
        "not a url",
        "http://no-such-host.invalid/",
    ],
)
def test_private_and_unresolvable_addresses_are_not_public(url: str) -> None:
    assert not is_public_url(url)


@pytest.mark.parametrize(
    ("address", "public"),
    [
        ("93.184.215.14", True),
        ("2606:4700::6810:84e5", True),
        ("100.100.100.200", False),  # carrier-grade NAT (100.64/10); is_private misses it
        ("::ffff:127.0.0.1", False),  # IPv4-mapped loopback
        ("::ffff:10.0.0.5", False),
        ("::ffff:93.184.215.14", True),
        ("fe80::1%eth0", False),  # link-local with a zone id
        ("224.0.0.1", False),
        ("198.18.0.1", False),  # benchmarking range
    ],
)
def test_ip_is_public(address: str, public: bool) -> None:
    assert ip_is_public(address) is public


def fake_dns(monkeypatch: pytest.MonkeyPatch, answers: dict[str, list[str]]) -> list[str]:
    asked: list[str] = []

    def getaddrinfo(host, port, *args, **kwargs):
        asked.append(host)
        if host not in answers:
            raise OSError("no such host")
        return [(0, 0, 0, "", (a, port or 0)) for a in answers[host]]

    monkeypatch.setattr(base.socket, "getaddrinfo", getaddrinfo)
    return asked


def test_one_private_address_makes_the_host_private(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_dns(monkeypatch, {"mixed.example": ["93.184.215.14", "10.0.0.5"]})
    assert public_addresses("mixed.example") == []


def test_dns_failures_are_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    answers: dict[str, list[str]] = {}
    asked = fake_dns(monkeypatch, answers)
    assert public_addresses("later.example") == []
    answers["later.example"] = ["93.184.215.14"]
    assert public_addresses("later.example") == ["93.184.215.14"]
    assert asked == ["later.example", "later.example"]


def test_backend_refuses_private_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_dns(monkeypatch, {"rebind.example": ["127.0.0.1"]})
    with pytest.raises(httpcore.ConnectError, match="not a public address"):
        PublicOnlyBackend().connect_tcp("rebind.example", 80)


def test_backend_connects_to_the_address_it_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_dns(monkeypatch, {"site.example": ["93.184.215.14"]})
    dialed: list[str] = []

    def connect_tcp(self, host, port, *args, **kwargs):
        dialed.append(host)
        return "stream"

    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", connect_tcp)
    assert PublicOnlyBackend().connect_tcp("site.example", 443) == "stream"
    assert dialed == ["93.184.215.14"]  # the IP, not a second lookup of the name


def test_public_client_uses_the_guard_and_the_pinned_backend() -> None:
    c = public_client(timeout=5)
    assert base.guard_request in c.event_hooks["request"]
    assert isinstance(c._transport._pool._network_backend, PublicOnlyBackend)


def test_public_client_blocks_a_real_request_to_a_private_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(base, "address_check", is_public_url)
    with pytest.raises(base.BlockedAddress), public_client(timeout=5) as c:
        c.get("http://127.0.0.1:9/")


def test_decode_body_survives_unknown_charsets() -> None:
    assert decode_body("café".encode(), "no-such-charset") == "café"
    assert decode_body("café".encode("latin-1"), "latin-1") == "café"
    assert decode_body(b"\xff ok", None).endswith(" ok")


def client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_bounded_get_stops_at_the_size_cap() -> None:
    body = b"x" * 5000
    got = bounded_get(
        client(lambda r: httpx.Response(200, content=body)), "https://s.com/", 1000, 60
    )
    assert got.too_large and got.content == b""
    ok = bounded_get(
        client(lambda r: httpx.Response(200, content=body)), "https://s.com/", 10_000, 60
    )
    assert not ok.too_large and ok.content == body and ok.status == 200


def test_bounded_get_has_an_overall_deadline() -> None:
    with pytest.raises(httpx.ReadTimeout):
        bounded_get(client(lambda r: httpx.Response(200, content=b"x")), "https://s.com/", 10, -1)


def test_gunzip_is_capped_against_gzip_bombs() -> None:
    bomb = gzip.compress(b"\0" * 1_000_000)  # about 1 KB that unpacks to 1 MB
    assert len(bomb) < 5_000
    with pytest.raises(TooLarge):
        gunzip_capped(bomb, 100_000)
    assert gunzip_capped(gzip.compress(b"hello"), 100) == b"hello"
    with pytest.raises(ValueError):
        gunzip_capped(b"\x1f\x8bnot gzip", 100)


def test_guard_blocks_every_hop_of_a_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base, "address_check", lambda url: "10.0.0.5" not in url)
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://10.0.0.5/admin"})

    c = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
        event_hooks={"request": [base.guard_request]},
    )
    with pytest.raises(base.BlockedAddress):
        c.get("https://public.example/")
    assert seen == ["https://public.example/"]  # the private hop was never sent


def test_cache_writes_are_atomic(tmp_path) -> None:
    cache = DailyCache(tmp_path, today=lambda: date(2026, 9, 29))
    errors: list[Exception] = []
    big = {"rows": list(range(20_000))}

    def writer() -> None:
        for _ in range(20):
            cache.set("ns", "key", big)

    def reader() -> None:
        for _ in range(200):
            try:
                cache.get("ns", "key")
            except json.JSONDecodeError as exc:  # a half-written file
                errors.append(exc)

    cache.set("ns", "key", big)
    threads = [threading.Thread(target=writer) for _ in range(3)] + [
        threading.Thread(target=reader) for _ in range(3)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert not list(tmp_path.rglob("*.tmp"))  # no temporary files left behind
