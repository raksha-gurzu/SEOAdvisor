"""Site strength from the Tranco top-1M domain list (keyless, research-grade ranking).

The list is downloaded once a month into the cache folder and stored in SQLite so lookups
use almost no memory.
"""

import csv
import io
import sqlite3
import time
import zipfile
from pathlib import Path
from typing import Protocol

import httpx

TRANCO_URL = "https://tranco-list.eu/top-1m.csv.zip"


class RankLookup(Protocol):
    def rank(self, domain: str) -> int | None: ...


def candidates(domain: str) -> list[str]:
    """blog.shop.example.co.uk -> itself, then parents down to two labels."""
    labels = domain.lower().removeprefix("www.").split(".")
    return [".".join(labels[i:]) for i in range(len(labels) - 1)]


class DictRanks:
    """In-memory ranks (tests, or a custom list)."""

    def __init__(self, ranks: dict[str, int]) -> None:
        self.ranks = ranks

    def rank(self, domain: str) -> int | None:
        return next((self.ranks[d] for d in candidates(domain) if d in self.ranks), None)


class TrancoRanks:
    def __init__(
        self, cache_dir: Path, max_age_days: int = 30, client: httpx.Client | None = None
    ) -> None:
        self.db_path = cache_dir / "tranco" / "tranco.sqlite"
        self.max_age_s = max_age_days * 86400
        self.http = client
        self._conn: sqlite3.Connection | None = None

    def _fresh(self) -> bool:
        return self.db_path.exists() and time.time() - self.db_path.stat().st_mtime < self.max_age_s

    def _build(self) -> None:
        http = self.http or httpx.Client(follow_redirects=True, timeout=120.0)
        resp = http.get(TRANCO_URL)
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            text = zf.read(zf.namelist()[0]).decode("utf-8")
        rows = ((d.lower(), int(r)) for r, d in csv.reader(io.StringIO(text)))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.db_path.with_suffix(".tmp")
        tmp.unlink(missing_ok=True)
        with sqlite3.connect(tmp) as conn:
            conn.execute("CREATE TABLE ranks (domain TEXT PRIMARY KEY, rank INTEGER)")
            conn.executemany("INSERT OR IGNORE INTO ranks VALUES (?, ?)", rows)
        tmp.replace(self.db_path)

    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            if not self._fresh():
                self._build()
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        return self._conn

    def rank(self, domain: str) -> int | None:
        db = self._db()
        for d in candidates(domain):
            row = db.execute("SELECT rank FROM ranks WHERE domain = ?", (d,)).fetchone()
            if row:
                return int(row[0])
        return None
