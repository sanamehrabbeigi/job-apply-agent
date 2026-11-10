"""Small UTC date/time helpers. All timestamps in the database are ISO 8601 UTC strings."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_DAYS_AGO = re.compile(r"(\d+)\+?\s+days?\s+ago", re.I)


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def parse_datetime(value) -> datetime | None:
    """ISO strings (with ``Z`` or an offset), plain dates, or epoch seconds/milliseconds."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    text = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def iso_or_none(value) -> str | None:
    parsed = parse_datetime(value)
    return iso(parsed) if parsed else None


def parse_relative_posted(text: str, now: datetime) -> datetime | None:
    """Workday-style 'Posted Today' / 'Posted Yesterday' / 'Posted 4 Days Ago' / 'Posted 30+ Days Ago'."""
    lowered = (text or "").lower()
    if "today" in lowered or "just posted" in lowered:
        return now
    if "yesterday" in lowered:
        return now - timedelta(days=1)
    match = _DAYS_AGO.search(lowered)
    return now - timedelta(days=int(match.group(1))) if match else None
