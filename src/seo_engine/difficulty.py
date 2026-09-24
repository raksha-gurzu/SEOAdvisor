"""Free-mode keyword difficulty and intent, computed from the top 10 (docs/ARCHITECTURE.md §5.1).

One difficulty source per run (CLAUDE.md rule 7): this module, or DataForSEO, never both.
"""

from collections import Counter

from pydantic import BaseModel

from seo_engine.config import Thresholds
from seo_engine.providers.search import SerpItem, SerpResults
from seo_engine.providers.tranco import RankLookup

UGC_TYPES = {"forum", "video"}
INTENT_BY_TYPE = {
    "product": "commercial",
    "comparison": "commercial",
    "listicle": "commercial",
    "category": "commercial",
    "tool": "transactional",
    "guide": "informational",
    "news": "informational",
    "forum": "informational",
    "video": "informational",
}


class Difficulty(BaseModel):
    score: int  # 0 to 100
    strengths: list[float]  # per top-10 result
    small_sites: int  # results outside the ranking list


def site_strength(item: SerpItem, ranks: RankLookup, t: Thresholds) -> float:
    if item.page_type in UGC_TYPES:
        return t.ugc_strength
    rank = ranks.rank(item.domain or item.url.split("/")[2])
    if rank is None:
        return t.unlisted_strength
    return next((s for ceiling, s in t.tranco_strength if rank <= ceiling), t.unlisted_strength)


def computed_difficulty(serp: SerpResults, ranks: RankLookup, t: Thresholds) -> Difficulty:
    top = serp.items[:10]
    if not top:
        return Difficulty(score=0, strengths=[], small_sites=0)
    strengths = [site_strength(i, ranks, t) for i in top]
    small = sum(
        1
        for i in top
        if i.page_type not in UGC_TYPES and ranks.rank(i.domain or i.url.split("/")[2]) is None
    )
    return Difficulty(
        score=round(100 * sum(strengths) / len(strengths)), strengths=strengths, small_sites=small
    )


def intent_from_types(page_types: list[str]) -> str:
    """Intent read from the page types Google shows (§5.4), not the query words."""
    intents = Counter(INTENT_BY_TYPE[p] for p in page_types if p in INTENT_BY_TYPE)
    return intents.most_common(1)[0][0] if intents else "unknown"
