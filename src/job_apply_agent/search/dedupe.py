"""Recognize the same job posted on several sites, so it's stored and shown once."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit

from ..jobs import JobPosting

KNOWN_CITIES = [
    "toronto", "mississauga", "markham", "vaughan", "brampton", "oakville", "richmond hill", "north york",
    "etobicoke", "scarborough", "ottawa", "kanata", "gatineau", "vancouver", "burnaby", "montreal", "calgary",
    "edmonton", "waterloo", "kitchener", "victoria", "halifax", "winnipeg", "hamilton", "quebec", "london",
]
_LEGAL = re.compile(r"\b(?:inc|incorporated|ltd|limited|llc|llp|lp|corp|corporation|co|company|plc|ulc|gmbh)\b")
_BRACKETS = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_TRAILING_PLACE = re.compile(r"\s+[-–—|,]\s*(?:remote|hybrid|on[- ]?site|in[- ]office|toronto|ottawa|canada|gta)\b.*$")
_ABBREVIATIONS = {"sr": "senior", "jr": "junior", "mgr": "manager", "eng": "engineer"}


def fold(text: str) -> str:
    """Lowercase without accents: 'Montréal' -> 'montreal'."""
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


def _words(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9+#]+", " ", fold(text)).split()


def normalize_company(name: str) -> str:
    return " ".join(_LEGAL.sub(" ", " ".join(_words(name))).split())


def normalize_title(title: str) -> str:
    text = _TRAILING_PLACE.sub("", _BRACKETS.sub(" ", fold(title)))
    return " ".join(_ABBREVIATIONS.get(word, word) for word in _words(text))


def primary_city(location: str, remote: bool | None) -> str:
    padded = f" {' '.join(_words(location))} "
    for city in KNOWN_CITIES:
        if f" {city} " in padded:
            return city
    if remote or " remote " in padded:
        return "remote"
    return " ".join(_words((location or "").split(",")[0]))


def dedupe_key(p: JobPosting) -> str:
    return "|".join((normalize_company(p.company), normalize_title(p.title), primary_city(p.location, p.remote)))


def canonical_url(url: str) -> str:
    parts = urlsplit(url or "")
    if not parts.netloc:
        return ""
    return f"{parts.netloc.lower()}{parts.path.rstrip('/')}"
