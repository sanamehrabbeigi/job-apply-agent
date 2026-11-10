from datetime import datetime, timedelta, timezone
from pathlib import Path

from job_apply_agent import cli, runtime
from job_apply_agent.db import Database
from job_apply_agent.jobs import JobPosting
from job_apply_agent.preferences import merge_defaults
from job_apply_agent.search.base import SourceResult
from job_apply_agent.search.scheduler import Scheduler
from job_apply_agent.timeutil import iso

NOW = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)


class FakeRunner:
    def __init__(self):
        self.running = False
        self.calls = []

    async def run(self, *, trigger, sources=None, score=True):
        self.calls.append((trigger, sources))
        return 1


def test_due_sources_by_interval():
    db = Database(":memory:")
    db.mark_source_attempt("greenhouse", iso(NOW - timedelta(minutes=30)), success=True)  # 1h interval: not due
    db.mark_source_attempt("lever", iso(NOW - timedelta(hours=2)), success=True)  # due
    db.mark_source_attempt("jsearch", iso(NOW - timedelta(hours=5)), success=False)  # 24h interval: not due
    prefs = merge_defaults({"sources": {"linkedin": {"enabled": False}}})
    due = Scheduler(FakeRunner(), db, lambda: prefs, now_fn=lambda: NOW).due_sources(NOW)
    assert due == ["lever", "ashby", "workday", "adzuna"]  # never-run sources are due; linkedin disabled


async def test_tick_runs_due_sources_and_respects_running_and_disabled():
    db = Database(":memory:")
    runner = FakeRunner()
    prefs = {"value": merge_defaults({})}
    scheduler = Scheduler(runner, db, lambda: prefs["value"], now_fn=lambda: NOW)
    assert await scheduler.tick() == 1
    assert runner.calls[0][0] == "schedule" and "greenhouse" in runner.calls[0][1]
    runner.running = True
    assert await scheduler.tick() is None
    runner.running = False
    prefs["value"] = merge_defaults({"schedule": {"enabled": False}})
    assert await scheduler.tick() is None and len(runner.calls) == 1


def test_load_candidate_docs(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("JOB_AGENT_DATA_DIR", str(tmp_path))
    assert runtime.load_candidate_docs() is None
    (tmp_path / "my_resume.docx").write_bytes(b"")  # placeholder; read_resume is patched below
    monkeypatch.setattr(runtime, "read_resume", lambda path: "RESUME TEXT")
    docs = runtime.load_candidate_docs()
    assert docs.resume == "RESUME TEXT" and docs.profile == "" and docs.answers == ""


def test_cli_search_command(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.setenv("JOB_AGENT_DATA_DIR", str(tmp_path))

    async def fake_source(_ctx):
        return SourceResult(postings=[JobPosting(url="https://gh/1", title="Data Analyst", company="Acme",
                                                 location="Toronto, ON", external_id="1")])

    real_build = runtime.build_runtime
    monkeypatch.setattr(runtime, "build_runtime",
                        lambda: real_build(db=Database(":memory:"), sources={"greenhouse": fake_source}))
    assert cli.main(["search", "--sources", "greenhouse", "--no-score"]) == 0
    out = capsys.readouterr().out
    assert "greenhouse: 1 fetched, 1 relevant, 1 new" in out
    assert "scoring: Scoring was turned off for this run." in out


def test_format_stat_variants():
    assert cli.format_stat("jsearch", {"status": "skipped", "reason": "no API key"}) == "jsearch: skipped (no API key)"
    assert cli.format_stat("lever", {"status": "error", "error": "boom"}) == "lever: error: boom"
    line = cli.format_stat("ashby", {"status": "partial", "fetched": 2, "relevant": 1, "new": 0, "warnings": ["X: 404"]})
    assert line == "ashby: 2 fetched, 1 relevant, 0 new (1 warning(s), first: X: 404)"
