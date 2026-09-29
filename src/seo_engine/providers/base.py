"""Shared provider plumbing: daily cache, cost sink, retrying HTTP."""

import codecs
import hashlib
import ipaddress
import json
import os
import socket
import threading
import time
import zlib
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import urlparse

import httpcore
import httpx

CostSink = Callable[[float, str], None]


def no_cost(usd: float, label: str) -> None:
    """Default sink for callers that do not track cost."""


class DailyCache:
    """JSON cache keyed by (namespace, inputs, date). Never pay twice on the same day."""

    def __init__(self, root: Path, today: Callable[[], date] = date.today) -> None:
        self.root = root
        self.today = today

    def _path(self, namespace: str, key: Any) -> Path:
        digest = hashlib.sha256(json.dumps(key, sort_keys=True, default=str).encode()).hexdigest()
        return self.root / self.today().isoformat() / namespace / f"{digest[:32]}.json"

    def get(self, namespace: str, key: Any) -> Any | None:
        path = self._path(namespace, key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def set(self, namespace: str, key: Any, value: Any) -> None:
        """Atomic: write a temporary file, then rename. Parallel runs share cache files, and a
        reader must never see a half-written one."""
        path = self._path(namespace, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(
            f"{path.name}.{os.getpid()}.{threading.get_ident()}.{time.monotonic_ns()}.tmp"
        )
        tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)


RETRY_STATUS = {429, 500, 502, 503, 504}


def request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    attempts: int = 4,
    backoff_s: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    **kwargs: Any,
) -> httpx.Response:
    """HTTP call with exponential backoff on transport errors and retryable status codes."""
    for attempt in range(attempts):
        try:
            response = client.request(method, url, **kwargs)
        except httpx.TransportError:
            if attempt == attempts - 1:
                raise
        else:
            if response.status_code not in RETRY_STATUS or attempt == attempts - 1:
                response.raise_for_status()
                return response
        sleep(backoff_s * 2**attempt)
    raise AssertionError("unreachable")


# ——— Network safety: only public addresses, bounded downloads ———


def ip_is_public(address: str) -> bool:
    """Only globally routable unicast addresses. `is_global` also rejects ranges `is_private`
    misses, such as 100.64.0.0/10 (carrier-grade NAT; a cloud metadata address lives there),
    and an IPv4 address written as IPv6 (::ffff:127.0.0.1) is judged by its IPv4 part."""
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def public_addresses(host: str, port: int | None = None) -> list[str]:
    """The host's addresses, or [] when it does not resolve or ANY address is not public.
    Never cached: a DNS hiccup must not block a site for good, and a cached "public" would let
    the name later point somewhere else (DNS rebinding)."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        return []
    addresses = list(dict.fromkeys(info[4][0] for info in infos))
    return addresses if addresses and all(ip_is_public(a) for a in addresses) else []


def host_is_public(host: str) -> bool:
    """False for localhost, private, link-local, reserved, shared, multicast or unresolvable."""
    return bool(public_addresses(host))


def is_public_url(url: str) -> bool:
    """Only fetch public web pages: never localhost, private or link-local addresses."""
    host = urlparse(url).hostname
    return bool(host) and host_is_public(host.lower())


# Looked up at call time, so the tests can allow their made-up hosts (tests/conftest.py).
address_check: Callable[[str], bool] = is_public_url


def address_check_url(url: str) -> bool:
    """The current address check (never bound early, so tests can replace it)."""
    return address_check(url)


class BlockedAddress(httpx.TransportError):
    """A request (or a redirect hop) to a private or unresolvable address was stopped."""


def guard_request(request: httpx.Request) -> None:
    """httpx request hook: runs before every request, redirect hops included. Sites we read
    choose the URLs (robots.txt Sitemap lines, sitemap entries, redirects), so every one is
    checked, not only the address the user typed."""
    if not address_check_url(str(request.url)):
        raise BlockedAddress(
            f"blocked: {request.url.host} is not a public address", request=request
        )


class PublicOnlyBackend(httpcore.SyncBackend):
    """httpcore network backend that resolves the host ONCE, requires every address to be
    public, and connects to the address it checked. TLS still uses the host name (SNI) and the
    Host header is unchanged, because httpcore starts TLS separately with the request's host.
    Without this, the check and the connection would each look the name up, and a hostile DNS
    server could answer "public" to the first and "10.0.0.5" to the second."""

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.NetworkStream:
        addresses = public_addresses(host, port)
        if not addresses:
            raise httpcore.ConnectError(f"blocked: {host} is not a public address")
        return super().connect_tcp(addresses[0], port, timeout, local_address, socket_options)


def public_client(**kwargs: Any) -> httpx.Client:
    """An httpx client that can only reach public addresses: checked on every request and
    redirect hop (`guard_request`), and connected to the address that was checked."""
    transport = httpx.HTTPTransport(retries=0)
    pool = transport._pool  # httpx has no public way to set the network backend
    if not hasattr(pool, "_network_backend"):
        raise RuntimeError("httpx/httpcore changed: cannot install PublicOnlyBackend")
    pool._network_backend = PublicOnlyBackend()
    hooks = kwargs.pop("event_hooks", {})
    hooks = {**hooks, "request": [guard_request, *hooks.get("request", [])]}
    return httpx.Client(transport=transport, event_hooks=hooks, **kwargs)


def decode_body(content: bytes, charset: str | None) -> str:
    """Bytes to text with the declared charset, or UTF-8 when the charset is missing or
    unknown to Python (live pages say "utf8mb4" or "x-user-defined")."""
    try:
        codecs.lookup(charset or "utf-8")
    except LookupError:
        charset = "utf-8"
    return content.decode(charset or "utf-8", errors="replace")


class Download(NamedTuple):
    status: int
    content: bytes
    content_type: str
    charset: str | None
    too_large: bool


def bounded_get(client: httpx.Client, url: str, max_bytes: int, deadline_s: float) -> Download:
    """GET with a size cap and an overall time limit. httpx timeouts are per read, so a server
    that sends a byte a second would otherwise never time out; `too_large` stops the download
    early instead of holding the whole body in memory."""
    started = time.monotonic()
    with client.stream("GET", url) as resp:
        size, chunks = 0, []
        for chunk in resp.iter_bytes():
            size += len(chunk)
            if size > max_bytes:
                return Download(
                    resp.status_code,
                    b"",
                    resp.headers.get("content-type", ""),
                    resp.charset_encoding,
                    True,
                )
            if time.monotonic() - started > deadline_s:
                raise httpx.ReadTimeout(
                    f"download took over {deadline_s:.0f}s", request=resp.request
                )
            chunks.append(chunk)
        return Download(
            resp.status_code,
            b"".join(chunks),
            resp.headers.get("content-type", ""),
            resp.charset_encoding,
            False,
        )


class TooLarge(ValueError):
    """Unpacked data would exceed its size cap."""


def gunzip_capped(data: bytes, max_bytes: int) -> bytes:
    """gzip.decompress with an output cap: a 190 KB file can unpack to 200 MB (a gzip bomb)."""
    unpacker = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        out = unpacker.decompress(data, max_bytes + 1)
    except zlib.error as exc:  # corrupt data: report it as bad input, like any other
        raise ValueError(f"not valid gzip: {exc}") from None
    if len(out) > max_bytes or unpacker.unconsumed_tail:
        raise TooLarge(f"unpacks to more than {max_bytes} bytes")
    return out
