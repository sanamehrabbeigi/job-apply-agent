import asyncio
from datetime import datetime, timezone

import pytest
from fakes import FakeHttp

from job_apply_agent.db import Database
from job_apply_agent.jobs import JobPosting
from job_apply_agent.preferences import merge_defaults
from job_apply_agent.search.base import SourceResult
from job_apply_agent.search.events import EventBus
from job_apply_agent.search.pipeline import CandidateDocs, SearchAlreadyRunning, SearchRunner, refilter_jobs
from job_apply_agent.search.scoring import JobScore, ScoreOutcome
from job_apply_agent.timeutil import iso

NOW = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)


def jobs_a():
    return [
        JobPosting(url="https://gh/1", title="Data Analyst", company="Acme", location="Toronto, ON",
                   description="SQL " * 100, external_id="1", board="acme"),
        JobPosting(url="https://gh/2", title="Sales Rep", company="Acme", location="Toronto, ON", external_id="2"),
        JobPosting(url="https://gh/3", title="Data Analyst", company="Acme", location="Austin, TX", external_id="3"),
    ]


def source(make=jobs_a, *, error=None, skipped=None, seen=None, gate: asyncio.Event | None = None):
    async def fetch(_ctx):
        if gate is not None:
            await gate.wait()
        if error:
            raise error
        return SourceResult(postings=make(), seen_ids=seen or {}, skipped=skipped)
    return fetch


class FakeScorer:
    def __init__(self, outcome_fn=None):
        self.calls = []
        self.outcome_fn = outcome_fn

    async def __call__(self, jobs, **kwargs):
        self.calls.append((jobs, kwargs))
        kwargs["on_progress"](len(jobs), len(jobs))
        if self.outcome_fn:
            return self.outcome_fn(jobs)
        return ScoreOutcome(scores=[JobScore(j["id"], 80, "good", ["SQL"], [], "fit") for j in jobs])


DEFAULT_DOCS = CandidateDocs("my resume")


def make_runner(db, sources, *, docs=DEFAULT_DOCS, scorer=None, prefs=None, events=None):
    return SearchRunner(
        db, events=events or EventBus(), load_prefs=lambda: merge_defaults(prefs or {}), load_companies=lambda: [],
        load_env=lambda: {}, load_docs=lambda: docs, http_factory=FakeHttp, scorer=scorer or FakeScorer(),
        sources=sources, now_fn=lambda: NOW,
    )


@pytest.fixture
def db():
    d = Database(":memory:")
    yield d
    d.close()


async def test_run_stores_relevant_jobs_and_scores_them(db):
    scorer = FakeScorer()
    runner = make_runner(db, {"greenhouse": source()}, scorer=scorer)
    run_id = await runner.run(trigger="manual")
    [job] = db.list_jobs(now=iso(NOW))
    assert job["title"] == "Data Analyst" and job["location_label"] == "Toronto/GTA" and job["score"] == 80
    run = db.get_run(run_id)
    assert run["sources"]["greenhouse"] == {"status": "ok", "fetched": 3, "relevant": 1, "new": 1, "warnings": []}
    assert run["sources"]["scoring"]["status"] == "ok" and run["scored"] == 1
    assert scorer.calls[0][1]["model"] == "claude-haiku-5-5"
    assert db.source_states()["greenhouse"]["last_success_at"] == iso(NOW)


async def test_second_run_scores_nothing(db):
    scorer = FakeScorer()
    runner = make_runner(db, {"greenhouse": source()}, scorer=scorer)
    await runner.run(trigger="manual")
    second = await runner.run(trigger="schedule")
    assert len(scorer.calls) == 1
    assert db.get_run(second)["sources"]["scoring"]["message"] == "Nothing new to score."
    assert db.get_run(second)["sources"]["greenhouse"]["new"] == 0


async def test_resume_change_rescores_everything(db):
    scorer = FakeScorer()
    docs = {"value": CandidateDocs("v1")}
    runner = SearchRunner(db, events=EventBus(), load_prefs=lambda: merge_defaults({}), load_companies=lambda: [],
                          load_env=lambda: {}, load_docs=lambda: docs["value"], http_factory=FakeHttp,
                          scorer=scorer, sources={"greenhouse": source()}, now_fn=lambda: NOW)
    await runner.run(trigger="manual")
    docs["value"] = CandidateDocs("v2")
    await runner.run(trigger="manual", sources=[])  # score-only run
    assert len(scorer.calls) == 2 and len(scorer.calls[1][0]) == 1


async def test_missing_resume_skips_scoring(db):
    scorer = FakeScorer()
    run_id = await make_runner(db, {"greenhouse": source()}, docs=None, scorer=scorer).run(trigger="manual")
    assert scorer.calls == []
    assert db.get_run(run_id)["sources"]["scoring"]["status"] == "skipped"
    assert db.list_jobs(now=iso(NOW))[0]["score"] is None


async def test_failing_source_does_not_stop_others(db):
    runner = make_runner(db, {"greenhouse": source(), "lever": source(error=RuntimeError("HTML instead of JSON"))})
    run = db.get_run(await runner.run(trigger="manual"))
    assert run["sources"]["lever"] == {"status": "error", "error": "HTML instead of JSON"}
    assert run["sources"]["greenhouse"]["status"] == "ok" and run["error"] is None
    assert db.source_states()["lever"]["last_success_at"] is None


async def test_skipped_and_partial_sources(db):
    def with_warning():
        return jobs_a()[:1]

    async def warn(_ctx):
        return SourceResult(postings=with_warning(), warnings=["Shopify: HTTP 404"])

    runner = make_runner(db, {"jsearch": source(skipped="no API key"), "ashby": warn})
    run = db.get_run(await runner.run(trigger="manual"))
    assert run["sources"]["jsearch"] == {"status": "skipped", "reason": "no API key"}
    assert run["sources"]["ashby"]["status"] == "partial"


async def test_usage_limit_reported(db):
    scorer = FakeScorer(lambda jobs: ScoreOutcome(failed=[j["id"] for j in jobs], usage_limited=True,
                                                  errors=["usage limit"]))
    run = db.get_run(await make_runner(db, {"greenhouse": source()}, scorer=scorer).run(trigger="manual"))
    assert run["sources"]["scoring"]["status"] == "limited"


async def test_only_one_run_at_a_time(db):
    gate = asyncio.Event()
    runner = make_runner(db, {"greenhouse": source(gate=gate)})
    first = asyncio.create_task(runner.run(trigger="manual"))
    await asyncio.sleep(0)
    assert runner.running
    with pytest.raises(SearchAlreadyRunning):
        await runner.run(trigger="schedule")
    gate.set()
    await first
    assert not runner.running


async def test_explicit_sources_and_unknown_names(db):
    called = []

    async def lever(_ctx):
        called.append("lever")
        return SourceResult()

    runner = make_runner(db, {"greenhouse": source(), "lever": lever})
    run = db.get_run(await runner.run(trigger="manual", sources=["lever"]))
    assert called == ["lever"] and "greenhouse" not in run["sources"]
    with pytest.raises(ValueError):
        await runner.run(trigger="manual", sources=["monster"])


async def test_disabled_sources_are_skipped_by_default(db):
    runner = make_runner(db, {"greenhouse": source()}, prefs={"sources": {"greenhouse": {"enabled": False}}})
    run = db.get_run(await runner.run(trigger="manual"))
    assert "greenhouse" not in run["sources"]


async def test_events_are_published(db):
    events = EventBus()
    queue = events.subscribe()
    await make_runner(db, {"greenhouse": source()}, events=events).run(trigger="manual")
    types = []
    while not queue.empty():
        types.append(queue.get_nowait()["type"])
    assert types[0] == "run.started" and types[-1] == "run.finished"
    assert "run.source" in types and "run.scoring" in types


async def test_closed_jobs_tracked_from_seen_ids(db):
    runner = make_runner(db, {"greenhouse": source(seen={"acme": {"1"}})})
    await runner.run(trigger="manual")
    runner.sources["greenhouse"] = source(make=lambda: [], seen={"acme": set()})
    await runner.run(trigger="manual")
    await runner.run(trigger="manual")
    assert db.list_jobs(now=iso(NOW)) == []


async def test_refilter_after_role_change(db):
    await make_runner(db, {"greenhouse": source()}).run(trigger="manual")
    changed = refilter_jobs(db, merge_defaults({"role_terms": ["data scientist"]}))
    assert changed == 1 and db.list_jobs(now=iso(NOW)) == []
    assert refilter_jobs(db, merge_defaults({})) == 1


def test_event_bus_drops_when_full():
    bus = EventBus(maxsize=1)
    queue = bus.subscribe()
    bus.publish({"type": "a"})
    bus.publish({"type": "b"})  # dropped, no exception
    assert queue.qsize() == 1
    bus.unsubscribe(queue)
    bus.publish({"type": "c"})
    assert queue.qsize() == 1
