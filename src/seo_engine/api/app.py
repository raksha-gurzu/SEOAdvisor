"""FastAPI backend (docs/ARCHITECTURE.md §12). Runs the fixed pipeline in the background."""

import ipaddress
import socket
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from seo_engine.api.store import RunRecord, RunStore, RunSummary, new_record, now
from seo_engine.config import PROJECT_ROOT, Secrets, Settings, SiteStrength
from seo_engine.deps import Deps, from_env
from seo_engine.models import Run
from seo_engine.pipeline import run_pipeline
from seo_engine.providers.fetcher import HttpFetcher, PageFetcher
from seo_engine.report import build_report, site_name

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


def is_public_url(url: str) -> bool:
    """Only fetch public web pages: never localhost, private or link-local addresses."""
    host = urlparse(url).hostname
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


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


class Defaults(BaseModel):
    settings: RunSettingsIn
    countries: list[str]
    min_words: int


def public_record(rec: RunRecord) -> dict[str, Any]:
    """Run record without competitor page text (large, and the UI only needs counts)."""
    return rec.model_dump(mode="json", exclude={"run": {"competitors": {"__all__": {"text"}}}})


def create_app(
    runs_dir: Path = PROJECT_ROOT / "runs",
    deps_factory: Callable[[Run], Deps] = from_env,
    max_parallel_runs: int = 2,
    web_dist: Path = WEB_DIST,
    fetcher_factory: Callable[[], PageFetcher] = lambda: HttpFetcher(Settings()),
    url_guard: Callable[[str], bool] = is_public_url,
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
    slots = threading.BoundedSemaphore(max_parallel_runs)

    def execute(run_id: str) -> None:
        rec = store.get(run_id)
        with slots:
            rec.status = "running"
            store.save(rec)

            def on_step(name: str, status: str, detail: str) -> None:
                step = next(s for s in rec.steps if s.name == name)
                step.status, step.detail = status, detail  # type: ignore[assignment]
                if status == "running":
                    step.started_at = now()
                else:
                    step.finished_at = now()
                store.save(rec)

            try:
                rec.details = run_pipeline(rec.run, deps_factory(rec.run), on_step)
                rec.status = "done"
            except Exception as exc:  # report any failure to the UI instead of losing the run
                rec.status, rec.error = "failed", f"{type(exc).__name__}: {exc}"
                for step in rec.steps:
                    if step.status == "running":
                        step.status, step.finished_at = "failed", now()
            store.save(rec)

    @app.get("/api/health")
    def health() -> Health:
        s = Secrets()
        keys = {
            "deepseek": bool(s.deepseek_api_key.get_secret_value()),
            "gemini": bool(s.gemini_api_key.get_secret_value()),
            "serper": bool(s.serper_api_key.get_secret_value()),
            "bing": bool(s.bing_webmaster_api_key.get_secret_value()),
            "dataforseo": bool(s.dataforseo_login and s.dataforseo_password.get_secret_value()),
        }
        needed = ["deepseek", "gemini"]  # Serper and Bing improve results but have fallbacks
        missing = [k for k in needed if not keys[k]]
        return Health(keys=keys, ready_free_mode=not missing, missing_for_free_mode=missing)

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
