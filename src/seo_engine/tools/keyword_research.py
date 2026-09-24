"""seo_keyword_research: phrase discovery (docs/ARCHITECTURE.md §5.1).

A. gather candidates (LLM seeds, page phrases, related/borrowed keywords, autocomplete),
B. filter on demand and difficulty, C. cluster by shared top-10 URLs, D. rank clusters by
fit x demand x winnability. Code does every number; the LLM only proposes seeds and
confirms fit.

Free mode: demand = Bing impressions or Google autocomplete, difficulty computed from the
top 10 (difficulty.py). DataForSEO mode: DataForSEO volume and difficulty.
"""

import math
import re
from datetime import date

from pydantic import BaseModel, Field

from seo_engine.concurrency import pmap
from seo_engine.config import Settings
from seo_engine.deps import Deps
from seo_engine.difficulty import computed_difficulty, intent_from_types
from seo_engine.models import Phrase
from seo_engine.page_types import domain_of
from seo_engine.providers.embeddings import cosine, normalise
from seo_engine.providers.keywords import KeywordMetrics
from seo_engine.providers.keywords import normalise as norm_kw
from seo_engine.providers.search import SerpResults
from seo_engine.text import mmr, ngram_candidates, passages

SEED_SYSTEM = """You are an SEO researcher. Read the page and list the search phrases real buyers
would type into Google to find a page like this. Use buyer language, not the page's own slogans.
Mix intents: problem-aware, solution-aware, comparison and product phrases. 2 to 5 words each,
lowercase, no brand names of the page's own company."""

FIT_SYSTEM = """You judge search phrases for one page. For each phrase answer fits=true only if
someone searching it would be well served by this page: right topic, right kind of page, and the
same meaning. Answer fits=false when the phrase means something different from what the page
offers, even if the words overlap (for example "virtual assistant" meaning a hired person when the
page offers an AI feature, or a job title when the page sells software).
Answer for every phrase given, in the same order."""

QUESTION_START = re.compile(r"^(what|how|why|which|when|who|is|are|can|does|do|should)\b|\bvs\b")


class SeedPhrases(BaseModel):
    phrases: list[str] = Field(min_length=1)


class FitVerdict(BaseModel):
    phrase: str
    fits: bool


class FitVerdicts(BaseModel):
    verdicts: list[FitVerdict]


class Candidate(BaseModel):
    keyword: str
    sources: list[str]
    volume: int = 0
    in_autocomplete: bool | None = None  # free mode demand evidence
    difficulty: int | None = None
    intent: str = "unknown"
    fit: float = 0.0
    kept: bool = False
    reason: str = ""


class Cluster(BaseModel):
    head: str
    members: list[str]
    total_volume: int
    difficulty: int
    fit: float
    demand: float
    winnability: float
    score: float
    weak_spots: list[str] = []


class KeywordResearch(BaseModel):
    phrases: list[Phrase]
    clusters: list[Cluster]
    candidates: list[Candidate]
    questions: list[str] = []  # searcher questions seen in autocomplete (gap evidence)
    serps: dict[str, SerpResults] = {}  # reused by serp_top / competitor_analysis


def cut_words(text: str, n: int) -> str:
    return " ".join(text.split()[:n])


def url_key(url: str) -> str:
    """Normalise a URL for overlap checks: no scheme, www, query or trailing slash."""
    u = re.sub(r"^https?://(www\.)?", "", url.lower()).split("#")[0].split("?")[0]
    return u.rstrip("/")


def shared_urls(a: SerpResults, b: SerpResults, top_n: int = 10) -> int:
    return len(
        {url_key(i.url) for i in a.items[:top_n]} & {url_key(i.url) for i in b.items[:top_n]}
    )


def page_vector(deps: Deps, page_text: str, max_words: int) -> list[float]:
    """Mean of passage embeddings: a whole-page vector that fits embedding input limits."""
    chunks = passages(page_text, max_words) or [page_text]
    vecs = deps.embed.embed(chunks)
    return normalise([sum(col) / len(vecs) for col in zip(*vecs, strict=True)])


def page_phrases(
    deps: Deps, page_vec: list[float], page_text: str, settings: Settings
) -> list[str]:
    """KeyBERT-style: embed 2-4 word n-grams, pick relevant and diverse ones with MMR."""
    t = settings.thresholds
    cands = ngram_candidates(page_text)
    if not cands:
        return []
    vecs = deps.embed.embed(cands)
    return [cands[i] for i in mmr(page_vec, vecs, t.page_phrases_top_n, t.mmr_diversity)]


def weak_spots(
    serp: SerpResults, settings: Settings, today: date, small_sites: int = 0
) -> tuple[list[str], float]:
    """Signals that the top 10 is beatable, and the winnability bonus they add."""
    t = settings.thresholds
    top = serp.items[:10]
    signals: list[str] = []
    bonus = 0.0
    forums = [i.domain for i in top if i.page_type == "forum"]
    if forums:
        signals.append(f"forum in top 10 ({forums[0]})")
        bonus += t.weak_spot_forum_bonus
    stale_cutoff = today.year - t.stale_years
    stale = [
        i
        for i in top
        if (years := [int(y) for y in re.findall(r"\b(20[0-3]\d)\b", i.title)])
        and max(years) <= stale_cutoff
    ]
    if stale:
        signals.append(f"{len(stale)} stale page(s) in top 10")
        bonus += min(2, len(stale)) * t.weak_spot_stale_bonus
    if small_sites >= t.small_site_min_count:
        signals.append(f"{small_sites} small site(s) in top 10")
        bonus += t.weak_spot_small_site_bonus
    return signals, bonus


def cluster_candidates(
    kept: list[Candidate], serps: dict[str, SerpResults], min_shared: int, top_n: int
) -> list[list[Candidate]]:
    """Greedy, head-based: highest volume phrase opens a cluster; others join the first head
    they share >= min_shared top-10 URLs with. Head-based avoids chaining unrelated phrases."""
    clusters: list[list[Candidate]] = []
    for cand in sorted(kept, key=lambda c: (-c.volume, c.keyword)):
        for cluster in clusters:
            if shared_urls(serps[cluster[0].keyword], serps[cand.keyword], top_n) >= min_shared:
                cluster.append(cand)
                break
        else:
            clusters.append([cand])
    return clusters


def keyword_research(
    deps: Deps, page_text: str, settings: Settings, today: date | None = None
) -> KeywordResearch:
    t = settings.thresholds
    country = settings.country
    free = settings.data_mode == "free"
    today = today or date.today()
    llm_text = cut_words(page_text, t.llm_page_words)
    cands: dict[str, Candidate] = {}
    measured: set[str] = set()
    questions: list[str] = []
    floor = t.min_bing_impressions if free else t.min_volume

    def add(keyword: str, source: str, m: KeywordMetrics | None = None) -> None:
        k = norm_kw(keyword)
        if not k:
            return
        c = cands.setdefault(k, Candidate(keyword=k, sources=[]))
        if source not in c.sources:
            c.sources.append(source)
        if m is not None and k not in measured:
            c.volume, c.difficulty, c.intent = m.volume, m.difficulty, m.intent
            measured.add(k)

    def fill_metrics() -> None:
        """One bulk call (DataForSEO) or cached per-phrase calls (Bing) for new candidates."""
        missing = [k for k in cands if k not in measured]
        if missing:
            for m in deps.keywords.metrics(missing, country):
                c = cands[norm_kw(m.keyword)]
                c.volume, c.difficulty, c.intent = m.volume, m.difficulty, m.intent
            measured.update(missing)

    def check_autocomplete() -> None:
        """Free mode: Google autocomplete is demand evidence for phrases below the Bing floor."""
        if not (free and t.autocomplete_counts_as_demand and deps.autocomplete):
            return
        todo = [c for c in cands.values() if c.in_autocomplete is None and c.volume < floor]
        hits = pmap(lambda c: deps.autocomplete.is_searched(c.keyword, country), todo, 4)
        for c, hit in zip(todo, hits, strict=True):
            c.in_autocomplete = hit

    def has_demand(c: Candidate) -> bool:
        return c.volume >= floor or bool(free and c.in_autocomplete)

    def score_fit(keys: list[str]) -> None:
        if keys:
            for k, v in zip(keys, deps.embed.embed(keys), strict=True):
                cands[k].fit = round(max(0.0, cosine(page_vec, v)), 4)

    # A1 + A2: LLM seeds and page phrases
    seeds = deps.llm.structured(
        SEED_SYSTEM + f"\nReturn {t.seed_phrases_min} to {t.seed_phrases_max} phrases.",
        llm_text,
        SeedPhrases,
        tier="judgment",
    ).phrases[: t.seed_phrases_max]
    for s in seeds:
        add(s, "llm")
    page_vec = page_vector(deps, page_text, t.passage_max_words)
    for p in page_phrases(deps, page_vec, page_text, settings):
        add(p, "page")
    fill_metrics()
    check_autocomplete()
    score_fit(list(cands))

    expandable = [c for c in cands.values() if has_demand(c)]
    expandable.sort(key=lambda c: (-(c.fit * math.log10(2 + c.volume)), c.keyword))
    best = [c.keyword for c in expandable[: t.seeds_to_expand]]

    # A3: borrow the map (ranked keywords; DataForSEO only) and related keywords;
    # A4: autocomplete and question variants.
    serps: dict[str, SerpResults] = {}
    for seed in best:
        serps[seed] = deps.search.top(seed, country, 10)
        borrowed = [
            i
            for i in serps[seed].items
            if i.page_type not in ("forum", "video", "pdf", "login")
            and domain_of(i.url) not in t.authority_domains
        ][: t.borrow_pages_per_seed]
        for item in borrowed:
            for rk in deps.keywords.ranked_keywords(item.url, country, t.ranked_keywords_limit):
                add(rk.keyword, "borrowed", rk)
        for m in deps.keywords.suggestions(seed, country, t.suggestions_limit):
            add(m.keyword, "related", m)
        for s in deps.keywords.autocomplete(seed, country):
            add(s, "autocomplete")
            if cands[norm_kw(s)].in_autocomplete is None:
                cands[norm_kw(s)].in_autocomplete = True
        if deps.autocomplete:
            for s in deps.autocomplete.variants(
                seed, country, t.question_prefixes, t.question_suffixes
            ):
                if QUESTION_START.search(s):
                    questions.append(s)
                add(s, "autocomplete")
                cands[norm_kw(s)].in_autocomplete = True
        questions += serps[seed].people_also_ask
    fill_metrics()
    check_autocomplete()
    score_fit([k for k, c in cands.items() if c.fit == 0.0])

    # B1: demand gate
    survivors: list[Candidate] = []
    for c in cands.values():
        if has_demand(c):
            survivors.append(c)
        elif free:
            c.reason = (
                f"no demand: {c.volume} Bing impressions < {floor}, not in Google autocomplete"
            )
        else:
            c.reason = f"volume {c.volume} < {floor}"

    def pre_score(c: Candidate) -> float:
        kd = 0 if free or c.difficulty is None else c.difficulty
        return c.fit * math.log10(2 + c.volume) * (1 - kd / 100)

    survivors.sort(key=lambda c: (-pre_score(c), c.keyword))
    for c in survivors[t.cluster_max_candidates :]:
        c.reason = "below pre-rank cut-off"
    survivors = survivors[: t.cluster_max_candidates]

    # B2: difficulty (one source per run) and intent, then the site-strength ceiling
    todo = [c.keyword for c in survivors if c.keyword not in serps]
    for keyword, serp in zip(
        todo,
        pmap(lambda k: deps.search.top(k, country, 10), todo, settings.concurrency),
        strict=True,
    ):
        serps[keyword] = serp
    small_sites: dict[str, int] = {}
    ceiling = t.difficulty_ceiling[settings.site_strength]
    passed: list[Candidate] = []
    for c in survivors:
        serp = serps[c.keyword]
        if free:
            if deps.ranks is None:
                raise RuntimeError("free mode needs deps.ranks for computed difficulty")
            d = computed_difficulty(serp, deps.ranks, t)
            c.difficulty, small_sites[c.keyword] = d.score, d.small_sites
        if c.intent == "unknown":
            c.intent = intent_from_types([i.page_type for i in serp.items[:10]])
        if c.difficulty is None:
            c.reason = "no difficulty score"
        elif c.difficulty > ceiling:
            c.reason = f"difficulty {c.difficulty} > {ceiling} ({settings.site_strength} site)"
        else:
            passed.append(c)
    survivors = passed

    # LLM fit confirmation (yes/no), one call
    if survivors:
        listing = "\n".join(f"- {c.keyword}" for c in survivors)
        verdicts = deps.llm.structured(
            FIT_SYSTEM, f"PAGE:\n{llm_text}\n\nPHRASES:\n{listing}", FitVerdicts, tier="bulk"
        ).verdicts
        no = {norm_kw(v.phrase) for v in verdicts if not v.fits}
        for c in survivors:
            if c.keyword in no:
                c.reason = "LLM: page does not fit this phrase"
        survivors = [c for c in survivors if c.keyword not in no]

    # C: cluster by shared top-10 URLs
    groups = cluster_candidates(survivors, serps, t.cluster_min_shared_urls, t.cluster_top_n)

    # D: rank clusters
    clusters: list[Cluster] = []
    for group in groups:
        head = group[0]
        total = sum(c.volume for c in group)
        signals, bonus = weak_spots(
            serps[head.keyword], settings, today, small_sites.get(head.keyword, 0)
        )
        fit = max(c.fit for c in group)
        demand = math.log10(2 + total)  # 2, not 1: autocomplete-only clusters keep a small demand
        win = min(1.0, max(0.0, 1 - (head.difficulty or 0) / 100 + bonus))
        clusters.append(
            Cluster(
                head=head.keyword,
                members=[c.keyword for c in group],
                total_volume=total,
                difficulty=head.difficulty or 0,
                fit=fit,
                demand=round(demand, 4),
                winnability=round(win, 4),
                score=round(fit * demand * win, 4),
                weak_spots=signals,
            )
        )
    clusters.sort(key=lambda cl: (-cl.score, cl.head))

    unit = "Bing impressions/mo" if free else "/mo"
    phrases: list[Phrase] = []
    for cl in clusters[: settings.phrases_per_run]:
        head = cands[cl.head]
        head.kept = True
        if not free:
            volume_source = "dataforseo"
        elif head.volume >= floor:
            volume_source = "bing"
        else:
            volume_source = "autocomplete"
        demand_text = (
            f"{cl.total_volume} {unit}"
            if volume_source != "autocomplete"
            else "in Google autocomplete"
        )
        extra = f"; {', '.join(cl.weak_spots)}" if cl.weak_spots else ""
        phrases.append(
            Phrase(
                text=cl.head,
                volume=head.volume,
                volume_source=volume_source,
                difficulty=cl.difficulty,
                difficulty_source="computed" if free else "dataforseo",
                intent=head.intent,
                cluster=cl.members,
                reason=(
                    f"{demand_text} across {len(cl.members)} phrase(s), difficulty "
                    f"{cl.difficulty}, fit {cl.fit:.2f}{extra}"
                ),
            )
        )
        head.reason = "chosen: " + phrases[-1].reason
    for cl in clusters[settings.phrases_per_run :]:
        cands[cl.head].reason = (
            cands[cl.head].reason
            or f"cluster score {cl.score} below top {settings.phrases_per_run}"
        )

    return KeywordResearch(
        phrases=phrases,
        clusters=clusters,
        candidates=sorted(cands.values(), key=lambda c: (-c.volume, c.keyword)),
        questions=list(dict.fromkeys(questions)),
        serps=serps,
    )
