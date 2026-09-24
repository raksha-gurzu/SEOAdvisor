from seo_engine.providers.search import SerpItem, SerpResults
from seo_engine.tools.serp_top import intent_verdict, serp_top


class FakeSearch:
    def __init__(self, types: list[str]) -> None:
        self.types = types

    def top(self, phrase: str, country: str, n: int) -> SerpResults:
        items = [
            SerpItem(rank=i + 1, url=f"https://s{i}.com/", domain=f"s{i}.com", page_type=t)
            for i, t in enumerate(self.types[:n])
        ]
        return SerpResults(phrase=phrase, country=country, items=items)


def test_clear_intent_flags_different_type() -> None:
    v = intent_verdict(["listicle"] * 7 + ["product"] * 3, "product")
    assert v.verdict == "clear" and v.dominant == "listicle" and v.dominant_share == 0.7
    assert v.flag and "70%" in v.flag


def test_mixed_intent_no_flag() -> None:
    v = intent_verdict(["listicle"] * 4 + ["product"] * 3 + ["guide"] * 3, "product")
    assert v.verdict == "mixed" and v.flag is None


def test_our_type_absent_is_strong_flag() -> None:
    v = intent_verdict(["guide"] * 5 + ["listicle"] * 5, "product")
    assert v.flag and v.flag.startswith("Strong mismatch")


def test_unknowns_ignored() -> None:
    v = intent_verdict(["unknown"] * 8 + ["product"] * 2, "product")
    assert v.dominant == "product" and v.dominant_share == 1.0 and v.flag is None


def test_serp_top_uses_top_10_only() -> None:
    result = serp_top(FakeSearch(["product"] * 10 + ["listicle"] * 10), "x", "US", 20, "product")
    assert len(result.serp.items) == 20
    assert result.intent.mix == {"product": 10} and result.intent.flag is None
