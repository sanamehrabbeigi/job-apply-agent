"""What every job source receives and returns."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..jobs import JobPosting
from .companies import board_id
from .http import HttpError
from .quota import QuotaGuard


@dataclass
class SourceResult:
    postings: list[JobPosting] = field(default_factory=list)
    seen_ids: dict[str, set[str]] = field(default_factory=dict)  # board -> every job ID on it (closed-job tracking)
    warnings: list[str] = field(default_factory=list)
    skipped: str | None = None  # reason, e.g. "no API key"


@dataclass
class SourceContext:
    prefs: dict[str, Any]
    companies: list[dict[str, Any]]
    http: Any  # search.http.Http (or a test fake with the same methods)
    quota: QuotaGuard
    env: Mapping[str, str]
    role_ok: Callable[[str], bool]  # cheap title check, to skip fetching details of unrelated jobs
    known: Callable[[str, str], bool]  # (source, external_id) already stored -> no need to re-fetch details
    last_success: Callable[[str], datetime | None]
    progress: Callable[[str], None] = lambda _msg: None

    def source_prefs(self, name: str) -> dict[str, Any]:
        return self.prefs["sources"].get(name, {})

    def companies_for(self, ats: str) -> list[dict[str, Any]]:
        return [c for c in self.companies if c["ats"] == ats and c.get("enabled", True)]


Source = Callable[[SourceContext], Awaitable[SourceResult]]
FetchCompany = Callable[[SourceContext, dict[str, Any]], Awaitable[tuple[list[JobPosting], set[str] | None]]]


async def gather_companies(ctx: SourceContext, ats: str, fetch_company: FetchCompany,
                           concurrency: int = 4) -> SourceResult:
    """Run ``fetch_company`` for every enabled company on ``ats``; one company failing doesn't stop the rest."""
    companies = ctx.companies_for(ats)
    if not companies:
        return SourceResult(skipped="no companies configured")
    result = SourceResult()
    semaphore = asyncio.Semaphore(concurrency)

    async def one(company: dict[str, Any]) -> None:
        async with semaphore:
            try:
                postings, seen = await fetch_company(ctx, company)
            except HttpError as exc:
                result.warnings.append(f"{company['name']}: {exc}")
                return
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                result.warnings.append(f"{company['name']}: unexpected response ({exc!r})")
                return
            result.postings.extend(postings)
            if seen is not None:
                result.seen_ids[board_id(company)] = seen
            ctx.progress(f"{company['name']}: {len(postings)} matching")

    await asyncio.gather(*(one(c) for c in companies))
    return result
