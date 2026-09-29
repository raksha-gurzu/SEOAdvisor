"""Raw answers for the Site Snapshot technical checks (docs/SITE-SNAPSHOT-PLAN.md, Step 2).

The page fetcher returns cleaned text; the checks need what it throws away: every redirect hop
with its status code, the final address, the `X-Robots-Tag` and `Link` headers, and the raw
homepage HTML. This provider gets exactly that and nothing more:

- the four addresses people type (http/https x with/without www), without their bodies;
- robots.txt of the host the site settles on (the first 500 KiB, as Google reads it);
- the homepage HTML, only when robots.txt lets us read it, under the same rules as the page
  fetcher (`fetcher.robots_body`: an unreachable or refused robots.txt means "do not read").

Every request goes through `public_client` (public addresses only, each redirect hop checked).
"""

import time
from urllib.parse import urlparse

import httpx
from protego import Protego
from pydantic import BaseModel

from seo_engine.concurrency import pmap
from seo_engine.config import Settings
from seo_engine.providers.base import BlockedAddress, decode_body, public_client
from seo_engine.providers.fetcher import ROBOTS_MAX_BYTES, robots_body


class Hop(BaseModel):
    url: str
    status: int


class Probe(BaseModel):
    url: str  # as requested
    status: int | None = None  # final status; None when no answer came back
    final_url: str = ""
    hops: list[Hop] = []  # the redirects before the final answer, in order
    x_robots_tags: list[str] = []  # one item per X-Robots-Tag header (a crawler name is per header)
    link_header: str = ""
    body: str = ""  # only when asked for
    too_large: bool = False  # over the cap: the body is empty, or its start when keep_start
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.status == 200 and not self.error


class SiteProbe(BaseModel):
    domain: str
    variants: list[Probe]  # https://d, https://www.d, http://d, http://www.d
    home: str = ""  # the address the site settles on, "" when none answered 200
    robots: Probe | None = None
    homepage: Probe | None = None
    robots_blocks_us: bool = False  # the homepage body was not read, by the site's request


def variant_urls(domain: str) -> list[str]:
    return [
        f"https://{domain}/",
        f"https://www.{domain}/",
        f"http://{domain}/",
        f"http://www.{domain}/",
    ]


def home_of(variants: list[Probe]) -> str:
    """The first address that ends in a 200, https first."""
    return next((p.final_url for p in variants if p.ok), "")


def origin(url: str) -> str:
    parts = urlparse(url)
    return f"{parts.scheme}://{parts.netloc}"


class SiteProber:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.http = client or public_client(
            follow_redirects=True,
            max_redirects=10,
            timeout=settings.fetch_timeout_s,
            headers={"User-Agent": settings.user_agent, "Accept-Language": "en"},
        )

    def probe(
        self, url: str, body: bool = False, max_bytes: int | None = None, keep_start: bool = False
    ) -> Probe:
        cap = max_bytes or self.settings.max_page_bytes
        started = time.monotonic()
        try:
            with self.http.stream("GET", url) as resp:
                hops = [Hop(url=str(r.url), status=r.status_code) for r in resp.history]
                content, too_large = b"", False
                if body:
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in resp.iter_bytes():
                        size += len(chunk)
                        if size > cap:
                            too_large = True
                            if keep_start:
                                chunks.append(chunk[: len(chunk) - (size - cap)])
                            break
                        if time.monotonic() - started > self.settings.fetch_deadline_s:
                            raise httpx.ReadTimeout("download too slow", request=resp.request)
                        chunks.append(chunk)
                    content = b"" if too_large and not keep_start else b"".join(chunks)
                return Probe(
                    url=url,
                    status=resp.status_code,
                    final_url=str(resp.url),
                    hops=hops,
                    x_robots_tags=resp.headers.get_list("x-robots-tag"),
                    link_header=", ".join(resp.headers.get_list("link")),
                    body=decode_body(content, resp.charset_encoding) if content else "",
                    too_large=too_large,
                )
        except BlockedAddress:
            return Probe(url=url, error="not a public address")
        except httpx.TooManyRedirects:
            return Probe(url=url, error="too many redirects")
        except httpx.HTTPError as exc:
            reason = "not a public address" if "not a public address" in str(exc) else ""
            return Probe(url=url, error=reason or type(exc).__name__)

    def probe_site(self, domain: str) -> SiteProbe:
        domain = domain.strip().lower().removeprefix("www.").rstrip(".")
        variants = pmap(self.probe, variant_urls(domain), 4)
        home = home_of(variants)
        if not home:
            return SiteProbe(domain=domain, variants=variants)
        robots = self.probe(
            origin(home) + "/robots.txt", body=True, max_bytes=ROBOTS_MAX_BYTES, keep_start=True
        )
        answered = None if robots.error else robots.status
        rules, _ = robots_body(answered, robots.body, robots.too_large)
        blocked = not Protego.parse(rules).can_fetch(home, self.settings.robots_token)
        homepage = None if blocked else self.probe(home, body=True)
        return SiteProbe(
            domain=domain,
            variants=variants,
            home=home,
            robots=robots,
            homepage=homepage,
            robots_blocks_us=blocked,
        )
