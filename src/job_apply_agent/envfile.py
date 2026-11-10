"""API keys for job sources, read from ``data/.env`` (git-ignored) or the environment."""

from __future__ import annotations

import os
from pathlib import Path

from . import paths

KEYS = ("JSEARCH_API_KEY", "ADZUNA_APP_ID", "ADZUNA_APP_KEY")


def read_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_env(path: Path | None = None) -> dict[str, str]:
    """Values from the .env file, overridden by real environment variables."""
    values = read_env_file(path or paths.env_path())
    for key in KEYS:
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values
