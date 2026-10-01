"""Shared fake world for the Keyword Gap tests (and exercise ex20_keyword_gap_offline):
three sites, what the LLM says about their pages, Bing numbers and Google results."""

import re

from fakes import FakeAutocomplete, FakeKeywords, FakeLLM, FakeSearch
from seo_engine.gap_pipeline import GapDeps, GapRun
from seo_engine.providers.sitemap import SitePage, SiteSample
from seo_engine.providers.tranco import DictRanks


def site(domain: str, *paths: str) -> SiteSample:
    pages = [
        SitePage(url=f"https://{domain}{p}", status="ok", title=f"{p} | {domain}", headings=[p])
        for p in paths
    ]
    return SiteSample(domain=domain, origin=f"https://{domain}", pages=pages)


def llm_for(answers: dict[str, dict], fit: dict[str, int] | Exception | None = None) -> FakeLLM:
    """Per-site phrases (read from the SITE: line), and business fit per keyword (default 3;
    a keyword missing from `fit` with value -1 is left out of the answer)."""

    def phrases(system: str, user: str) -> dict:
        domain = re.search(r"^SITE: (\S+)", user, re.M).group(1)
        answer = answers[domain]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def scores(system: str, user: str) -> dict:
        if isinstance(fit, Exception):
            raise fit
        listing = user.split("KEYWORDS:\n", 1)[1].splitlines()
        out = []
        for line in listing:
            n, kw = line.split(". ", 1)
            value = (fit or {}).get(kw, 3)
            if value >= 0:
                out.append({"id": int(n), "fit": value})
        return {"scores": out}

    return FakeLLM({"SitePhrases": phrases, "FitScores": scores})


def page(n: int, keyword: str, *alternatives: str) -> dict:
    return {"page": n, "keyword": keyword, "alternatives": list(alternatives)}


SITES = [
    site("ours.com", "/", "/portal", "/pricing"),
    site("moxo.com", "/", "/portal", "/approvals"),
    site("rival.io", "/", "/crm"),
]
ANSWERS = {
    "ours.com": {
        "brand_names": ["Ours"],
        "pages": [
            page(1, "client workspace software"),
            page(2, "client portal software", "secure client portal"),
            page(3, "ours pricing"),
        ],
    },
    "moxo.com": {
        "brand_names": ["Moxo", "Moxo Flow"],
        "pages": [
            page(1, "client onboarding software"),
            page(2, "software for client portals"),  # a variant of ours
            page(3, "approval workflow software", "moxo approvals"),
        ],
    },
    "rival.io": {
        "brand_names": ["Rival"],
        "pages": [page(1, "agency crm"), page(2, "crm for agencies", "rival crm login")],
    },
}
VOLUMES = {
    "client workspace software": (40, None),
    "client portal software": (900, None),
    "secure client portal": (5, None),
    "client onboarding software": (300, None),
    "approval workflow software": (120, None),
    "agency crm": (210, None),
    "crm for agencies": (0, None),
}


SERPS = {
    "client portal software": [
        ("https://moxo.com/portal", "product"),
        ("https://g2.com/x", "listicle"),
        ("https://rival.io/portal", "product"),
    ],
    "client onboarding software": [("https://moxo.com/onboarding", "product")],
    "agency crm": [("https://ours.com/crm", "product"), ("https://rival.io/crm", "product")],
}


class FakeReader:
    def __init__(self, sites: list[SiteSample]) -> None:
        self.sites = {s.domain: s for s in sites}
        self.asked: list[str] = []  # the addresses the pipeline asked for, as given

    def read(self, site: str) -> SiteSample:
        self.asked.append(site)
        domain = site.removeprefix("https://").removeprefix("www.").split("/")[0]
        return self.sites.get(domain) or SiteSample(domain=domain, origin=f"https://{domain}")


def deps(sites=SITES, search=None, answers=ANSWERS, auto=()) -> GapDeps:
    return GapDeps(
        reader=FakeReader(sites),
        llm=llm_for(answers),
        keywords=FakeKeywords(VOLUMES),
        autocomplete=FakeAutocomplete(set(auto)),
        search=search or FakeSearch(SERPS),
        ranks=DictRanks({}),
        has_bing=True,
        credits_used=lambda: 7,
    )


def gap_run(**over) -> GapRun:
    return GapRun(site="ours.com", competitors=["moxo.com", "rival.io"], **over)
