from fakes import make_ctx

from job_apply_agent.search.http import HttpError
from job_apply_agent.search.sources import BOARD_LISTERS, SOURCES, ashby, greenhouse, lever

GH = {"name": "Faire", "ats": "greenhouse", "board": "faire", "enabled": True}
LV = {"name": "Achievers", "ats": "lever", "board": "achievers", "enabled": True}
AB = {"name": "Wealthsimple", "ats": "ashby", "board": "wealthsimple", "enabled": True}

GH_LIST = {"jobs": [
    {"id": 101, "title": "Senior Data Analyst", "location": {"name": "Toronto, ON"},
     "absolute_url": "https://boards.greenhouse.io/faire/jobs/101?gh_jid=101",
     "first_published": "2026-11-07T15:23:54-04:00", "updated_at": "2026-11-08T09:00:00-04:00",
     "metadata": [{"name": "Employment Type", "value": "Regular"}]},
    {"id": 102, "title": "Account Executive", "location": {"name": "New York, NY"},
     "absolute_url": "https://boards.greenhouse.io/faire/jobs/102", "updated_at": "2026-11-08T09:00:00-04:00"},
    {"id": 103, "title": "Data Engineer", "location": {"name": "Kitchener-Waterloo, ON"},
     "absolute_url": "https://boards.greenhouse.io/faire/jobs/103", "updated_at": "2026-11-08T09:00:00-04:00"},
]}
GH_DETAIL = {"id": 101, "content": "&lt;p&gt;&lt;strong&gt;About&lt;/strong&gt;&lt;/p&gt;&lt;ul&gt;&lt;li&gt;SQL&lt;/li&gt;&lt;/ul&gt;"}


async def test_greenhouse_fetches_details_only_for_matching_titles():
    ctx = make_ctx(companies=[GH], routes={
        "https://boards-api.greenhouse.io/v1/boards/faire/jobs/101": GH_DETAIL,
        "https://boards-api.greenhouse.io/v1/boards/faire/jobs/103": HttpError(404, "gone"),
        "https://boards-api.greenhouse.io/v1/boards/faire/jobs": GH_LIST,
    })
    result = await SOURCES["greenhouse"](ctx)
    assert [p.title for p in result.postings] == ["Senior Data Analyst", "Data Engineer"]
    first, second = result.postings
    assert first.source == "greenhouse" and first.external_id == "101" and first.board == "faire"
    assert first.company == "Faire" and first.location == "Toronto, ON"
    assert first.posted_at == "2026-11-07T19:23:54+00:00" and first.employment_type == "Regular"
    assert "About" in first.description and "- SQL" in first.description
    assert second.description == "" and second.description_is_partial is True  # detail 404 -> partial
    assert result.seen_ids == {"faire": {"101", "102", "103"}}
    detail_calls = [c for c in ctx.http.calls if c[1].endswith("/102")]
    assert detail_calls == []


async def test_greenhouse_skips_detail_for_known_jobs():
    ctx = make_ctx(companies=[GH], known=[("greenhouse", "101"), ("greenhouse", "103")],
                   routes={"https://boards-api.greenhouse.io/v1/boards/faire/jobs": GH_LIST})
    result = await greenhouse.fetch(ctx)
    assert len(result.postings) == 2 and len(ctx.http.calls) == 1


LV_LIST = [
    {"id": "a1", "text": "Data  Analyst", "categories": {"location": "Toronto", "allLocations": ["Toronto", "Remote"],
     "commitment": "Full-time permanent"}, "workplaceType": "hybrid", "createdAt": 1791216082758,
     "hostedUrl": "https://jobs.lever.co/achievers/a1", "country": "CA",
     "descriptionPlain": "We need an analyst.", "lists": [{"text": "What you'll do", "content": "<li>SQL</li><li>Looker</li>"}],
     "additionalPlain": "Benefits..."},
    {"id": "a2", "text": "Customer Success Associate", "categories": {"location": "Toronto"}, "hostedUrl": "x"},
]


async def test_lever_maps_fields():
    ctx = make_ctx(companies=[LV], routes={"https://api.lever.co/v0/postings/achievers": LV_LIST})
    result = await lever.fetch(ctx)
    [p] = result.postings
    assert p.title == "Data Analyst" and p.location == "Toronto; Remote" and p.remote is False
    assert p.country == "CA" and p.employment_type == "Full-time permanent"
    assert "What you'll do\n- SQL\n- Looker" in p.description and p.description.endswith("Benefits...")
    assert p.posted_at.startswith("2026-") and result.seen_ids == {"achievers": {"a1", "a2"}}
    assert ctx.http.calls[0][2] == {"mode": "json"}


AB_LIST = {"jobs": [
    {"id": "u1", "title": "Data Scientist", "location": "Remote (Canada)", "secondaryLocations": [],
     "isRemote": True, "workplaceType": "Remote", "publishedAt": "2026-11-05T17:56:22.425+00:00",
     "jobUrl": "https://jobs.ashbyhq.com/wealthsimple/u1", "descriptionPlain": "Model things.",
     "employmentType": "FullTime", "address": {"postalAddress": {"addressCountry": "Canada"}}, "isListed": True},
    {"id": "u2", "title": "Data Analyst", "location": "Toronto", "secondaryLocations": [{"location": "Montreal"}],
     "isListed": False, "jobUrl": "x"},
]}


async def test_ashby_maps_fields_and_skips_unlisted():
    ctx = make_ctx(companies=[AB], routes={"https://api.ashbyhq.com/posting-api/job-board/wealthsimple": AB_LIST})
    result = await ashby.fetch(ctx)
    [p] = result.postings
    assert p.remote is True and p.country == "Canada" and p.location == "Remote (Canada)"
    assert p.posted_at == "2026-11-05T17:56:22+00:00" and p.url.endswith("/u1")
    assert result.seen_ids == {"wealthsimple": {"u1"}}


async def test_board_listers_for_settings_test_button():
    ctx = make_ctx(routes={"https://api.lever.co/v0/postings/achievers": LV_LIST})
    assert len(await BOARD_LISTERS["lever"](ctx.http, LV)) == 2
