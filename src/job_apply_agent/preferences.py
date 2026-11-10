"""Search and app preferences, stored in ``data/preferences.yaml`` and editable in Settings."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from . import paths

SOURCE_NAMES = ("greenhouse", "lever", "ashby", "workday", "jsearch", "adzuna", "linkedin")

ROLE_TERMS = [
    "data analyst",
    "data scientist",
    "data engineer",
    "analytics engineer",
    "business intelligence",
    "bi analyst",
    "bi developer",
    "analytics",
    "product analyst",
    "reporting analyst",
    "insights analyst",
]

DEFAULT_PREFERENCES: dict[str, Any] = {
    "resume_path": "",  # empty = data/my_resume.docx
    "role_terms": ROLE_TERMS,
    "locations": {
        "cities": {
            "Toronto/GTA": [
                "toronto", "mississauga", "markham", "vaughan", "brampton", "oakville",
                "richmond hill", "north york", "etobicoke", "scarborough", "greater toronto", "gta",
            ],
            "Ottawa": ["ottawa", "kanata", "gatineau"],
        },
        "remote_canada": True,
        "include_unknown": True,
    },
    "excluded_companies": [],
    "sources": {
        "greenhouse": {"enabled": True, "interval_hours": 1},
        "lever": {"enabled": True, "interval_hours": 1},
        "ashby": {"enabled": True, "interval_hours": 1},
        "workday": {
            "enabled": True,
            "interval_hours": 1,
            "search_terms": ["data analyst", "data scientist", "data engineer", "analytics", "business intelligence"],
            "max_pages": 2,
        },
        "jsearch": {
            "enabled": True,
            "interval_hours": 24,
            "budget": 180,
            "budget_period": "month",
            "base_url": "https://jsearch.p.rapidapi.com/search",
            "queries": [
                "data analyst jobs in Toronto, Ontario",
                "data scientist jobs in Toronto, Ontario",
                "data engineer jobs in Toronto, Ontario",
                "data analyst OR data scientist OR data engineer remote Canada",
                "data analyst OR data scientist OR data engineer jobs in Ottawa, Ontario",
            ],
        },
        "adzuna": {
            "enabled": True,
            "interval_hours": 8,
            "budget": 100,
            "budget_period": "day",
            "what": ["data analyst", "data scientist", "data engineer"],
            "where": ["Toronto", "Ottawa"],
            "max_days_old": 3,
        },
        "linkedin": {
            "enabled": True,
            "interval_hours": 12,
            "keywords": ["data analyst", "data scientist", "data engineer"],
            "locations": ["Toronto, Ontario, Canada", "Ottawa, Ontario, Canada"],
            "remote_canada": True,
            "max_pages": 2,
        },
    },
    "models": {"scoring": "claude-haiku-5-5", "tailoring": None},
    "scoring": {"batch_size": 5, "concurrency": 2},
    "target_score": 85,
    "schedule": {"enabled": True},
}


def _merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        merged = {key: copy.deepcopy(value) for key, value in base.items()}
        for key, value in override.items():
            merged[key] = _merge(base[key], value) if key in base else copy.deepcopy(value)
        return merged
    return copy.deepcopy(override)


def merge_defaults(prefs: dict[str, Any] | None) -> dict[str, Any]:
    """User values win; nested dicts merge; lists are replaced, not appended."""
    return _merge(DEFAULT_PREFERENCES, prefs or {})


def validate_preferences(prefs: dict[str, Any]) -> dict[str, Any]:
    terms = prefs.get("role_terms")
    if not isinstance(terms, list) or not [t for t in terms if isinstance(t, str) and t.strip()]:
        raise ValueError("role_terms must list at least one job title term.")
    prefs["role_terms"] = [t.strip() for t in terms if isinstance(t, str) and t.strip()]
    cities = prefs.get("locations", {}).get("cities")
    if not isinstance(cities, dict) or not all(isinstance(v, list) for v in cities.values()):
        raise ValueError("locations.cities must map a label to a list of city names.")
    if not isinstance(prefs.get("excluded_companies"), list):
        raise ValueError("excluded_companies must be a list.")
    sources = prefs.get("sources")
    if not isinstance(sources, dict):
        raise ValueError("sources must be a mapping.")
    unknown = sorted(set(sources) - set(SOURCE_NAMES))
    if unknown:
        raise ValueError(f"Unknown source(s): {', '.join(unknown)}.")
    for name, cfg in sources.items():
        hours = cfg.get("interval_hours")
        if not isinstance(hours, (int, float)) or hours <= 0:
            raise ValueError(f"sources.{name}.interval_hours must be a number above 0.")
        if "budget" in cfg and (not isinstance(cfg["budget"], int) or cfg["budget"] < 0):
            raise ValueError(f"sources.{name}.budget must be a whole number (0 or more).")
        if "budget_period" in cfg and cfg["budget_period"] not in ("day", "month"):
            raise ValueError(f"sources.{name}.budget_period must be 'day' or 'month'.")
    scoring_model = prefs.get("models", {}).get("scoring")
    if not isinstance(scoring_model, str) or not scoring_model.strip():
        raise ValueError("models.scoring must name a Claude model, e.g. claude-haiku-5-5.")
    if prefs["models"].get("tailoring") == "":
        prefs["models"]["tailoring"] = None
    score = prefs.get("target_score")
    if not isinstance(score, int) or not 0 <= score <= 100:
        raise ValueError("target_score must be between 0 and 100.")
    return prefs


def load_preferences(path: Path | None = None) -> dict[str, Any]:
    path = path or paths.preferences_path()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return validate_preferences(merge_defaults(data or {}))


def save_preferences(prefs: dict[str, Any], path: Path | None = None) -> None:
    path = path or paths.preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = validate_preferences(merge_defaults(prefs))
    path.write_text(yaml.safe_dump(clean, sort_keys=False, allow_unicode=True), encoding="utf-8")


def resume_path(prefs: dict[str, Any]) -> Path:
    """The custom path if one is set, else data/my_resume.docx|.md|.txt (whichever exists)."""
    custom = (prefs.get("resume_path") or "").strip()
    if custom:
        return Path(custom)
    for suffix in (".docx", ".pdf", ".md", ".txt"):
        candidate = paths.data_dir() / f"my_resume{suffix}"
        if candidate.is_file():
            return candidate
    return paths.data_dir() / "my_resume.docx"
