from datetime import datetime, timezone

from fakes import make_ctx

from job_apply_agent.search.sources import SOURCES, workday

TD = {"name": "TD Bank", "ats": "workday", "host": "td.wd3.myworkdayjobs.com", "tenant": "td",
      "site": "TD_Bank_Careers", "enabled": True}
BASE = "https://td.wd3.myworkdayjobs.com/wday/cxs/td/TD_Bank_Careers"
PATH = "/job/Toronto-Ontario/Sr-IT-Data-Analyst_R_1520114"
LIST = {"total": 2, "jobPostings": [
    {"title": "Sr. IT Data Analyst", "externalPath": PATH, "locationsText": "3 Locations", "postedOn": "Posted 4 Days Ago"},
    {"title": "Branch Manager", "externalPath": "/job/x/Branch_R_1", "locationsText": "Ottawa", "postedOn": "Posted Today"},
]}
DETAIL = {"jobPostingInfo": {"title": "Sr. IT Data Analyst", "jobDescription": "<p>Build <b>reports</b>.</p>",
                             "location": "Toronto, Ontario", "additionalLocations": ["Ottawa, Ontario"],
                             "startDate": "2026-11-05", "timeType": "Full time", "remoteType": "Office Focused",
                             "externalUrl": f"https://td.wd3.myworkdayjobs.com/TD_Bank_Careers{PATH}",
                             "country": {"descriptor": "Canada"}}}
NOW = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)


async def test_workday_searches_terms_and_fetches_details():
    ctx = make_ctx(companies=[TD], prefs={"sources": {"workday": {"search_terms": ["data analyst", "analytics"]}}},
                   routes={f"{BASE}/jobs": LIST, f"{BASE}{PATH}": DETAIL})
    result = await SOURCES["workday"](ctx)
    [p] = result.postings  # same job found by both terms is fetched once; Branch Manager filtered out
    assert p.location == "Toronto, Ontario; Ottawa, Ontario" and p.country == "Canada"
    assert p.posted_at == "2026-11-05T00:00:00+00:00" and p.description == "Build reports."
    assert p.external_id == PATH and p.board == "td/TD_Bank_Careers" and p.url.endswith(PATH)
    posts = [c for c in ctx.http.calls if c[0] == "POST"]
    assert [c[2]["searchText"] for c in posts] == ["data analyst", "analytics"]
    assert result.seen_ids == {}  # keyword search can't see the whole board


async def test_workday_known_job_uses_list_data_only():
    ctx = make_ctx(companies=[TD], known=[("workday", PATH)], routes={f"{BASE}/jobs": LIST})
    result = await workday.fetch(ctx)
    [p] = result.postings
    assert p.description == "" and p.description_is_partial is True and p.location == "3 Locations"
    assert all(c[0] == "POST" for c in ctx.http.calls)


def test_relative_posted_date_when_no_start_date():
    item = {"title": "Data Analyst", "externalPath": "/job/a", "locationsText": "Toronto", "postedOn": "Posted 4 Days Ago"}
    p = workday.to_posting(TD, item, None, NOW)
    assert p.posted_at == "2026-11-05T12:00:00+00:00"
