from fakes import make_ctx
from test_jobs import LINKEDIN_PAGE

from job_apply_agent.search.http import RateLimited
from job_apply_agent.search.sources import SOURCES, linkedin

SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/"


def card(job_id: str, title: str, company="Example Co", location="Toronto, Ontario, Canada") -> str:
    return f"""<li>
  <div class="base-card relative base-search-card job-search-card" data-entity-urn="urn:li:jobPosting:{job_id}">
    <a class="base-card__full-link" href="https://ca.linkedin.com/jobs/view/x-{job_id}"></a>
    <div class="base-search-card__info">
      <h3 class="base-search-card__title">
            {title}
      </h3>
      <h4 class="base-search-card__subtitle"><a class="hidden-nested-link" href="#">{company}</a></h4>
      <div class="base-search-card__metadata">
        <span class="job-search-card__location">{location}</span>
        <time class="job-search-card__listdate--new" datetime="2026-11-08">1 day ago</time>
      </div>
    </div>
  </div>
</li>"""


PAGE = card("111", "Data Analyst") + card("222", "Nurse") + card("111", "Data Analyst")


def test_parse_search_cards():
    cards = linkedin.parse_search(PAGE)
    assert [c["id"] for c in cards] == ["111", "222"]
    assert cards[0] == {"id": "111", "title": "Data Analyst", "company": "Example Co",
                        "location": "Toronto, Ontario, Canada", "posted": "2026-11-08"}


async def test_linkedin_fetches_details_for_matching_titles():
    prefs = {"sources": {"linkedin": {"keywords": ["data analyst"], "locations": ["Toronto, Ontario, Canada"],
                                      "remote_canada": False, "max_pages": 1}}}
    ctx = make_ctx(prefs=prefs, routes={SEARCH: PAGE, DETAIL: LINKEDIN_PAGE})
    result = await SOURCES["linkedin"](ctx)
    [p] = result.postings
    assert p.source == "linkedin" and p.external_id == "111" and p.company == "Example Co"
    assert p.posted_at == "2026-11-08T00:00:00+00:00" and "Power BI" in p.description
    assert p.url == "https://www.linkedin.com/jobs/view/111/"
    _m, _u, params, _h = ctx.http.calls[0]
    assert params["keywords"] == "data analyst" and params["f_TPR"] == "r604800"


async def test_linkedin_rate_limit_keeps_found_cards_as_partial():
    prefs = {"sources": {"linkedin": {"keywords": ["data analyst"], "locations": ["Toronto, Ontario, Canada"],
                                      "remote_canada": False, "max_pages": 1}}}
    ctx = make_ctx(prefs=prefs, routes={SEARCH: PAGE, DETAIL: RateLimited(429, DETAIL)})
    result = await linkedin.fetch(ctx)
    [p] = result.postings
    assert p.description_is_partial is True and p.title == "Data Analyst"
    assert "limiting requests" in result.warnings[0]


async def test_linkedin_blocked_immediately_is_a_warning():
    ctx = make_ctx(routes={SEARCH: RateLimited(429, SEARCH)})
    result = await linkedin.fetch(ctx)
    assert result.postings == [] and result.warnings


async def test_remote_canada_search_uses_work_type_filter():
    prefs = {"sources": {"linkedin": {"keywords": ["data analyst"], "locations": [], "remote_canada": True,
                                      "max_pages": 1}}}
    ctx = make_ctx(prefs=prefs, known=[("linkedin", "111")], routes={SEARCH: PAGE})
    result = await linkedin.fetch(ctx)
    assert ctx.http.calls[0][2]["f_WT"] == "2" and ctx.http.calls[0][2]["location"] == "Canada"
    assert result.postings[0].remote is True
