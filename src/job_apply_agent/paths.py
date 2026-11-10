"""Where the app keeps its files.

Everything personal lives under DATA_DIR (default ``./data``, git-ignored). Set
``JOB_AGENT_DATA_DIR`` / ``JOB_AGENT_OUTPUT_DIR`` to keep them somewhere else.
The functions read the environment on every call, so tests can point them at a temp folder.
"""

from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("JOB_AGENT_DATA_DIR", "data"))


def output_dir() -> Path:
    return Path(os.environ.get("JOB_AGENT_OUTPUT_DIR", "output"))


def profile_dir() -> Path:
    return data_dir() / "profile"


def jobs_dir() -> Path:
    return data_dir() / "jobs"


def db_path() -> Path:
    return data_dir() / "app.db"


def preferences_path() -> Path:
    return data_dir() / "preferences.yaml"


def companies_path() -> Path:
    return data_dir() / "companies.yaml"


def env_path() -> Path:
    return data_dir() / ".env"
