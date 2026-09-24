"""Cheap, code-only page-type guess from URL, title and schema.org type (§5.4 step 2).

Returns "unknown" when rules are not confident; the Page Reader (small LLM) decides those.
"""

import re
from typing import Literal
from urllib.parse import urlparse

PageType = Literal[
    "listicle",
    "guide",
    "product",
    "category",
    "comparison",
    "tool",
    "forum",
    "video",
    "news",
    "pdf",
    "login",
    "unknown",
]
PAGE_TYPES: tuple[str, ...] = (
    "listicle",
    "guide",
    "product",
    "category",
    "comparison",
    "tool",
    "forum",
    "video",
    "news",
)

FORUM_DOMAINS = ("reddit.com", "quora.com", "stackexchange.com", "stackoverflow.com")
VIDEO_DOMAINS = ("youtube.com", "youtu.be", "vimeo.com", "tiktok.com")
NEWS_DOMAINS = ("techcrunch.com", "theverge.com", "reuters.com", "bbc.co.uk", "cnn.com")

SCHEMA_TYPES: dict[str, str] = {
    "product": "product",
    "softwareapplication": "product",
    "service": "product",
    "howto": "guide",
    "article": "guide",
    "blogposting": "guide",
    "techarticle": "guide",
    "newsarticle": "news",
    "itemlist": "listicle",
    "videoobject": "video",
    "qapage": "forum",
    "discussionforumposting": "forum",
    "collectionpage": "category",
    "webapplication": "tool",
}

LISTICLE = re.compile(
    r"\b(best|top)[- ]\d*|\b\d+[- ](best|top|ways|tools|apps|tips|examples)\b", re.I
)
COMPARISON = re.compile(r"\bvs\.?\b|-vs-|/vs/|\balternatives?\b|\bcompar", re.I)
GUIDE = re.compile(r"how[- ]to|\bguide\b|what[- ]is|tutorial|\bexplained\b", re.I)
TOOL = re.compile(r"calculator|generator|checker|converter|\btemplate\b|free[- ]tool", re.I)
LOGIN = re.compile(r"/(login|signin|sign-in|signup|sign-up|register|auth)\b", re.I)
PRODUCT_PATH = re.compile(r"^/?$|^/(pricing|product|products|features|solutions|platform)\b", re.I)
CATEGORY_PATH = re.compile(r"/(category|categories|directory|collections?|tag)/", re.I)
FORUM_PATH = re.compile(r"/(forum|forums|community|discussions?|threads?)/|/t/", re.I)


def _domain_matches(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def guess_page_type(url: str, title: str = "", schema_type: str = "") -> str:
    """Guess a page type; "unknown" means ask the Page Reader."""
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path
    text = f"{path} {title}"

    if path.lower().endswith(".pdf"):
        return "pdf"
    if LOGIN.search(path):
        return "login"
    if _domain_matches(host, VIDEO_DOMAINS):
        return "video"
    if _domain_matches(host, FORUM_DOMAINS) or FORUM_PATH.search(path):
        return "forum"
    if schema_type and (mapped := SCHEMA_TYPES.get(schema_type.lower())):
        return mapped
    if COMPARISON.search(text):
        return "comparison"
    if LISTICLE.search(text):
        return "listicle"
    if TOOL.search(text):
        return "tool"
    if GUIDE.search(text):
        return "guide"
    if _domain_matches(host, NEWS_DOMAINS) or "/news/" in path:
        return "news"
    if CATEGORY_PATH.search(path):
        return "category"
    if PRODUCT_PATH.search(path):
        return "product"
    return "unknown"


def domain_of(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")
