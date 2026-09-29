"""File-based run stores: one JSON file per run (git-ignored). Briefs live in `runs/`,
Keyword Gap analyses in `runs/gaps/`, Site Snapshots in `runs/snapshots/`; all share
`JsonStore`."""

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel

from seo_engine.gap_pipeline import GAP_STEPS, GapRun
from seo_engine.models import Run
from seo_engine.pipeline import STEPS, PipelineDetails
from seo_engine.snapshot_pipeline import SNAPSHOT_STEPS, SnapshotRun

RunStatus = Literal["queued", "running", "done", "failed"]
StepStatus = Literal["pending", "running", "done", "failed"]


def now() -> datetime:
    return datetime.now(UTC)


class Step(BaseModel):
    name: str
    label: str
    status: StepStatus = "pending"
    detail: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None


class StoredRecord(BaseModel):
    """What every stored run has, whatever it analyses."""

    id: str
    created_at: datetime
    updated_at: datetime
    status: RunStatus = "queued"
    error: str | None = None
    steps: list[Step]


class RunRecord(StoredRecord):
    run: Run
    details: PipelineDetails | None = None


class GapRecord(StoredRecord):
    run: GapRun


class SnapshotRecord(StoredRecord):
    run: SnapshotRun


class RunSummary(BaseModel):
    id: str
    created_at: datetime
    status: RunStatus
    title: str
    score: int | None
    cost_usd: float


class GapSummary(BaseModel):
    id: str
    created_at: datetime
    status: RunStatus
    title: str  # "emitii.com vs 2 competitors"
    to_add: int | None  # number of top keywords to add
    credits_used: int
    cost_usd: float


class SnapshotSummary(BaseModel):
    id: str
    created_at: datetime
    status: RunStatus
    title: str  # the domain
    found: int | None  # keywords in the top `depth`, of `checked`
    checked: int | None
    credits_used: int
    cost_usd: float


def _ids(steps: list[tuple[str, str]]) -> list[Step]:
    return [Step(name=n, label=label) for n, label in steps]


def new_record(run: Run) -> RunRecord:
    t = now()
    return RunRecord(id=uuid4().hex[:12], created_at=t, updated_at=t, steps=_ids(STEPS), run=run)


def new_gap_record(run: GapRun) -> GapRecord:
    t = now()
    return GapRecord(
        id=uuid4().hex[:12], created_at=t, updated_at=t, steps=_ids(GAP_STEPS), run=run
    )


def new_snapshot_record(run: SnapshotRun) -> SnapshotRecord:
    t = now()
    return SnapshotRecord(
        id=uuid4().hex[:12], created_at=t, updated_at=t, steps=_ids(SNAPSHOT_STEPS), run=run
    )


def snapshot_summary(rec: SnapshotRecord) -> SnapshotSummary:
    result = rec.run.result
    return SnapshotSummary(
        id=rec.id,
        created_at=rec.created_at,
        status=rec.status,
        title=rec.run.domain or rec.run.site,
        found=result.keywords_found if result else None,
        checked=result.keywords_checked if result else None,
        credits_used=rec.run.credits_used,
        cost_usd=rec.run.cost_usd,
    )


def summary(rec: RunRecord) -> RunSummary:
    if rec.run.source_url:
        title = rec.run.source_url.split("://", 1)[-1].removeprefix("www.").rstrip("/")
    elif rec.run.phrases:
        title = rec.run.phrases[0].text
    else:
        title = " ".join(rec.run.page_text.split()[:10])
    return RunSummary(
        id=rec.id,
        created_at=rec.created_at,
        status=rec.status,
        title=title,
        score=rec.run.brief.score if rec.run.brief else None,
        cost_usd=rec.run.cost_usd,
    )


def gap_summary(rec: GapRecord) -> GapSummary:
    n = len(rec.run.competitors)
    ours = rec.run.domains[0] if rec.run.domains else rec.run.site
    return GapSummary(
        id=rec.id,
        created_at=rec.created_at,
        status=rec.status,
        title=f"{ours} vs {n} competitor{'s' if n != 1 else ''}",
        to_add=len(rec.run.result.top) if rec.run.result else None,
        credits_used=rec.run.credits_used,
        cost_usd=rec.run.cost_usd,
    )


class JsonStore[R: StoredRecord, S: BaseModel]:
    def __init__(self, root: Path, model: type[R], summarize: Callable[[R], S]) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.model = model
        self.summarize = summarize
        self._lock = threading.Lock()

    def _path(self, run_id: str) -> Path:
        if not run_id.isalnum():
            raise KeyError(run_id)
        return self.root / f"{run_id}.json"

    def save(self, rec: R) -> None:
        with self._lock:
            rec.updated_at = now()
            path = self._path(rec.id)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(rec.model_dump_json(), encoding="utf-8")
            tmp.replace(path)

    def get(self, run_id: str) -> R:
        path = self._path(run_id)
        if not path.exists():
            raise KeyError(run_id)
        return self.model.model_validate_json(path.read_text(encoding="utf-8"))

    def _records(self) -> list[R]:
        out: list[R] = []
        for path in self.root.glob("*.json"):
            try:
                out.append(self.model.model_validate_json(path.read_text(encoding="utf-8")))
            except ValueError:
                continue  # skip unreadable files instead of failing the whole list
        return out

    def list(self) -> list[S]:
        records = sorted(self._records(), key=lambda r: r.created_at, reverse=True)
        return [self.summarize(r) for r in records]

    def delete(self, run_id: str) -> None:
        path = self._path(run_id)
        if not path.exists():
            raise KeyError(run_id)
        path.unlink()

    def fail_interrupted(self) -> None:
        """Runs left "running" by a server restart can never finish; mark them failed."""
        for rec in self._records():
            if rec.status in ("queued", "running"):
                rec.status, rec.error = "failed", "interrupted by a server restart"
                for step in rec.steps:  # otherwise the UI timer counts up forever
                    if step.status == "running":
                        step.status, step.finished_at = "failed", now()
                self.save(rec)


class RunStore(JsonStore[RunRecord, RunSummary]):
    def __init__(self, root: Path) -> None:
        super().__init__(root, RunRecord, summary)


class GapStore(JsonStore[GapRecord, GapSummary]):
    def __init__(self, root: Path) -> None:
        super().__init__(root, GapRecord, gap_summary)


class SnapshotStore(JsonStore[SnapshotRecord, SnapshotSummary]):
    def __init__(self, root: Path) -> None:
        super().__init__(root, SnapshotRecord, snapshot_summary)
