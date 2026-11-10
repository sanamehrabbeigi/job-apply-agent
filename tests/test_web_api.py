import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from job_apply_agent.db import Database
from job_apply_agent.jobs import JobPosting
from job_apply_agent.runtime import build_runtime
from job_apply_agent.search.base import SourceResult
from job_apply_agent.web.app import create_app


async def fake_source(_ctx):
    return SourceResult(postings=[
        JobPosting(url="https://gh/1", title="Data Analyst", company="Acme", location="Toronto, ON",
                   description="SQL " * 100, external_id="1"),
        JobPosting(url="https://gh/2", title="Data Scientist", company="Beta", location="Ottawa, ON",
                   description="Python " * 100, external_id="2"),
    ])


@pytest.fixture
def client(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("JOB_AGENT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("JOB_AGENT_OUTPUT_DIR", str(tmp_path / "output"))
    for key in ("JSEARCH_API_KEY", "ADZUNA_APP_ID", "ADZUNA_APP_KEY"):
        monkeypatch.delenv(key, raising=False)
    rt = build_runtime(db=Database(":memory:"), sources={"greenhouse": fake_source})
    with TestClient(create_app(rt, start_scheduler=False), base_url="http://127.0.0.1") as c:
        c.rt = rt
        yield c


def wait_for_run(client, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        runs = client.get("/api/runs").json()
        if runs and runs[0]["finished_at"]:
            return runs[0]
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_search_then_list_and_filter(client):
    assert client.post("/api/search", json={"sources": ["greenhouse"]}).status_code == 202
    run = wait_for_run(client)
    assert run["sources"]["greenhouse"]["relevant"] == 2
    body = client.get("/api/jobs").json()
    assert len(body["jobs"]) == 2 and all(j["score"] is None for j in body["jobs"])  # no resume yet -> unscored
    assert body["counts"]["relevant"] == 2
    ottawa = client.get("/api/jobs", params={"location": "Ottawa"}).json()["jobs"]
    assert [j["company"] for j in ottawa] == ["Beta"]
    by_company = client.get("/api/jobs", params={"sort": "company", "order": "asc"}).json()["jobs"]
    assert [j["company"] for j in by_company] == ["Acme", "Beta"]
    assert client.get("/api/jobs", params={"sort": "salary"}).status_code == 422


def test_job_detail_update_and_404(client):
    client.post("/api/search", json={"sources": ["greenhouse"]})
    wait_for_run(client)
    job_id = client.get("/api/jobs").json()["jobs"][0]["id"]
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["links"][0]["source"] == "greenhouse" and "description" in detail
    updated = client.patch(f"/api/jobs/{job_id}", json={"status": "applied", "notes": "sent Monday"}).json()
    assert updated["status"] == "applied" and updated["notes"] == "sent Monday"
    assert client.patch(f"/api/jobs/{job_id}", json={"status": "bogus"}).status_code == 422
    assert client.get("/api/jobs/9999").status_code == 404


def test_search_conflict_when_running(client):
    client.rt.runner._lock._locked = True  # simulate a run in progress
    try:
        assert client.post("/api/search", json={}).status_code == 409
    finally:
        client.rt.runner._lock._locked = False


def test_preferences_roundtrip_and_validation(client):
    prefs = client.get("/api/preferences").json()
    assert prefs["models"]["scoring"] == "claude-haiku-5-5"
    prefs["excluded_companies"] = ["Acme"]
    result = client.put("/api/preferences", json=prefs).json()
    assert result["preferences"]["excluded_companies"] == ["Acme"] and result["refiltered"] == 0
    prefs["target_score"] = 500
    assert client.put("/api/preferences", json=prefs).status_code == 422


def test_preferences_change_refilters_stored_jobs(client):
    client.post("/api/search", json={"sources": ["greenhouse"]})
    wait_for_run(client)
    prefs = client.get("/api/preferences").json()
    prefs["role_terms"] = ["data scientist"]
    assert client.put("/api/preferences", json=prefs).json()["refiltered"] == 1
    assert [j["title"] for j in client.get("/api/jobs").json()["jobs"]] == ["Data Scientist"]


def test_companies_get_put_and_validation(client):
    companies = client.get("/api/companies").json()
    assert len(companies) >= 40
    saved = client.put("/api/companies", json=companies[:3]).json()
    assert len(saved) == 3 and len(client.get("/api/companies").json()) == 3
    assert client.put("/api/companies", json=[{"name": "X", "ats": "taleo"}]).status_code == 422


def test_profile_uploads(client, tmp_path: Path):
    assert client.get("/api/profile").json()["resume"]["exists"] is False
    r = client.post("/api/profile/resume", files={"file": ("cv.md", b"# Jane Doe\nSQL", "text/markdown")})
    assert r.status_code == 200 and r.json()["resume"]["exists"] is True
    assert r.json()["resume"]["name"] == "my_resume.md"
    assert client.post("/api/profile/resume", files={"file": ("cv.rtf", b"{\\rtf1}", "application/rtf")}).status_code == 422
    doc = client.post("/api/profile/documents", files={"file": ("../skills.md", b"Looker", "text/markdown")})
    assert [d["name"] for d in doc.json()["documents"]] == ["skills.md"]  # path stripped
    assert client.post("/api/profile/documents", files={"file": ("answers.md", b"x", "text/markdown")}).status_code == 422
    assert client.delete("/api/profile/documents/skills.md").json()["documents"] == []
    assert client.delete("/api/profile/documents/skills.md").status_code == 404


def test_status_without_resume(client):
    status = client.get("/api/status").json()
    assert status["resume"] is False and status["keys"] == {"jsearch": False, "adzuna": False}
    assert status["quota"]["jsearch"]["budget"] == 180 and status["search_running"] is False
    assert status["last_run"] is None and status["counts"]["relevant"] == 0


def test_root_without_built_ui_or_with(client):
    r = client.get("/")
    assert r.status_code == 200


def test_saving_stale_settings_after_resume_upload_keeps_the_resume(client):
    stale = client.get("/api/preferences").json()  # loaded before the upload, like the Settings page
    client.post("/api/profile/resume", files={"file": ("cv.md", b"# Jane Doe\nSQL", "text/markdown")})
    client.put("/api/preferences", json=stale)
    assert client.get("/api/status").json()["resume"] is True


def test_new_resume_upload_replaces_other_formats(client):
    client.post("/api/profile/resume", files={"file": ("cv.md", b"# Jane", "text/markdown")})
    client.post("/api/profile/resume", files={"file": ("cv.txt", b"Jane", "text/plain")})
    assert client.get("/api/profile").json()["resume"]["name"] == "my_resume.txt"


def test_cross_site_writes_are_blocked(client):
    evil = client.post("/api/search", json={}, headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    r = client.post("/api/profile/resume", files={"file": ("cv.md", b"x", "text/markdown")},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and client.get("/api/profile").json()["resume"]["exists"] is False
    assert client.get("/api/status", headers={"Host": "evil.example"}).status_code == 400
    dev_ui = client.post("/api/search", json={"sources": []}, headers={"Origin": "http://localhost:5173"})
    assert dev_ui.status_code == 202


def test_status_reports_outdated_scores_and_rescore_is_accepted(client):
    client.post("/api/profile/resume", files={"file": ("cv.md", b"# Jane v1", "text/markdown")})
    rt = client.rt
    from job_apply_agent.search.scoring import profile_hash

    job_id, _ = rt.db.upsert_posting(
        JobPosting(url="https://gh/7", title="Data Analyst", company="Acme", location="Toronto", source="lever",
                   external_id="7", description="x" * 400),
        dedupe_key="k7", canonical_url="gh/7", relevant=True, location_label="Toronto/GTA", run_id=None,
        now=time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()))
    rt.db.save_score(job_id, score=50, summary="", reasons=[], gaps=[], seniority_fit="fit", model="m",
                     profile_hash=profile_hash("old resume", ""), now="2026-11-09T00:00:00+00:00")
    assert client.get("/api/status").json()["outdated_scores"] == 1
    assert client.post("/api/search", json={"sources": [], "rescore": True}).status_code == 202


def test_pdf_resume_and_profile_document_uploads(client, tmp_path: Path):
    from pdf_helpers import write_text_pdf

    pdf = write_text_pdf(tmp_path / "cv.pdf", ["Jane Doe", "Data Analyst"]).read_bytes()
    client.post("/api/profile/resume", files={"file": ("cv.md", b"# Jane", "text/markdown")})
    r = client.post("/api/profile/resume", files={"file": ("cv.pdf", pdf, "application/pdf")})
    assert r.status_code == 200 and r.json()["resume"]["name"] == "my_resume.pdf"
    assert client.get("/api/status").json()["resume"] is True
    doc = client.post("/api/profile/documents", files={"file": ("history.pdf", pdf, "application/pdf")})
    assert [d["name"] for d in doc.json()["documents"]] == ["history.pdf"]
