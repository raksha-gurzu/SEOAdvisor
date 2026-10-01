import csv
import io

import pytest

from gap_fakes import deps, gap_run
from seo_engine.gap_pipeline import run_gap
from seo_engine.gap_report import keywords_csv, safe


def test_csv_has_one_row_per_keyword_and_stable_columns() -> None:
    run = gap_run()
    run_gap(run, deps())
    rows = list(csv.reader(io.StringIO(keywords_csv(run))))
    header, body = rows[0], rows[1:]
    assert header[:6] == [
        "keyword",
        "categories",
        "business_fit",
        "position ours.com",
        "position moxo.com",
        "position rival.io",
    ]
    assert len(body) == len(run.result.rows)
    assert all(len(r) == len(header) for r in body)
    crm = next(r for r in body if r[0] == "agency crm")
    assert crm[1] == "strong" and crm[3] == "1" and crm[5] == "2"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('=HYPERLINK("http://evil")', '\'=HYPERLINK("http://evil")'),
        ("+1", "'+1"),
        ("-cmd", "'-cmd"),
        ("@SUM(A1)", "'@SUM(A1)"),
        ("client portal", "client portal"),
        (5, 5),
    ],
)
def test_csv_cells_cannot_become_formulas(value, expected) -> None:
    assert safe(value) == expected


def test_csv_needs_a_finished_analysis() -> None:
    with pytest.raises(ValueError):
        keywords_csv(gap_run())
