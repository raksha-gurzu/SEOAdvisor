"""Hand-counted scenario (passages = one paragraph each).

FakeEmbed is bag-of-words, so similarity is easy to work out by hand:
cos = shared words / sqrt(len_a * len_b), after dropping stopwords and a plural "s".
"""

import pytest

from fakes import FakeEmbed, FakeLLM, all_gaps_relevant, fake_passage_labels
from seo_engine.config import Settings, Thresholds
from seo_engine.deps import Deps
from seo_engine.models import Page, TopicCount
from seo_engine.tools.topic_coverage import (
    Evidence,
    content_score,
    percentile,
    topic_coverage,
)


def _page(domain: str, topics: list[str], text: str) -> Page:
    return Page(
        url=f"https://{domain}/",
        source="google#1",
        page_type="product",
        text=text,
        headings=[],
        topics=topics,
    )


COMPETITORS = [
    _page(
        "a.com",
        ["file sharing", "client approvals"],
        "file sharing for clients\nclient approvals process\npricing plans compared",
    ),
    _page(
        "b.com",
        ["File sharing"],
        "file sharing for clients\nclient approvals process\nfile sharing securely",
    ),
    _page(
        "c.com",
        ["file sharing", "pricing plans"],
        "file sharing for clients\npricing plans compared",
    ),
    _page(
        "suitedash.com",
        ["suitedash integrations", "time tracking"],
        "time tracking hours\nsuitedash integrations list",
    ),
    _page("e.com", ["file sharing"], "file sharing for clients\nproject dashboard overview"),
    # "approvals workflow for clients today" discusses "client approvals" (all its words appear)
    _page(
        "f.com",
        ["project dashboard"],
        "project dashboard overview\napprovals workflow for clients today",
    ),
]
OURS = Page(
    url="ours",
    source="input",
    page_type="product",
    text="client approvals process\nclient approvals in one place\nour pricing plans",
    headings=[],
    topics=[],
)
EVIDENCE = [
    Evidence(text="time tracking", source="related search"),
    Evidence(text="can clients sign contracts online?", source="People Also Ask"),
    Evidence(text="file sharing for clients", source="People Also Ask"),  # competitors cover it
]


def _settings() -> Settings:
    # every paragraph is 3+ words, so no two paragraphs share a passage
    return Settings(thresholds=Thresholds(passage_max_words=5))


def _deps() -> tuple[Deps, FakeLLM]:
    llm = FakeLLM(
        {
            "PassageLabels": fake_passage_labels,
            "NoiseTopics": lambda s, u: {"noise": []},
            "GapFits": all_gaps_relevant,
        }
    )
    deps = Deps(search=None, keywords=None, fetcher=None, llm=llm, embed=FakeEmbed())  # type: ignore[arg-type]
    return deps, llm


def test_counts_match_hand_count() -> None:
    deps, llm = _deps()
    out = topic_coverage(deps, COMPETITORS, OURS, ["client portal"], EVIDENCE, _settings())
    by = {c.topic: c for c in out.counts}

    assert (by["file sharing"].covered_by, by["file sharing"].bucket) == (4, "must")
    assert by["file sharing"].ours_passages == 0
    # listed by a.com; labelled passages on a.com, b.com and f.com
    assert (by["client approvals"].covered_by, by["client approvals"].bucket) == (3, "worth")
    assert by["client approvals"].ours_passages == 2
    assert (by["pricing plans"].covered_by, by["pricing plans"].ours_passages) == (2, 1)
    assert (by["project dashboard"].covered_by, by["project dashboard"].bucket) == (2, "worth")
    assert (by["time tracking"].covered_by, by["time tracking"].bucket) == (1, "rare")
    assert by["suitedash integrations"].bucket == "noise"
    assert all(c.total == 6 for c in out.counts)
    assert llm.calls.count("PassageLabels") == 7  # one per page: 6 competitors + ours

    # Must-cover first, never-mentioned before mentioned.
    assert out.counts[0].topic == "file sharing"

    # score = 100 * (3/6*2/3.2 + 2/6*1/2.2) / ((4+3+2+2)/6 * 0.77) = 32.9
    assert out.score == 33
    assert "100 × 0.46 / 1.41" in out.score_arithmetic

    # our 2 passages on "client approvals" beat the 90th percentile of [1,1,0,0,0,1] = 1
    assert out.stuffing_warnings and "client approvals" in out.stuffing_warnings[0]


def test_gaps_need_evidence_and_low_coverage() -> None:
    deps, _ = _deps()
    out = topic_coverage(deps, COMPETITORS, OURS, ["client portal"], EVIDENCE, _settings())
    gaps = {g.topic: g for g in out.gaps}
    assert gaps["time tracking"].evidence == "related search: time tracking"
    assert gaps["time tracking"].covered_by == 1
    assert gaps["can clients sign contracts online?"].covered_by == 0
    assert "file sharing for clients" not in gaps  # 4 of 6 competitors cover it
    for g in out.gaps:
        assert g.covered_by / 6 < 0.2


def test_synonyms_merge_before_counting() -> None:
    deps, _ = _deps()
    comps = [_page("a.com", ["file sharing"], "x"), _page("b.com", ["files sharing"], "y")]
    out = topic_coverage(
        deps, comps, OURS, ["x"], [], Settings(thresholds=Thresholds(passage_max_words=4))
    )
    fs = [c for c in out.counts if "sharing" in c.topic]
    assert len(fs) == 1 and fs[0].covered_by == 2


def test_score_saturates_and_caps() -> None:
    counts = [
        TopicCount(topic="a", covered_by=6, total=6, ours_passages=n, bucket="must") for n in (100,)
    ]
    assert content_score(counts, 1.2, 0.77)[0] == 100
    zero = [TopicCount(topic="a", covered_by=6, total=6, ours_passages=0, bucket="must")]
    assert content_score(zero, 1.2, 0.77)[0] == 0


def test_percentile() -> None:
    assert percentile([0, 0, 0, 1, 1, 1], 0.9) == pytest.approx(1.0)
    assert percentile([1, 2, 3, 4, 5], 0.5) == 3


def test_off_topic_questions_are_dropped() -> None:
    deps, llm = _deps()

    def job_questions_off(system: str, user: str) -> dict:
        lines = user.split("QUESTIONS:\n")[1].splitlines()
        return {
            "answers": [
                {"id": int(line.split(".", 1)[0]), "relevant": "contracts" not in line}
                for line in lines
            ]
        }

    llm.handlers["GapFits"] = job_questions_off
    out = topic_coverage(deps, COMPETITORS, OURS, ["client portal"], EVIDENCE, _settings())
    topics = {g.topic for g in out.gaps}
    assert "time tracking" in topics
    assert "can clients sign contracts online?" not in topics
