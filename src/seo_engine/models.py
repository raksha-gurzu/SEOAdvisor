"""Core Pydantic models shared by every tool and agent (docs/ARCHITECTURE.md §9)."""

import threading
from typing import Literal

from pydantic import BaseModel, Field

from seo_engine.config import Settings

Bucket = Literal["must", "worth", "rare", "noise"]
_COST_LOCK = threading.Lock()  # tools call providers from worker threads


class Phrase(BaseModel):
    text: str
    volume: int
    volume_source: str = "dataforseo"  # or "bing" / "autocomplete"
    difficulty: int
    difficulty_source: str = "dataforseo"  # or "computed"
    intent: str
    cluster: list[str] = []
    reason: str = ""


class Page(BaseModel):
    url: str
    source: str  # "google#3" or "gemini 12/30"
    page_type: str
    text: str
    headings: list[str]
    topics: list[str] = []


class TopicCount(BaseModel):
    topic: str
    covered_by: int
    total: int
    ours_passages: int
    bucket: Bucket


class Gap(BaseModel):
    topic: str
    covered_by: int
    evidence: str  # the question or phrase proving demand


class DraftSection(BaseModel):
    heading: str  # an H2
    body: str  # paragraphs separated by blank lines; bullet lines start with "- "


class FaqItem(BaseModel):
    question: str
    answer: str


class DraftCheck(BaseModel):
    label: str
    ok: bool
    detail: str = ""


class ContentDraft(BaseModel):
    """Suggested page copy. Facts come only from the page; the rest is [ADD: …] placeholders."""

    h1: str
    intro: str
    sections: list[DraftSection]
    faq: list[FaqItem] = []
    cta: str = ""
    word_count: int = 0
    placeholders: list[str] = []  # every [ADD: …] the team must fill
    checks: list[DraftCheck] = []


class Brief(BaseModel):
    phrases: list[Phrase] = Field(min_length=1, max_length=3)  # main phrase first
    titles: list[str]
    description: str
    must_cover: list[TopicCount]
    gaps: list[Gap]
    headings: list[str]
    intent_flag: str | None
    score: int = Field(ge=0, le=100)
    score_arithmetic: str = ""
    checklist: dict[str, bool]
    draft: ContentDraft | None = None


class CostEntry(BaseModel):
    label: str  # e.g. "dataforseo.serp", "deepseek-chat"
    usd: float


class Run(BaseModel):
    page_text: str
    source_url: str | None = None  # set when the text was fetched from a website
    settings: Settings = Field(default_factory=Settings)
    phrases: list[Phrase] = []
    competitors: list[Page] = []
    coverage: list[TopicCount] = []
    gaps: list[Gap] = []
    brief: Brief | None = None
    cost_usd: float = 0.0
    costs: list[CostEntry] = []  # one entry per paid call (CLAUDE.md rule 5)
    notes: list[str] = []  # e.g. "reduced depth", dropped competitors with reasons

    def add_cost(self, usd: float, label: str = "") -> None:
        with _COST_LOCK:
            self.costs.append(CostEntry(label=label, usd=usd))
            self.cost_usd = round(self.cost_usd + usd, 6)
