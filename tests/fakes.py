"""Offline stand-ins for providers. No test may hit a paid API."""

import hashlib
import math
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from seo_engine.providers.fetcher import FetchedPage
from seo_engine.providers.keywords import KeywordMetrics, RankedKeyword
from seo_engine.providers.search import SerpItem, SerpResults
from seo_engine.text import STOPWORDS, words

DIMS = 256


def _stem(w: str) -> str:
    return w[:-1] if w.endswith("s") and len(w) > 3 else w


class FakeEmbed:
    """Bag-of-stemmed-words hashing vectors: texts sharing content words are similar."""

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [self._vec(t) for t in texts]

    def _vec(self, text: str) -> list[float]:
        vec = [0.0] * DIMS
        for w in words(text):
            if w in STOPWORDS:
                continue
            h = int(hashlib.md5(_stem(w).encode()).hexdigest(), 16)
            vec[h % DIMS] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class FakeLLM:
    """Routes each structured call to a handler by schema name."""

    def __init__(self, handlers: dict[str, Callable[[str, str], Any]]) -> None:
        self.handlers = handlers
        self.calls: list[str] = []

    def structured(self, system: str, user: str, schema: type[BaseModel], tier: str = "bulk"):
        self.calls.append(schema.__name__)
        return schema.model_validate(self.handlers[schema.__name__](system, user))


class FakeSearch:
    def __init__(
        self, serps: dict[str, list[tuple[str, str]]], paa: dict[str, list[str]] | None = None
    ):
        self.serps = serps  # phrase -> [(url, page_type)]
        self.paa = paa or {}
        self.calls: list[str] = []

    def top(self, phrase: str, country: str, n: int) -> SerpResults:
        self.calls.append(phrase)
        items = [
            SerpItem(
                rank=i + 1, url=u, domain=u.split("/")[2].removeprefix("www."), title=u, page_type=t
            )
            for i, (u, t) in enumerate(self.serps.get(phrase, [])[:n])
        ]
        return SerpResults(
            phrase=phrase, country=country, items=items, people_also_ask=self.paa.get(phrase, [])
        )


class FakeKeywords:
    def __init__(
        self,
        data: dict[str, tuple[int, int | None]],
        autocomplete: dict[str, list[str]] | None = None,
        ranked: dict[str, list[str]] | None = None,
    ) -> None:
        self.data = data  # keyword -> (volume, difficulty)
        self.auto = autocomplete or {}
        self.ranked = ranked or {}
        self.metric_calls = 0

    def _m(self, k: str) -> KeywordMetrics:
        vol, kd = self.data.get(k, (0, None))
        return KeywordMetrics(keyword=k, volume=vol, difficulty=kd, intent="commercial")

    def metrics(self, keywords: list[str], country: str) -> list[KeywordMetrics]:
        self.metric_calls += 1
        return [self._m(" ".join(k.lower().split())) for k in keywords]

    def autocomplete(self, phrase: str, country: str) -> list[str]:
        return self.auto.get(phrase, [])

    def suggestions(self, phrase: str, country: str, limit: int = 50) -> list[KeywordMetrics]:
        return []

    def ranked_keywords(self, target: str, country: str, limit: int = 100) -> list[RankedKeyword]:
        return [
            RankedKeyword(**self._m(k).model_dump(), rank=5, url=target)
            for k in self.ranked.get(target, [])
        ]


class FakeFetcher:
    def __init__(self, pages: dict[str, FetchedPage]) -> None:
        self.pages = pages

    def fetch(self, url: str) -> FetchedPage:
        return self.pages.get(url) or FetchedPage(url=url, status="http_error", reason="404")


class FakeAutocomplete:
    """Stands in for GoogleAutocomplete: `searched` phrases autocomplete to themselves."""

    def __init__(self, searched: set[str], variants: list[str] | None = None) -> None:
        self.searched = searched
        self._variants = variants or []

    def suggest(self, phrase: str, country: str) -> list[str]:
        return [phrase] if phrase in self.searched else []

    def is_searched(self, phrase: str, country: str) -> bool:
        return phrase in self.searched

    def variants(self, seed: str, country: str, prefixes: list[str], suffixes: list[str]):
        return list(self._variants)


def fake_passage_labels(system: str, user: str) -> dict:
    """Stand-in for the per-page labelling call: a passage discusses a topic when it contains
    every content word of the topic (after dropping stopwords and a plural "s")."""
    topics_part, passages_part = user.split("\n\nPASSAGES:\n")
    topics = [line.split(". ", 1)[1] for line in topics_part.removeprefix("TOPICS:\n").splitlines()]
    passages = [block.split("] ", 1)[1] for block in passages_part.split("\n\n")]

    def content(text: str) -> set[str]:
        return {_stem(w) for w in words(text) if w not in STOPWORDS}

    labels = []
    for ti, topic in enumerate(topics, 1):
        need = content(topic)
        hits = [pi for pi, p in enumerate(passages, 1) if need and need <= content(p)]
        labels.append({"topic": ti, "passages": hits})
    return {"labels": labels}


def all_gaps_relevant(system: str, user: str) -> dict:
    """Stand-in for the gap relevance check: every question is relevant."""
    ids = [int(line.split(".", 1)[0]) for line in user.split("QUESTIONS:\n")[1].splitlines()]
    return {"answers": [{"id": i, "relevant": True} for i in ids]}
