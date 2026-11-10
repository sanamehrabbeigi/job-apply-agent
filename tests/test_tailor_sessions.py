import asyncio
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_tailor import STRUCTURED

from job_apply_agent.db import Database
from job_apply_agent.jobs import JobFetchError, JobPosting
from job_apply_agent.preferences import merge_defaults
from job_apply_agent.runtime import build_runtime
from job_apply_agent.search.events import EventBus
from job_apply_agent.tailor import TailoredResume
from job_apply_agent.tailor_flow import TailorOutcome
from job_apply_agent.tailor_sessions import MissingResume, NotWaiting, TailorManager
from job_apply_agent.web.app import create_app


@pytest.fixture
def env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("JOB_AGENT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("JOB_AGENT_OUTPUT_DIR", str(tmp_path / "output"))
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "my_resume.md").write_text("# Alex\nSQL", encoding="utf-8")
    prefs = merge_defaults({"resume_path": str(tmp_path / "data" / "my_resume.md")})
    return tmp_path, prefs


def add_job(db: Database, description="Full posting " * 40, partial=False) -> int:
    job_id, _ = db.upsert_posting(
        JobPosting(url="https://jobs.example/1", title="Data Analyst", company="Acme", location="Toronto",
                   description=description, description_is_partial=partial, source="adzuna", external_id="1"),
        dedupe_key="k", canonical_url="jobs.example/1", relevant=True, location_label="Toronto/GTA",
        run_id=None, now="2026-11-09T12:00:00+00:00")
    return job_id


def fake_flow(tmp_path: Path, asks: list):
    async def flow(req, *, ask=None, progress=None, status=None):
        status("Round 1: tailoring")
        progress("Reading the posting")
        answers = await ask(["Used dbt?"])
        asks.append((req, answers))
        folder = tmp_path / "output" / "2026-11-09_Acme_Data-Analyst"
        folder.mkdir(parents=True)
        md = folder / "Alex_Resume_Acme.md"
        md.write_text("# Alex", encoding="utf-8")
        tailored = TailoredResume.from_structured_output({**STRUCTURED, "company": "Acme", "job_title": "Data Analyst"})
        return TailorOutcome(tailored=tailored, folder=folder, files=[md], warnings=["PDF skipped: no LibreOffice"],
                             rounds=2)
    return flow


async def test_session_asks_waits_for_answers_and_finishes(env):
    tmp_path, prefs = env
    db = Database(":memory:")
    job_id = add_job(db)
    asks = []
    manager = TailorManager(db, EventBus(), load_prefs=lambda: prefs, flow=fake_flow(tmp_path, asks))
    session = manager.start(job_id)
    for _ in range(20):
        await asyncio.sleep(0)
        if session.state == "waiting":
            break
    assert session.state == "waiting" and session.questions == ["Used dbt?"]
    assert session.progress[:2] == ["Round 1: tailoring", "Reading the posting"]
    manager.answer(session.id, [("Used dbt?", "Yes, 6 months"), ("Other", "  ")])
    await manager.wait(session.id)
    assert session.state == "done"
    req, answers = asks[0]
    assert answers == [("Used dbt?", "Yes, 6 months")]  # blank answers dropped
    assert req.job_text.startswith("Source: https://jobs.example/1") and req.job_url is None
    assert session.result["files"] == ["2026-11-09_Acme_Data-Analyst/Alex_Resume_Acme.md"]
    assert db.get_job(job_id)["tailored_folder"] == "2026-11-09_Acme_Data-Analyst"
    with pytest.raises(NotWaiting):
        manager.answer(session.id, [])


async def test_answer_timeout_continues_with_no_answers(env):
    tmp_path, prefs = env
    db = Database(":memory:")
    asks = []
    manager = TailorManager(db, EventBus(), load_prefs=lambda: prefs, answer_timeout=0.01,
                            flow=fake_flow(tmp_path, asks))
    session = manager.start(add_job(db))
    await manager.wait(session.id)
    assert session.state == "done" and asks[0][1] == []


async def test_partial_description_fetches_full_posting_or_falls_back_to_url(env):
    tmp_path, prefs = env
    db = Database(":memory:")
    job_id = add_job(db, description="snippet", partial=True)
    asks = []

    def fetch_ok(url):
        return JobPosting(url=url, title="Data Analyst", company="Acme", description="The full text " * 50)

    manager = TailorManager(db, EventBus(), load_prefs=lambda: prefs, answer_timeout=0.01,
                            flow=fake_flow(tmp_path, asks), fetch=fetch_ok)
    await manager.wait(manager.start(job_id).id)
    assert "The full text" in asks[0][0].job_text

    def fetch_fail(url):
        raise JobFetchError("blocked")

    db2 = Database(":memory:")
    job2 = add_job(db2, description="", partial=True)
    asks2 = []
    (tmp_path / "output").rename(tmp_path / "output_old")
    manager2 = TailorManager(db2, EventBus(), load_prefs=lambda: prefs, answer_timeout=0.01,
                             flow=fake_flow(tmp_path, asks2), fetch=fetch_fail)
    await manager2.wait(manager2.start(job2).id)
    assert asks2[0][0].job_text is None and asks2[0][0].job_url == "https://jobs.example/1"


async def test_errors_and_missing_resume(env):
    tmp_path, prefs = env
    db = Database(":memory:")

    async def broken(req, **_kw):
        raise RuntimeError("agent failed")

    manager = TailorManager(db, EventBus(), load_prefs=lambda: prefs, flow=broken)
    session = manager.start(add_job(db))
    await manager.wait(session.id)
    assert session.state == "error" and session.error == "agent failed"
    with pytest.raises(KeyError):
        manager.start(999)
    no_resume = TailorManager(db, EventBus(), load_prefs=lambda: merge_defaults({"resume_path": "/nope.docx"}))
    with pytest.raises(MissingResume):
        no_resume.start(1)


def test_tailor_routes_and_file_download(env):
    tmp_path, prefs = env
    from job_apply_agent.preferences import save_preferences

    save_preferences(prefs)
    rt = build_runtime(db=Database(":memory:"), sources={})
    asks = []
    rt.tailor.flow = fake_flow(tmp_path, asks)
    rt.tailor.answer_timeout = 5
    job_id = add_job(rt.db)
    with TestClient(create_app(rt, start_scheduler=False), base_url="http://127.0.0.1") as client:
        started = client.post(f"/api/jobs/{job_id}/tailor")
        assert started.status_code == 202
        sid = started.json()["id"]
        for _ in range(100):
            state = client.get(f"/api/tailor/{sid}").json()
            if state["state"] == "waiting":
                break
            time.sleep(0.02)
        assert state["questions"] == ["Used dbt?"]
        client.post(f"/api/tailor/{sid}/answers", json={"answers": [{"question": "Used dbt?", "answer": "Yes"}]})
        for _ in range(100):
            state = client.get(f"/api/tailor/{sid}").json()
            if state["state"] == "done":
                break
            time.sleep(0.02)
        assert state["state"] == "done"
        path = state["result"]["files"][0]
        assert client.get(f"/api/files/{path}").text == "# Alex"
        assert client.get("/api/files/../data/my_resume.md").status_code == 404
        assert client.get("/api/tailor/nope").status_code == 404
        assert client.post("/api/jobs/999/tailor").status_code == 404
