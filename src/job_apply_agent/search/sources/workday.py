"""Workday career sites (used by most Canadian banks and insurers).

Workday has no public board listing, so we search by keyword on the site's own JSON
endpoint, then fetch details only for new jobs whose title matches.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ...jobs import JobPosting, clean_inline, html_to_text
from ...timeutil import iso, iso_or_none, now_utc, parse_relative_posted
from ..base import SourceContext, SourceResult, gather_companies
from ..companies import board_id
from ..http import HttpError

PAGE_SIZE = 20


def _base(company: dict[str, Any]) -> str:
    return f"https://{company['host']}/wday/cxs/{company['tenant']}/{company['site']}"


async def list_board(http, company: dict[str, Any], search_text: str = "", offset: int = 0) -> dict[str, Any]:
    body = {"appliedFacets": {}, "limit": PAGE_SIZE, "offset": offset, "searchText": search_text}
    return await http.post_json(f"{_base(company)}/jobs", body)


async def list_first_page(http, company: dict[str, Any]) -> list[dict[str, Any]]:
    return list((await list_board(http, company)).get("jobPostings") or [])


def to_posting(company: dict[str, Any], item: dict[str, Any], detail: dict[str, Any] | None,
               now: datetime) -> JobPosting:
    info = (detail or {}).get("jobPostingInfo") or {}
    path = item["externalPath"]
    locations = [info.get("location") or item.get("locationsText") or ""] + list(info.get("additionalLocations") or [])
    posted = iso_or_none(info.get("startDate"))
    if posted is None:
        relative = parse_relative_posted(item.get("postedOn", ""), now)
        posted = iso(relative) if relative else None
    return JobPosting(
        url=info.get("externalUrl") or f"https://{company['host']}/{company['site']}{path}",
        title=clean_inline(info.get("title") or item.get("title", "")),
        company=company["name"],
        location="; ".join(loc for loc in locations if loc),
        description=html_to_text(info.get("jobDescription", "")),
        description_is_partial=not info,
        source="workday",
        external_id=path,
        posted_at=posted,
        remote=True if "remote" in (info.get("remoteType") or "").lower() else None,
        country=(info.get("country") or {}).get("descriptor") or "",
        employment_type=info.get("timeType") or "",
        board=board_id(company),
    )


async def fetch_company(ctx: SourceContext, company: dict[str, Any]):
    prefs = ctx.source_prefs("workday")
    now = now_utc()
    found: dict[str, dict[str, Any]] = {}
    for term in prefs.get("search_terms", []):
        for page in range(int(prefs.get("max_pages", 2))):
            data = await list_board(ctx.http, company, term, page * PAGE_SIZE)
            items = data.get("jobPostings") or []
            for item in items:
                if item.get("externalPath") and ctx.role_ok(item.get("title", "")):
                    found.setdefault(item["externalPath"], item)
            if len(items) < PAGE_SIZE:
                break
    postings = []
    for path, item in found.items():
        detail = None
        if not ctx.known("workday", path):
            try:
                detail = await ctx.http.get_json(f"{_base(company)}{path}")
            except HttpError:
                detail = None
        postings.append(to_posting(company, item, detail, now))
    return postings, None


async def fetch(ctx: SourceContext) -> SourceResult:
    return await gather_companies(ctx, "workday", fetch_company, concurrency=2)
