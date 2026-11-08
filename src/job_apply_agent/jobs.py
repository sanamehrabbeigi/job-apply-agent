"""Fetch a job posting from a link and turn it into clean text.

- LinkedIn: any LinkedIn job link works, including search-results links with
  ``currentJobId=...``. The public, logged-out job page is read (no LinkedIn account is
  used). LinkedIn's terms restrict automated access, so keep this to occasional,
  personal use.
- Other sites (company career pages, Greenhouse, Lever, Workday, ...): the
  schema.org ``JobPosting`` data that most job pages embed for search engines is used;
  otherwise the page is converted to plain text.

If fetching fails, the caller can fall back to the agent's WebFetch tool, or you can save
the posting text to a file and use ``--job-file``.
"""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
MIN_DESCRIPTION_CHARS = 300


class JobFetchError(RuntimeError):
    """Raised when a job posting can't be fetched or recognized."""


@dataclass
class JobPosting:
    url: str
    title: str = ""
    company: str = ""
    location: str = ""
    details: dict[str, str] = field(default_factory=dict)
    description: str = ""

    def to_text(self) -> str:
        lines = [f"Source: {self.url}"]
        if self.title:
            lines.append(f"Job title: {self.title}")
        if self.company:
            lines.append(f"Company: {self.company}")
        if self.location:
            lines.append(f"Location: {self.location}")
        lines += [f"{key}: {value}" for key, value in self.details.items()]
        lines += ["", "Description:", self.description.strip()]
        return "\n".join(lines).strip() + "\n"

    def save(self, folder: str | Path = "data/jobs") -> Path:
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        name = "_".join(
            part for part in (_slug(self.company), _slug(self.title), linkedin_job_id(self.url) or "") if part
        )
        path = folder / f"{name or 'job'}.txt"
        path.write_text(self.to_text(), encoding="utf-8")
        return path


def fetch_job(url: str, timeout: float = 30) -> JobPosting:
    """Fetch and parse the job posting at ``url``."""
    job_id = linkedin_job_id(url)
    if job_id:
        return fetch_linkedin_job(job_id, timeout=timeout)
    page = _http_get(url, timeout)
    posting = parse_json_ld(page, url) or parse_generic(page, url)
    if len(posting.description) < MIN_DESCRIPTION_CHARS:
        raise JobFetchError(f"Couldn't find a job description on {url} (the page may need a login or JavaScript).")
    return posting


# --- LinkedIn --------------------------------------------------------------------------


def linkedin_job_id(url: str) -> str | None:
    """Job ID from any LinkedIn job link (view, search results, collections), else None."""
    if "linkedin." not in url.lower():
        return None
    for pattern in (r"[?&]currentJobId=(\d+)", r"/jobs/view/(?:[^/?#]*?-)?(\d{6,})", r"jobPosting/(\d+)"):
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def fetch_linkedin_job(job_id: str, timeout: float = 30) -> JobPosting:
    page = _http_get(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}", timeout)
    posting = parse_linkedin(page, f"https://www.linkedin.com/jobs/view/{job_id}/")
    if len(posting.description) < MIN_DESCRIPTION_CHARS:
        raise JobFetchError(
            f"LinkedIn didn't return job {job_id} (it may be closed, or LinkedIn is limiting requests). "
            "Copy the posting text into a file and use --job-file instead."
        )
    return posting


def parse_linkedin(page: str, url: str) -> JobPosting:
    def text_of(pattern: str) -> str:
        match = re.search(pattern, page, re.S)
        return _clean_inline(match.group(1)) if match else ""

    details = {
        _clean_inline(key): _clean_inline(value)
        for key, value in re.findall(
            r'<h3 class="description__job-criteria-subheader">(.*?)</h3>\s*<span[^>]*>(.*?)</span>', page, re.S
        )
    }
    description = re.search(r'<div class="show-more-less-html__markup[^"]*"[^>]*>(.*?)</div>', page, re.S)
    return JobPosting(
        url=url,
        title=text_of(r"<h2[^>]*top-card-layout__title[^>]*>(.*?)</h2>"),
        company=text_of(r'class="topcard__org-name-link[^"]*"[^>]*>(.*?)</a>'),
        location=text_of(r'<span class="topcard__flavor topcard__flavor--bullet">(.*?)</span>'),
        details=details,
        description=html_to_text(description.group(1)) if description else "",
    )


# --- Other job sites -------------------------------------------------------------------


def parse_json_ld(page: str, url: str) -> JobPosting | None:
    """Use the schema.org JobPosting data most job sites embed for Google Jobs."""
    for block in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page, re.S | re.I):
        try:
            data = json.loads(html.unescape(block.strip()))
        except json.JSONDecodeError:
            continue
        for item in _walk_json_ld(data):
            if item.get("@type") != "JobPosting" and "JobPosting" not in (item.get("@type") or []):
                continue
            org = item.get("hiringOrganization") or {}
            details = {}
            if item.get("employmentType"):
                kind = item["employmentType"]
                details["Employment type"] = ", ".join(kind) if isinstance(kind, list) else str(kind)
            if item.get("datePosted"):
                details["Date posted"] = str(item["datePosted"])
            return JobPosting(
                url=url,
                title=_clean_inline(str(item.get("title", ""))),
                company=_clean_inline(str(org.get("name", "") if isinstance(org, dict) else org)),
                location=_json_ld_location(item.get("jobLocation")),
                details=details,
                description=html_to_text(str(item.get("description", ""))),
            )
    return None


def parse_generic(page: str, url: str) -> JobPosting:
    title = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
    body = re.search(r"<body[^>]*>(.*)</body>", page, re.S | re.I)
    content = body.group(1) if body else page
    content = re.sub(r"<(script|style|noscript|svg|nav|footer|header)\b.*?</\1>", " ", content, flags=re.S | re.I)
    return JobPosting(url=url, title=_clean_inline(title.group(1)) if title else "", description=html_to_text(content))


# --- helpers ---------------------------------------------------------------------------


def html_to_text(fragment: str) -> str:
    """Small HTML -> text conversion that keeps paragraphs and bullet points."""
    text = re.sub(r"<li[^>]*>", "\n- ", fragment, flags=re.I)
    text = re.sub(r"<br\s*/?>|</p>|</div>|</h\d>|</ul>|</ol>|<p[^>]*>|<h\d[^>]*>", "\n", text, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    text = re.sub(r"[ \t\xa0]+", " ", text)
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _clean_inline(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _http_get(url: str, timeout: float) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        raise JobFetchError(f"{url} returned HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise JobFetchError(f"Couldn't reach {url}: {exc}") from exc


def _walk_json_ld(data):
    if isinstance(data, list):
        for item in data:
            yield from _walk_json_ld(item)
    elif isinstance(data, dict):
        yield data
        for key in ("@graph", "itemListElement"):
            if key in data:
                yield from _walk_json_ld(data[key])


def _json_ld_location(location) -> str:
    places = location if isinstance(location, list) else [location]
    names = []
    for place in places:
        if not isinstance(place, dict):
            continue
        address = place.get("address") or {}
        if isinstance(address, dict):
            parts = [address.get(k) for k in ("addressLocality", "addressRegion", "addressCountry")]
            names.append(", ".join(str(p) if not isinstance(p, dict) else str(p.get("name", "")) for p in parts if p))
    return "; ".join(n for n in names if n)


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()[:40]
