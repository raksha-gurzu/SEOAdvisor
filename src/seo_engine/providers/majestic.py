"""Referring subnets and IPs from the Majestic Million (keyless CSV, CC BY 3.0; plan F4).

Only the top one million domains are listed, so most small sites are "not in the list".
The CSV (about 80 MB) is streamed into SQLite once every `max_age_days`, like the Tranco list,
so lookups use almost no memory. The UI must show the attribution in `ATTRIBUTION`.
"""

import csv
import sqlite3
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

import httpx
from pydantic import BaseModel

from seo_engine.providers.tranco import build_lock, candidates

MAJESTIC_URL = "https://downloads.majestic.com/majestic_million.csv"
ATTRIBUTION = "Majestic Million, by Majestic (majestic.com), licensed under CC BY 3.0"


class MajesticEntry(BaseModel):
    domain: str
    global_rank: int
    ref_subnets: int  # referring class-C subnets
    ref_ips: int


class MajesticLookup(Protocol):
    def lookup(self, domain: str, exact: bool = False) -> MajesticEntry | None:
        """The domain's entry; a subdomain falls back to its parent unless `exact`."""
        ...


class DictMajestic:
    """In-memory entries (tests)."""

    def __init__(self, entries: list[MajesticEntry]) -> None:
        self.by_domain = {e.domain: e for e in entries}

    def lookup(self, domain: str, exact: bool = False) -> MajesticEntry | None:
        return next(
            (self.by_domain[d] for d in candidates(domain, exact) if d in self.by_domain), None
        )


def parse_rows(lines: Iterator[str]) -> Iterator[tuple[str, int, int, int]]:
    """(domain, global rank, referring subnets, referring IPs) from the CSV, header by name."""
    reader = csv.DictReader(lines)
    for row in reader:
        try:
            yield (
                row["Domain"].strip().lower(),
                int(row["GlobalRank"]),
                int(row["RefSubNets"]),
                int(row["RefIPs"]),
            )
        except (KeyError, ValueError, AttributeError):
            continue  # a malformed row is skipped, not fatal


class MajesticMillion:
    def __init__(
        self,
        cache_dir: Path,
        max_age_days: int = 7,
        client: httpx.Client | None = None,
        timeout_s: float = 120.0,
    ) -> None:
        self.db_path = cache_dir / "majestic" / "majestic.sqlite"
        self.max_age_s = max_age_days * 86400
        self.http = client
        self.timeout_s = timeout_s
        self._conn: sqlite3.Connection | None = None

    def _fresh(self) -> bool:
        return self.db_path.exists() and time.time() - self.db_path.stat().st_mtime < self.max_age_s

    def _build(self) -> None:
        http = self.http or httpx.Client(follow_redirects=True, timeout=self.timeout_s)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.db_path.with_suffix(f".{threading.get_ident()}.tmp")
        try:
            with http.stream("GET", MAJESTIC_URL) as resp:
                resp.raise_for_status()
                with sqlite3.connect(tmp) as conn:
                    # A throwaway file until the rename, so no journal is needed (7 s -> 4 s for
                    # one million rows); the index is built once, after the inserts.
                    conn.execute("PRAGMA journal_mode=OFF")
                    conn.execute("PRAGMA synchronous=OFF")
                    conn.execute(
                        "CREATE TABLE entries (domain TEXT, global_rank INTEGER,"
                        " ref_subnets INTEGER, ref_ips INTEGER)"
                    )
                    conn.executemany(
                        "INSERT INTO entries VALUES (?, ?, ?, ?)", parse_rows(resp.iter_lines())
                    )
                    conn.execute("CREATE INDEX by_domain ON entries (domain)")
                    count = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
            if count == 0:  # an error page or a changed format
                raise ValueError("Majestic Million download had no rows")
            tmp.replace(self.db_path)
        finally:
            tmp.unlink(missing_ok=True)  # a failed or partial download leaves nothing behind

    def _db(self) -> sqlite3.Connection:
        with build_lock(self.db_path):
            if self._conn is None:
                if not self._fresh():
                    try:
                        self._build()
                    except Exception:
                        if not self.db_path.exists():
                            raise
                        # A failed refresh keeps the old list: last week's numbers beat none.
                self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            return self._conn

    def lookup(self, domain: str, exact: bool = False) -> MajesticEntry | None:
        db = self._db()
        for d in candidates(domain, exact):
            row = db.execute(
                "SELECT domain, global_rank, ref_subnets, ref_ips FROM entries WHERE domain = ?",
                (d,),
            ).fetchone()
            if row:
                return MajesticEntry(
                    domain=row[0], global_rank=row[1], ref_subnets=row[2], ref_ips=row[3]
                )
        return None
