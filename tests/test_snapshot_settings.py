import pytest
from pydantic import ValidationError

from seo_engine.config import GapSettings, SnapshotSettings


def test_defaults_match_the_plan() -> None:
    s = SnapshotSettings()
    assert s.gap.keywords == 30  # owner decision Q1: about 60 Serper credits
    assert s.gap.depth == 20
    assert s.gap.second_pass_keywords == 0  # the second pass needs competitors
    assert s.position_groups == [(1, 3), (4, 10), (11, 20)]
    assert s.crux_form_factor == "PHONE"


def test_each_snapshot_gets_its_own_gap_settings() -> None:
    a, b = SnapshotSettings(), SnapshotSettings()
    assert a.gap is not b.gap


@pytest.mark.parametrize(
    ("metric", "p75", "status"),
    [
        ("largest_contentful_paint", 2500, "good"),  # "good" is at or below the threshold
        ("largest_contentful_paint", 2501, "needs work"),
        ("largest_contentful_paint", 4000, "needs work"),
        ("largest_contentful_paint", 4001, "poor"),
        ("interaction_to_next_paint", 200, "good"),
        ("interaction_to_next_paint", 501, "poor"),
        ("cumulative_layout_shift", 0.1, "good"),
        ("cumulative_layout_shift", 0.25, "needs work"),
        ("cumulative_layout_shift", 0.26, "poor"),
    ],
)
def test_vital_status_uses_the_web_dev_thresholds(metric: str, p75: float, status: str) -> None:
    assert SnapshotSettings().vital_status(metric, p75) == status


@pytest.mark.parametrize(
    "groups",
    [
        [(1, 3), (3, 10)],  # overlap
        [(4, 10), (1, 3)],  # out of order
        [(5, 1)],  # upside down
        [(1, 3), (4, 30)],  # deeper than the Google check (20)
    ],
)
def test_bad_position_groups_are_rejected(groups) -> None:
    with pytest.raises(ValidationError):
        SnapshotSettings(position_groups=groups)


def test_keywords_must_be_an_offered_option() -> None:
    SnapshotSettings(gap=GapSettings(keywords=60, second_pass_keywords=0))
    with pytest.raises(ValidationError):
        SnapshotSettings(gap=GapSettings(keywords=45, second_pass_keywords=0))


def test_deeper_check_allows_deeper_groups() -> None:
    s = SnapshotSettings(
        gap=GapSettings(keywords=30, depth=30, second_pass_keywords=0),
        position_groups=[(1, 3), (4, 10), (11, 30)],
    )
    assert s.position_groups[-1] == (11, 30)
