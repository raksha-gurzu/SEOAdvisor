"""seo_serp_top: ranked Google results with page type, SERP features and intent mix (§5.4)."""

from collections import Counter

from pydantic import BaseModel

from seo_engine.config import Thresholds
from seo_engine.providers.search import SearchProvider, SerpResults

IGNORED_TYPES = {"unknown", "pdf", "login"}


class IntentVerdict(BaseModel):
    mix: dict[str, int]  # page type -> count in the top 10
    dominant: str | None
    dominant_share: float
    verdict: str  # "clear", "mixed" or "unclear"
    flag: str | None  # text for Brief.intent_flag; None when ours fits


class SerpTop(BaseModel):
    serp: SerpResults
    intent: IntentVerdict


def intent_verdict(
    page_types: list[str], our_type: str | None, thresholds: Thresholds | None = None
) -> IntentVerdict:
    """Read intent from the page types Google shows, not from the query words."""
    t = thresholds or Thresholds()
    known = [p for p in page_types if p not in IGNORED_TYPES]
    mix = dict(Counter(known).most_common())
    if not known:
        return IntentVerdict(
            mix={}, dominant=None, dominant_share=0.0, verdict="unclear", flag=None
        )
    dominant, count = next(iter(mix.items()))
    share = count / len(known)
    verdict = (
        "clear"
        if share >= t.intent_clear_share
        else "mixed"
        if share <= t.intent_mixed_share
        else "leaning"
    )

    flag: str | None = None
    if our_type and our_type not in IGNORED_TYPES:
        pct = f"{round(share * 100)}%"
        if our_type not in mix:
            flag = (
                f"Strong mismatch: no {our_type} pages rank in the top 10; Google shows "
                f"mostly {dominant} pages ({pct})."
            )
        elif verdict == "clear" and our_type != dominant:
            flag = (
                f"Intent mismatch: {pct} of the top 10 are {dominant} pages; ours is a "
                f"{our_type} page ({mix[our_type]} of {len(known)} results)."
            )
    return IntentVerdict(
        mix=mix, dominant=dominant, dominant_share=round(share, 2), verdict=verdict, flag=flag
    )


def serp_top(
    search: SearchProvider,
    phrase: str,
    country: str,
    n: int = 20,
    our_type: str | None = None,
    thresholds: Thresholds | None = None,
) -> SerpTop:
    serp = search.top(phrase, country, n)
    top10 = [item.page_type for item in serp.items[:10]]
    return SerpTop(serp=serp, intent=intent_verdict(top10, our_type, thresholds))
