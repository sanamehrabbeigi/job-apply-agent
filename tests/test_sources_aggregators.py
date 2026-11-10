from datetime import datetime, timedelta, timezone

import pytest
from fakes import make_ctx

from job_apply_agent.search.http import HttpError
from job_apply_agent.search.sources import SOURCES, jsearch

JS_URL = "https://jsearch.p.rapidapi.com/search"
JOB = {"job_id": "js1", "job_title": "Data Analyst", "employer_name": "Shopify", "job_city": "Toronto",
       "job_state": "Ontario", "job_country": "CA", "job_is_remote": False,
       "job_posted_at_datetime_utc": "2026-11-09T08:00:00.000Z", "job_apply_link": "https://apply/js1",
       "job_description": "Full description", "job_publisher": "LinkedIn", "job_employment_type": "Full-time"}
OTHER = {**JOB, "job_id": "js2", "job_title": "Store Associate"}
NOW = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)


def test_parse_jsearch_both_shapes():
    assert jsearch.parse_jsearch({"status": "OK", "data": [JOB]}) == [JOB]
    assert jsearch.parse_jsearch({"status": "OK", "data": {"jobs": [JOB], "cursor": "c"}}) == [JOB]
    with pytest.raises(ValueError):
        jsearch.parse_jsearch({"message": "You are not subscribed"})


def test_jsearch_to_posting():
    p = jsearch.to_posting(JOB)
    assert (p.title, p.company, p.location, p.country) == ("Data Analyst", "Shopify", "Toronto, Ontario", "CA")
    assert p.posted_at == "2026-11-09T08:00:00+00:00" and p.details == {"Publisher": "LinkedIn"}
    assert p.remote is False and p.source == "jsearch" and p.url == "https://apply/js1"


async def test_jsearch_skips_without_key():
    result = await SOURCES["jsearch"](make_ctx())
    assert result.skipped.startswith("no API key")


async def test_jsearch_runs_queries_filters_titles_and_counts_quota():
    prefs = {"sources": {"jsearch": {"queries": ["q1", "q2"], "budget": 5}}}
    ctx = make_ctx(prefs=prefs, env={"JSEARCH_API_KEY": "k"}, routes={JS_URL: {"data": [JOB, OTHER]}},
                   last_success={"jsearch": datetime.now(timezone.utc) - timedelta(hours=2)}, now=NOW)
    result = await jsearch.fetch(ctx)
    assert [p.external_id for p in result.postings] == ["js1", "js1"]  # dedupe happens in the pipeline
    _method, _url, params, headers = ctx.http.calls[0]
    assert params == {"query": "q1", "country": "ca", "date_posted": "today", "num_pages": 1}
    assert headers == {"X-RapidAPI-Key": "k", "X-RapidAPI-Host": "jsearch.p.rapidapi.com"}
    assert ctx.quota.remaining("jsearch") == 3


async def test_jsearch_quota_reached_is_a_skip_not_an_error():
    ctx = make_ctx(prefs={"sources": {"jsearch": {"budget": 0}}}, env={"JSEARCH_API_KEY": "k"}, now=NOW)
    result = await jsearch.fetch(ctx)
    assert result.skipped == "free quota reached until 2026-12-01" and ctx.http.calls == []


async def test_jsearch_bad_key_raises_and_other_errors_warn():
    ctx = make_ctx(env={"JSEARCH_API_KEY": "k"}, routes={JS_URL: HttpError(403, JS_URL)})
    with pytest.raises(HttpError):
        await jsearch.fetch(ctx)
    ctx = make_ctx(prefs={"sources": {"jsearch": {"queries": ["q1"]}}}, env={"JSEARCH_API_KEY": "k"},
                   routes={JS_URL: HttpError(500, JS_URL)})
    with pytest.raises(HttpError, match="every JSearch request failed"):  # all failed -> error, not success
        await jsearch.fetch(ctx)


AZ_URL = "https://api.adzuna.com/v1/api/jobs/ca/search/1"
AZ = {"results": [
    {"id": "az1", "title": "<strong>Data</strong> Scientist", "description": "Snippet only…",
     "redirect_url": "https://www.adzuna.ca/details/az1", "created": "2026-11-08T18:07:39Z",
     "company": {"display_name": "Sun Life"}, "location": {"display_name": "Toronto, Ontario"},
     "contract_time": "full_time"},
]}


async def test_adzuna_maps_and_marks_partial():
    prefs = {"sources": {"adzuna": {"what": ["data scientist"], "where": ["Toronto"], "budget": 10}}}
    ctx = make_ctx(prefs=prefs, env={"ADZUNA_APP_ID": "id", "ADZUNA_APP_KEY": "key"}, routes={AZ_URL: AZ})
    result = await SOURCES["adzuna"](ctx)
    [p] = result.postings
    assert p.title == "Data Scientist" and p.company == "Sun Life" and p.description_is_partial is True
    params = ctx.http.calls[0][2]
    assert params["app_id"] == "id" and params["what"] == "data scientist" and params["where"] == "Toronto"
    assert params["max_days_old"] == 3 and params["sort_by"] == "date"


async def test_adzuna_skips_without_keys():
    assert (await SOURCES["adzuna"](make_ctx(env={"ADZUNA_APP_ID": "id"}))).skipped.startswith("no API key")


def test_null_fields_do_not_break_parsing():
    p = jsearch.to_posting({**JOB, "employer_name": None, "job_title": None, "job_description": None})
    assert p.company == "" and p.title == "" and p.description == ""
    from job_apply_agent.search.sources import adzuna

    q = adzuna.to_posting({"id": "1", "title": None, "description": None, "company": None, "location": None})
    assert q.title == "" and q.company == "" and q.location == ""


async def test_quota_sources_never_retry_and_stop_at_rate_limit():
    from job_apply_agent.search.http import RateLimited

    prefs = {"sources": {"jsearch": {"queries": ["q1", "q2", "q3"], "budget": 10}}}
    ok = make_ctx(prefs=prefs, env={"JSEARCH_API_KEY": "k"}, routes={JS_URL: {"data": [JOB]}})
    await jsearch.fetch(ok)
    assert ok.http.retries == [0, 0, 0]
    limited = make_ctx(prefs=prefs, env={"JSEARCH_API_KEY": "k"}, routes={JS_URL: RateLimited(429, JS_URL)})
    with pytest.raises(HttpError):
        await jsearch.fetch(limited)
    assert len(limited.http.calls) == 1  # stopped at the first 429


async def test_adzuna_all_failed_is_an_error():
    prefs = {"sources": {"adzuna": {"what": ["data analyst"], "where": ["Toronto"], "budget": 10}}}
    ctx = make_ctx(prefs=prefs, env={"ADZUNA_APP_ID": "id", "ADZUNA_APP_KEY": "key"},
                   routes={AZ_URL: HttpError(500, AZ_URL)})
    with pytest.raises(HttpError, match="every Adzuna request failed"):
        await SOURCES["adzuna"](ctx)
    assert ctx.http.retries == [0]
