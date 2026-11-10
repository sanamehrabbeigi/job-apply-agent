"""Lever public postings API (https://github.com/lever/postings-api)."""

from __future__ import annotations

from typing import Any

from ...jobs import JobPosting, clean_inline, html_to_text
from ...timeutil import iso_or_none
from ..base import SourceContext, SourceResult, gather_companies

API = "https://api.lever.co/v0/postings"


async def list_board(http, company: dict[str, Any]) -> list[dict[str, Any]]:
    data = await http.get_json(f"{API}/{company['board']}", params={"mode": "json"})
    if not isinstance(data, list):
        raise ValueError("Lever returned something other than a list of postings")
    return data


def to_posting(company: dict[str, Any], item: dict[str, Any]) -> JobPosting:
    categories = item.get("categories") or {}
    locations = categories.get("allLocations") or ([categories["location"]] if categories.get("location") else [])
    parts = [item.get("descriptionPlain") or html_to_text(item.get("description", ""))]
    for section in item.get("lists") or []:
        parts.append(f"{clean_inline(section.get('text', ''))}\n{html_to_text(section.get('content', ''))}")
    if item.get("additionalPlain"):
        parts.append(item["additionalPlain"])
    workplace = (item.get("workplaceType") or "").lower()
    remote = True if workplace == "remote" else (False if workplace in ("onsite", "on-site", "hybrid") else None)
    return JobPosting(
        url=item.get("hostedUrl", ""),
        title=clean_inline(item.get("text", "")),
        company=company["name"],
        location="; ".join(locations),
        description="\n\n".join(part.strip() for part in parts if part and part.strip()),
        source="lever",
        external_id=str(item["id"]),
        posted_at=iso_or_none(item.get("createdAt")),
        remote=remote,
        country=item.get("country") or "",
        employment_type=categories.get("commitment") or "",
        board=company["board"],
    )


async def fetch_company(ctx: SourceContext, company: dict[str, Any]):
    items = await list_board(ctx.http, company)
    postings = [to_posting(company, item) for item in items if ctx.role_ok(item.get("text", ""))]
    return postings, {str(item["id"]) for item in items}


async def fetch(ctx: SourceContext) -> SourceResult:
    return await gather_companies(ctx, "lever", fetch_company)
