from itertools import pairwise

import pytest
from pydantic import ValidationError

from seo_engine.config import GapSettings


def test_defaults_match_the_plan() -> None:
    s = GapSettings()
    assert (s.max_competitors, s.pages_per_site, s.keywords, s.depth) == (4, 30, 60, 20)
    assert s.base.country == "US"
    assert len(s.ctr_by_position) == 20


def test_ctr_curve_never_rises_with_position() -> None:
    curve = GapSettings().ctr_curve()
    assert all(a >= b for a, b in pairwise(curve))
    assert curve[:6] == [0.2002, 0.1036, 0.0389, 0.0171, 0.0108, 0.0073]
    assert curve[6:19] == [0.0046] * 13  # AWR shows 11-19 above 7-10; capped
    assert curve[19] == 0.0027


@pytest.mark.parametrize(
    ("position", "ctr"), [(1, 0.2002), (3, 0.0389), (10, 0.0046), (20, 0.0027)]
)
def test_ctr_at_ranked_positions(position: int, ctr: float) -> None:
    assert GapSettings().ctr_at(position) == ctr


@pytest.mark.parametrize("position", [None, 0, -1, 21, 100])
def test_ctr_is_zero_when_not_ranked_or_beyond_the_table(position: int | None) -> None:
    assert GapSettings().ctr_at(position) == 0.0


def test_google_per_bing_from_statcounter_shares() -> None:
    s = GapSettings()
    assert s.google_per_bing("US") == pytest.approx(86.01 / 8.99)
    assert s.google_per_bing("us") == s.google_per_bing("US")
    assert s.google_per_bing("GB") == pytest.approx(91.75 / 5.66)


def test_google_per_bing_is_none_without_data_or_when_switched_off() -> None:
    assert GapSettings().google_per_bing("BR") is None
    assert GapSettings(google_estimate=False).google_per_bing("US") is None


def test_share_keys_are_normalised_to_upper_case() -> None:
    s = GapSettings(search_shares={"us": (90.0, 5.0)})
    assert s.google_per_bing("US") == pytest.approx(18.0)


@pytest.mark.parametrize(
    "bad",
    [
        {"depth": 25},
        {"depth": 110},
        {"depth": 0},
        {"keywords": 5},
        {"keywords": 101},
        {"max_competitors": 5},
        {"max_competitors": 0},
        {"min_business_fit": 4},
        {"ctr_by_position": []},
        {"ctr_by_position": [1.2]},
        {"ctr_by_position": [-0.1]},
        {"search_shares": {"US": (86.0, 0.0)}},
    ],
)
def test_invalid_settings_are_rejected(bad: dict) -> None:
    with pytest.raises(ValidationError):
        GapSettings(**bad)


def test_round_trips_through_json() -> None:
    s = GapSettings(depth=30, keywords=40)
    again = GapSettings.model_validate_json(s.model_dump_json())
    assert again == s
    assert again.search_shares["US"] == (86.01, 8.99)
