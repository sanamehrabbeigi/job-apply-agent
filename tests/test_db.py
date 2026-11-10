from datetime import datetime, timedelta, timezone

import pytest

from job_apply_agent.db import Database
from job_apply_agent.jobs import JobPosting
from job_apply_agent.timeutil import iso, iso_or_none, parse_datetime, parse_relative_posted

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
T = iso(NOW)


def posting(**kw) -> JobPosting:
    base = dict(url="https://jobs.example/1", title="Data Analyst", company="Acme", location="Toronto, ON",
                description="Analyse data. " * 30, source="greenhouse", external_id="1", board="acme")
    base.update(kw)
    return JobPosting(**base)


def add(db, p, key="acme|data analyst|toronto", relevant=True, run_id=None, now=T):
    return db.upsert_posting(p, dedupe_key=key, canonical_url=p.url, relevant=relevant,
                             location_label="Toronto/GTA", run_id=run_id, now=now)


@pytest.fixture
def db():
    d = Database(":memory:")
    yield d
    d.close()


def test_time_helpers():
    assert iso_or_none("2026-11-05T17:56:22.425+00:00") == "2026-11-05T17:56:22+00:00"
    assert iso_or_none("2026-10-07T15:23:54-04:00") == "2026-10-07T19:23:54+00:00"
    assert iso_or_none(1791216082758) == iso(datetime.fromtimestamp(1791216082.758, tz=timezone.utc))
    assert parse_datetime("2026-11-08").day == 8 and parse_datetime("garbage") is None
    assert parse_relative_posted("Posted 4 Days Ago", NOW) == NOW - timedelta(days=4)
    assert parse_relative_posted("Posted 30+ Days Ago", NOW) == NOW - timedelta(days=30)
    assert parse_relative_posted("Posted Today", NOW) == NOW
    assert parse_relative_posted("Posted Yesterday", NOW) == NOW - timedelta(days=1)


def test_upsert_new_then_same_link_updates(db):
    run = db.start_run("manual", T)
    job_id, new = add(db, posting(), run_id=run)
    assert new is True
    again, new2 = add(db, posting(description="short"), run_id=run)
    assert again == job_id and new2 is False
    job = db.get_job(job_id)
    assert job["description"].startswith("Analyse data.")  # shorter text never replaces longer
    assert job["links"] == [{"source": "greenhouse", "url": "https://jobs.example/1"}]


def test_cross_source_merge_adds_link(db):
    job_id, _ = add(db, posting())
    other, new = add(db, posting(source="jsearch", external_id="js-9", url="https://apply.example/9"))
    assert other == job_id and new is False
    assert {link["source"] for link in db.get_job(job_id)["links"]} == {"greenhouse", "jsearch"}
    assert db.list_jobs(now=T)[0]["sources"] == ["greenhouse", "jsearch"]


def test_partial_description_replaced_by_full(db):
    job_id, _ = add(db, posting(source="adzuna", external_id="a1", description="snippet", description_is_partial=True))
    add(db, posting(source="lever", external_id="l1", url="https://jobs.lever.co/acme/l1"))
    job = db.get_job(job_id)
    assert job["description_is_partial"] is False and job["description"].startswith("Analyse")


def test_mark_missing_closes_after_two_runs(db):
    job_id, _ = add(db, posting())
    assert db.mark_missing("greenhouse", "acme", set()) == 0
    assert db.mark_missing("greenhouse", "acme", set()) == 1
    assert db.get_job(job_id)["closed"] is True
    assert db.list_jobs(now=T) == []
    assert len(db.list_jobs(now=T, include_closed=True)) == 1
    add(db, posting())  # seen again -> reopened
    assert db.get_job(job_id)["closed"] is False


def test_stale_jobs_hidden(db):
    add(db, posting(), now=iso(NOW - timedelta(days=30)))
    assert db.list_jobs(now=T) == []


def test_new_tab_rule_excludes_first_run_backlog(db):
    first = db.start_run("manual", T)
    add(db, posting(posted_at=None), run_id=first)  # backlog from very first run
    second = db.start_run("schedule", T)
    add(db, posting(external_id="2", url="https://jobs.example/2", title="Data Scientist"), key="k2", run_id=second)
    add(db, posting(external_id="3", url="https://jobs.example/3", title="Data Engineer",
                    posted_at=iso(NOW - timedelta(hours=3))), key="k3", run_id=first)
    titles = {j["title"] for j in db.list_jobs(now=T, tab="new")}
    assert titles == {"Data Scientist", "Data Engineer"}
    assert db.counts(T)["new_24h"] == 2


def test_sorting_filters_and_scores(db):
    a, _ = add(db, posting(), key="a")
    b, _ = add(db, posting(external_id="2", url="https://jobs.example/2", title="BI Analyst", company="Beta"), key="b")
    add(db, posting(external_id="3", url="https://jobs.example/3", title="Data Engineer", company="Zed"), key="c")
    db.save_score(a, score=60, summary="ok", reasons=["SQL"], gaps=["dbt"], seniority_fit="fit", model="m",
                  profile_hash="h1", now=T)
    db.save_score(b, score=90, summary="great", reasons=[], gaps=[], seniority_fit="fit", model="m",
                  profile_hash="h1", now=T)
    assert [j["score"] for j in db.list_jobs(now=T)] == [90, 60, None]  # unscored last
    assert [j["company"] for j in db.list_jobs(now=T, sort="company", order="asc")] == ["Acme", "Beta", "Zed"]
    assert [j["title"] for j in db.list_jobs(now=T, role="engineer")] == ["Data Engineer"]
    assert [j["score"] for j in db.list_jobs(now=T, min_score=70)] == [90]
    assert {j["id"] for j in db.jobs_to_score("h1")} == {3}
    assert len(db.jobs_to_score("h2")) == 3  # resume changed -> everything re-scored
    assert db.get_job(a)["reasons"] == ["SQL"]


def test_update_job_and_hide_done(db):
    job_id, _ = add(db, posting())
    assert db.update_job(job_id, status="applied", notes="sent")["status"] == "applied"
    assert db.list_jobs(now=T, hide_done=True) == []
    with pytest.raises(ValueError):
        db.update_job(job_id, status="bogus")
    assert db.update_job(999, status="saved") is None


def test_irrelevant_jobs_never_listed_or_scored(db):
    add(db, posting(title="Sales Rep"), relevant=False)
    assert db.list_jobs(now=T) == [] and db.jobs_to_score("h") == []


def test_runs_quota_and_source_state(db):
    run = db.start_run("manual", T)
    db.finish_run(run, sources={"lever": {"status": "ok", "fetched": 3}}, scored=2, error=None, now=T)
    assert db.get_run(run)["sources"]["lever"]["fetched"] == 3
    assert db.list_runs()[0]["scored"] == 2 and db.first_run_id() == run
    db.quota_add("jsearch", "2026-11")
    db.quota_add("jsearch", "2026-11", 2)
    assert db.quota_used("jsearch", "2026-11") == 3 and db.quota_used("jsearch", "2026-12") == 0
    db.mark_source_attempt("lever", T, success=False)
    assert db.source_states()["lever"] == {"last_attempt_at": T, "last_success_at": None}
    db.mark_source_attempt("lever", T, success=True)
    assert db.source_states()["lever"]["last_success_at"] == T
    assert db.has_link("greenhouse", "1") is False


def test_relevant_posting_merged_into_irrelevant_job_takes_its_location(db):
    job_id, _ = add(db, posting(location="Remote - US"), relevant=False)
    add(db, posting(source="lever", external_id="l9", url="https://jobs.lever.co/acme/l9", location="Remote - Canada"))
    job = db.get_job(job_id)
    assert job["relevant"] is True and job["location"] == "Remote - Canada"


def test_known_complete_only_when_full_description(db):
    add(db, posting(source="linkedin", external_id="li1", description="", description_is_partial=True))
    assert db.has_link("linkedin", "li1") is True
    assert db.is_known_complete("linkedin", "li1") is False
    add(db, posting())  # greenhouse link with a full description
    assert db.is_known_complete("greenhouse", "1") is True


def test_full_description_arriving_later_clears_score(db):
    job_id, _ = add(db, posting(source="linkedin", external_id="li1", description="", description_is_partial=True))
    db.save_score(job_id, score=40, summary="title only", reasons=[], gaps=[], seniority_fit="fit", model="m",
                  profile_hash="h", now=T)
    add(db, posting(source="linkedin", external_id="li1", description="Full text " * 50))
    assert db.get_job(job_id)["score"] is None
    assert [j["id"] for j in db.jobs_to_score("h")] == [job_id]


def test_date_only_posting_from_yesterday_found_today_is_new(db):
    db.start_run("manual", T)  # first run
    second = db.start_run("schedule", T)
    # LinkedIn/Workday give only a date: posted yesterday, stored as midnight UTC; first seen this morning
    add(db, posting(posted_at=iso(datetime(2026, 11, 8, tzinfo=timezone.utc))), run_id=second,
        now=iso(datetime(2026, 11, 9, 11, 0, tzinfo=timezone.utc)))
    assert len(db.list_jobs(now=T, tab="new")) == 1
