"""Two dates for a domain (keyless; plan F10, F11, F15).

- "Registered": the RDAP `registration` event, from the registry the IANA bootstrap file
  names for the TLD. It is the start of the CURRENT registration. Some TLDs (.io, .co, .np,
  .de, .us on 29 Sep 2026) are not in the bootstrap file: the date is then unknown.
- "First seen online": the oldest Wayback Machine capture of the homepage. It can be older
  than the registration (a previous owner of the name: emitii.com 2015 vs 2023).

The two are different facts, so both are kept and labelled; neither is called "site age".
Registry URLs come from a file on the internet, so every request goes through
`public_client` (the public-address guard).
"""

from datetime import date, datetime
from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from seo_engine.concurrency import pmap
from seo_engine.providers.base import DailyCache, public_client
from seo_engine.providers.tranco import candidates

RDAP_BOOTSTRAP_URL = "https://data.iana.org/rdap/dns.json"
WAYBACK_CDX_URL = "https://web.archive.org/cdx/search/cdx"
RDAP_MAX_TRIES = 3  # blog.shop.example.com -> itself, shop.example.com, example.com


class DomainDates(BaseModel):
    domain: str
    registered: date | None = None
    registered_via: str = ""  # the RDAP server that answered
    registered_domain: str = ""  # the name registered: blog.x.com has no record of its own
    first_seen: date | None = None
    first_seen_url: str = ""  # the Wayback capture's original URL
    notes: list[str] = []


class DomainDatesProvider(Protocol):
    def dates(self, domain: str) -> DomainDates: ...


def rdap_servers(bootstrap: dict[str, Any]) -> dict[str, str]:
    """TLD -> first RDAP base URL (RFC 9224), https only."""
    servers: dict[str, str] = {}
    for tlds, urls in (s[:2] for s in bootstrap.get("services") or [] if len(s) >= 2):
        https = [u for u in urls if u.startswith("https://")]
        for tld in tlds if https else []:
            servers.setdefault(tld.lower(), https[0].rstrip("/") + "/")
    return servers


def registration_date(body: dict[str, Any]) -> date | None:
    for event in body.get("events") or []:
        if event.get("eventAction") == "registration":
            try:
                return datetime.fromisoformat(str(event["eventDate"]).replace("Z", "+00:00")).date()
            except (KeyError, ValueError):
                return None
    return None


def first_capture(rows: list[list[str]]) -> tuple[date, str] | None:
    """CDX JSON: a header row, then rows of (timestamp, original, statuscode)."""
    for row in rows[1:]:
        try:
            return datetime.strptime(row[0][:8], "%Y%m%d").date(), row[1]
        except (IndexError, ValueError):
            continue
    return None


class DomainAge:
    def __init__(
        self,
        cache: DailyCache,
        user_agent: str,
        client: httpx.Client | None = None,
        rdap_timeout_s: float = 20.0,
        wayback_timeout_s: float = 60.0,
    ) -> None:
        self.cache = cache
        self.http = client or public_client(follow_redirects=True, timeout=rdap_timeout_s)
        self.headers = {"User-Agent": user_agent}
        self.wayback_timeout_s = wayback_timeout_s

    def _bootstrap(self) -> dict[str, str]:
        cached = self.cache.get("rdap_bootstrap", RDAP_BOOTSTRAP_URL)
        if cached is None:
            resp = self.http.get(RDAP_BOOTSTRAP_URL, headers=self.headers)
            resp.raise_for_status()
            cached = rdap_servers(resp.json())
            self.cache.set("rdap_bootstrap", RDAP_BOOTSTRAP_URL, cached)
        return cached

    def registered(self, domain: str) -> tuple[date | None, str, str, str]:
        """(date, server, note, registered name). A missing TLD or domain is a note, never an
        exception."""
        cached = self.cache.get("rdap", domain)
        if cached is not None:
            day = date.fromisoformat(cached["date"]) if cached["date"] else None
            return day, cached["server"], cached["note"], cached.get("name", "")
        try:
            servers = self._bootstrap()
        except (httpx.HTTPError, ValueError) as exc:
            return None, "", f"registration date: RDAP list unavailable ({type(exc).__name__})", ""
        tld = domain.rsplit(".", 1)[-1]
        server = servers.get(tld, "")
        if not server:
            return None, "", f"registration date: .{tld} has no public RDAP service", ""
        day, note, found_name = None, "registration date: not found in RDAP", ""
        for name in candidates(domain)[:RDAP_MAX_TRIES]:
            try:
                resp = self.http.get(
                    f"{server}domain/{name}",
                    headers={**self.headers, "Accept": "application/rdap+json"},
                )
            except httpx.HTTPError as exc:
                return None, server, f"registration date: RDAP failed ({type(exc).__name__})", ""
            if resp.status_code == 404:
                continue
            if resp.status_code != 200:
                return None, server, f"registration date: RDAP HTTP {resp.status_code}", ""
            try:
                day = registration_date(resp.json())
            except ValueError:
                return None, server, "registration date: RDAP answer was not JSON", ""
            note = "" if day else "registration date: RDAP has no registration event"
            found_name = name
            break
        self.cache.set(
            "rdap",
            domain,
            {
                "date": day.isoformat() if day else None,
                "server": server,
                "note": note,
                "name": found_name,
            },
        )
        return day, server, note, found_name

    def first_seen(self, domain: str) -> tuple[date | None, str, str]:
        """(date, captured URL, note). The oldest homepage capture; www is the same site."""
        cached = self.cache.get("wayback_first", domain)
        if cached is not None:
            day = date.fromisoformat(cached["date"]) if cached["date"] else None
            return day, cached["url"], cached["note"]
        try:
            resp = self.http.get(
                WAYBACK_CDX_URL,
                params={
                    "url": domain,
                    "limit": 1,
                    "output": "json",
                    "fl": "timestamp,original,statuscode",
                },
                headers=self.headers,
                timeout=self.wayback_timeout_s,
            )
            resp.raise_for_status()
            rows = resp.json() if resp.content.strip() else []
        except (httpx.HTTPError, ValueError) as exc:  # Wayback limits bulk traffic (F11)
            return None, "", f"first seen online: Wayback unavailable ({type(exc).__name__})"
        found = first_capture(rows)
        day, url = found if found else (None, "")
        note = "" if found else "first seen online: no Wayback capture"
        self.cache.set(
            "wayback_first",
            domain,
            {"date": day.isoformat() if day else None, "url": url, "note": note},
        )
        return day, url, note

    def dates(self, domain: str) -> DomainDates:
        domain = domain.strip().lower().removeprefix("www.").rstrip(".")
        (reg, server, reg_note, reg_name), (seen, url, seen_note) = pmap(
            lambda f: f(domain), [self.registered, self.first_seen], 2
        )
        return DomainDates(
            domain=domain,
            registered=reg,
            registered_via=server,
            registered_domain=reg_name,
            first_seen=seen,
            first_seen_url=url,
            notes=[n for n in (reg_note, seen_note) if n],
        )
