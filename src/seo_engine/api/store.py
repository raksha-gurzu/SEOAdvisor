"""File-based run store: one JSON file per run in `runs/` (git-ignored)."""

import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel

from seo_engine.models import Run
from seo_engine.pipeline import STEPS, PipelineDetails

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


class RunRecord(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    status: RunStatus = "queued"
    error: str | None = None
    steps: list[Step]
    run: Run
    details: PipelineDetails | None = None


class RunSummary(BaseModel):
    id: str
    created_at: datetime
    status: RunStatus
    title: str
    score: int | None
    cost_usd: float


def new_record(run: Run) -> RunRecord:
    t = now()
    return RunRecord(
        id=uuid4().hex[:12],
        created_at=t,
        updated_at=t,
        steps=[Step(name=n, label=label) for n, label in STEPS],
        run=run,
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


class RunStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, run_id: str) -> Path:
        if not run_id.isalnum():
            raise KeyError(run_id)
        return self.root / f"{run_id}.json"

    def save(self, rec: RunRecord) -> None:
        with self._lock:
            rec.updated_at = now()
            path = self._path(rec.id)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(rec.model_dump_json(), encoding="utf-8")
            tmp.replace(path)

    def get(self, run_id: str) -> RunRecord:
        path = self._path(run_id)
        if not path.exists():
            raise KeyError(run_id)
        return RunRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self) -> list[RunSummary]:
        out = []
        for path in self.root.glob("*.json"):
            try:
                out.append(summary(RunRecord.model_validate_json(path.read_text(encoding="utf-8"))))
            except ValueError:
                continue  # skip unreadable files instead of failing the whole list
        return sorted(out, key=lambda s: s.created_at, reverse=True)

    def delete(self, run_id: str) -> None:
        path = self._path(run_id)
        if not path.exists():
            raise KeyError(run_id)
        path.unlink()

    def fail_interrupted(self) -> None:
        """Runs left "running" by a server restart can never finish; mark them failed."""
        for path in self.root.glob("*.json"):
            try:
                rec = RunRecord.model_validate_json(path.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if rec.status in ("queued", "running"):
                rec.status, rec.error = "failed", "interrupted by a server restart"
                self.save(rec)
