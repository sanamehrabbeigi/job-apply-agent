"""Relevance gate: only data jobs in the target locations go on to Claude scoring.

This is not ranking. Every job that passes is scored by Claude; this only stops Claude
from scoring the many unrelated jobs that company career sites list.
"""

from __future__ import annotations

import re
from typing import Any

from ..jobs import JobPosting
from .dedupe import fold, normalize_company

REMOTE = re.compile(r"\bremote\b|\banywhere\b|work from home|\bwfh\b|\bdistributed\b|\bvirtual\b", re.I)
CANADA = re.compile(
    r"\bcanada\b|\bcanadian\b|\(can\)|\bontario\b|\bquebec\b|\bbritish columbia\b|\balberta\b|\bnova scotia\b"
    r"|\bmanitoba\b|\bsaskatchewan\b|\bnew brunswick\b|\bnewfoundland\b"
    r"|,\s*(?:on|bc|ab|qc|ns|mb|sk|nb|nl|pe)\b|\b(?:on|bc|ab|qc|ns|mb|sk|nb|nl|pe),",
    re.I,
)
COUNTRY_ONLY = {"canada", "ca", "can", "remote canada", "canada remote"}


def _padded(text: str) -> str:
    return " " + " ".join(re.sub(r"[^a-z0-9+#]+", " ", fold(text)).split()) + " "


def role_matches(title: str, role_terms: list[str]) -> bool:
    padded = _padded(title)
    return any(_padded(term) in padded for term in role_terms if term.strip())


def _is_canada_country(country: str) -> bool:
    return (country or "").strip().lower() in {"ca", "can", "canada"}


def location_label(p: JobPosting, loc_prefs: dict[str, Any]) -> str | None:
    """'Toronto/GTA', 'Ottawa', 'Remote (Canada)', 'Unknown', or None when the job is elsewhere."""
    location = p.location or ""
    if not location.strip() and p.remote is None and not p.country:
        return "Unknown" if loc_prefs.get("include_unknown", True) else None
    padded = _padded(location)
    for label, cities in loc_prefs.get("cities", {}).items():
        if any(_padded(city) in padded for city in cities if city.strip()):
            return label
    if loc_prefs.get("remote_canada", True):
        if padded.strip() in COUNTRY_ONLY:
            return "Remote (Canada)"
        remote = p.remote is True or bool(REMOTE.search(location))
        canada = _is_canada_country(p.country) or bool(CANADA.search(fold(location)))
        if remote and canada:
            return "Remote (Canada)"
    return None


def company_excluded(company: str, excluded: list[str]) -> bool:
    name = normalize_company(company)
    return any(normalize_company(other) == name for other in excluded if other.strip())


def evaluate(p: JobPosting, prefs: dict[str, Any]) -> tuple[bool, str]:
    """(relevant, location label). Irrelevant jobs are stored but never shown or scored."""
    if not role_matches(p.title, prefs["role_terms"]):
        return False, ""
    if company_excluded(p.company, prefs.get("excluded_companies", [])):
        return False, ""
    label = location_label(p, prefs["locations"])
    return (label is not None), (label or "")
