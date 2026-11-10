"""Greenhouse public job board API (https://developers.greenhouse.io/job-board.html)."""

from __future__ import annotations

import html
from typing import Any

from ...jobs import JobPosting, clean_inline, html_to_text
from ...timeutil import iso_or_none
from ..base import SourceContext, SourceResult, gather_companies
from ..http import HttpError

API = "https://boards-api.greenhouse.io/v1/boards"


async def list_board(http, company: dict[str, Any]) -> list[dict[str, Any]]:
    data = await http.get_json(f"{API}/{company['board']}/jobs")
    return list(data["jobs"])


def to_posting(company: dict[str, Any], item: dict[str, Any], detail: dict[str, Any] | None = None) -> JobPosting:
    content = (detail or {}).get("content") or ""
    employment = next(
        (m.get("value") for m in item.get("metadata") or []
         if (m.get("name") or "").lower() == "employment type" and isinstance(m.get("value"), str)),
        "",
    )
    return JobPosting(
        url=item.get("absolute_url", ""),
        title=clean_inline(item.get("title", "")),
        company=company["name"],
        location=(item.get("location") or {}).get("name") or "",
        description=html_to_text(html.unescape(content)) if content else "",
        description_is_partial=not content,
        source="greenhouse",
        external_id=str(item["id"]),
        posted_at=iso_or_none(item.get("first_published") or item.get("updated_at")),
        employment_type=employment,
        board=company["board"],
    )


async def fetch_company(ctx: SourceContext, company: dict[str, Any]):
    items = await list_board(ctx.http, company)
    postings = []
    for item in items:
        if not ctx.role_ok(item.get("title", "")):
            continue
        detail = None
        if not ctx.known("greenhouse", str(item["id"])):
            try:
                detail = await ctx.http.get_json(f"{API}/{company['board']}/jobs/{item['id']}")
            except HttpError:
                detail = None
        postings.append(to_posting(company, item, detail))
    return postings, {str(item["id"]) for item in items}


async def fetch(ctx: SourceContext) -> SourceResult:
    return await gather_companies(ctx, "greenhouse", fetch_company)
