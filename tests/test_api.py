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
    assert set(health["keys"]) == {
        "deepseek",
        "gemini",
        "serper",
        "bing",
        "dataforseo",
        "openpagerank",
        "crux",
    }
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


# --- Keyword Gap ------------------------------------------------------------------------

GAP_BODY = {"site": "ours.com", "competitors": ["moxo.com", "rival.io"]}


def _gap_client(tmp_path, factory=None, guard=lambda url: True) -> TestClient:
    from gap_fakes import deps

    app = create_app(
        runs_dir=tmp_path / "runs",
        deps_factory=lambda run: _deps(_llm(DRAFT)),
        web_dist=tmp_path / "no-web-build",
        url_guard=guard,
        gap_deps_factory=factory or (lambda run: deps()),
    )
    return TestClient(app)


def test_gap_lifecycle(tmp_path) -> None:
    client = _gap_client(tmp_path)
    resp = client.post("/api/gaps", json={**GAP_BODY, "settings": {"depth": 30, "keywords": 40}})
    assert resp.status_code == 202
    gap_id = resp.json()["id"]

    rec = client.get(f"/api/gaps/{gap_id}").json()
    assert rec["status"] == "done", rec["error"]
    assert [s["status"] for s in rec["steps"]] == ["done"] * 5
    assert rec["steps"][2]["detail"] == "5 of 5 keywords, 7 credits"
    assert rec["run"]["settings"]["depth"] == 30 and rec["run"]["settings"]["keywords"] == 40
    assert rec["run"]["result"]["top"][0]["keyword"] == "client portal software"
    assert all("snippet" not in p for s in rec["run"]["sites"] for p in s["pages"])

    [summary] = client.get("/api/gaps").json()
    assert summary["title"] == "ours.com vs 2 competitors"
    assert summary["credits_used"] == 7 and summary["to_add"] >= 1
    assert client.get("/api/runs").json() == []  # briefs and gaps are separate histories

    csv_resp = client.get(f"/api/gaps/{gap_id}/keywords.csv")
    assert csv_resp.status_code == 200
    assert csv_resp.headers["content-type"].startswith("text/csv")
    assert 'filename="keyword-gap-ours-com.csv"' in csv_resp.headers["content-disposition"]
    assert csv_resp.text.startswith("keyword,categories,business_fit,position ours.com")

    assert client.delete(f"/api/gaps/{gap_id}").status_code == 204
    assert client.get(f"/api/gaps/{gap_id}").status_code == 404
    assert client.delete(f"/api/gaps/{gap_id}").status_code == 404


def test_gap_validation(tmp_path) -> None:
    client = _gap_client(tmp_path)
    cases = [
        ({"site": "ours.com", "competitors": []}, None),
        ({"site": "ours.com", "competitors": ["ours.com"]}, "ours.com is your own site"),
        ({"site": "ours.com", "competitors": [f"c{i}.com" for i in range(5)]}, None),
        ({**GAP_BODY, "settings": {"country": "XX"}}, None),
        ({**GAP_BODY, "settings": {"depth": 25}}, None),
        ({**GAP_BODY, "settings": {"keywords": 500}}, None),
        ({"site": "localhost", "competitors": ["moxo.com"]}, "not a website address"),
    ]
    for body, message in cases:
        resp = client.post("/api/gaps", json=body)
        assert resp.status_code == 422, body
        if message:
            assert message in resp.json()["detail"]
    assert client.get("/api/gaps").json() == []  # nothing was started


def test_gap_rejects_private_sites(tmp_path) -> None:
    client = _gap_client(tmp_path, guard=lambda url: "moxo" not in url)
    resp = client.post("/api/gaps", json=GAP_BODY)
    assert resp.status_code == 422
    assert resp.json()["detail"] == "moxo.com is not a public website we can reach."


def test_gap_user_error_is_shown_as_written(tmp_path) -> None:
    from seo_engine.gap_pipeline import GapError

    def no_key(run):
        raise GapError("Keyword Gap needs SERPER_API_KEY in .env (Google positions).")

    client = _gap_client(tmp_path, factory=no_key)
    gap_id = client.post("/api/gaps", json=GAP_BODY).json()["id"]
    rec = client.get(f"/api/gaps/{gap_id}").json()
    assert rec["status"] == "failed"
    assert rec["error"] == "Keyword Gap needs SERPER_API_KEY in .env (Google positions)."
    assert client.get(f"/api/gaps/{gap_id}/keywords.csv").status_code == 409


def test_gap_unexpected_error_keeps_its_type(tmp_path) -> None:
    def broken(run):
        raise RuntimeError("boom")

    client = _gap_client(tmp_path, factory=broken)
    gap_id = client.post("/api/gaps", json=GAP_BODY).json()["id"]
    assert client.get(f"/api/gaps/{gap_id}").json()["error"] == "RuntimeError: boom"


def test_gap_defaults_and_health(tmp_path) -> None:
    client = _gap_client(tmp_path)
    d = client.get("/api/gaps/defaults").json()
    assert d["settings"] == {"country": "US", "depth": 20, "keywords": 60}
    assert d["max_competitors"] == 4 and d["depths"] == [10, 20, 30, 50]
    assert "missing_for_keyword_gap" in client.get("/api/health").json()


def test_gap_restart_marks_running_analyses_failed(tmp_path) -> None:
    from seo_engine.api.store import GapStore, new_gap_record
    from seo_engine.gap_pipeline import GapRun

    store = GapStore(tmp_path / "runs" / "gaps")
    rec = new_gap_record(GapRun(site="ours.com", competitors=["moxo.com"]))
    rec.status = "running"
    store.save(rec)
    client = _gap_client(tmp_path)
    assert client.get(f"/api/gaps/{rec.id}").json()["status"] == "failed"


def test_gap_health_lists_exactly_the_keys_it_needs(tmp_path, monkeypatch) -> None:
    from pydantic import SecretStr

    from seo_engine.api import app as app_module

    class NoSerper:
        deepseek_api_key = SecretStr("x")
        gemini_api_key = SecretStr("x")
        serper_api_key = SecretStr("")
        bing_webmaster_api_key = SecretStr("")
        dataforseo_login = ""
        dataforseo_password = SecretStr("")
        openpagerank_api_key = SecretStr("x")
        crux_api_key = SecretStr("")

    monkeypatch.setattr(app_module, "Secrets", NoSerper)
    health = _gap_client(tmp_path).get("/api/health").json()
    assert health["missing_for_keyword_gap"] == ["serper"]  # Bing is optional
    assert health["missing_for_free_mode"] == []
    assert health["missing_for_site_snapshot"] == []  # a snapshot runs without Serper
    assert health["optional_for_site_snapshot"] == ["serper", "crux", "bing"]


def test_gap_blank_competitors_are_dropped_and_www_is_guarded_as_typed(tmp_path) -> None:
    guarded: list[str] = []
    client = _gap_client(tmp_path, guard=lambda url: guarded.append(url) or True)
    body = {"site": "https://www.ours.com", "competitors": ["moxo.com", "  ", "rival.io"]}
    gap_id = client.post("/api/gaps", json=body).json()["id"]
    assert guarded == ["https://www.ours.com/", "https://moxo.com/", "https://rival.io/"]
    rec = client.get(f"/api/gaps/{gap_id}").json()
    assert rec["run"]["competitors"] == ["moxo.com", "rival.io"]
    assert client.get("/api/gaps").json()[0]["title"] == "ours.com vs 2 competitors"


def test_gap_overlapping_sites_are_a_422(tmp_path) -> None:
    resp = _gap_client(tmp_path).post(
        "/api/gaps", json={"site": "ours.com", "competitors": ["blog.ours.com"]}
    )
    assert resp.status_code == 422 and "overlap" in resp.json()["detail"]


def test_restart_closes_the_step_that_was_running(tmp_path) -> None:
    from seo_engine.api.store import GapStore, new_gap_record
    from seo_engine.gap_pipeline import GapRun

    store = GapStore(tmp_path / "runs" / "gaps")
    rec = new_gap_record(GapRun(site="ours.com", competitors=["moxo.com"]))
    rec.status, rec.steps[0].status = "running", "running"
    store.save(rec)
    _gap_client(tmp_path)  # a new app: the restart
    after = store.get(rec.id)
    assert after.status == "failed" and after.steps[0].status == "failed"
    assert after.steps[0].finished_at is not None


# --- Site Snapshot ---------------------------------------------------------------------------


def _snapshot_client(tmp_path, factory=None, guard=lambda url: True) -> TestClient:
    from snapshot_fakes import snapshot_deps

    app = create_app(
        runs_dir=tmp_path / "runs",
        deps_factory=lambda run: _deps(_llm(DRAFT)),
        web_dist=tmp_path / "no-web-build",
        url_guard=guard,
        snapshot_deps_factory=factory or (lambda run: snapshot_deps()),
    )
    return TestClient(app)


def test_snapshot_lifecycle(tmp_path) -> None:
    client = _snapshot_client(tmp_path)
    resp = client.post("/api/snapshots", json={"site": "ours.com", "settings": {"keywords": 60}})
    assert resp.status_code == 202
    snap_id = resp.json()["id"]

    rec = client.get(f"/api/snapshots/{snap_id}").json()
    assert rec["status"] == "done", rec["error"]
    assert [s["status"] for s in rec["steps"]] == ["done"] * 5
    assert rec["run"]["settings"]["gap"]["keywords"] == 60
    assert rec["run"]["settings"]["gap"]["second_pass_keywords"] == 0
    result = rec["run"]["result"]
    assert (result["keywords_found"], result["keywords_checked"]) == (2, 3)
    assert result["facts"]["link"]["score"] == 2.5
    assert all("snippet" not in p for p in rec["run"]["sample"]["pages"])
    assert rec["run"]["probe"]["homepage"]["body"] == ""

    [summary] = client.get("/api/snapshots").json()
    assert summary["title"] == "ours.com"
    assert (summary["found"], summary["checked"], summary["credits_used"]) == (2, 3, 6)
    assert client.get("/api/gaps").json() == []  # separate histories

    csv_resp = client.get(f"/api/snapshots/{snap_id}/keywords.csv")
    assert csv_resp.status_code == 200
    assert 'filename="site-snapshot-ours-com.csv"' in csv_resp.headers["content-disposition"]
    lines = csv_resp.text.splitlines()
    assert lines[0].startswith("keyword,position,url,bing_searches_per_month")
    assert lines[1].startswith("client portal software,2,https://ours.com/portal")

    assert client.delete(f"/api/snapshots/{snap_id}").status_code == 204
    assert client.get(f"/api/snapshots/{snap_id}").status_code == 404
    assert client.delete(f"/api/snapshots/{snap_id}").status_code == 404


def test_snapshot_validation(tmp_path) -> None:
    client = _snapshot_client(tmp_path)
    cases = [
        ({"site": "localhost"}, "not a website address"),
        ({"site": "ours.com", "settings": {"keywords": 45}}, None),
        ({"site": "ours.com", "settings": {"country": "XX"}}, None),
        ({}, None),
    ]
    for body, message in cases:
        resp = client.post("/api/snapshots", json=body)
        assert resp.status_code == 422, body
        if message:
            assert message in resp.json()["detail"]
    assert client.get("/api/snapshots").json() == []


def test_snapshot_rejects_private_sites_and_guards_the_address_as_typed(tmp_path) -> None:
    guarded: list[str] = []
    client = _snapshot_client(tmp_path, guard=lambda url: guarded.append(url) or False)
    resp = client.post("/api/snapshots", json={"site": "https://www.ours.com/about"})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "ours.com is not a public website we can reach."
    assert guarded == ["https://www.ours.com/"]


def test_snapshot_unexpected_error_is_reported(tmp_path) -> None:
    def broken(run):
        raise RuntimeError("boom")

    client = _snapshot_client(tmp_path, factory=broken)
    snap_id = client.post("/api/snapshots", json={"site": "ours.com"}).json()["id"]
    rec = client.get(f"/api/snapshots/{snap_id}").json()
    assert rec["status"] == "failed" and rec["error"] == "RuntimeError: boom"
    assert client.get(f"/api/snapshots/{snap_id}/keywords.csv").status_code == 409


def test_snapshot_defaults(tmp_path) -> None:
    d = _snapshot_client(tmp_path).get("/api/snapshots/defaults").json()
    assert d["settings"] == {"country": "US", "keywords": 30}
    assert d["keyword_options"] == [30, 60] and d["depth"] == 20


def test_snapshot_restart_marks_running_snapshots_failed(tmp_path) -> None:
    from seo_engine.api.store import SnapshotStore, new_snapshot_record
    from seo_engine.snapshot_pipeline import SnapshotRun

    store = SnapshotStore(tmp_path / "runs" / "snapshots")
    rec = new_snapshot_record(SnapshotRun(site="ours.com"))
    rec.status, rec.steps[1].status = "running", "running"
    store.save(rec)
    after = _snapshot_client(tmp_path).get(f"/api/snapshots/{rec.id}").json()
    assert after["status"] == "failed" and after["steps"][1]["status"] == "failed"
