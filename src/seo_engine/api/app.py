"""FastAPI backend (docs/ARCHITECTURE.md §12). Runs the fixed pipelines (briefs, Keyword Gap,
Site Snapshot) in the background."""

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from seo_engine.api.store import (
    GapStore,
    GapSummary,
    RunStore,
    RunSummary,
    SnapshotStore,
    SnapshotSummary,
    StoredRecord,
    new_gap_record,
    new_record,
    new_snapshot_record,
    now,
)
from seo_engine.config import (
    PROJECT_ROOT,
    GapSettings,
    Secrets,
    Settings,
    SiteStrength,
    SnapshotSettings,
)
from seo_engine.deps import Deps, from_env
from seo_engine.gap_pipeline import (
    GapDeps,
    GapError,
    GapRun,
    gap_deps_from_env,
    run_gap,
    site_origins,
)
from seo_engine.gap_report import keywords_csv
from seo_engine.models import Run
from seo_engine.pipeline import run_pipeline
from seo_engine.providers.base import is_public_url  # noqa: F401  (public name of the API module)
from seo_engine.providers.fetcher import HttpFetcher, PageFetcher
from seo_engine.report import build_report, site_name
from seo_engine.snapshot_pipeline import (
    SnapshotDeps,
    SnapshotError,
    SnapshotRun,
    run_snapshot,
    snapshot_deps_from_env,
    snapshot_origin,
)
from seo_engine.snapshot_report import snapshot_csv

MIN_WORDS = 50
COUNTRIES = ["US", "GB", "CA", "AU", "IN", "NP", "DE", "FR", "NZ", "IE", "SG"]
WEB_DIST = PROJECT_ROOT / "web" / "dist"


class RunSettingsIn(BaseModel):
    country: str = "US"
    site_strength: SiteStrength = "new"
    phrases_per_run: int = Field(3, ge=1, le=3)
    pages_per_phrase: Literal[10, 20] = 20
    data_mode: Literal["free", "dataforseo"] = "free"


class RunRequest(BaseModel):
    page_text: str
    source_url: str | None = None
    settings: RunSettingsIn = RunSettingsIn()

    @field_validator("page_text")
    @classmethod
    def enough_text(cls, v: str) -> str:
        if len(v.split()) < MIN_WORDS:
            raise ValueError(f"paste at least {MIN_WORDS} words of page text")
        return v.strip()


GAP_DEFAULTS = GapSettings()


class GapSettingsIn(BaseModel):
    country: str = "US"
    depth: int = GAP_DEFAULTS.depth  # results checked; 1 Serper credit per 10
    keywords: int = Field(GAP_DEFAULTS.keywords, ge=10, le=100)

    @field_validator("depth")
    @classmethod
    def offered_depth(cls, v: int) -> int:
        if v not in GAP_DEFAULTS.depth_options:
            raise ValueError(f"depth must be one of {GAP_DEFAULTS.depth_options}")
        return v

    @field_validator("country")
    @classmethod
    def known_country(cls, v: str) -> str:
        if v.upper() not in COUNTRIES:
            raise ValueError(f"country must be one of {', '.join(COUNTRIES)}")
        return v.upper()


class GapRequest(BaseModel):
    site: str
    competitors: list[str] = Field(min_length=1, max_length=GAP_DEFAULTS.max_competitors)
    settings: GapSettingsIn = GapSettingsIn()


class GapDefaults(BaseModel):
    settings: GapSettingsIn
    countries: list[str]
    max_competitors: int
    depths: list[int]
    keyword_options: list[int]


SNAPSHOT_DEFAULTS = SnapshotSettings()


class SnapshotSettingsIn(BaseModel):
    country: str = "US"
    keywords: int = SNAPSHOT_DEFAULTS.gap.keywords  # 2 Serper credits each at depth 20

    @field_validator("keywords")
    @classmethod
    def offered_keywords(cls, v: int) -> int:
        if v not in SNAPSHOT_DEFAULTS.keyword_options:
            raise ValueError(f"keywords must be one of {SNAPSHOT_DEFAULTS.keyword_options}")
        return v

    @field_validator("country")
    @classmethod
    def known_country(cls, v: str) -> str:
        if v.upper() not in COUNTRIES:
            raise ValueError(f"country must be one of {', '.join(COUNTRIES)}")
        return v.upper()


class SnapshotRequest(BaseModel):
    site: str
    settings: SnapshotSettingsIn = SnapshotSettingsIn()


class SnapshotDefaults(BaseModel):
    settings: SnapshotSettingsIn
    countries: list[str]
    keyword_options: list[int]
    depth: int


class ExtractRequest(BaseModel):
    url: str


class ExtractResult(BaseModel):
    url: str
    title: str
    text: str
    word_count: int
    method: str


def normalise_url(raw: str) -> str:
    url = raw.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


COPY_INSTEAD = "Copy the text from the page instead."
FETCH_ERRORS = {
    "robots_blocked": f"This site’s robots.txt blocks automated reading. {COPY_INSTEAD}",
    "http_error": f"Couldn’t load that page. Check the address, or {COPY_INSTEAD.lower()}",
    "not_html": "That address isn’t a web page (it may be a PDF or image).",
}


class Health(BaseModel):
    keys: dict[str, bool]
    ready_free_mode: bool
    missing_for_free_mode: list[str]
    missing_for_keyword_gap: list[str] = []
    missing_for_site_snapshot: list[str] = []  # without these a snapshot cannot run
    optional_for_site_snapshot: list[str] = []  # without these, parts show "not set up"


class Defaults(BaseModel):
    settings: RunSettingsIn
    countries: list[str]
    min_words: int


def public_record(rec: StoredRecord) -> dict[str, Any]:
    """Run record without competitor page text (large, and the UI only needs counts)."""
    return rec.model_dump(mode="json", exclude={"run": {"competitors": {"__all__": {"text"}}}})


def public_gap_record(rec: StoredRecord) -> dict[str, Any]:
    """Gap record without the page snippets read for keyword discovery."""
    pages = {"pages": {"__all__": {"snippet"}}}
    return rec.model_dump(mode="json", exclude={"run": {"sites": {"__all__": pages}}})


def public_snapshot_record(rec: StoredRecord) -> dict[str, Any]:
    """Snapshot record without the page snippets read for keyword discovery."""
    return rec.model_dump(
        mode="json", exclude={"run": {"sample": {"pages": {"__all__": {"snippet"}}}}}
    )


def create_app(
    runs_dir: Path = PROJECT_ROOT / "runs",
    deps_factory: Callable[[Run], Deps] = from_env,
    max_parallel_runs: int = 2,
    web_dist: Path = WEB_DIST,
    fetcher_factory: Callable[[], PageFetcher] = lambda: HttpFetcher(Settings()),
    url_guard: Callable[[str], bool] = is_public_url,
    gap_deps_factory: Callable[[GapRun], GapDeps] = gap_deps_from_env,
    snapshot_deps_factory: Callable[[SnapshotRun], SnapshotDeps] = snapshot_deps_from_env,
) -> FastAPI:
    app = FastAPI(title="SEO Engine", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:4280"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    store = RunStore(runs_dir)
    store.fail_interrupted()
    gaps = GapStore(runs_dir / "gaps")
    gaps.fail_interrupted()
    snapshots = SnapshotStore(runs_dir / "snapshots")
    snapshots.fail_interrupted()
    slots = threading.BoundedSemaphore(max_parallel_runs)

    def run_in_background(
        target: RunStore | GapStore | SnapshotStore, run_id: str, work: Callable
    ) -> None:
        """Shared by all features: one slot, live step progress, failures kept."""
        rec = target.get(run_id)
        with slots:
            rec.status = "running"
            target.save(rec)

            def on_step(name: str, status: str, detail: str) -> None:
                step = next(s for s in rec.steps if s.name == name)
                step.started_at = step.started_at or now()  # progress updates keep the start
                step.status, step.detail = status, detail  # type: ignore[assignment]
                if status == "done":
                    step.finished_at = now()
                target.save(rec)

            try:
                work(rec, on_step)
                rec.status = "done"
            except (GapError, SnapshotError) as exc:  # the user can fix it: show as written
                rec.status, rec.error = "failed", str(exc)
            except Exception as exc:  # report any failure to the UI instead of losing the run
                rec.status, rec.error = "failed", f"{type(exc).__name__}: {exc}"
            if rec.status == "failed":
                for step in rec.steps:
                    if step.status == "running":
                        step.status, step.finished_at = "failed", now()
            target.save(rec)

    def execute(run_id: str) -> None:
        def work(rec, on_step) -> None:
            rec.details = run_pipeline(rec.run, deps_factory(rec.run), on_step)

        run_in_background(store, run_id, work)

    def execute_gap(run_id: str) -> None:
        def work(rec, on_step) -> None:
            run_gap(rec.run, gap_deps_factory(rec.run), on_step)

        run_in_background(gaps, run_id, work)

    def execute_snapshot(run_id: str) -> None:
        def work(rec, on_step) -> None:
            run_snapshot(rec.run, snapshot_deps_factory(rec.run), on_step)

        run_in_background(snapshots, run_id, work)

    @app.get("/api/health")
    def health() -> Health:
        s = Secrets()
        keys = {
            "deepseek": bool(s.deepseek_api_key.get_secret_value()),
            "gemini": bool(s.gemini_api_key.get_secret_value()),
            "serper": bool(s.serper_api_key.get_secret_value()),
            "bing": bool(s.bing_webmaster_api_key.get_secret_value()),
            "dataforseo": bool(s.dataforseo_login and s.dataforseo_password.get_secret_value()),
            "openpagerank": bool(s.openpagerank_api_key.get_secret_value()),
            "crux": bool(s.crux_api_key.get_secret_value()),
        }
        needed = ["deepseek", "gemini"]  # Serper and Bing improve results but have fallbacks
        missing = [k for k in needed if not keys[k]]
        gap_missing = [k for k in ("deepseek", "serper") if not keys[k]]  # Bing is optional
        return Health(
            keys=keys,
            ready_free_mode=not missing,
            missing_for_free_mode=missing,
            missing_for_keyword_gap=gap_missing,
            # The LLM names the keywords; everything else only fills parts of the page.
            missing_for_site_snapshot=[k for k in ("deepseek",) if not keys[k]],
            optional_for_site_snapshot=[
                k for k in ("serper", "openpagerank", "crux", "bing") if not keys[k]
            ],
        )

    @app.get("/api/settings/defaults")
    def defaults() -> Defaults:
        return Defaults(settings=RunSettingsIn(), countries=COUNTRIES, min_words=MIN_WORDS)

    @app.post("/api/extract")
    def extract_page(req: ExtractRequest) -> ExtractResult:
        """Import a page's readable text so the user can review it before creating a brief."""
        url = normalise_url(req.url)
        if not url_guard(url):
            raise HTTPException(
                422, "Enter the address of a public web page, like https://example.com/page."
            )
        page = fetcher_factory().fetch(url)
        if page.status in FETCH_ERRORS:
            raise HTTPException(422, FETCH_ERRORS[page.status])
        if not page.text.strip():
            raise HTTPException(
                422, "No readable text found on that page. Copy the text from the page instead."
            )
        return ExtractResult(
            url=url,
            title=page.title,
            text=page.text,
            word_count=page.word_count,
            method=page.method,
        )

    @app.post("/api/runs", status_code=202)
    def start_run(req: RunRequest, background: BackgroundTasks) -> dict[str, str]:
        settings = Settings(**req.settings.model_dump())
        rec = new_record(Run(page_text=req.page_text, source_url=req.source_url, settings=settings))
        store.save(rec)
        background.add_task(execute, rec.id)
        return {"id": rec.id, "status": rec.status}

    @app.get("/api/runs")
    def list_runs() -> list[RunSummary]:
        return store.list()

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        try:
            return public_record(store.get(run_id))
        except KeyError:
            raise HTTPException(404, "run not found") from None

    @app.get("/api/runs/{run_id}/report.docx")
    def report(run_id: str) -> Response:
        try:
            rec = store.get(run_id)
        except KeyError:
            raise HTTPException(404, "run not found") from None
        if rec.run.brief is None:
            raise HTTPException(409, "this brief isn’t finished yet")
        name = site_name(rec.run) or rec.run.brief.phrases[0].text
        filename = "seo-brief-" + "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip(
            "-"
        )
        return Response(
            build_report(rec.run, rec.created_at),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}.docx"'},
        )

    @app.delete("/api/runs/{run_id}", status_code=204)
    def delete_run(run_id: str) -> None:
        try:
            store.delete(run_id)
        except KeyError:
            raise HTTPException(404, "run not found") from None

    @app.get("/api/gaps/defaults")
    def gap_defaults() -> GapDefaults:
        return GapDefaults(
            settings=GapSettingsIn(),
            countries=COUNTRIES,
            max_competitors=GAP_DEFAULTS.max_competitors,
            depths=GAP_DEFAULTS.depth_options,
            keyword_options=GAP_DEFAULTS.keyword_options,
        )

    @app.post("/api/gaps", status_code=202)
    def start_gap(req: GapRequest, background: BackgroundTasks) -> dict[str, str]:
        base = GapSettings()
        try:
            sites = site_origins(req.site, req.competitors, base.max_competitors)
        except GapError as exc:
            raise HTTPException(422, str(exc)) from None
        for domain, origin in sites:
            if not url_guard(origin + "/"):  # the address as typed (www kept) is what we fetch
                raise HTTPException(422, f"{domain} is not a public website we can reach.")
        settings = GapSettings(
            base=Settings(country=req.settings.country),
            depth=req.settings.depth,
            keywords=req.settings.keywords,
        )
        competitors = [c.strip() for c in req.competitors if c.strip()]
        rec = new_gap_record(
            GapRun(site=req.site.strip(), competitors=competitors, settings=settings)
        )
        gaps.save(rec)
        background.add_task(execute_gap, rec.id)
        return {"id": rec.id, "status": rec.status}

    @app.get("/api/gaps")
    def list_gaps() -> list[GapSummary]:
        return gaps.list()

    @app.get("/api/gaps/{run_id}")
    def get_gap(run_id: str) -> dict[str, Any]:
        try:
            return public_gap_record(gaps.get(run_id))
        except KeyError:
            raise HTTPException(404, "analysis not found") from None

    @app.get("/api/gaps/{run_id}/keywords.csv")
    def gap_csv(run_id: str) -> Response:
        try:
            rec = gaps.get(run_id)
        except KeyError:
            raise HTTPException(404, "analysis not found") from None
        if rec.run.result is None:
            raise HTTPException(409, "this analysis isn’t finished yet")
        name = "".join(ch if ch.isalnum() else "-" for ch in rec.run.domains[0])
        return Response(
            keywords_csv(rec.run),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="keyword-gap-{name}.csv"'},
        )

    @app.delete("/api/gaps/{run_id}", status_code=204)
    def delete_gap(run_id: str) -> None:
        try:
            gaps.delete(run_id)
        except KeyError:
            raise HTTPException(404, "analysis not found") from None

    @app.get("/api/snapshots/defaults")
    def snapshot_defaults() -> SnapshotDefaults:
        return SnapshotDefaults(
            settings=SnapshotSettingsIn(),
            countries=COUNTRIES,
            keyword_options=SNAPSHOT_DEFAULTS.keyword_options,
            depth=SNAPSHOT_DEFAULTS.gap.depth,
        )

    @app.post("/api/snapshots", status_code=202)
    def start_snapshot(req: SnapshotRequest, background: BackgroundTasks) -> dict[str, str]:
        try:
            domain, origin = snapshot_origin(req.site)
        except SnapshotError as exc:
            raise HTTPException(422, str(exc)) from None
        if not url_guard(origin + "/"):  # the address as typed (www kept) is what we fetch
            raise HTTPException(422, f"{domain} is not a public website we can reach.")
        gap = GapSettings(
            base=Settings(country=req.settings.country),
            keywords=req.settings.keywords,
            second_pass_keywords=0,
        )
        rec = new_snapshot_record(
            SnapshotRun(site=req.site.strip(), settings=SnapshotSettings(gap=gap))
        )
        snapshots.save(rec)
        background.add_task(execute_snapshot, rec.id)
        return {"id": rec.id, "status": rec.status}

    @app.get("/api/snapshots")
    def list_snapshots() -> list[SnapshotSummary]:
        return snapshots.list()

    @app.get("/api/snapshots/{run_id}")
    def get_snapshot(run_id: str) -> dict[str, Any]:
        try:
            return public_snapshot_record(snapshots.get(run_id))
        except KeyError:
            raise HTTPException(404, "snapshot not found") from None

    @app.get("/api/snapshots/{run_id}/keywords.csv")
    def snapshot_keywords_csv(run_id: str) -> Response:
        try:
            rec = snapshots.get(run_id)
        except KeyError:
            raise HTTPException(404, "snapshot not found") from None
        if rec.run.result is None:
            raise HTTPException(409, "this snapshot isn’t finished yet")
        name = "".join(ch if ch.isalnum() else "-" for ch in rec.run.domain)
        return Response(
            snapshot_csv(rec.run),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="site-snapshot-{name}.csv"'},
        )

    @app.delete("/api/snapshots/{run_id}", status_code=204)
    def delete_snapshot(run_id: str) -> None:
        try:
            snapshots.delete(run_id)
        except KeyError:
            raise HTTPException(404, "snapshot not found") from None

    if (web_dist / "index.html").exists():  # production: serve the built React app
        root = web_dist.resolve()
        if (root / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            if path.startswith("api/"):
                raise HTTPException(404, "not found")
            file = (root / path).resolve()
            if path and file.is_file() and file.is_relative_to(root):
                return FileResponse(file)
            return FileResponse(root / "index.html")  # never serve anything outside web/dist

    return app


app = create_app()
