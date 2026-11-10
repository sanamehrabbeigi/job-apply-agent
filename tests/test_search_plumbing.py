from datetime import datetime, timezone
from pathlib import Path

import pytest
from fakes import make_ctx

from job_apply_agent.db import Database
from job_apply_agent.jobs import JobPosting
from job_apply_agent.search import companies as companies_mod
from job_apply_agent.search.base import gather_companies
from job_apply_agent.search.http import Http, HttpError, RateLimited, Response
from job_apply_agent.search.quota import QuotaExceeded, QuotaGuard, next_reset, period_key

NOW = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)


class ScriptedFetch:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url, headers, body))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


async def no_sleep(_seconds):
    return None


async def test_http_retries_5xx_then_succeeds():
    fetch = ScriptedFetch(Response(503, ""), Response(200, '{"ok": true}'))
    http = Http(fetch, sleep=no_sleep, default_delay=0)
    assert await http.get_json("https://api.example/x", params={"q": "data analyst"}) == {"ok": True}
    assert fetch.calls[0][1] == "https://api.example/x?q=data+analyst"
    assert len(fetch.calls) == 2


async def test_http_network_error_after_retries():
    fetch = ScriptedFetch(OSError("down"), OSError("down"), OSError("down"))
    http = Http(fetch, sleep=no_sleep, default_delay=0)
    with pytest.raises(HttpError, match="Couldn't reach"):
        await http.get_text("https://api.example/x")


async def test_http_429_without_retry_raises_rate_limited():
    http = Http(ScriptedFetch(Response(429, "")), sleep=no_sleep, default_delay=0)
    with pytest.raises(RateLimited):
        await http.get_text("https://www.linkedin.com/x", retry_429=False)


async def test_http_4xx_and_bad_json():
    http = Http(ScriptedFetch(Response(404, "nope"), Response(200, "<html>")), sleep=no_sleep, default_delay=0)
    with pytest.raises(HttpError) as err:
        await http.get_json("https://api.example/a")
    assert err.value.status == 404
    with pytest.raises(HttpError, match="JSON"):
        await http.get_json("https://api.example/b")


async def test_http_post_sends_json_body():
    fetch = ScriptedFetch(Response(200, "{}"))
    await Http(fetch, sleep=no_sleep, default_delay=0).post_json("https://wd/x", {"a": 1})
    method, _url, headers, body = fetch.calls[0]
    assert method == "POST" and body == b'{"a": 1}' and headers["Content-Type"] == "application/json"


def test_quota_guard_budget_and_reset():
    db = Database(":memory:")
    guard = QuotaGuard(db, {"jsearch": (2, "month")}, now_fn=lambda: NOW)
    assert guard.remaining("jsearch") == 2 and guard.remaining("greenhouse") is None
    guard.consume("jsearch")
    guard.consume("jsearch")
    with pytest.raises(QuotaExceeded, match="2026-12-01"):
        guard.consume("jsearch")
    assert guard.usage()["jsearch"] == {"used": 2, "budget": 2, "period": "month", "resets": "2026-12-01"}
    assert period_key("day", NOW) == "2026-11-09" and str(next_reset("day", NOW)) == "2026-11-10"


def test_companies_default_file_valid_and_roundtrip(tmp_path: Path):
    items = companies_mod.load_companies(tmp_path / "missing.yaml")
    assert len(items) >= 40
    assert {c["ats"] for c in items} == {"greenhouse", "lever", "ashby", "workday"}
    td = next(c for c in items if c["name"] == "TD Bank")
    assert companies_mod.board_id(td) == "td/TD_Bank_Careers"
    path = tmp_path / "companies.yaml"
    companies_mod.save_companies(items[:2], path)
    assert companies_mod.load_companies(path) == items[:2]


@pytest.mark.parametrize(
    "bad",
    [[{"name": "", "ats": "lever", "board": "x"}], [{"name": "A", "ats": "taleo", "board": "x"}],
     [{"name": "A", "ats": "workday", "host": "h"}], [{"name": "A", "ats": "lever"}]],
)
def test_companies_validation(bad):
    with pytest.raises(ValueError):
        companies_mod.validate_companies(bad)


async def test_gather_companies_isolates_failures():
    companies = [{"name": "Good", "ats": "lever", "board": "good", "enabled": True},
                 {"name": "Bad", "ats": "lever", "board": "bad", "enabled": True},
                 {"name": "Off", "ats": "lever", "board": "off", "enabled": False}]
    ctx = make_ctx(companies=companies)

    async def fetch_company(_ctx, company):
        if company["board"] == "bad":
            raise HttpError(500, "https://api.lever.co/bad")
        return [JobPosting(url="u", title="Data Analyst", source="lever", external_id="1")], {"1", "2"}

    result = await gather_companies(ctx, "lever", fetch_company)
    assert len(result.postings) == 1
    assert result.seen_ids == {"good": {"1", "2"}}
    assert result.warnings == ["Bad: https://api.lever.co/bad returned HTTP 500"]


async def test_gather_companies_skips_when_none_configured():
    result = await gather_companies(make_ctx(), "ashby", None)
    assert result.skipped == "no companies configured"


async def test_http_per_request_retries_zero_sends_once():
    fetch = ScriptedFetch(Response(503, ""), Response(200, "{}"))
    with pytest.raises(HttpError):
        await Http(fetch, sleep=no_sleep, default_delay=0).get_json("https://api.example/x", retries=0)
    assert len(fetch.calls) == 1
