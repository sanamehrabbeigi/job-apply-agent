"""Adzuna job search API for Canada (descriptions are snippets; the full posting is fetched when tailoring)."""

from __future__ import annotations

from typing import Any

from ...jobs import JobPosting, clean_inline
from ...timeutil import iso_or_none
from ..base import SourceContext, SourceResult
from ..http import HttpError
from ..quota import QuotaExceeded

URL = "https://api.adzuna.com/v1/api/jobs/ca/search/1"


def to_posting(item: dict[str, Any]) -> JobPosting:
    location = item.get("location") or {}
    return JobPosting(
        url=item.get("redirect_url") or "",
        title=clean_inline(item.get("title") or ""),
        company=clean_inline((item.get("company") or {}).get("display_name") or ""),
        location=location.get("display_name") or "",
        description=clean_inline(item.get("description") or ""),
        description_is_partial=True,
        source="adzuna",
        external_id=str(item.get("id", "")),
        posted_at=iso_or_none(item.get("created")),
        country="CA",
        employment_type=item.get("contract_time") or "",
    )


async def fetch(ctx: SourceContext) -> SourceResult:
    prefs = ctx.source_prefs("adzuna")
    app_id, app_key = ctx.env.get("ADZUNA_APP_ID"), ctx.env.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        return SourceResult(skipped="no API key (add ADZUNA_APP_ID and ADZUNA_APP_KEY to data/.env)")
    result = SourceResult()
    calls = 0
    for what in prefs.get("what", []):
        for where in prefs.get("where", []):
            try:
                ctx.quota.consume("adzuna")
            except QuotaExceeded as exc:
                if calls == 0:
                    return SourceResult(skipped=str(exc))
                result.warnings.append(str(exc))
                return result
            calls += 1
            params = {
                "app_id": app_id, "app_key": app_key, "what": what, "where": where,
                "max_days_old": prefs.get("max_days_old", 3), "results_per_page": 50,
                "sort_by": "date", "content-type": "application/json",
            }
            try:
                data = await ctx.http.get_json(URL, params=params)
            except HttpError as exc:
                if exc.status in (401, 403):
                    raise HttpError(exc.status, exc.url, "Adzuna rejected the app ID/key") from exc
                result.warnings.append(f"{what} in {where}: {exc}")
                continue
            items = data.get("results") or []
            result.postings.extend(to_posting(i) for i in items if i.get("id") and ctx.role_ok(clean_inline(i.get("title") or "")))
            ctx.progress(f"{what} in {where}: {len(items)} results")
    return result
