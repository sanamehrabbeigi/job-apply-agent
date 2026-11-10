"""JSearch (Google for Jobs data: LinkedIn, Indeed, Glassdoor, ZipRecruiter...) via RapidAPI.

Free tier: about 200 requests/month; the guard stops at the configured budget (default 180).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit

from ...jobs import JobPosting, clean_inline
from ...timeutil import iso_or_none, now_utc
from ..base import SourceContext, SourceResult
from ..http import HttpError
from ..quota import QuotaExceeded

DEFAULT_URL = "https://jsearch.p.rapidapi.com/search"


def parse_jsearch(data: Any) -> list[dict[str, Any]]:
    payload = data.get("data") if isinstance(data, dict) else None
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("jobs"), list):
        return payload["jobs"]
    message = data.get("message") if isinstance(data, dict) else None
    raise ValueError(f"unexpected JSearch response{': ' + str(message) if message else ''}")


def to_posting(item: dict[str, Any]) -> JobPosting:
    city, state = item.get("job_city") or "", item.get("job_state") or ""
    location = ", ".join(part for part in (city, state) if part) or item.get("job_location") or ""
    posted = iso_or_none(item.get("job_posted_at_datetime_utc")) or iso_or_none(item.get("job_posted_at_timestamp"))
    remote = item.get("job_is_remote")
    return JobPosting(
        url=item.get("job_apply_link") or item.get("job_google_link") or "",
        title=clean_inline(item.get("job_title", "")),
        company=clean_inline(item.get("employer_name", "")),
        location=location,
        details={"Publisher": item["job_publisher"]} if item.get("job_publisher") else {},
        description=(item.get("job_description") or "").strip(),
        source="jsearch",
        external_id=str(item.get("job_id", "")),
        posted_at=posted,
        remote=None if remote is None else bool(remote),
        country=item.get("job_country") or "",
        employment_type=item.get("job_employment_type") or "",
    )


async def fetch(ctx: SourceContext) -> SourceResult:
    prefs = ctx.source_prefs("jsearch")
    key = ctx.env.get("JSEARCH_API_KEY")
    if not key:
        return SourceResult(skipped="no API key (add JSEARCH_API_KEY to data/.env)")
    base_url = prefs.get("base_url") or DEFAULT_URL
    headers = {"X-RapidAPI-Key": key, "X-RapidAPI-Host": urlsplit(base_url).hostname or ""}
    last = ctx.last_success("jsearch")
    date_posted = "today" if last is not None and now_utc() - last < timedelta(hours=36) else "3days"

    result = SourceResult()
    calls = 0
    for query in prefs.get("queries", []):
        try:
            ctx.quota.consume("jsearch")
        except QuotaExceeded as exc:
            if calls == 0:
                return SourceResult(skipped=str(exc))
            result.warnings.append(str(exc))
            break
        calls += 1
        params = {"query": query, "country": "ca", "date_posted": date_posted, "num_pages": 1}
        try:
            data = await ctx.http.get_json(base_url, params=params, headers=headers)
            items = parse_jsearch(data)
        except HttpError as exc:
            if exc.status in (401, 403):
                raise HttpError(exc.status, exc.url, "JSearch rejected the API key (check JSEARCH_API_KEY)") from exc
            result.warnings.append(f"“{query}”: {exc}")
            continue
        except ValueError as exc:
            result.warnings.append(f"“{query}”: {exc}")
            continue
        result.postings.extend(to_posting(i) for i in items if i.get("job_id") and ctx.role_ok(i.get("job_title", "")))
        ctx.progress(f"“{query}”: {len(items)} results")
    return result
