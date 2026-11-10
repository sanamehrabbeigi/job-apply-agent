"""Ashby public job board API (https://developers.ashbyhq.com/docs/public-job-posting-api)."""

from __future__ import annotations

from typing import Any

from ...jobs import JobPosting, clean_inline, html_to_text
from ...timeutil import iso_or_none
from ..base import SourceContext, SourceResult, gather_companies

API = "https://api.ashbyhq.com/posting-api/job-board"


async def list_board(http, company: dict[str, Any]) -> list[dict[str, Any]]:
    data = await http.get_json(f"{API}/{company['board']}")
    return list(data["jobs"])


def to_posting(company: dict[str, Any], item: dict[str, Any]) -> JobPosting:
    locations = [item.get("location") or ""] + [s.get("location", "") for s in item.get("secondaryLocations") or []]
    country = ((item.get("address") or {}).get("postalAddress") or {}).get("addressCountry") or ""
    workplace = (item.get("workplaceType") or "").lower()
    remote = True if item.get("isRemote") or workplace == "remote" else (False if workplace in ("onsite", "hybrid") else None)
    return JobPosting(
        url=item.get("jobUrl", ""),
        title=clean_inline(item.get("title", "")),
        company=company["name"],
        location="; ".join(loc for loc in locations if loc),
        description=(item.get("descriptionPlain") or html_to_text(item.get("descriptionHtml", ""))).strip(),
        source="ashby",
        external_id=str(item["id"]),
        posted_at=iso_or_none(item.get("publishedAt")),
        remote=remote,
        country=country,
        employment_type=item.get("employmentType") or "",
        board=company["board"],
    )


async def fetch_company(ctx: SourceContext, company: dict[str, Any]):
    items = [item for item in await list_board(ctx.http, company) if item.get("isListed", True)]
    postings = [to_posting(company, item) for item in items if ctx.role_ok(item.get("title", ""))]
    return postings, {str(item["id"]) for item in items}


async def fetch(ctx: SourceContext) -> SourceResult:
    return await gather_companies(ctx, "ashby", fetch_company)
