"""Brief Writer (one LLM call) and brief assembly (code).

The writer only drafts titles, the description and headings from run-state data. Every
phrase, topic, count, gap, score and checklist item in the Brief is filled by code from the
run state (CLAUDE.md rule 6).
"""

import re

from pydantic import BaseModel, Field

from seo_engine.config import Settings
from seo_engine.models import (
    Brief,
    ContentDraft,
    DraftCheck,
    DraftSection,
    FaqItem,
    Gap,
    Phrase,
    TopicCount,
)
from seo_engine.providers.llm import LLMProvider
from seo_engine.tools.snippet_check import SnippetCheck, snippet_check

WRITER_SYSTEM = """You write the search snippet and heading outline for one web page. You never
rewrite the page and never state facts, numbers, prices or claims that are not in the page text.

Rules:
- titles: 3 options, each about 50 to 60 characters. Main phrase first. If the page names its
  brand, put the brand last after " | ". Specific and clickable, no clickbait.
- description: 120 to 155 characters. Put the payoff and the main phrase in the first 120
  characters. Only promise what the page offers.
- headings: an outline for the page. First item is the H1 and must contain the main phrase.
  Then H2s that cover the must-cover topics the page misses and the gaps (as questions the
  page should answer). 6 to 12 items. Use the topic names given; do not add new topics."""


class BriefDraft(BaseModel):
    titles: list[str] = Field(min_length=1)
    description: str
    headings: list[str] = Field(min_length=1)


class BriefResult(BaseModel):
    brief: Brief
    snippets: list[SnippetCheck]  # one per title, description checked with each
    rewrites: int


def writer_input(
    page_text: str,
    phrases: list[Phrase],
    must: list[TopicCount],
    worth: list[TopicCount],
    gaps: list[Gap],
    intent_flag: str | None,
    max_words: int,
) -> str:
    def topics(items: list[TopicCount]) -> str:
        return (
            "\n".join(
                f"- {t.topic} (covered by {t.covered_by}/{t.total} competitors; "
                f"{'missing from' if t.ours_passages == 0 else 'already in'} our page)"
                for t in items
            )
            or "- none"
        )

    gap_lines = "\n".join(f"- {g.topic} (evidence: {g.evidence})" for g in gaps) or "- none"
    phrase_lines = "\n".join(f"- {p.text}" for p in phrases)
    return (
        f"MAIN PHRASE: {phrases[0].text}\nOTHER PHRASES:\n{phrase_lines}\n\n"
        f"MUST-COVER TOPICS:\n{topics(must)}\n\nWORTH COVERING:\n{topics(worth)}\n\n"
        f"GAPS:\n{gap_lines}\n\nINTENT WARNING: {intent_flag or 'none'}\n\n"
        f"PAGE TEXT:\n{' '.join(page_text.split()[:max_words])}"
    )


def check_draft(draft: BriefDraft, phrase: str, settings: Settings) -> list[SnippetCheck]:
    return [snippet_check(t, draft.description, phrase, settings.thresholds) for t in draft.titles]


def write_brief(
    llm: LLMProvider,
    page_text: str,
    phrases: list[Phrase],
    coverage: list[TopicCount],
    gaps: list[Gap],
    score: int,
    score_arithmetic: str,
    intent_flag: str | None,
    stuffing_warnings: list[str],
    settings: Settings,
) -> BriefResult:
    if not phrases:
        raise ValueError("no target phrases: nothing to write a brief for")
    main = phrases[0].text
    # Never-mentioned first (coverage is already ordered), capped so the brief stays actionable;
    # the full list stays in the run's coverage.
    must = [c for c in coverage if c.bucket == "must"][: settings.thresholds.brief_max_must]
    worth = [c for c in coverage if c.bucket == "worth"]
    user = writer_input(
        page_text, phrases, must, worth, gaps, intent_flag, settings.thresholds.llm_page_words
    )

    draft = llm.structured(WRITER_SYSTEM, user, BriefDraft, tier="judgment")
    checks = check_draft(draft, main, settings)
    rewrites = 0
    if not any(c.passed for c in checks):
        problems = "\n".join(f"- {c.title!r}: {'; '.join(c.reasons)}" for c in checks)
        draft = llm.structured(
            WRITER_SYSTEM,
            f"{user}\n\nYOUR LAST DRAFT FAILED THESE CHECKS, fix them:\n{problems}",
            BriefDraft,
            tier="judgment",
        )
        checks = check_draft(draft, main, settings)
        rewrites = 1

    # Passing titles first; keep at most 3.
    ranked = sorted(zip(draft.titles, checks, strict=True), key=lambda tc: not tc[1].passed)[:3]
    titles = [t for t, _ in ranked]
    best = ranked[0][1]
    h1 = draft.headings[0].lower() if draft.headings else ""
    checklist = {
        "phrase_in_title": bool(best.phrase_in_title),
        "phrase_first_in_title": bool(best.phrase_first_in_title),
        "title_width_ok": best.title_ok,
        "description_length_ok": best.description_ok,
        "phrase_in_description_payoff": bool(best.phrase_in_description_payoff),
        "phrase_in_h1": main.lower() in h1,
        "intent_matches": intent_flag is None,
        "no_stuffing": not stuffing_warnings,
    }
    brief = Brief(
        phrases=phrases[:3],
        titles=titles,
        description=draft.description,
        must_cover=must,
        gaps=gaps,
        headings=draft.headings,
        intent_flag=intent_flag,
        score=score,
        score_arithmetic=score_arithmetic,
        checklist=checklist,
    )
    return BriefResult(brief=brief, snippets=[c for _, c in ranked], rewrites=rewrites)


# ——— Suggested content (PRD §5.9) ———

DRAFT_SYSTEM = """You are a senior SEO copywriter. Write a complete, publish-ready draft of one web
page from the brief below. Follow SEO best practice:
- h1: one clear H1 that contains the main phrase naturally.
- intro: 2 to 3 short sentences; use the main phrase within the first 100 words; say plainly
  who the page is for and what they get.
- sections: 4 to 7 H2 sections that follow the outline. Each has 2 to 4 short paragraphs (2 to
  3 sentences each) or a short bullet list ("- " lines). Cover every must-cover topic somewhere.
  Never repeat an FAQ question as a section.
- faq: 3 to 6 questions searchers ask (from the gap questions), each with a direct 2 to 3
  sentence answer. Skip any question the page's product has no reason to answer.
- Stay close to the target length; do not pad.
- cta: one sentence that invites the reader to act, based on the page's own call to action.
- Use the main phrase and related phrases naturally; never stuff keywords.
- Plain, confident, active voice. No hype words like "revolutionary" or "game-changing".

FACTS RULE (most important): only state facts that appear in the PAGE TEXT. For anything
specific you do not know (prices, numbers, customer names, integrations, dates, guarantees,
features not described), write a placeholder in exactly this form: [ADD: what the team must
supply]. Never guess a fact. Write the page in the same language as the page text."""

PLACEHOLDER = re.compile(r"\[ADD:[^\]]*\]")


class DraftOut(BaseModel):
    h1: str
    intro: str
    sections: list[DraftSection] = Field(min_length=2)
    faq: list[FaqItem] = []
    cta: str = ""


def draft_text(d: DraftOut | ContentDraft) -> str:
    parts = [d.h1, d.intro]
    for s in d.sections:
        parts += [s.heading, s.body]
    for f in d.faq:
        parts += [f.question, f.answer]
    parts.append(d.cta)
    return "\n".join(p for p in parts if p)


def phrase_count(text: str, phrase: str) -> int:
    return len(re.findall(rf"\b{re.escape(phrase.lower())}\b", text.lower()))


def check_draft_content(d: DraftOut, phrase: str, settings: Settings) -> list[DraftCheck]:
    """SEO standards, checked in code (CLAUDE.md rule 1)."""
    t = settings.thresholds
    text = draft_text(d)
    words = len(text.split())
    first_100 = " ".join(f"{d.h1} {d.intro}".split()[:100])
    uses = phrase_count(text, phrase)
    density = 100 * uses * len(phrase.split()) / max(words, 1)
    covered_h2 = len(d.sections)
    return [
        DraftCheck(label="Main search phrase in the H1", ok=phrase.lower() in d.h1.lower()),
        DraftCheck(
            label="Main phrase in the first 100 words", ok=phrase.lower() in first_100.lower()
        ),
        DraftCheck(
            label="No keyword stuffing",
            ok=density <= t.draft_max_density,
            detail=f"phrase used {uses}× ({density:.1f} per 100 words)",
        ),
        DraftCheck(
            label="Right length to compete",
            ok=t.draft_min_words <= words <= t.draft_max_words * 1.2,
            detail=f"{words} words (aim for {t.draft_min_words} to {t.draft_max_words})",
        ),
        DraftCheck(
            label="Clear section structure",
            ok=3 <= covered_h2 <= 8,
            detail=f"{covered_h2} sections",
        ),
        DraftCheck(
            label="FAQ answers searcher questions",
            ok=len(d.faq) >= 3,
            detail=f"{len(d.faq)} questions",
        ),
    ]


def draft_input(
    page_text: str, brief: Brief, worth: list[TopicCount], target_words: int, max_words: int
) -> str:
    must = "\n".join(f"- {t.topic}" for t in brief.must_cover) or "- none"
    extra = "\n".join(f"- {t.topic}" for t in worth[:8]) or "- none"
    gaps = "\n".join(f"- {g.topic}" for g in brief.gaps) or "- none"
    outline = "\n".join(f"- {h}" for h in brief.headings)
    others = ", ".join(p.text for p in brief.phrases[1:]) or "none"
    return (
        f"MAIN PHRASE: {brief.phrases[0].text}\nRELATED PHRASES: {others}\n"
        f"TITLE TAG (already chosen): {brief.titles[0]}\n\n"
        f"OUTLINE:\n{outline}\n\nMUST-COVER TOPICS:\n{must}\n\nALSO WORTH COVERING:\n{extra}\n\n"
        f"GAP QUESTIONS FOR THE FAQ:\n{gaps}\n\nTARGET LENGTH: about {target_words} words.\n\n"
        f"PAGE TEXT (the only source of facts):\n{' '.join(page_text.split()[:max_words])}"
    )


def write_draft(
    llm: LLMProvider,
    page_text: str,
    brief: Brief,
    coverage: list[TopicCount],
    competitor_words: list[int],
    settings: Settings,
) -> ContentDraft:
    t = settings.thresholds
    median = sorted(competitor_words)[len(competitor_words) // 2] if competitor_words else 0
    target = min(t.draft_max_words, max(t.draft_min_words, median))
    worth = [c for c in coverage if c.bucket == "worth"]
    user = draft_input(page_text, brief, worth, target, t.llm_page_words)
    phrase = brief.phrases[0].text

    out = llm.structured(DRAFT_SYSTEM, user, DraftOut, tier="judgment")
    checks = check_draft_content(out, phrase, settings)
    if not (checks[0].ok and checks[1].ok):  # phrase placement is the one thing worth a retry
        fix = "; ".join(c.label for c in checks[:2] if not c.ok)
        out = llm.structured(
            DRAFT_SYSTEM, f"{user}\n\nFIX IN THIS VERSION: {fix}.", DraftOut, tier="judgment"
        )
        checks = check_draft_content(out, phrase, settings)

    text = draft_text(out)
    placeholders = list(dict.fromkeys(PLACEHOLDER.findall(text)))
    checks.append(
        DraftCheck(
            label="Facts to fill in",
            ok=not placeholders,
            detail=f"{len(placeholders)} placeholder(s) marked [ADD: …]"
            if placeholders
            else "none",
        )
    )
    return ContentDraft(
        **out.model_dump(), word_count=len(text.split()), placeholders=placeholders, checks=checks
    )
