import pytest
from pydantic import ValidationError

from seo_engine.config import Settings
from seo_engine.models import Brief, Gap, Phrase, Run, TopicCount


def _phrase() -> Phrase:
    return Phrase(text="client project workspace", volume=320, difficulty=22, intent="commercial")


def test_run_validates_with_defaults() -> None:
    run = Run(page_text="Emitii is a client project workspace.")
    assert run.settings.country == "US"
    assert run.settings.thresholds.difficulty_ceiling["new"] == 30
    assert run.cost_usd == 0.0


def test_run_round_trips_with_brief() -> None:
    brief = Brief(
        phrases=[_phrase()],
        titles=["Client Project Workspace | Emitii"],
        description="Share files, tasks and approvals with clients in one workspace.",
        must_cover=[
            TopicCount(topic="client portal", covered_by=6, total=8, ours_passages=0, bucket="must")
        ],
        gaps=[
            Gap(
                topic="pricing per client",
                covered_by=1,
                evidence="PAA: how much does a client portal cost",
            )
        ],
        headings=["What is a client project workspace?"],
        intent_flag=None,
        score=42,
        checklist={"phrase_in_title": True},
    )
    run = Run(page_text="x", phrases=[_phrase()], brief=brief)
    run.add_cost(0.002)
    run.add_cost(0.0006)
    again = Run.model_validate_json(run.model_dump_json())
    assert again == run
    assert again.cost_usd == pytest.approx(0.0026)


def test_brief_rejects_bad_score_and_empty_phrases() -> None:
    with pytest.raises(ValidationError):
        Brief(
            phrases=[],
            titles=[],
            description="",
            must_cover=[],
            gaps=[],
            headings=[],
            intent_flag=None,
            score=120,
            checklist={},
        )


def test_settings_override() -> None:
    s = Settings(site_strength="established", country="GB")
    assert s.thresholds.difficulty_ceiling[s.site_strength] == 60
