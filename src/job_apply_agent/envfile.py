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


def export_claude_token(path: Path | None = None) -> bool:
    """Make a ``CLAUDE_CODE_OAUTH_TOKEN`` from data/.env visible to the Agent SDK (it reads the environment).

    A token already set in the real environment wins. Returns True when the file's token was used."""
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        return False
    token = read_env_file(path or paths.env_path()).get("CLAUDE_CODE_OAUTH_TOKEN")
    if not token:
        return False
    os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = token
    return True
