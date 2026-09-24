"""seo_topic_coverage: merge topics, count coverage by meaning, bucket, find gaps, score.

docs/ARCHITECTURE.md §5.3 and §5.5. Embeddings merge synonymous topic labels. Coverage is
read by the LLM, one call per page: it names which numbered passages discuss each topic.
Code counts those passages, buckets topics, finds gaps and computes the score.
"""

import math
import re
from dataclasses import dataclass

from pydantic import BaseModel

from seo_engine.concurrency import pmap
from seo_engine.config import Settings, Thresholds
from seo_engine.deps import Deps
from seo_engine.models import Bucket, Gap, Page, TopicCount
from seo_engine.page_types import domain_of
from seo_engine.providers.embeddings import cosine
from seo_engine.text import passages, truncate_words

LABEL_SYSTEM = """You read one web page split into numbered passages, and a numbered list of
topics. For every topic, list the numbers of the passages that actually discuss it: explain,
describe or answer it, not just mention a word from it. Use an empty list when no passage
discusses the topic. Include every topic number exactly once."""

NOISE_SYSTEM = """You clean a topic list for an SEO brief about the given search phrases.
Mark a topic as noise if it is: site boilerplate (cookies, newsletter, login, contact us,
navigation), a company or product brand name, or off-intent for someone searching these phrases.
Return only the noise topics, each with a short reason."""


QUESTION_SOURCES = {"People Also Ask", "Google autocomplete"}


class Evidence(BaseModel):
    text: str
    source: (
        str  # "People Also Ask", "Google autocomplete", "related search", "competitors rank for"
    )


class TopicPassages(BaseModel):
    topic: int
    passages: list[int] = []


class PassageLabels(BaseModel):
    labels: list[TopicPassages]


GAP_FIT_SYSTEM = """You check searcher questions for one page. For each question answer
relevant=true only if a visitor of this page would expect the page itself to answer it, given the
page's product and the search phrases. Answer relevant=false for career, hiring, academic or
general-knowledge questions the product page has no reason to answer. Answer every id given."""


class GapFit(BaseModel):
    id: int
    relevant: bool


class GapFits(BaseModel):
    answers: list[GapFit]


class NoiseItem(BaseModel):
    topic: str
    reason: str


class NoiseTopics(BaseModel):
    noise: list[NoiseItem] = []


class TopicDetail(BaseModel):
    topic: str
    members: list[str]
    competitor_passages: list[int]  # per competitor, same order as input
    noise_reason: str = ""
    stuffing: bool = False


class TopicCoverage(BaseModel):
    counts: list[TopicCount]
    details: list[TopicDetail]
    gaps: list[Gap]
    score: int
    score_arithmetic: str
    stuffing_warnings: list[str]


@dataclass
class _Group:
    label: str
    members: list[str]
    vecs: list[list[float]]
    listed_by: set[int]  # competitor indexes whose Page Reader named it


def merge_topics(competitors: list[Page], deps: Deps, threshold: float) -> list[_Group]:
    """Group synonymous topic labels by embedding similarity (§5.3 B)."""
    listed: dict[str, set[int]] = {}
    for i, page in enumerate(competitors):
        for topic in page.topics:
            label = " ".join(topic.lower().split())
            if label:
                listed.setdefault(label, set()).add(i)
    labels = sorted(listed, key=lambda lb: (-len(listed[lb]), len(lb), lb))
    vecs = dict(zip(labels, deps.embed.embed(labels), strict=True)) if labels else {}
    groups: list[_Group] = []
    for label in labels:
        for g in groups:
            if cosine(g.vecs[0], vecs[label]) >= threshold:
                g.members.append(label)
                g.vecs.append(vecs[label])
                g.listed_by |= listed[label]
                break
        else:
            groups.append(_Group(label, [label], [vecs[label]], set(listed[label])))
    return groups


def bucket_for(share: float, t: Thresholds) -> Bucket:
    if share >= t.must_cover_share:
        return "must"
    if share >= t.worth_covering_share:
        return "worth"
    return "rare"


def saturation(n: int, k: float) -> float:
    return n / (n + k)


def content_score(counts: list[TopicCount], k: float, target: float) -> tuple[int, str]:
    """BM25-style saturation weighted by competitor coverage (§5.5).

    `target` is the saturation that counts as full marks (0.77 ~ 4 passages at k = 1.2).
    """
    scored = [c for c in counts if c.bucket in ("must", "worth") and c.total]
    if not scored:
        return 0, "no must-cover or worth-covering topics"
    ref = target
    num = sum(c.covered_by / c.total * saturation(c.ours_passages, k) for c in scored)
    den = sum(c.covered_by / c.total * ref for c in scored)
    score = min(100, round(100 * num / den))
    terms = " + ".join(
        f"{c.covered_by}/{c.total}×{saturation(c.ours_passages, k):.2f}" for c in scored[:12]
    )
    more = f" + … ({len(scored) - 12} more)" if len(scored) > 12 else ""
    arithmetic = (
        f"score = min(100, 100 × Σ(w×s) / Σ(w×{ref})) = 100 × {num:.2f} / {den:.2f} = "
        f"{100 * num / den:.0f} → {score}; w = share of competitors covering the topic, "
        f"s = n/(n+{k}) for n passages in our page. Terms: {terms}{more}"
    )
    return score, arithmetic


def percentile(values: list[int], q: float) -> float:
    """Linear-interpolated percentile, q in [0, 1]."""
    if not values:
        return 0.0
    s = sorted(values)
    pos = (len(s) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def brand_tokens(competitors: list[Page]) -> set[str]:
    return {domain_of(p.url).split(".")[0] for p in competitors if p.url.startswith("http")}


def label_page(deps: Deps, page_passages: list[str], labels: list[str]) -> list[list[int]]:
    """One LLM call: for each label, the (0-based) passages of this page that discuss it."""
    if not page_passages or not labels:
        return [[] for _ in labels]
    topics = "\n".join(f"{i}. {label}" for i, label in enumerate(labels, 1))
    body = "\n\n".join(f"[{i}] {text}" for i, text in enumerate(page_passages, 1))
    out = deps.llm.structured(
        LABEL_SYSTEM, f"TOPICS:\n{topics}\n\nPASSAGES:\n{body}", PassageLabels, tier="bulk"
    )
    found: list[set[int]] = [set() for _ in labels]
    for item in out.labels:
        if 1 <= item.topic <= len(labels):
            found[item.topic - 1] |= {p - 1 for p in item.passages if 1 <= p <= len(page_passages)}
    return [sorted(f) for f in found]


def topic_coverage(
    deps: Deps,
    competitors: list[Page],
    ours: Page,
    phrases: list[str],
    evidence: list[Evidence],
    settings: Settings,
) -> TopicCoverage:
    t = settings.thresholds
    total = len(competitors)
    groups = merge_topics(competitors, deps, t.topic_merge_similarity)
    groups.sort(key=lambda g: (-len(g.listed_by), g.label))
    labelled = groups[: t.coverage_max_topics]  # the rest keep reader-listed coverage only

    # Searcher questions that match no topic are labelled too, so gaps are counted the same way.
    ev_vecs = deps.embed.embed([e.text for e in evidence]) if evidence else []
    open_questions = [
        (e, v)
        for e, v in zip(evidence, ev_vecs, strict=True)
        if e.source in QUESTION_SOURCES
        and not any(max(cosine(gv, v) for gv in g.vecs) >= t.evidence_similarity for g in groups)
    ][: t.max_open_questions]
    labels = [g.label for g in labelled] + [e.text for e, _ in open_questions]

    # One labelling call per page (ours last), in parallel. Code counts the passages.
    pages = [*competitors, ours]
    page_passages = [
        passages(truncate_words(p.text, t.llm_page_words), t.passage_max_words) for p in pages
    ]
    per_page = pmap(lambda pp: label_page(deps, pp, labels), page_passages, settings.concurrency)
    ours_idx = len(pages) - 1

    def passage_count(label_idx: int, page_idx: int) -> int:
        return len(per_page[page_idx][label_idx])

    counts: list[TopicCount] = []
    details: list[TopicDetail] = []
    for gi, g in enumerate(groups):
        if gi < len(labelled):
            per_comp = [passage_count(gi, ci) for ci in range(total)]
            ours_n = passage_count(gi, ours_idx)
        else:
            per_comp, ours_n = [0] * total, 0
        covered = sum(1 for ci in range(total) if per_comp[ci] > 0 or ci in g.listed_by)
        counts.append(
            TopicCount(
                topic=g.label,
                covered_by=covered,
                total=total,
                ours_passages=ours_n,
                bucket=bucket_for(covered / total if total else 0, t),
            )
        )
        details.append(TopicDetail(topic=g.label, members=g.members, competitor_passages=per_comp))

    question_cover = []
    for qi in range(len(open_questions)):
        li = len(labelled) + qi
        question_cover.append(
            (
                sum(1 for ci in range(total) if passage_count(li, ci) > 0),
                passage_count(li, ours_idx) > 0,
            )
        )

    # Noise: competitor brands by code, boilerplate/off-intent by LLM.
    brands = brand_tokens(competitors)
    for c, d in zip(counts, details, strict=True):
        hit = next((b for b in brands if re.search(rf"\b{re.escape(b)}\b", c.topic)), None)
        if hit:
            c.bucket, d.noise_reason = "noise", f"competitor brand ({hit})"
    labels = [c.topic for c in counts if c.bucket != "noise"]
    if labels:
        noise = deps.llm.structured(
            NOISE_SYSTEM,
            f"PHRASES: {', '.join(phrases)}\nTOPICS:\n" + "\n".join(f"- {lb}" for lb in labels),
            NoiseTopics,
            tier="bulk",
        ).noise
        reasons = {" ".join(n.topic.lower().split()): n.reason for n in noise}
        for c, d in zip(counts, details, strict=True):
            if c.topic in reasons and c.bucket != "noise":
                c.bucket, d.noise_reason = "noise", reasons[c.topic]

    # Stuffing: ours repeats a topic more than 90% of competitors do.
    warnings: list[str] = []
    for c, d in zip(counts, details, strict=True):
        if c.bucket in ("must", "worth") and c.ours_passages >= 2:
            p90 = percentile(d.competitor_passages, t.stuffing_percentile)
            if c.ours_passages > p90:
                d.stuffing = True
                warnings.append(
                    f"'{c.topic}' appears in {c.ours_passages} passages; 90% of "
                    f"competitors use at most {p90:.0f}"
                )

    score, arithmetic = content_score(counts, t.bm25_k, t.score_target_saturation)
    gaps = relevant_gaps(
        deps,
        ours,
        phrases,
        find_gaps(groups, counts, evidence, ev_vecs, open_questions, question_cover, total, t),
    )
    order = {"must": 0, "worth": 1, "rare": 2, "noise": 3}
    ranked = sorted(
        zip(counts, details, strict=True),
        key=lambda cd: (
            order[cd[0].bucket],
            cd[0].ours_passages > 0,
            -cd[0].covered_by,
            cd[0].topic,
        ),
    )
    return TopicCoverage(
        counts=[c for c, _ in ranked],
        details=[d for _, d in ranked],
        gaps=gaps,
        score=score,
        score_arithmetic=arithmetic,
        stuffing_warnings=warnings,
    )


def relevant_gaps(deps: Deps, ours: Page, phrases: list[str], gaps: list[Gap]) -> list[Gap]:
    """Keep only questions this page is expected to answer (one bulk LLM yes/no call)."""
    if not gaps:
        return gaps
    listing = "\n".join(f"{i}. {g.topic}" for i, g in enumerate(gaps))
    page = " ".join(ours.text.split()[:600])
    answers = deps.llm.structured(
        GAP_FIT_SYSTEM,
        f"SEARCH PHRASES: {', '.join(phrases)}\nPAGE (start):\n{page}\n\nQUESTIONS:\n{listing}",
        GapFits,
        tier="bulk",
    ).answers
    off = {a.id for a in answers if not a.relevant}
    return [g for i, g in enumerate(gaps) if i not in off]


def find_gaps(
    groups: list[_Group],
    counts: list[TopicCount],
    evidence: list[Evidence],
    ev_vecs: list[list[float]],
    open_questions: list[tuple[Evidence, list[float]]],
    question_cover: list[tuple[int, bool]],
    total: int,
    t: Thresholds,
) -> list[Gap]:
    """A gap needs low competitor coverage, none on our page, and demand evidence (§5.3 E)."""
    gaps: list[Gap] = []
    if evidence:
        # 1. Rare topics that searchers ask about.
        for g, c in zip(groups, counts, strict=True):
            if c.bucket != "rare" or c.ours_passages > 0:
                continue
            sims = [max(cosine(gv, ev) for gv in g.vecs) for ev in ev_vecs]
            best = max(range(len(evidence)), key=sims.__getitem__)
            if sims[best] >= t.evidence_similarity:
                e = evidence[best]
                gaps.append(
                    Gap(topic=c.topic, covered_by=c.covered_by, evidence=f"{e.source}: {e.text}")
                )

    # 2. Questions searchers ask that no topic matches and few pages answer.
    for (e, _), (covered, ours) in zip(open_questions, question_cover, strict=True):
        if not ours and (total == 0 or covered / total < t.worth_covering_share):
            gaps.append(Gap(topic=e.text, covered_by=covered, evidence=f"{e.source}: {e.text}"))
    return gaps[: t.max_gaps]
