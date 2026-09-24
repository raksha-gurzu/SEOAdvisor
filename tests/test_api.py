from fastapi.testclient import TestClient

from seo_engine.api.app import create_app
from seo_engine.api.store import RunStore, new_record
from seo_engine.models import Run
from test_pipeline import GOOD_DESC, GOOD_TITLE, PAGE, _deps, _llm

LONG_PAGE = (PAGE + "\n") * 5  # over the 50-word minimum
DRAFT = {
    "titles": [GOOD_TITLE],
    "description": GOOD_DESC,
    "headings": ["Client workspace for agencies"],
}


def _client(tmp_path, factory=None, web_dist=None) -> TestClient:
    def deps_for(run: Run):
        run.settings.cache_dir = tmp_path / "cache"
        return _deps(_llm(DRAFT))

    app = create_app(
        runs_dir=tmp_path / "runs",
        deps_factory=factory or deps_for,
        web_dist=web_dist or tmp_path / "no-web-build",
    )
    return TestClient(app)


def test_run_lifecycle(tmp_path) -> None:
    client = _client(tmp_path)
    resp = client.post("/api/runs", json={"page_text": LONG_PAGE, "settings": {"country": "US"}})
    assert resp.status_code == 202
    run_id = resp.json()["id"]

    rec = client.get(f"/api/runs/{run_id}").json()  # TestClient runs background tasks first
    assert rec["status"] == "done", rec["error"]
    assert [s["status"] for s in rec["steps"]] == ["done"] * 6
    brief = rec["run"]["brief"]
    assert brief["titles"][0] == GOOD_TITLE and brief["phrases"][0]["text"] == "client workspace"
    assert all("text" not in c for c in rec["run"]["competitors"])  # page text left out
    assert rec["details"]["snippets"][0]["title_px"] > 0

    report = client.get(f"/api/runs/{run_id}/report.docx")
    assert report.status_code == 200 and report.content[:2] == b"PK"  # a .docx is a zip
    assert "attachment" in report.headers["content-disposition"]

    [summary] = client.get("/api/runs").json()
    assert summary["id"] == run_id and summary["title"] == "client workspace"
    assert summary["score"] == brief["score"]

    assert client.delete(f"/api/runs/{run_id}").status_code == 204
    assert client.get(f"/api/runs/{run_id}").status_code == 404


def test_failure_is_reported_not_lost(tmp_path) -> None:
    def broken(run: Run):
        raise RuntimeError("DEEPSEEK_API_KEY is not set in .env")

    client = _client(tmp_path, factory=broken)
    run_id = client.post("/api/runs", json={"page_text": LONG_PAGE}).json()["id"]
    rec = client.get(f"/api/runs/{run_id}").json()
    assert rec["status"] == "failed" and "DEEPSEEK_API_KEY" in rec["error"]


def test_validation_and_defaults(tmp_path) -> None:
    client = _client(tmp_path)
    assert client.post("/api/runs", json={"page_text": "too short"}).status_code == 422
    bad = {"page_text": LONG_PAGE, "settings": {"phrases_per_run": 7}}
    assert client.post("/api/runs", json=bad).status_code == 422
    d = client.get("/api/settings/defaults").json()
    assert d["settings"]["data_mode"] == "free" and "US" in d["countries"]
    health = client.get("/api/health").json()
    assert set(health["keys"]) == {"deepseek", "gemini", "serper", "bing", "dataforseo"}
    assert client.get("/api/runs/not.a.valid.id").status_code == 404


def test_restart_marks_running_runs_failed(tmp_path) -> None:
    store = RunStore(tmp_path / "runs")
    rec = new_record(Run(page_text="x"))
    rec.status = "running"
    store.save(rec)
    client = _client(tmp_path)
    assert client.get(f"/api/runs/{rec.id}").json()["status"] == "failed"


def test_spa_serves_build_but_never_outside_it(tmp_path) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("do not serve")
    client = _client(tmp_path, web_dist=dist)

    assert client.get("/").text == "<html>app</html>"
    assert client.get("/favicon.svg").text == "<svg/>"
    assert client.get("/runs/abc").text == "<html>app</html>"  # client-side route
    for sneaky in ["/%2e%2e/secret.txt", "/..%2fsecret.txt", "/%2e%2e%2fsecret.txt"]:
        assert "do not serve" not in client.get(sneaky).text
    assert client.get("/api/nope").status_code == 404


def _extract_client(tmp_path, pages):
    from fakes import FakeFetcher

    app = create_app(
        runs_dir=tmp_path / "runs",
        web_dist=tmp_path / "no-web-build",
        fetcher_factory=lambda: FakeFetcher(pages),
        url_guard=lambda url: "internal" not in url,
    )
    return TestClient(app)


def test_extract_imports_page_text(tmp_path) -> None:
    from seo_engine.providers.fetcher import FetchedPage

    pages = {
        "https://site.com/pricing": FetchedPage(
            url="https://site.com/pricing",
            status="ok",
            title="Pricing",
            text="Plans\nStarter plan",
            word_count=3,
            method="httpx",
        ),
        "https://blocked.com/": FetchedPage(url="https://blocked.com/", status="robots_blocked"),
    }
    client = _extract_client(tmp_path, pages)
    ok = client.post("/api/extract", json={"url": "site.com/pricing"})  # scheme added
    assert ok.status_code == 200
    assert (
        ok.json()["text"] == "Plans\nStarter plan"
        and ok.json()["url"] == "https://site.com/pricing"
    )

    blocked = client.post("/api/extract", json={"url": "https://blocked.com/"})
    assert blocked.status_code == 422 and "robots.txt" in blocked.json()["detail"]
    internal = client.post("/api/extract", json={"url": "http://internal.local/admin"})
    assert internal.status_code == 422 and "public web page" in internal.json()["detail"]


def test_url_guard_rejects_private_addresses() -> None:
    from seo_engine.api.app import is_public_url

    assert not is_public_url("http://127.0.0.1:8000/api/health")
    assert not is_public_url("http://localhost/")
    assert not is_public_url("http://10.0.0.5/")
    assert not is_public_url("not a url")


def test_run_keeps_source_url(tmp_path) -> None:
    client = _client(tmp_path)
    body = {"page_text": LONG_PAGE, "source_url": "https://emitii.com"}
    run_id = client.post("/api/runs", json=body).json()["id"]
    assert client.get(f"/api/runs/{run_id}").json()["run"]["source_url"] == "https://emitii.com"
