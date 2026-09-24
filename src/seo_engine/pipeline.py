"""Fixed pipeline over the 5 tools (docs/ARCHITECTURE.md §2c). Serves the API and UI."""

from collections.abc import Callable
from datetime import date
from typing import Literal

from pydantic import BaseModel

from seo_engine.brief import write_brief, write_draft
from seo_engine.deps import Deps
from seo_engine.models import Run
from seo_engine.providers.search import SerpResults
from seo_engine.tools.competitor_analysis import Dropped, competitor_analysis
from seo_engine.tools.keyword_research import Candidate, Cluster, keyword_research
from seo_engine.tools.serp_top import IntentVerdict, intent_verdict, serp_top
from seo_engine.tools.snippet_check import SnippetCheck
from seo_engine.tools.topic_coverage import Evidence, TopicDetail, topic_coverage

StepName = Literal["keywords", "serp", "competitors", "coverage", "brief", "draft"]
STEPS: list[tuple[StepName, str]] = [
    ("keywords", "Finding target phrases"),
    ("serp", "Reading Google results"),
    ("competitors", "Fetching and reading competitor pages"),
    ("coverage", "Counting topic coverage and gaps"),
    ("brief", "Writing and checking the brief"),
    ("draft", "Writing suggested content"),
]
OnStep = Callable[[StepName, Literal["running", "done"], str], None]


class PipelineDetails(BaseModel):
    """Everything behind the brief, for the UI to show its working."""

    candidates: list[Candidate] = []
    clusters: list[Cluster] = []
    serps: list[SerpResults] = []
    intent: IntentVerdict | None = None
    ours_page_type: str = ""
    ours_topics: list[str] = []
    dropped: list[Dropped] = []
    type_mix: dict[str, int] = {}
    topic_details: list[TopicDetail] = []
    stuffing_warnings: list[str] = []
    snippets: list[SnippetCheck] = []
    rewrites: int = 0


def _noop(step: StepName, status: str, detail: str) -> None:
    pass


def gather_evidence(
    serps: list[SerpResults], questions: list[str], cluster_phrases: list[str]
) -> list[Evidence]:
    """Demand evidence for gaps: People Also Ask, related searches, autocomplete questions."""
    seen: set[str] = set()
    out: list[Evidence] = []

    def add(text: str, source: str) -> None:
        key = " ".join(text.lower().split())
        if key and key not in seen:
            seen.add(key)
            out.append(Evidence(text=text, source=source))

    for serp in serps:
        for q in serp.people_also_ask:
            add(q, "People Also Ask")
    for q in questions:
        add(q, "Google autocomplete")
    for serp in serps:
        for r in serp.related_searches:
            add(r, "related search")
    for p in cluster_phrases:
        add(p, "search phrase")
    return out


def run_pipeline(
    run: Run, deps: Deps, on_step: OnStep = _noop, today: date | None = None
) -> PipelineDetails:
    """Fill `run` (phrases, competitors, coverage, gaps, brief) and return the details."""
    s = run.settings
    details = PipelineDetails()

    on_step("keywords", "running", "")
    research = keyword_research(deps, run.page_text, s, today)
    run.phrases = research.phrases
    details.candidates = research.candidates[:60]
    details.clusters = research.clusters
    if not run.phrases:
        raise RuntimeError(
            "no phrase passed the demand and difficulty filters; try a higher "
            "site strength or check the provider keys"
        )
    on_step("keywords", "done", ", ".join(p.text for p in run.phrases))

    on_step("serp", "running", "")
    tops = [
        serp_top(deps.search, p.text, s.country, s.pages_per_phrase, None, s.thresholds)
        for p in run.phrases
    ]
    serps = [t.serp for t in tops]
    details.serps = serps
    sources = sorted({sr.source for sr in serps})
    on_step("serp", "done", f"{sum(len(sr.items) for sr in serps)} results ({', '.join(sources)})")

    on_step("competitors", "running", "")
    comp = competitor_analysis(deps, serps, run.page_text, s)
    run.competitors = comp.kept
    run.notes += comp.notes
    details.ours_page_type, details.ours_topics = comp.ours.page_type, comp.ours.topics
    details.dropped, details.type_mix = comp.dropped, comp.type_mix
    # Intent from the page types the Page Reader assigned (URL guesses are often "unknown");
    # wrong-format results (forums, videos) still count, from the SERP.
    read = comp.read_types or [i.page_type for i in serps[0].items[:10]]
    ugc = [i.page_type for i in serps[0].items[:10] if i.page_type in ("forum", "video")]
    details.intent = intent_verdict((read + ugc)[:10], comp.ours.page_type, s.thresholds)
    on_step("competitors", "done", f"{len(comp.kept)} kept, {len(comp.dropped)} dropped")

    on_step("coverage", "running", "")
    evidence = gather_evidence(
        serps, research.questions, [m for p in run.phrases for m in p.cluster]
    )
    cov = topic_coverage(deps, comp.kept, comp.ours, [p.text for p in run.phrases], evidence, s)
    run.coverage, run.gaps = cov.counts, cov.gaps
    details.topic_details, details.stuffing_warnings = cov.details, cov.stuffing_warnings
    must = sum(1 for c in cov.counts if c.bucket == "must")
    on_step(
        "coverage", "done", f"{must} must-cover topics, {len(cov.gaps)} gaps, score {cov.score}"
    )

    on_step("brief", "running", "")
    result = write_brief(
        deps.llm,
        run.page_text,
        run.phrases,
        cov.counts,
        cov.gaps,
        cov.score,
        cov.score_arithmetic,
        details.intent.flag,
        cov.stuffing_warnings,
        s,
    )
    run.brief = result.brief
    details.snippets, details.rewrites = result.snippets, result.rewrites
    passed = sum(run.brief.checklist.values())
    on_step("brief", "done", f"checklist {passed}/{len(run.brief.checklist)} passed")

    on_step("draft", "running", "")
    run.brief.draft = write_draft(
        deps.llm,
        run.page_text,
        run.brief,
        cov.counts,
        [len(p.text.split()) for p in comp.kept],
        s,
    )
    todo = len(run.brief.draft.placeholders)
    on_step(
        "draft", "done", f"{run.brief.draft.word_count} words, {todo} fact(s) for you to fill in"
    )
    return details


STEP_LABELS = dict(STEPS)
