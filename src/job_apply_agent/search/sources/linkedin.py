"""LinkedIn's public, logged-out job search, read slowly. Your LinkedIn account is never used.

LinkedIn's terms restrict automated access and it often answers with HTTP 429, so this
source stops at the first sign of rate limiting and keeps what it already found.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from ...jobs import JobPosting, clean_inline, parse_linkedin
from ...timeutil import iso_or_none, now_utc
from ..base import SourceContext, SourceResult
from ..http import HttpError, RateLimited

SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{id}"
VIEW = "https://www.linkedin.com/jobs/view/{id}/"
PAGE_SIZE = 10
_URN = re.compile(r"urn:li:jobPosting:(\d+)")


def parse_search(page: str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    seen: set[str] = set()
    for chunk in re.split(r"<li[\s>]", page):
        match = _URN.search(chunk)
        if not match or match.group(1) in seen:
            continue
        seen.add(match.group(1))

        def grab(pattern: str, text: str = chunk) -> str:
            found = re.search(pattern, text, re.S)
            return clean_inline(found.group(1)) if found else ""

        cards.append({
            "id": match.group(1),
            "title": grab(r'class="base-search-card__title"[^>]*>(.*?)</h3>'),
            "company": grab(r'class="base-search-card__subtitle"[^>]*>(.*?)</h4>'),
            "location": grab(r'class="job-search-card__location"[^>]*>(.*?)</span>'),
            "posted": grab(r'<time[^>]*datetime="([^"]+)"'),
        })
    return cards


def _card_posting(card: dict[str, Any]) -> JobPosting:
    return JobPosting(
        url=VIEW.format(id=card["id"]), title=card["title"], company=card["company"], location=card["location"],
        description_is_partial=True, source="linkedin", external_id=card["id"],
        posted_at=iso_or_none(card["posted"]), remote=card.get("remote"),
    )


def _merge(posting: JobPosting, card: dict[str, Any]) -> JobPosting:
    posting.source, posting.external_id = "linkedin", card["id"]
    posting.title = posting.title or card["title"]
    posting.company = posting.company or card["company"]
    posting.location = posting.location or card["location"]
    posting.posted_at = iso_or_none(card["posted"])
    posting.remote = card.get("remote")
    posting.description_is_partial = len(posting.description) < 300
    return posting


async def fetch(ctx: SourceContext) -> SourceResult:
    prefs = ctx.source_prefs("linkedin")
    last = ctx.last_success("linkedin")
    window = "r86400" if last is not None and now_utc() - last < timedelta(hours=36) else "r604800"
    searches = [(kw, loc, None) for kw in prefs.get("keywords", []) for loc in prefs.get("locations", [])]
    if prefs.get("remote_canada"):
        searches += [(kw, "Canada", "2") for kw in prefs.get("keywords", [])]

    result = SourceResult()
    cards: dict[str, dict[str, Any]] = {}
    try:
        for keywords, location, work_type in searches:
            for page in range(int(prefs.get("max_pages", 2))):
                params = {"keywords": keywords, "location": location, "f_TPR": window, "start": page * PAGE_SIZE}
                if work_type:
                    params["f_WT"] = work_type
                found = parse_search(await ctx.http.get_text(SEARCH, params=params, retry_429=False))
                for card in found:
                    if work_type:
                        card["remote"] = True
                    cards.setdefault(card["id"], card)
                if len(found) < PAGE_SIZE:
                    break
        for card in cards.values():
            if not ctx.role_ok(card["title"]):
                continue
            if ctx.known("linkedin", card["id"]):
                result.postings.append(_card_posting(card))
                continue
            try:
                page_html = await ctx.http.get_text(DETAIL.format(id=card["id"]), retry_429=False)
            except RateLimited:
                raise
            except HttpError:
                result.postings.append(_card_posting(card))
                continue
            result.postings.append(_merge(parse_linkedin(page_html, VIEW.format(id=card["id"])), card))
    except RateLimited:
        result.warnings.append("LinkedIn is limiting requests; stopped early. It will try again on the next run.")
        done = {p.external_id for p in result.postings}
        result.postings.extend(
            _card_posting(c) for c in cards.values() if c["id"] not in done and ctx.role_ok(c["title"])
        )
    ctx.progress(f"{len(cards)} LinkedIn cards, {len(result.postings)} matching")
    return result
