import pytest

from seo_engine.tools.snippet_check import pixel_width, snippet_check

GOOD_DESC = (
    "Share tasks, files and approvals with every client in one workspace. "
    "Set up in minutes, free for small teams."
)


def test_pixel_width_known_values() -> None:
    assert pixel_width("iiii") == 18  # 4 x 222 x 20 / 1000 = 17.76
    assert pixel_width("WWWW") == 76  # 4 x 944 x 20 / 1000 = 75.52
    assert pixel_width("") == 0


@pytest.mark.parametrize(
    "title",
    [
        "Client Project Workspace for Agencies | Emitii",
        "Client Portal Software: Share Files and Tasks | Emitii",
    ],
)
def test_normal_titles_pass(title: str) -> None:
    result = snippet_check(title, GOOD_DESC)
    assert result.title_ok, result.reasons
    assert result.title_px <= 600


def test_long_title_fails_on_pixels() -> None:
    title = (
        "The Complete Client Project Workspace for Marketing Agencies, Studios and Consultancies"
    )
    result = snippet_check(title, GOOD_DESC)
    assert not result.title_ok and result.title_px > 600
    assert "px" in result.reasons[0]


def test_wide_letters_fail_before_char_limit() -> None:
    title = "WWW MMM WWW MMM WWW MMM WWW MMM WWW MMM WWW"  # 43 chars but very wide
    assert len(title) < 60
    assert not snippet_check(title, GOOD_DESC).title_ok


def test_short_title_fails() -> None:
    result = snippet_check("Emitii", GOOD_DESC)
    assert not result.title_ok and "under" in result.reasons[0]


def test_description_length_bounds() -> None:
    title = "Client Project Workspace for Agencies | Emitii"
    assert snippet_check(title, GOOD_DESC).description_ok
    assert not snippet_check(title, "Too short.").description_ok
    assert not snippet_check(title, GOOD_DESC * 2).description_ok


def test_phrase_checks() -> None:
    result = snippet_check(
        "Emitii | Client Project Workspace for Agencies",
        "A client project workspace where tasks, files and approvals live together for "
        "agencies and clients.",
        phrase="client project workspace",
    )
    assert result.phrase_in_title and not result.phrase_first_in_title
    assert result.phrase_in_description_payoff
    assert any("start of the title" in r for r in result.reasons)
    missing = snippet_check("Agency Software | Emitii Tools", GOOD_DESC, phrase="client portal")
    assert missing.phrase_in_title is False and not missing.passed
