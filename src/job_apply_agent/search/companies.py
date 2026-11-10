"""The list of company career sites to search (``data/companies.yaml``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .. import paths

ATS = ("greenhouse", "lever", "ashby", "workday")
DEFAULT_FILE = Path(__file__).with_name("default_companies.yaml")


def validate_companies(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        raise ValueError("The companies list must be a list.")
    out: list[dict[str, Any]] = []
    for number, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Company #{number} must be a mapping.")
        name = str(item.get("name", "")).strip()
        ats = str(item.get("ats", "")).strip().lower()
        if not name:
            raise ValueError(f"Company #{number} needs a name.")
        if ats not in ATS:
            raise ValueError(f"{name}: ats must be one of {', '.join(ATS)}.")
        entry: dict[str, Any] = {"name": name, "ats": ats, "enabled": bool(item.get("enabled", True))}
        if ats == "workday":
            for key in ("host", "tenant", "site"):
                value = str(item.get(key, "")).strip()
                if not value:
                    raise ValueError(f"{name}: Workday companies need host, tenant and site.")
                entry[key] = value
        else:
            board = str(item.get("board", "")).strip()
            if not board:
                raise ValueError(f"{name}: board is required.")
            entry["board"] = board
        out.append(entry)
    return out


def load_companies(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or paths.companies_path()
    source = path if path.is_file() else DEFAULT_FILE
    return validate_companies(yaml.safe_load(source.read_text(encoding="utf-8")) or [])


def save_companies(items: Any, path: Path | None = None) -> list[dict[str, Any]]:
    path = path or paths.companies_path()
    clean = validate_companies(items)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(clean, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return clean


def board_id(company: dict[str, Any]) -> str:
    return f"{company['tenant']}/{company['site']}" if company["ats"] == "workday" else company["board"]


async def test_company(company: dict[str, Any], http) -> dict[str, Any]:
    """Check that a company's board answers; used by the Settings 'Test' button."""
    from .sources import BOARD_LISTERS  # imported here to avoid an import cycle

    try:
        [clean] = validate_companies([company])
        items = await BOARD_LISTERS[clean["ats"]](http, clean)
    except Exception as exc:  # noqa: BLE001 - shown to the user as the test result
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "jobs": len(items)}
