"""Live smoke test for every provider (PLAN.md phase 0).

Free mode (default) costs only a fraction of a cent of DeepSeek tokens. Results are cached
for the day, so a second run costs nothing and spends no Serper credits.

    python scripts/check_live.py                  # all free-mode checks
    python scripts/check_live.py serper tranco    # just some:
        serper | grounding | autocomplete | bing | tranco | llm | embed | fetch
        dataforseo (optional paid mode)
"""

import sys

from pydantic import BaseModel

from seo_engine.config import Settings
from seo_engine.difficulty import computed_difficulty
from seo_engine.models import Run
from seo_engine.providers.autocomplete import GoogleAutocomplete
from seo_engine.providers.base import DailyCache
from seo_engine.providers.bing import BingKeywords
from seo_engine.providers.embeddings import GeminiEmbeddings, cosine
from seo_engine.providers.fetcher import HttpFetcher
from seo_engine.providers.gemini_search import GeminiGroundedSearch
from seo_engine.providers.llm import DeepSeekLLM
from seo_engine.providers.search import DataForSEOSearch, SerpResults
from seo_engine.providers.serper import SerperSearch
from seo_engine.providers.tranco import TrancoRanks

PHRASE = "client project workspace"
FREE_CHECKS = ["serper", "grounding", "autocomplete", "bing", "tranco", "llm", "embed", "fetch"]


class Echo(BaseModel):
    topics: list[str]


def show_serp(serp: SerpResults) -> None:
    for item in serp.items:
        print(f"  #{item.rank:<2} {item.page_type:<10} {item.url}")
    print(f"  features: {serp.features}\n  PAA: {serp.people_also_ask[:3]}")
    print(f"  related: {serp.related_searches[:5]}")


def check(name: str, run: Run) -> None:
    s = run.settings
    cache = DailyCache(s.cache_dir)
    if name == "serper":
        serp = SerperSearch.from_env(cache).top(PHRASE, s.country, 10)
        show_serp(serp)
        d = computed_difficulty(serp, TrancoRanks(s.cache_dir), s.thresholds)
        print(f"  computed difficulty: {d.score} (small sites in top 10: {d.small_sites})")
    elif name == "grounding":
        show_serp(
            GeminiGroundedSearch.from_env(s.models, cache, run.add_cost).top(PHRASE, s.country, 10)
        )
    elif name == "autocomplete":
        ac = GoogleAutocomplete(cache)
        print(f"  suggest: {ac.suggest('client portal', s.country)[:6]}")
        print(f"  '{PHRASE}' searched: {ac.is_searched(PHRASE, s.country)}")
        print(f"  questions: {ac.variants('client portal', s.country, ['what is'], ['vs'])[:6]}")
    elif name == "bing":
        bing = BingKeywords.from_env(cache, GoogleAutocomplete(cache))
        if not bing.api_key:
            raise RuntimeError("BING_WEBMASTER_API_KEY is not set in .env")
        for m in bing.metrics([PHRASE, "client portal", "client portal software"], s.country):
            print(f"  {m.keyword:<28} {m.volume} Bing impressions/mo")
        related = bing.suggestions("client portal", s.country)[:5]
        print(f"  related: {[(r.keyword, r.volume) for r in related]}")
    elif name == "tranco":
        ranks = TrancoRanks(s.cache_dir)
        for d in ["hubspot.com", "blog.hubspot.com", "gurzu.com", "emitii.com"]:
            print(f"  {d:<20} rank {ranks.rank(d)}")
    elif name == "llm":
        llm = DeepSeekLLM.from_env(s.models, run.add_cost)
        out = llm.structured(
            "List 3 subtopics of the text.", "Share files and approvals with clients.", Echo
        )
        print(f"  {out.topics}")
    elif name == "embed":
        emb = GeminiEmbeddings.from_env(s.models, cache, run.add_cost)
        a, b, c = emb.embed(["client portal", "customer portal software", "banana bread recipe"])
        print(f"  dims={len(a)} sim(related)={cosine(a, b):.3f} sim(unrelated)={cosine(a, c):.3f}")
    elif name == "fetch":
        page = HttpFetcher(s).fetch("https://www.moxo.com/blog/what-is-a-client-portal")
        words, heads = page.word_count, len(page.headings)
        print(f"  {page.status} via {page.method}: {words} words, {heads} headings")
    elif name == "dataforseo":
        show_serp(DataForSEOSearch.from_env(s, run.add_cost).top(PHRASE, s.country, 10))
    else:
        raise SystemExit(f"unknown check {name!r}")


def main() -> None:
    names = sys.argv[1:] or FREE_CHECKS
    run = Run(page_text="", settings=Settings())
    failed = False
    for name in names:
        print(f"[{name}]")
        try:
            check(name, run)
        except Exception as exc:  # report every provider, not just the first failure
            failed = True
            print(f"  FAILED: {type(exc).__name__}: {exc}")
    print(f"\ncost this run: ${run.cost_usd:.4f}")
    for c in run.costs:
        print(f"  {c.label:<36} ${c.usd:.5f}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
