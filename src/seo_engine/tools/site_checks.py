"""Technical basics for Site Snapshot (docs/SITE-SNAPSHOT-PLAN.md, Step 2). Plain code.

Each check has one of four results: pass, warn, fail, or unknown (we could not see it). The
rules follow Google Search Central (sources in the plan, section 9):
- permanent redirects are 301 and 308; 302, 303 and 307 are temporary;
- `noindex` works as a robots `<meta>` tag or an `X-Robots-Tag` header, and Google never sees
  it when robots.txt blocks the page;
- `rel="canonical"` is a strong signal, and Google recommends it on the canonical page itself;
- Google writes the snippet mostly from the page; the meta description is used when it fits;
- robots.txt: Google reads the first 500 KiB; a 4xx other than 429 means "no rules", while a
  5xx or 429 makes Google stop crawling for a while.
"""

import re
from typing import Literal
from urllib.parse import urljoin, urlparse

from lxml import etree
from lxml import html as lxml_html
from protego import Protego
from pydantic import BaseModel

from seo_engine.config import Thresholds
from seo_engine.providers.site_probe import SiteProbe
from seo_engine.providers.sitemap import SiteSample
from seo_engine.tools.snippet_check import snippet_check

CheckStatus = Literal["pass", "warn", "fail", "unknown"]
PERMANENT = {301, 308}
GOOGLEBOT = "Googlebot"


class Check(BaseModel):
    key: str
    label: str
    status: CheckStatus
    detail: str


class HomeTags(BaseModel):
    title: str | None = None
    description: str | None = None
    robots: list[str] = []  # content of <meta name="robots"> and <meta name="googlebot">
    canonical: str | None = None  # absolute URL


class SiteChecks(BaseModel):
    home: str
    checks: list[Check]

    def count(self, status: CheckStatus) -> int:
        return sum(1 for c in self.checks if c.status == status)


def same_page(a: str, b: str) -> bool:
    """https://Site.com and https://site.com/ are the same page; the query string counts."""
    pa, pb = urlparse(a), urlparse(b)
    return (
        pa.scheme.lower() == pb.scheme.lower()
        and (pa.hostname or "").lower() == (pb.hostname or "").lower()
        and (pa.path or "/").rstrip("/") == (pb.path or "/").rstrip("/")
        and pa.query == pb.query
    )


def canonical_from_link_header(link: str, base: str) -> str | None:
    """`<https://x.com/>; rel="canonical"` in an HTTP Link header."""
    for part in link.split(","):
        m = re.match(r"\s*<([^>]+)>\s*;(.*)", part)
        if m and re.search(r'rel\s*=\s*"?[^";]*\bcanonical\b', m.group(2), re.I):
            return urljoin(base, m.group(1).strip())
    return None


XML_DECLARATION = re.compile(r"^\s*<\?xml[^>]*\?>", re.I)


def read_tags(html: str, base: str) -> HomeTags | None:
    """None when the page cannot be parsed (the checks then say "unknown", never pass or fail).
    lxml refuses a str that starts with an XML declaration (XHTML pages), so it is removed."""
    try:
        tree = lxml_html.fromstring(XML_DECLARATION.sub("", html, count=1))
    except (etree.ParserError, ValueError):
        return None
    title = tree.findtext(".//title")
    tags = HomeTags(title=" ".join(title.split()) if title is not None else None)
    for meta in tree.iter("meta"):
        name = (meta.get("name") or "").strip().lower()
        content = meta.get("content")
        if name == "description" and tags.description is None and content is not None:
            tags.description = " ".join(content.split())
        elif name in ("robots", GOOGLEBOT.lower()) and content:
            tags.robots.append(content.lower())
    for link in tree.iter("link"):
        rels = (link.get("rel") or "").lower().split()
        if "canonical" in rels and link.get("href") and tags.canonical is None:
            tags.canonical = urljoin(base, link.get("href").strip())
    return tags


# Robots rules that take a value ("max-snippet: 50"); any other "name:" names a crawler.
VALUE_RULES = {"max-snippet", "max-image-preview", "max-video-preview", "unavailable_after"}


def says_noindex(values: list[str], header: bool = False) -> bool:
    """`noindex` or `none` for all crawlers or for Googlebot. In an X-Robots-Tag header a rule
    can name a crawler first ("googlebot: noindex"); the rules after it, in the same header,
    apply to that crawler. Each header (each item of `values`) starts again for all crawlers."""
    for value in values:
        agent = ""
        for part in value.lower().split(","):
            part = part.strip()
            if header and ":" in part:
                name, rest = (x.strip() for x in part.split(":", 1))
                if name in VALUE_RULES:
                    continue  # a rule with a value, not a crawler name
                agent, part = name, rest
            if part in ("noindex", "none") and agent in ("", GOOGLEBOT.lower()):
                return True
    return False


def check_https(probe: SiteProbe) -> Check:
    label = "Secure connection (HTTPS)"
    if not probe.home:
        answered = [p for p in probe.variants if p.status is not None]
        detail = (
            f"No address showed a page (HTTP {', '.join(str(p.status) for p in answered)}). "
            "The site may block automated visits."
            if answered
            else "No address of the site answered."
        )
        return Check(key="https", label=label, status="unknown", detail=detail)
    if probe.home.startswith("https://"):
        return Check(
            key="https", label=label, status="pass", detail=f"The site settles on {probe.home}."
        )
    return Check(
        key="https",
        label=label,
        status="fail",
        detail=f"The site settles on {probe.home}, without HTTPS.",
    )


def check_http_redirect(probe: SiteProbe) -> Check:
    """Judged by where http:// ends, whatever the final status (a bot wall can answer 403)."""
    label = "http:// goes to https://"
    plain = probe.variants[2]  # http://domain/
    if plain.error or plain.status is None or not plain.final_url:
        why = plain.error or "no answer"
        return Check(
            key="http_redirect",
            label=label,
            status="unknown",
            detail=f"http://{probe.domain} did not answer ({why}).",
        )
    status = "" if plain.status == 200 else f" (it answered HTTP {plain.status})"
    if plain.final_url.startswith("https://"):
        return Check(
            key="http_redirect",
            label=label,
            status="pass",
            detail=f"http://{probe.domain} redirects to {plain.final_url}{status}.",
        )
    return Check(
        key="http_redirect",
        label=label,
        status="fail",
        detail=f"http://{probe.domain} stays on {plain.final_url} (HTTP {plain.status}).",
    )


def check_one_address(probe: SiteProbe) -> Check:
    label = "One address for the site"
    reached = [p for p in probe.variants if p.ok]
    finals = list(dict.fromkeys(p.final_url for p in reached))
    if not reached:
        return Check(
            key="one_address", label=label, status="unknown", detail="No address answered."
        )
    distinct = [f for i, f in enumerate(finals) if not any(same_page(f, g) for g in finals[:i])]
    if len(distinct) > 1:
        return Check(
            key="one_address",
            label=label,
            status="warn",
            detail="These addresses show the site without redirecting to one another: "
            + ", ".join(distinct)
            + ". Google may treat them as duplicates.",
        )
    missing = [p.url for p in probe.variants if not p.ok]
    extra = f" ({len(missing)} of 4 addresses did not answer.)" if missing else ""
    return Check(
        key="one_address",
        label=label,
        status="pass",
        detail=f"All working addresses lead to {distinct[0]}.{extra}",
    )


def check_permanent_redirects(probe: SiteProbe) -> Check:
    label = "Redirects are permanent"
    temporary = [
        f"{hop.url} (HTTP {hop.status})"
        for p in probe.variants
        if p.ok
        for hop in p.hops
        if hop.status not in PERMANENT
    ]
    if temporary:
        return Check(
            key="permanent_redirects",
            label=label,
            status="warn",
            detail="Temporary redirects: "
            + ", ".join(dict.fromkeys(temporary))
            + ". Google recommends 301 or 308 for a permanent move.",
        )
    if not any(p.hops for p in probe.variants if p.ok):
        return Check(
            key="permanent_redirects", label=label, status="pass", detail="No redirects are needed."
        )
    return Check(
        key="permanent_redirects",
        label=label,
        status="pass",
        detail="All redirects use 301 or 308.",
    )


def check_robots(probe: SiteProbe) -> Check:
    label = "robots.txt lets Google in"
    r = probe.robots
    if r is None or not probe.home:
        return Check(key="robots", label=label, status="unknown", detail="The site did not answer.")
    if r.error or r.status is None or r.status >= 500 or r.status == 429:
        why = r.error or f"HTTP {r.status}"
        return Check(
            key="robots",
            label=label,
            status="warn",
            detail=f"robots.txt could not be read ({why}). Google stops crawling until it can.",
        )
    if r.status >= 400:
        detail = (
            "No robots.txt: every page may be crawled."
            if r.status in (404, 410)
            else f"robots.txt answered HTTP {r.status}; Google treats that as no rules."
        )
        return Check(key="robots", label=label, status="pass", detail=detail)
    if not Protego.parse(r.body).can_fetch(probe.home, GOOGLEBOT):
        return Check(
            key="robots",
            label=label,
            status="fail",
            detail="robots.txt blocks Googlebot from the homepage.",
        )
    extra = " (Google reads only the first 500 KiB of the file.)" if r.too_large else ""
    return Check(
        key="robots", label=label, status="pass", detail=f"Googlebot may crawl the homepage.{extra}"
    )


def check_sitemap(sample: SiteSample | None) -> Check:
    label = "Sitemap"
    if sample is None or (sample.source == "none" and not sample.sitemaps):
        return Check(
            key="sitemap", label=label, status="unknown", detail="The site could not be read."
        )
    files = len(sample.sitemaps)
    if files and sample.sitemap_urls:
        plural = "s" if files != 1 else ""
        return Check(
            key="sitemap",
            label=label,
            status="pass",
            detail=f"{sample.sitemap_urls} page addresses listed in {files} sitemap file{plural}.",
        )
    if files:
        return Check(
            key="sitemap",
            label=label,
            status="warn",
            detail="The sitemap lists no pages of this site.",
        )
    return Check(
        key="sitemap",
        label=label,
        status="warn",
        detail="No sitemap found. A sitemap helps Google find every page.",
    )


def homepage_checks(probe: SiteProbe, t: Thresholds) -> list[Check]:
    labels = {
        "indexable": "Homepage can be indexed",
        "title": "Homepage title",
        "description": "Homepage description",
        "canonical": "Canonical tag",
    }
    page = probe.homepage
    if page is None or not page.ok or not page.body:
        why = (
            "robots.txt asks crawlers like ours not to read the homepage"
            if probe.robots_blocks_us
            else "the page was too large"
            if page is not None and page.too_large
            else "the homepage could not be read"
        )
        return [
            Check(key=k, label=v, status="unknown", detail=why[0].upper() + why[1:] + ".")
            for k, v in labels.items()
        ]
    tags = read_tags(page.body, page.final_url)
    if tags is None:
        return [
            Check(key=k, label=v, status="unknown", detail="The homepage HTML could not be read.")
            for k, v in labels.items()
        ]
    checks: list[Check] = []

    header_noindex = says_noindex(page.x_robots_tags, header=True)
    if header_noindex or says_noindex(tags.robots):
        where = "an X-Robots-Tag header" if header_noindex else "a robots meta tag"
        checks.append(
            Check(
                key="indexable",
                label=labels["indexable"],
                status="fail",
                detail=f"The homepage says noindex in {where}: Google drops it from search.",
            )
        )
    else:
        checks.append(
            Check(
                key="indexable", label=labels["indexable"], status="pass", detail="No noindex rule."
            )
        )

    if not tags.title:
        checks.append(
            Check(
                key="title",
                label=labels["title"],
                status="fail",
                detail="The homepage has no title.",
            )
        )
        snip = None
    else:
        snip = snippet_check(tags.title, tags.description or "", thresholds=t)
        status = "pass" if snip.title_ok else "warn"
        why = next((r for r in snip.reasons if r.startswith("title")), "")
        checks.append(
            Check(
                key="title",
                label=labels["title"],
                status=status,
                detail=f"“{tags.title}” ({snip.title_chars} characters, {snip.title_px}px)"
                + (f": {why}." if why else "."),
            )
        )

    if not tags.description:
        checks.append(
            Check(
                key="description",
                label=labels["description"],
                status="warn",
                detail="No meta description. Google writes its own snippet from the page.",
            )
        )
    else:
        ok = t.description_min_chars <= len(tags.description) <= t.description_max_chars
        detail = f"{len(tags.description)} characters"
        if not ok:
            detail += f"; aim for {t.description_min_chars} to {t.description_max_chars}"
        checks.append(
            Check(
                key="description",
                label=labels["description"],
                status="pass" if ok else "warn",
                detail=detail + ".",
            )
        )

    canonical = tags.canonical or canonical_from_link_header(page.link_header, page.final_url)
    if canonical is None:
        checks.append(
            Check(
                key="canonical",
                label=labels["canonical"],
                status="warn",
                detail="No canonical tag. Google recommends one on the page itself.",
            )
        )
    elif same_page(canonical, page.final_url):
        checks.append(
            Check(
                key="canonical",
                label=labels["canonical"],
                status="pass",
                detail="Points to the homepage itself.",
            )
        )
    elif (urlparse(canonical).hostname or "").lower().removeprefix("www.") != probe.domain:
        checks.append(
            Check(
                key="canonical",
                label=labels["canonical"],
                status="warn",
                detail=f"Points to another site: {canonical}.",
            )
        )
    else:
        checks.append(
            Check(
                key="canonical",
                label=labels["canonical"],
                status="warn",
                detail=f"Points to {canonical}, not to the homepage address {page.final_url}.",
            )
        )
    return checks


def site_checks(
    probe: SiteProbe, sample: SiteSample | None, thresholds: Thresholds | None = None
) -> SiteChecks:
    t = thresholds or Thresholds()
    checks = [
        check_https(probe),
        check_http_redirect(probe),
        check_one_address(probe),
        check_permanent_redirects(probe),
        check_robots(probe),
        check_sitemap(sample),
        *homepage_checks(probe, t),
    ]
    return SiteChecks(home=probe.home, checks=checks)
