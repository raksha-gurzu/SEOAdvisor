"""Keyword Gap CSV download: one row per checked keyword, ours first in every domain column.

Keywords and URLs come from other people's web pages. A cell that starts with = + - @ can run
as a formula when the file is opened in a spreadsheet (CSV injection), so such cells get a
leading apostrophe.
"""

import csv
import io

from seo_engine.gap_pipeline import GapRun

FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def safe(value: object) -> object:
    if isinstance(value, str) and value.startswith(FORMULA_START):
        return "'" + value
    return value


def keywords_csv(run: GapRun) -> str:
    if run.result is None:
        raise ValueError("the analysis has no result yet")
    domains = run.result.domains
    header = (
        ["keyword", "categories", "business_fit"]
        + [f"position {d}" for d in domains]
        + ["bing_searches_per_month", "bing_status", "google_searches_estimate"]
        + [f"visits_estimate {d}" for d in domains]
        + ["traffic_lift", "difficulty", "difficulty_band", "intent", "cluster", "serp_features"]
        + [f"ranking_url {d}" for d in domains]
        + ["sources"]
    )
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    for row in run.result.rows:
        cells = (
            [row.keyword, ";".join(row.categories), row.business_fit]
            + [row.positions[d] for d in domains]
            + [row.bing_searches, row.bing_status, row.google_estimate]
            + [row.visits.get(d) for d in domains]
            + [row.traffic_lift, row.difficulty, row.difficulty_band, row.intent, row.cluster]
            + [";".join(row.features)]
            + [row.urls[d] for d in domains]
            + [";".join(row.sources)]
        )
        writer.writerow(["" if c is None else safe(c) for c in cells])
    return out.getvalue()
