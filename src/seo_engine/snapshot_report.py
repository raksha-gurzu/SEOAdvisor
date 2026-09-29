"""Site Snapshot CSV download: one row per checked keyword.

Keywords and URLs come from web pages, so cells that could run as a spreadsheet formula get a
leading apostrophe (`gap_report.safe`, CSV injection).
"""

import csv
import io

from seo_engine.gap_report import safe
from seo_engine.snapshot_pipeline import SnapshotRun

HEADER = [
    "keyword",
    "position",
    "url",
    "bing_searches_per_month",
    "bing_status",
    "google_searches_estimate",
    "visits_estimate",
    "difficulty",
    "difficulty_band",
    "intent",
    "serp_features",
]


def snapshot_csv(run: SnapshotRun) -> str:
    if run.result is None:
        raise ValueError("the snapshot has no result yet")
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(HEADER)
    for k in run.result.keywords:
        cells = [
            k.keyword,
            k.position,
            k.url,
            k.bing_searches,
            k.bing_status,
            k.google_estimate,
            k.visits,
            k.difficulty,
            k.difficulty_band,
            k.intent,
            ";".join(k.features),
        ]
        writer.writerow(["" if c is None else safe(c) for c in cells])
    return out.getvalue()
