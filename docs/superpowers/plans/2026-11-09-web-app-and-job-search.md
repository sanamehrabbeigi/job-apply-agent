# Web App + Automatic Job Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `job-apply-agent` into a local web app (FastAPI + React/TypeScript) that searches job sources on a schedule, scores every relevant Data Analyst / Scientist / Engineer job with Claude Haiku 5.5, lists them by match score, and runs the existing resume tailoring from the browser.

**Architecture:** The existing Python package stays the core. New modules: `paths`/`preferences` (config), `db` (SQLite), `search/` (sources, relevance gate, dedupe, scoring, pipeline, scheduler), `tailor_flow`/`tailor_sessions` (tailoring loop shared by CLI and web), `runtime` (wiring), `web/app.py` (FastAPI routes + SSE + static UI). The React UI in `frontend/` builds into `src/job_apply_agent/web/static/`, which is committed, so `job-agent serve` needs only Python.

**Tech Stack:** Python 3.10+, FastAPI, uvicorn, PyYAML, sqlite3, urllib (stdlib), claude-agent-sdk; React 18 + TypeScript + Vite + Vitest; pytest, ruff; GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-09-web-app-and-job-search-design.md`

## Global Constraints

- Python `>=3.10` (CI runs 3.10 and 3.12). HTTP uses stdlib `urllib` via `asyncio.to_thread`; no `requests`/`httpx` at runtime.
- New runtime deps only: `fastapi>=0.115`, `uvicorn[standard]>=0.30`, `python-multipart>=0.0.9` (file uploads), `pyyaml>=6.0`. Dev: `httpx>=0.27`, `ruff>=0.6`.
- Scoring model default: `claude-haiku-5-5`. Tailoring model default: `None` (the account default, as today).
- Server binds to `127.0.0.1` only (default port 8000).
- All personal data lives under `DATA_DIR` (`$JOB_AGENT_DATA_DIR` or `./data`) and `OUTPUT_DIR` (`$JOB_AGENT_OUTPUT_DIR` or `./output`); both stay git-ignored. Never write tests that touch the real `data/`.
- Default role terms (verbatim): `data analyst`, `data scientist`, `data engineer`, `analytics engineer`, `business intelligence`, `bi analyst`, `bi developer`, `analytics`, `product analyst`, `reporting analyst`, `insights analyst`. (No `machine learning engineer`.)
- Target locations: Toronto/GTA, Remote (Canada), Ottawa. No seniority filter.
- Free-tier budgets (configurable): JSearch 180 requests/month, Adzuna 100 requests/day.
- LinkedIn: logged-out guest endpoints only, 3–6 s between requests, stop at the first 429/999.
- Honesty rules from the repo stay: nothing invented; no automatic applying.
- Git: work on branch `feature/web-app-job-search`; one commit per task step marked "Commit", conventional-commit messages (`feat:`, `refactor:`, `test:`, `chore:`, `docs:`, `ci:`); every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. `pytest` and `ruff check` must pass before each commit. Never push or open a PR without the user's go-ahead.
- Tests never call the network or Claude. Use the fakes in `tests/fakes.py`.

## Review Focus

1. **Ambiguous location strings** (`Toronto, CA`, `Remote - US`, `Remote (United States | Canada)`, `KOHO (CAN)`, `3 Locations`, empty): Toronto/Canada ones pass, US-only remote fails, empty passes as "Unknown". Pinned in Task 5 `test_location_cases`.
2. **An hourly run that finds nothing new** must make zero Claude calls. Pinned in Task 12 `test_second_run_scores_nothing`.
3. **First launch without a resume**: search still collects jobs; scoring is skipped with a clear message; the status API reports `resume: false`. Pinned in Task 12 `test_missing_resume_skips_scoring` and Task 14 `test_status_without_resume`.
4. **A source returning a different shape or an error page** (JSearch v1 list vs v2 `{jobs, cursor}`; HTML instead of JSON): that source records an error, the others finish. Pinned in Task 9 `test_parse_jsearch_both_shapes` and Task 12 `test_failing_source_does_not_stop_others`.
5. **The same job from two sources with different casing or "(Remote)" suffixes** merges into one row; "Senior Data Analyst" and "Data Analyst" stay separate. Pinned in Task 5 `test_dedupe_key_merges_variants`.

## Spec refinements made while planning

- Search modules live in a `search/` subpackage (`src/job_apply_agent/search/...`) instead of the package root, to keep the root readable.
- Workday searches by keyword, so it can't see a whole board; Workday jobs are not closed by "missed runs". Instead, **any** job not seen for 21 days is hidden as stale (all sources). Company APIs still close after 2 missed runs.
- The relevance gate also stores a `location_label` (`Toronto/GTA`, `Ottawa`, `Remote (Canada)`, `Unknown`) used by the location filter.
- A location of just "Canada" is treated as Remote (Canada).
- Tailor progress is polled (`GET /api/tailor/{id}` every 1.5 s); search progress uses SSE.
- `POST /api/search {"sources": []}` scores pending jobs without fetching.
- After a resume/profile change, jobs are re-scored on the next search run (the Settings page says so); there is no separate confirmation dialog.

## File Map

```
pyproject.toml                         (modify) deps, ruff, version
.gitignore                             (modify) node_modules, frontend build cache
.github/workflows/ci.yml               (create) Python + frontend checks
src/job_apply_agent/
  paths.py                             (create) DATA_DIR / OUTPUT_DIR helpers
  preferences.py                       (create) preferences.yaml defaults/load/save/validate
  envfile.py                           (create) data/.env reader for API keys
  timeutil.py                          (create) UTC ISO helpers, relative dates
  jobs.py                              (modify) JobPosting fields, clean_inline, save() default
  outputs.py                           (create) save_outputs/slugify/candidate_name (moved from cli)
  tailor_flow.py                       (create) ask-then-rewrite loop (moved from cli)
  cli.py                               (modify) uses tailor_flow/outputs; new serve, search
  db.py                                (create) SQLite schema + queries
  search/__init__.py                   (create)
  search/filters.py                    (create) relevance gate
  search/dedupe.py                     (create) normalization + dedupe keys
  search/http.py                       (create) polite async HTTP helper
  search/quota.py                      (create) free-tier quota guard
  search/companies.py                  (create) companies.yaml load/save/validate/test
  search/default_companies.yaml        (create) 42 verified Canadian employers
  search/base.py                       (create) SourceContext/SourceResult/gather_companies
  search/sources/__init__.py           (create) SOURCES + BOARD_LISTERS registry
  search/sources/greenhouse.py|lever.py|ashby.py|workday.py|jsearch.py|adzuna.py|linkedin.py
  search/scoring.py                    (create) Claude Haiku scoring
  search/events.py                     (create) in-process pub/sub for SSE
  search/pipeline.py                   (create) SearchRunner + refilter_jobs
  search/scheduler.py                  (create) per-source interval loop
  tailor_sessions.py                   (create) browser tailoring sessions
  runtime.py                           (create) builds db/runner/scheduler/tailor
  web/__init__.py, web/app.py          (create) FastAPI app
  web/static/                          (generated by frontend build, committed)
frontend/                              (create) React + TS app
tests/fakes.py                         (create) FakeHttp, make_ctx, fixtures
tests/test_*.py                        (create) one per module
```

---

### Task 1: Tooling baseline (deps, ruff, CI)

**Files:**
- Modify: `pyproject.toml`, `.gitignore`
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: nothing.
- Produces: an installed dev environment (`.venv`), `ruff check` config, CI that later tasks extend (Task 17 adds the frontend job).

- [ ] **Step 1: Create the virtualenv and confirm the baseline passes**

```bash
cd /home/mohammad/job-apply-agent
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
```
Expected: all existing tests pass (the PDF assertion is skipped automatically without LibreOffice).

- [ ] **Step 2: Add dependencies and ruff config to `pyproject.toml`**

Replace the `dependencies` list and `[project.optional-dependencies]`, bump the version and description, and add ruff:

```toml
[project]
name = "job-apply-agent"
version = "0.2.0"
description = "A personal AI agent (Claude Agent SDK) that finds jobs that fit you and tailors your resume to them."
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "claude-agent-sdk>=0.2.170",
    # Bundles the pandoc binary, so DOCX <-> Markdown works without a system install.
    "pypandoc-binary>=1.13",
    "python-docx>=1.1",
    # Local web app
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "python-multipart>=0.0.9",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
# DOCX -> PDF through Microsoft Word (Windows/macOS) when LibreOffice is not installed.
word = ["docx2pdf>=0.1.8"]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "httpx>=0.27", "ruff>=0.6"]
```

Append at the end of the file:

```toml
[tool.ruff]
line-length = 120
target-version = "py310"
extend-exclude = ["frontend"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
ignore = ["E501"]
```

- [ ] **Step 3: Ignore frontend build artifacts**

Append to `.gitignore`:

```gitignore

# Frontend
node_modules/
frontend/.vite/
```

- [ ] **Step 4: Install, lint and auto-fix the existing code**

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/ruff check src tests --fix
.venv/bin/ruff check src tests
.venv/bin/pytest -q
```
Expected: `All checks passed!` and all tests pass. If ruff reports something it can't auto-fix, fix it by hand without changing behavior.

- [ ] **Step 5: Add CI**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  python:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      - run: ruff check src tests
      - run: pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore .github/workflows/ci.yml src tests
git commit -m "chore: add web app deps, ruff and CI

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Paths, preferences and the .env reader

**Files:**
- Create: `src/job_apply_agent/paths.py`, `src/job_apply_agent/preferences.py`, `src/job_apply_agent/envfile.py`
- Test: `tests/test_preferences.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `paths.data_dir() -> Path`, `paths.output_dir() -> Path`, `paths.profile_dir()`, `paths.jobs_dir()`, `paths.db_path()`, `paths.preferences_path()`, `paths.companies_path()`, `paths.env_path()` (all `-> Path`, read env vars on every call).
  - `preferences.DEFAULT_PREFERENCES: dict`, `preferences.ROLE_TERMS: list[str]`, `preferences.SOURCE_NAMES: tuple[str, ...]` = `("greenhouse","lever","ashby","workday","jsearch","adzuna","linkedin")`.
  - `preferences.merge_defaults(prefs: dict) -> dict`, `validate_preferences(prefs: dict) -> dict` (raises `ValueError`), `load_preferences(path: Path | None = None) -> dict`, `save_preferences(prefs: dict, path: Path | None = None) -> None`, `resume_path(prefs: dict) -> Path`.
  - `envfile.KEYS`, `envfile.read_env_file(path: Path) -> dict[str, str]`, `envfile.load_env(path: Path | None = None) -> dict[str, str]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_preferences.py`:

```python
from pathlib import Path

import pytest

from job_apply_agent import envfile, paths, preferences
from job_apply_agent.preferences import (
    DEFAULT_PREFERENCES,
    load_preferences,
    merge_defaults,
    resume_path,
    save_preferences,
    validate_preferences,
)


def test_paths_follow_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("JOB_AGENT_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("JOB_AGENT_OUTPUT_DIR", str(tmp_path / "o"))
    assert paths.data_dir() == tmp_path / "d"
    assert paths.profile_dir() == tmp_path / "d" / "profile"
    assert paths.db_path() == tmp_path / "d" / "app.db"
    assert paths.output_dir() == tmp_path / "o"


def test_defaults_when_file_missing(tmp_path: Path):
    prefs = load_preferences(tmp_path / "missing.yaml")
    assert prefs == merge_defaults({})
    assert "machine learning engineer" not in prefs["role_terms"]
    assert "analytics engineer" in prefs["role_terms"]
    assert prefs["models"]["scoring"] == "claude-haiku-5-5"
    assert prefs["sources"]["jsearch"]["budget"] == 180


def test_user_values_override_defaults_and_lists_replace():
    merged = merge_defaults({"role_terms": ["data analyst"], "sources": {"linkedin": {"enabled": False}}})
    assert merged["role_terms"] == ["data analyst"]
    assert merged["sources"]["linkedin"]["enabled"] is False
    assert merged["sources"]["linkedin"]["interval_hours"] == DEFAULT_PREFERENCES["sources"]["linkedin"]["interval_hours"]
    assert merged["sources"]["greenhouse"]["enabled"] is True


def test_save_and_load_roundtrip(tmp_path: Path):
    path = tmp_path / "prefs.yaml"
    prefs = merge_defaults({"excluded_companies": ["Acme"]})
    save_preferences(prefs, path)
    assert load_preferences(path)["excluded_companies"] == ["Acme"]


@pytest.mark.parametrize(
    "bad",
    [
        {"role_terms": []},
        {"sources": {"monster": {"enabled": True}}},
        {"sources": {"lever": {"interval_hours": 0}}},
        {"target_score": 150},
        {"models": {"scoring": ""}},
    ],
)
def test_validate_rejects_bad_values(bad):
    with pytest.raises(ValueError):
        validate_preferences(merge_defaults(bad))


def test_resume_path_default_and_custom(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("JOB_AGENT_DATA_DIR", str(tmp_path))
    assert resume_path(merge_defaults({})) == tmp_path / "my_resume.docx"
    assert resume_path(merge_defaults({"resume_path": "/x/cv.md"})) == Path("/x/cv.md")


def test_env_file_and_environment(monkeypatch, tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text('# keys\nJSEARCH_API_KEY="abc"\nexport ADZUNA_APP_ID=id1\nnot a line\n', encoding="utf-8")
    monkeypatch.delenv("JSEARCH_API_KEY", raising=False)
    monkeypatch.setenv("ADZUNA_APP_ID", "from-env")
    values = envfile.load_env(env)
    assert values["JSEARCH_API_KEY"] == "abc"
    assert values["ADZUNA_APP_ID"] == "from-env"  # real environment wins
    assert envfile.read_env_file(tmp_path / "none") == {}


def test_preferences_module_exposes_source_names():
    assert preferences.SOURCE_NAMES == ("greenhouse", "lever", "ashby", "workday", "jsearch", "adzuna", "linkedin")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_preferences.py -q`
Expected: FAIL with `ImportError: cannot import name 'envfile'` (modules don't exist yet).

- [ ] **Step 3: Implement `paths.py`**

```python
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
```

- [ ] **Step 4: Implement `preferences.py`**

```python
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
    custom = (prefs.get("resume_path") or "").strip()
    return Path(custom) if custom else paths.data_dir() / "my_resume.docx"
```

- [ ] **Step 5: Implement `envfile.py`**

```python
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
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_preferences.py -q && .venv/bin/ruff check src tests`
Expected: PASS, `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add src/job_apply_agent/paths.py src/job_apply_agent/preferences.py src/job_apply_agent/envfile.py tests/test_preferences.py
git commit -m "feat: add data paths, search preferences and .env key loading

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Extract the tailoring loop and outputs from the CLI

**Files:**
- Modify: `src/job_apply_agent/jobs.py` (JobPosting fields, `clean_inline`, `save()` default)
- Create: `src/job_apply_agent/outputs.py`, `src/job_apply_agent/tailor_flow.py`
- Modify: `src/job_apply_agent/cli.py` (use them; `--resume` optional; path defaults)
- Test: `tests/test_tailor_flow.py`; existing tests must still pass unchanged.

**Interfaces:**
- Consumes: `paths.*`, `preferences.load_preferences`, `preferences.resume_path` (Task 2).
- Produces:
  - `JobPosting(url, title="", company="", location="", details={}, description="", source="", external_id="", posted_at=None, remote=None, country="", employment_type="", description_is_partial=False, board="")`.
  - `jobs.clean_inline(fragment: str) -> str`, `jobs.html_to_text(fragment: str) -> str` (existing).
  - `outputs.slugify(text, max_len=40) -> str`, `outputs.candidate_name(markdown) -> str`, `outputs.save_outputs(tailored, out_root: Path, formats: list[str], reference_docx: Path | None) -> tuple[Path, list[Path], list[str]]` (folder, files, warnings).
  - `tailor_flow.AskFn = Callable[[list[str]], Awaitable[list[tuple[str, str]]]]`, `TailorRequest`, `TailorOutcome(tailored, folder, files, warnings, rounds)`, `async run_tailor_flow(req, *, ask=None, progress=None, status=None) -> TailorOutcome`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tailor_flow.py`:

```python
from pathlib import Path

from job_apply_agent import outputs
from job_apply_agent.documents import ConversionError
from job_apply_agent.jobs import JobPosting
from job_apply_agent.tailor import TailoredResume
from job_apply_agent.tailor_flow import TailorRequest, run_tailor_flow
from test_profile_and_questions import SequenceQuery
from test_tailor import STRUCTURED


def test_job_posting_new_fields_default_and_to_text_unchanged():
    p = JobPosting(url="https://x/1", title="Data Analyst", company="Acme", description="Do analysis.")
    assert p.source == "" and p.external_id == "" and p.posted_at is None and p.remote is None
    assert p.description_is_partial is False and p.board == ""
    assert p.to_text().startswith("Source: https://x/1\nJob title: Data Analyst\nCompany: Acme")


async def test_flow_asks_saves_answers_and_rewrites(monkeypatch, tmp_path: Path, sample_resume_docx: Path):
    first = {**STRUCTURED, "match_score": 70, "questions_for_candidate": ["Used dbt?"]}
    second = {**STRUCTURED, "match_score": 88, "questions_for_candidate": []}
    fq = SequenceQuery([first, second])
    monkeypatch.setattr("job_apply_agent.tailor.query", fq)
    asked = []

    async def ask(questions):
        asked.append(questions)
        return [("Used dbt?", "Yes, 6 months at Northwind")]

    req = TailorRequest(resume_path=sample_resume_docx, job_text="Data Analyst at Maple", profile_dir=tmp_path / "p",
                        formats=["md"], out_dir=tmp_path / "out")
    outcome = await run_tailor_flow(req, ask=ask)

    assert asked == [["Used dbt?"]]
    assert outcome.rounds == 2 and outcome.tailored.match_score == 88
    assert "6 months at Northwind" in fq.prompts[1]
    assert (tmp_path / "p" / "answers.md").exists()
    assert {p.suffix for p in outcome.files} == {".md"}
    assert outcome.folder.parent == tmp_path / "out"


async def test_flow_without_ask_does_one_round(monkeypatch, tmp_path: Path, sample_resume_docx: Path):
    fq = SequenceQuery([{**STRUCTURED, "match_score": 60, "questions_for_candidate": ["Q?"]}])
    monkeypatch.setattr("job_apply_agent.tailor.query", fq)
    req = TailorRequest(resume_path=sample_resume_docx, job_text="job", profile_dir=tmp_path / "p",
                        formats=["md"], out_dir=tmp_path / "out")
    outcome = await run_tailor_flow(req, ask=None)
    assert outcome.rounds == 1 and len(fq.prompts) == 1


def test_save_outputs_reports_pdf_warning(monkeypatch, tmp_path: Path):
    def boom(_path):
        raise ConversionError("LibreOffice not found")

    monkeypatch.setattr(outputs, "docx_to_pdf", boom)
    tailored = TailoredResume.from_structured_output(STRUCTURED)
    folder, files, warnings = outputs.save_outputs(tailored, tmp_path, ["md", "docx", "pdf"], None)
    assert any("PDF skipped" in w for w in warnings)
    assert {p.suffix for p in files} == {".md", ".docx"}
    assert folder.name.endswith("_Maple-Commerce_Senior-Data-Analyst")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_tailor_flow.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_apply_agent.tailor_flow'`.

- [ ] **Step 3: Extend `JobPosting` in `jobs.py`**

In `src/job_apply_agent/jobs.py`, add `from . import paths` to the imports and replace the dataclass and `save` with:

```python
@dataclass
class JobPosting:
    url: str
    title: str = ""
    company: str = ""
    location: str = ""
    details: dict[str, str] = field(default_factory=dict)
    description: str = ""
    # Filled in by job search sources:
    source: str = ""  # greenhouse, lever, ashby, workday, jsearch, adzuna, linkedin
    external_id: str = ""  # the source's own ID for the job
    posted_at: str | None = None  # ISO 8601 UTC, when known
    remote: bool | None = None  # None = not stated
    country: str = ""
    employment_type: str = ""
    description_is_partial: bool = False  # True when the source only gives a snippet
    board: str = ""  # company board ID for career-site sources

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

    def save(self, folder: str | Path | None = None) -> Path:
        folder = Path(folder) if folder is not None else paths.jobs_dir()
        folder.mkdir(parents=True, exist_ok=True)
        name = "_".join(
            part for part in (_slug(self.company), _slug(self.title), linkedin_job_id(self.url) or "") if part
        )
        path = folder / f"{name or 'job'}.txt"
        path.write_text(self.to_text(), encoding="utf-8")
        return path
```

Below `_clean_inline` add the public alias:

```python
clean_inline = _clean_inline
```

- [ ] **Step 4: Create `outputs.py` (moved from `cli.py`, now returns warnings)**

```python
"""Write a tailored resume to disk as Markdown, Word and PDF, plus the report."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .documents import ConversionError, docx_to_pdf, write_docx
from .tailor import TailoredResume


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")
    return slug[:max_len].strip("-") or "job"


def candidate_name(markdown: str) -> str:
    """Name from the resume's first '# ' heading, e.g. 'Jane_Doe'."""
    match = re.search(r"^#\s+(.+)$", markdown, flags=re.MULTILINE)
    return slugify(match.group(1), 40).replace("-", "_") if match else "Resume"


def save_outputs(
    tailored: TailoredResume, out_root: Path, formats: list[str], reference_docx: Path | None
) -> tuple[Path, list[Path], list[str]]:
    """Returns (folder, saved files, warnings). Markdown and the report are always saved."""
    folder_name = f"{date.today():%Y-%m-%d}_{slugify(tailored.company or 'company', 30)}_{slugify(tailored.job_title)}"
    folder = out_root / folder_name
    folder.mkdir(parents=True, exist_ok=True)

    base = f"{candidate_name(tailored.tailored_resume_markdown)}_Resume"
    if tailored.company:
        base += f"_{slugify(tailored.company, 30).replace('-', '_')}"

    saved: list[Path] = []
    warnings: list[str] = []
    md_path = folder / f"{base}.md"
    md_path.write_text(tailored.tailored_resume_markdown + "\n", encoding="utf-8")
    saved.append(md_path)

    report_path = folder / "tailoring_report.md"
    report_path.write_text(tailored.report_markdown(), encoding="utf-8")
    saved.append(report_path)

    if "docx" in formats or "pdf" in formats:
        docx_path = write_docx(tailored.tailored_resume_markdown, folder / f"{base}.docx", reference_docx)
        if "docx" in formats:
            saved.append(docx_path)
        if "pdf" in formats:
            try:
                saved.append(docx_to_pdf(docx_path))
            except ConversionError as exc:
                warnings.append(f"PDF skipped: {exc}")
            if "docx" not in formats:
                docx_path.unlink(missing_ok=True)
    return folder, saved, warnings
```

- [ ] **Step 5: Create `tailor_flow.py`**

```python
"""The ask-then-rewrite tailoring loop, shared by the CLI and the web app.

Round 1 tailors the resume. If the match score is below the target and the agent has
questions, ``ask`` is called with them; true answers are saved to the profile and the
resume is rewritten, up to ``max_rounds`` rounds.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from . import tailor as tailor_module
from .career_profile import load_answers, load_profile, save_answers
from .documents import read_resume
from .outputs import save_outputs
from .tailor import DEFAULT_TARGET_SCORE, TailoredResume

AskFn = Callable[[list[str]], Awaitable[list[tuple[str, str]]]]
MessageFn = Callable[[str], None]


@dataclass
class TailorRequest:
    resume_path: Path
    job_text: str | None = None
    job_url: str | None = None
    profile_dir: Path | None = None
    extra_profile: list[Path] = field(default_factory=list)
    target_score: int = DEFAULT_TARGET_SCORE
    max_rounds: int = 3
    model: str | None = None
    instructions: str | None = None
    formats: list[str] = field(default_factory=lambda: ["md", "docx", "pdf"])
    out_dir: Path = field(default_factory=paths.output_dir)


@dataclass
class TailorOutcome:
    tailored: TailoredResume
    folder: Path
    files: list[Path]
    warnings: list[str]
    rounds: int


async def run_tailor_flow(
    req: TailorRequest,
    *,
    ask: AskFn | None = None,
    progress: MessageFn | None = None,
    status: MessageFn | None = None,
) -> TailorOutcome:
    """``progress`` gets the agent's own messages; ``status`` gets round-level updates."""
    say = status or (lambda _msg: None)
    resume_md = read_resume(req.resume_path)
    profile = load_profile(req.profile_dir, req.extra_profile)

    tailored: TailoredResume | None = None
    rounds = 0
    for round_no in range(1, max(1, req.max_rounds) + 1):
        rounds = round_no
        say(f"Round {round_no}: tailoring {req.resume_path.name} ... (usually a minute or two)")
        tailored = await tailor_module.tailor_resume(
            resume_md,
            job_text=req.job_text,
            job_url=req.job_url,
            profile=profile,
            answers=load_answers(req.profile_dir),
            target_score=req.target_score,
            extra_instructions=req.instructions,
            model=req.model,
            on_progress=progress,
        )
        say(f"Estimated match: {tailored.match_score}/100 (target {req.target_score})")
        if (
            tailored.match_score >= req.target_score
            or not tailored.questions_for_candidate
            or ask is None
            or req.profile_dir is None
            or round_no == req.max_rounds
        ):
            break
        answered = await ask(tailored.questions_for_candidate)
        if not answered:
            break
        path = save_answers(req.profile_dir, f"{tailored.job_title} at {tailored.company}", answered)
        say(f"Saved your answers to {path} (reused for future jobs).")

    assert tailored is not None
    reference = req.resume_path if req.resume_path.suffix.lower() == ".docx" else None
    folder, files, warnings = save_outputs(tailored, req.out_dir, req.formats, reference)
    return TailorOutcome(tailored=tailored, folder=folder, files=files, warnings=warnings, rounds=rounds)
```

- [ ] **Step 6: Update `cli.py` to use the shared code**

In `src/job_apply_agent/cli.py`:

1. Replace the imports block (lines 1–17) with:

```python
"""Command-line interface: ``job-agent tailor|fetch-job|render|search|serve ...``."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable
from pathlib import Path

from . import __version__, paths
from .documents import ConversionError, docx_to_pdf, write_docx
from .jobs import JobFetchError, fetch_job
from .outputs import candidate_name, save_outputs, slugify  # noqa: F401  (re-exported for compatibility)
from .preferences import load_preferences, resume_path
from .tailor import DEFAULT_TARGET_SCORE, TailoringError, auth_warning
from .tailor_flow import TailorRequest, run_tailor_flow
```

2. Delete the old `slugify`, `candidate_name` and `save_outputs` function bodies from `cli.py` (they now live in `outputs.py`).

3. In `build_parser`, change these arguments:

```python
    t.add_argument("--resume", type=Path, help="Your master resume (.docx, .md or .txt). Default: the one set in the app.")
```
```python
    t.add_argument(
        "--profile-dir",
        type=Path,
        default=paths.profile_dir(),
        help=f"Folder with your career profile documents and saved answers (default: {paths.profile_dir()}).",
    )
```
```python
    t.add_argument("--jobs-dir", type=Path, default=paths.jobs_dir(), help="Where fetched postings are saved.")
    t.add_argument("--out", type=Path, default=paths.output_dir(), help="Output folder (default: ./output).")
```
```python
    f.add_argument("--jobs-dir", type=Path, default=paths.jobs_dir(), help="Folder to save into (default: data/jobs).")
```

4. Replace `run_tailor` with:

```python
async def run_tailor(args: argparse.Namespace, ask: Callable[[str], str] = input) -> int:
    warning = auth_warning()
    if warning:
        print(f"! {warning}", file=sys.stderr)

    resume = args.resume or resume_path(load_preferences())
    if not resume.is_file():
        raise FileNotFoundError(f"Resume not found: {resume}. Pass --resume or add it in the app's Settings.")
    job_text, job_url = resolve_job(args)
    interactive = not args.no_questions and (ask is not input or sys.stdin.isatty())

    async def terminal_ask(questions: list[str]) -> list[tuple[str, str]]:
        return ask_questions(questions, ask)

    req = TailorRequest(
        resume_path=resume,
        job_text=job_text,
        job_url=job_url,
        profile_dir=args.profile_dir,
        extra_profile=args.profile,
        target_score=args.target_score,
        max_rounds=args.max_rounds,
        model=args.model,
        instructions=args.instructions,
        formats=args.formats,
        out_dir=args.out,
    )
    outcome = await run_tailor_flow(
        req,
        ask=terminal_ask if interactive else None,
        progress=None if args.quiet else (lambda msg: print(f"  · {msg}")),
        status=lambda msg: print(f"\n{msg}" if msg.startswith("Round") else msg),
    )
    for note in outcome.warnings:
        print(f"! {note}", file=sys.stderr)

    tailored = outcome.tailored
    print(f"\nDone: {tailored.job_title}{' at ' + tailored.company if tailored.company else ''}")
    print(f"Estimated match: {tailored.match_score}/100")
    if tailored.match_score < args.target_score:
        print("Below target. See the report's questions; answering them truthfully is the way to raise it.")
    if tailored.missing_keywords:
        print("Not shown in your resume or profile (not added): " + ", ".join(tailored.missing_keywords))
    print(f"\nSaved to {outcome.folder}/")
    for path in outcome.files:
        print(f"  - {path.name}")
    print("\nReview the resume before sending it: check every line is true and reads like you.")
    return 0
```

5. `run_render` still uses `write_docx`/`docx_to_pdf` directly; leave it unchanged.

- [ ] **Step 7: Run all tests and lint**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check src tests`
Expected: all tests pass, including the unchanged `test_profile_and_questions.py` and `test_tailor.py`.

- [ ] **Step 8: Commit**

```bash
git add src/job_apply_agent/jobs.py src/job_apply_agent/outputs.py src/job_apply_agent/tailor_flow.py src/job_apply_agent/cli.py tests/test_tailor_flow.py
git commit -m "refactor: share the tailoring loop and outputs between CLI and app

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Time helpers and the SQLite database

**Files:**
- Create: `src/job_apply_agent/timeutil.py`, `src/job_apply_agent/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `JobPosting` (Task 3).
- Produces:
  - `timeutil.now_utc() -> datetime`, `iso(dt) -> str` (UTC, seconds, `+00:00`), `parse_datetime(value) -> datetime | None` (ISO strings incl. `Z`, dates, epoch s/ms), `iso_or_none(value) -> str | None`, `parse_relative_posted(text, now) -> datetime | None` ("Posted Today", "Posted Yesterday", "Posted 4 Days Ago", "Posted 30+ Days Ago").
  - `db.Database(path: Path | str)` (`":memory:"` allowed) with: `close()`, `start_run(trigger, now) -> int`, `finish_run(run_id, *, sources: dict, scored: int, error: str | None, now)`, `get_run(id) -> dict | None`, `list_runs(limit=20) -> list[dict]`, `first_run_id() -> int | None`, `mark_source_attempt(source, now, success: bool)`, `source_states() -> dict[str, dict]`, `has_link(source, external_id) -> bool`, `upsert_posting(p, *, dedupe_key, canonical_url, relevant, location_label, run_id, now) -> tuple[int, bool]`, `mark_missing(source, board, seen_ids: set[str]) -> int`, `jobs_to_score(profile_hash) -> list[dict]`, `save_score(job_id, *, score, summary, reasons, gaps, seniority_fit, model, profile_hash, now)`, `list_jobs(*, now, tab="all", sort="score", order="desc", role=None, location=None, source=None, status=None, min_score=None, include_closed=False, hide_done=False) -> list[dict]`, `get_job(job_id) -> dict | None`, `update_job(job_id, **fields) -> dict | None` (fields: `status`, `notes`, `tailored_folder`), `all_jobs_for_refilter() -> list[dict]`, `set_relevance(job_id, relevant: bool, location_label: str)`, `counts(now) -> dict` (`relevant`, `unscored`, `new_24h`), `quota_used(source, period) -> int`, `quota_add(source, period, n=1)`.
  - `db.STATUSES`, `db.STALE_DAYS = 21`.
  - Job dicts from `list_jobs`: `id, title, company, location, location_label, remote, posted_at, first_seen_at, last_seen_at, score, summary, seniority_fit, status, closed, tailored_folder, sources (list[str])`. `get_job` adds `description, description_is_partial, reasons, gaps, notes, employment_type, links ([{source, url}])`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_db.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest

from job_apply_agent.db import Database
from job_apply_agent.jobs import JobPosting
from job_apply_agent.timeutil import iso, iso_or_none, parse_datetime, parse_relative_posted

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
T = iso(NOW)


def posting(**kw) -> JobPosting:
    base = dict(url="https://jobs.example/1", title="Data Analyst", company="Acme", location="Toronto, ON",
                description="Analyse data. " * 30, source="greenhouse", external_id="1", board="acme")
    base.update(kw)
    return JobPosting(**base)


def add(db, p, key="acme|data analyst|toronto", relevant=True, run_id=None, now=T):
    return db.upsert_posting(p, dedupe_key=key, canonical_url=p.url, relevant=relevant,
                             location_label="Toronto/GTA", run_id=run_id, now=now)


@pytest.fixture
def db():
    d = Database(":memory:")
    yield d
    d.close()


def test_time_helpers():
    assert iso_or_none("2026-11-05T17:56:22.425+00:00") == "2026-11-05T17:56:22+00:00"
    assert iso_or_none("2026-10-07T15:23:54-04:00") == "2026-10-07T19:23:54+00:00"
    assert iso_or_none(1791216082758) == iso(datetime.fromtimestamp(1791216082.758, tz=timezone.utc))
    assert parse_datetime("2026-11-08").day == 8 and parse_datetime("garbage") is None
    assert parse_relative_posted("Posted 4 Days Ago", NOW) == NOW - timedelta(days=4)
    assert parse_relative_posted("Posted 30+ Days Ago", NOW) == NOW - timedelta(days=30)
    assert parse_relative_posted("Posted Today", NOW) == NOW
    assert parse_relative_posted("Posted Yesterday", NOW) == NOW - timedelta(days=1)


def test_upsert_new_then_same_link_updates(db):
    run = db.start_run("manual", T)
    job_id, new = add(db, posting(), run_id=run)
    assert new is True
    again, new2 = add(db, posting(description="short"), run_id=run)
    assert again == job_id and new2 is False
    job = db.get_job(job_id)
    assert job["description"].startswith("Analyse data.")  # shorter text never replaces longer
    assert job["links"] == [{"source": "greenhouse", "url": "https://jobs.example/1"}]


def test_cross_source_merge_adds_link(db):
    job_id, _ = add(db, posting())
    other, new = add(db, posting(source="jsearch", external_id="js-9", url="https://apply.example/9"))
    assert other == job_id and new is False
    assert {link["source"] for link in db.get_job(job_id)["links"]} == {"greenhouse", "jsearch"}
    assert db.list_jobs(now=T)[0]["sources"] == ["greenhouse", "jsearch"]


def test_partial_description_replaced_by_full(db):
    job_id, _ = add(db, posting(source="adzuna", external_id="a1", description="snippet", description_is_partial=True))
    add(db, posting(source="lever", external_id="l1", url="https://jobs.lever.co/acme/l1"))
    job = db.get_job(job_id)
    assert job["description_is_partial"] is False and job["description"].startswith("Analyse")


def test_mark_missing_closes_after_two_runs(db):
    job_id, _ = add(db, posting())
    assert db.mark_missing("greenhouse", "acme", set()) == 0
    assert db.mark_missing("greenhouse", "acme", set()) == 1
    assert db.get_job(job_id)["closed"] is True
    assert db.list_jobs(now=T) == []
    assert len(db.list_jobs(now=T, include_closed=True)) == 1
    add(db, posting())  # seen again -> reopened
    assert db.get_job(job_id)["closed"] is False


def test_stale_jobs_hidden(db):
    add(db, posting(), now=iso(NOW - timedelta(days=30)))
    assert db.list_jobs(now=T) == []


def test_new_tab_rule_excludes_first_run_backlog(db):
    first = db.start_run("manual", T)
    add(db, posting(posted_at=None), run_id=first)  # backlog from very first run
    second = db.start_run("schedule", T)
    add(db, posting(external_id="2", url="https://jobs.example/2", title="Data Scientist"), key="k2", run_id=second)
    add(db, posting(external_id="3", url="https://jobs.example/3", title="Data Engineer",
                    posted_at=iso(NOW - timedelta(hours=3))), key="k3", run_id=first)
    titles = {j["title"] for j in db.list_jobs(now=T, tab="new")}
    assert titles == {"Data Scientist", "Data Engineer"}
    assert db.counts(T)["new_24h"] == 2


def test_sorting_filters_and_scores(db):
    a, _ = add(db, posting(), key="a")
    b, _ = add(db, posting(external_id="2", url="https://jobs.example/2", title="BI Analyst", company="Beta"), key="b")
    add(db, posting(external_id="3", url="https://jobs.example/3", title="Data Engineer", company="Zed"), key="c")
    db.save_score(a, score=60, summary="ok", reasons=["SQL"], gaps=["dbt"], seniority_fit="fit", model="m",
                  profile_hash="h1", now=T)
    db.save_score(b, score=90, summary="great", reasons=[], gaps=[], seniority_fit="fit", model="m",
                  profile_hash="h1", now=T)
    assert [j["score"] for j in db.list_jobs(now=T)] == [90, 60, None]  # unscored last
    assert [j["company"] for j in db.list_jobs(now=T, sort="company", order="asc")] == ["Acme", "Beta", "Zed"]
    assert [j["title"] for j in db.list_jobs(now=T, role="engineer")] == ["Data Engineer"]
    assert [j["score"] for j in db.list_jobs(now=T, min_score=70)] == [90]
    assert {j["id"] for j in db.jobs_to_score("h1")} == {3}
    assert len(db.jobs_to_score("h2")) == 3  # resume changed -> everything re-scored
    assert db.get_job(a)["reasons"] == ["SQL"]


def test_update_job_and_hide_done(db):
    job_id, _ = add(db, posting())
    assert db.update_job(job_id, status="applied", notes="sent")["status"] == "applied"
    assert db.list_jobs(now=T, hide_done=True) == []
    with pytest.raises(ValueError):
        db.update_job(job_id, status="bogus")
    assert db.update_job(999, status="saved") is None


def test_irrelevant_jobs_never_listed_or_scored(db):
    add(db, posting(title="Sales Rep"), relevant=False)
    assert db.list_jobs(now=T) == [] and db.jobs_to_score("h") == []


def test_runs_quota_and_source_state(db):
    run = db.start_run("manual", T)
    db.finish_run(run, sources={"lever": {"status": "ok", "fetched": 3}}, scored=2, error=None, now=T)
    assert db.get_run(run)["sources"]["lever"]["fetched"] == 3
    assert db.list_runs()[0]["scored"] == 2 and db.first_run_id() == run
    db.quota_add("jsearch", "2026-11")
    db.quota_add("jsearch", "2026-11", 2)
    assert db.quota_used("jsearch", "2026-11") == 3 and db.quota_used("jsearch", "2026-12") == 0
    db.mark_source_attempt("lever", T, success=False)
    assert db.source_states()["lever"] == {"last_attempt_at": T, "last_success_at": None}
    db.mark_source_attempt("lever", T, success=True)
    assert db.source_states()["lever"]["last_success_at"] == T
    assert db.has_link("greenhouse", "1") is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_db.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_apply_agent.db'`.

- [ ] **Step 3: Implement `timeutil.py`**

```python
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
```

- [ ] **Step 4: Implement `db.py`**

```python
"""Local SQLite database (``data/app.db``): jobs, where each was found, search runs, quotas."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import timedelta
from pathlib import Path
from typing import Any

from .jobs import JobPosting
from .timeutil import iso, parse_datetime

SCHEMA_VERSION = 1
STALE_DAYS = 21
STATUSES = ("new", "saved", "applied", "interview", "offer", "rejected")

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY,
  dedupe_key TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  company TEXT NOT NULL DEFAULT '',
  location TEXT NOT NULL DEFAULT '',
  location_label TEXT NOT NULL DEFAULT '',
  remote INTEGER,
  country TEXT NOT NULL DEFAULT '',
  employment_type TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  description_is_partial INTEGER NOT NULL DEFAULT 0,
  posted_at TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  first_run_id INTEGER,
  relevant INTEGER NOT NULL DEFAULT 0,
  closed INTEGER NOT NULL DEFAULT 0,
  score INTEGER,
  summary TEXT,
  reasons TEXT NOT NULL DEFAULT '[]',
  gaps TEXT NOT NULL DEFAULT '[]',
  seniority_fit TEXT,
  scored_at TEXT,
  score_model TEXT,
  profile_hash TEXT,
  status TEXT NOT NULL DEFAULT 'new',
  notes TEXT NOT NULL DEFAULT '',
  tailored_folder TEXT,
  status_updated_at TEXT
);
CREATE INDEX IF NOT EXISTS jobs_listing ON jobs (relevant, closed, score);
CREATE TABLE IF NOT EXISTS job_links (
  id INTEGER PRIMARY KEY,
  job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  source TEXT NOT NULL,
  external_id TEXT NOT NULL,
  board TEXT NOT NULL DEFAULT '',
  url TEXT NOT NULL,
  canonical_url TEXT NOT NULL DEFAULT '',
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  missed_runs INTEGER NOT NULL DEFAULT 0,
  UNIQUE (source, external_id)
);
CREATE INDEX IF NOT EXISTS job_links_canonical ON job_links (canonical_url);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  trigger TEXT NOT NULL,
  sources TEXT NOT NULL DEFAULT '{}',
  scored INTEGER NOT NULL DEFAULT 0,
  error TEXT
);
CREATE TABLE IF NOT EXISTS quota (
  source TEXT NOT NULL,
  period TEXT NOT NULL,
  calls INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (source, period)
);
CREATE TABLE IF NOT EXISTS source_state (
  source TEXT PRIMARY KEY,
  last_attempt_at TEXT,
  last_success_at TEXT
);
"""

LIST_COLUMNS = (
    "j.id, j.title, j.company, j.location, j.location_label, j.remote, j.posted_at, j.first_seen_at, "
    "j.last_seen_at, j.score, j.summary, j.seniority_fit, j.status, j.closed, j.tailored_folder"
)
SOURCES_SUBQUERY = "(SELECT GROUP_CONCAT(DISTINCT l.source) FROM job_links l WHERE l.job_id = j.id) AS sources"
NEW_SQL = (
    "(j.posted_at >= ? OR (j.posted_at IS NULL AND j.first_seen_at >= ? "
    "AND j.first_run_id IS NOT NULL AND j.first_run_id != ?))"
)
SORTS = {
    "score": "j.score IS NULL, j.score {o}, COALESCE(j.posted_at, j.first_seen_at) DESC",
    "posted": "COALESCE(j.posted_at, j.first_seen_at) {o}",
    "company": "j.company COLLATE NOCASE {o}",
    "title": "j.title COLLATE NOCASE {o}",
}
UPDATABLE = ("status", "notes", "tailored_folder")


def _job(row: sqlite3.Row) -> dict[str, Any]:
    job = dict(row)
    if job.get("remote") is not None:
        job["remote"] = bool(job["remote"])
    for key in ("closed", "description_is_partial", "relevant"):
        if key in job:
            job[key] = bool(job[key])
    for key in ("reasons", "gaps"):
        if key in job:
            job[key] = json.loads(job[key] or "[]")
    if "sources" in job:
        job["sources"] = sorted(set(job["sources"].split(","))) if job["sources"] else []
    return job


def _run(row: sqlite3.Row) -> dict[str, Any]:
    run = dict(row)
    run["sources"] = json.loads(run["sources"] or "{}")
    return run


def _shift(now: str, **delta) -> str:
    parsed = parse_datetime(now)
    assert parsed is not None, f"bad timestamp {now!r}"
    return iso(parsed - timedelta(**delta))


class Database:
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._conn.execute("PRAGMA foreign_keys = ON")
            if self.path != ":memory:":
                self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.executescript(SCHEMA)
            if self._conn.execute("SELECT version FROM schema_version").fetchone() is None:
                self._conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- low-level helpers -------------------------------------------------------------

    def _write(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, args)
            self._conn.commit()
            return cur

    def _all(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, args).fetchall()

    def _one(self, sql: str, args: tuple = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, args).fetchone()

    # --- runs and source state ---------------------------------------------------------

    def start_run(self, trigger: str, now: str) -> int:
        return int(self._write("INSERT INTO runs (started_at, trigger) VALUES (?, ?)", (now, trigger)).lastrowid)

    def finish_run(self, run_id: int, *, sources: dict, scored: int, error: str | None, now: str) -> None:
        self._write(
            "UPDATE runs SET finished_at = ?, sources = ?, scored = ?, error = ? WHERE id = ?",
            (now, json.dumps(sources), scored, error, run_id),
        )

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        row = self._one("SELECT * FROM runs WHERE id = ?", (run_id,))
        return _run(row) if row else None

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        return [_run(r) for r in self._all("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))]

    def first_run_id(self) -> int | None:
        row = self._one("SELECT MIN(id) AS id FROM runs")
        return row["id"] if row else None

    def mark_source_attempt(self, source: str, now: str, success: bool) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO source_state (source, last_attempt_at) VALUES (?, ?) "
                "ON CONFLICT(source) DO UPDATE SET last_attempt_at = excluded.last_attempt_at",
                (source, now),
            )
            if success:
                self._conn.execute("UPDATE source_state SET last_success_at = ? WHERE source = ?", (now, source))
            self._conn.commit()

    def source_states(self) -> dict[str, dict[str, str | None]]:
        rows = self._all("SELECT source, last_attempt_at, last_success_at FROM source_state")
        return {r["source"]: {"last_attempt_at": r["last_attempt_at"], "last_success_at": r["last_success_at"]}
                for r in rows}

    # --- jobs ---------------------------------------------------------------------------

    def has_link(self, source: str, external_id: str) -> bool:
        return self._one("SELECT 1 FROM job_links WHERE source = ? AND external_id = ?",
                         (source, external_id)) is not None

    def upsert_posting(
        self,
        p: JobPosting,
        *,
        dedupe_key: str,
        canonical_url: str,
        relevant: bool,
        location_label: str,
        run_id: int | None,
        now: str,
    ) -> tuple[int, bool]:
        """Insert or update a posting. Returns (job_id, created_new_job)."""
        external_id = p.external_id or canonical_url or p.url
        with self._lock:
            c = self._conn
            row = c.execute("SELECT job_id FROM job_links WHERE source = ? AND external_id = ?",
                            (p.source, external_id)).fetchone()
            if row:
                job_id = row["job_id"]
                c.execute(
                    "UPDATE job_links SET last_seen_at = ?, missed_runs = 0, url = ? WHERE source = ? AND external_id = ?",
                    (now, p.url, p.source, external_id),
                )
                self._merge_job(job_id, p, relevant, location_label, now)
                c.commit()
                return job_id, False
            row = c.execute("SELECT id FROM jobs WHERE dedupe_key = ?", (dedupe_key,)).fetchone()
            if row is None and canonical_url:
                row = c.execute("SELECT job_id AS id FROM job_links WHERE canonical_url = ?", (canonical_url,)).fetchone()
            if row:
                job_id = row["id"]
                self._insert_link(job_id, p, external_id, canonical_url, now)
                self._merge_job(job_id, p, relevant, location_label, now)
                c.commit()
                return job_id, False
            cur = c.execute(
                "INSERT INTO jobs (dedupe_key, title, company, location, location_label, remote, country, "
                "employment_type, description, description_is_partial, posted_at, first_seen_at, last_seen_at, "
                "first_run_id, relevant) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    dedupe_key, p.title, p.company, p.location, location_label if relevant else "",
                    None if p.remote is None else int(p.remote), p.country, p.employment_type, p.description,
                    int(p.description_is_partial or not p.description), p.posted_at, now, now, run_id, int(relevant),
                ),
            )
            job_id = int(cur.lastrowid)
            self._insert_link(job_id, p, external_id, canonical_url, now)
            c.commit()
            return job_id, True

    def _insert_link(self, job_id: int, p: JobPosting, external_id: str, canonical_url: str, now: str) -> None:
        self._conn.execute(
            "INSERT INTO job_links (job_id, source, external_id, board, url, canonical_url, first_seen_at, last_seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (job_id, p.source, external_id, p.board, p.url, canonical_url, now, now),
        )

    def _merge_job(self, job_id: int, p: JobPosting, relevant: bool, label: str, now: str) -> None:
        old = self._conn.execute(
            "SELECT description, description_is_partial, relevant, posted_at FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        new_full = bool(p.description) and not p.description_is_partial
        replace = bool(p.description) and (
            not old["description"]
            or (old["description_is_partial"] and new_full)
            or (new_full and len(p.description) > len(old["description"]))
        )
        fields: dict[str, Any] = {"last_seen_at": now, "closed": 0}
        if replace:
            fields["description"] = p.description
            fields["description_is_partial"] = int(not new_full)
        if not old["posted_at"] and p.posted_at:
            fields["posted_at"] = p.posted_at
        if relevant and not old["relevant"]:
            fields["relevant"] = 1
            fields["location_label"] = label
        assignments = ", ".join(f"{key} = ?" for key in fields)
        self._conn.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", (*fields.values(), job_id))

    def mark_missing(self, source: str, board: str, seen_ids: set[str]) -> int:
        """Count a missed run for this board's links not in ``seen_ids``; close jobs missed twice.

        Returns the number of jobs closed by this call."""
        with self._lock:
            c = self._conn
            rows = c.execute("SELECT id, external_id FROM job_links WHERE source = ? AND board = ?",
                             (source, board)).fetchall()
            missing = [(r["id"],) for r in rows if r["external_id"] not in seen_ids]
            c.executemany("UPDATE job_links SET missed_runs = missed_runs + 1 WHERE id = ?", missing)
            cur = c.execute(
                "UPDATE jobs SET closed = 1 WHERE closed = 0 AND id IN "
                "(SELECT job_id FROM job_links WHERE source = ? AND board = ? AND missed_runs >= 2) "
                "AND NOT EXISTS (SELECT 1 FROM job_links l WHERE l.job_id = jobs.id AND l.missed_runs < 2)",
                (source, board),
            )
            c.commit()
            return cur.rowcount

    def jobs_to_score(self, profile_hash: str) -> list[dict[str, Any]]:
        rows = self._all(
            "SELECT id, title, company, location, description FROM jobs WHERE relevant = 1 AND closed = 0 "
            "AND (score IS NULL OR profile_hash IS NOT ?) ORDER BY first_seen_at DESC, id DESC",
            (profile_hash,),
        )
        return [dict(r) for r in rows]

    def save_score(self, job_id: int, *, score: int, summary: str, reasons: list[str], gaps: list[str],
                   seniority_fit: str, model: str, profile_hash: str, now: str) -> None:
        self._write(
            "UPDATE jobs SET score = ?, summary = ?, reasons = ?, gaps = ?, seniority_fit = ?, score_model = ?, "
            "profile_hash = ?, scored_at = ? WHERE id = ?",
            (score, summary, json.dumps(reasons), json.dumps(gaps), seniority_fit, model, profile_hash, now, job_id),
        )

    def list_jobs(
        self,
        *,
        now: str,
        tab: str = "all",
        sort: str = "score",
        order: str = "desc",
        role: str | None = None,
        location: str | None = None,
        source: str | None = None,
        status: str | None = None,
        min_score: int | None = None,
        include_closed: bool = False,
        hide_done: bool = False,
    ) -> list[dict[str, Any]]:
        where = ["j.relevant = 1"]
        args: list[Any] = []
        if not include_closed:
            where.append("j.closed = 0 AND j.last_seen_at >= ?")
            args.append(_shift(now, days=STALE_DAYS))
        if tab == "new":
            cutoff = _shift(now, hours=24)
            where.append(NEW_SQL)
            args += [cutoff, cutoff, self.first_run_id() or -1]
        if role:
            where.append("LOWER(j.title) LIKE ?")
            args.append(f"%{role.lower()}%")
        if location:
            where.append("j.location_label = ?")
            args.append(location)
        if source:
            where.append("EXISTS (SELECT 1 FROM job_links l WHERE l.job_id = j.id AND l.source = ?)")
            args.append(source)
        if status:
            where.append("j.status = ?")
            args.append(status)
        if hide_done:
            where.append("j.status NOT IN ('applied', 'rejected')")
        if min_score is not None:
            where.append("j.score >= ?")
            args.append(min_score)
        direction = "ASC" if order == "asc" else "DESC"
        order_by = SORTS.get(sort, SORTS["score"]).format(o=direction)
        sql = (f"SELECT {LIST_COLUMNS}, {SOURCES_SUBQUERY} FROM jobs j WHERE {' AND '.join(where)} "
               f"ORDER BY {order_by} LIMIT 1000")
        return [_job(r) for r in self._all(sql, tuple(args))]

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        row = self._one(f"SELECT j.*, {SOURCES_SUBQUERY} FROM jobs j WHERE j.id = ?", (job_id,))
        if row is None:
            return None
        job = _job(row)
        job["links"] = [
            {"source": r["source"], "url": r["url"]}
            for r in self._all("SELECT source, url FROM job_links WHERE job_id = ? ORDER BY id", (job_id,))
        ]
        return job

    def update_job(self, job_id: int, **fields: Any) -> dict[str, Any] | None:
        unknown = set(fields) - set(UPDATABLE)
        if unknown:
            raise ValueError(f"Can't update: {', '.join(sorted(unknown))}")
        if "status" in fields and fields["status"] not in STATUSES:
            raise ValueError(f"Unknown status {fields['status']!r}")
        if self._one("SELECT 1 FROM jobs WHERE id = ?", (job_id,)) is None:
            return None
        if fields:
            assignments = ", ".join(f"{key} = ?" for key in fields)
            self._write(f"UPDATE jobs SET {assignments} WHERE id = ?", (*fields.values(), job_id))
        return self.get_job(job_id)

    def all_jobs_for_refilter(self) -> list[dict[str, Any]]:
        rows = self._all("SELECT id, title, company, location, remote, country, relevant, location_label FROM jobs")
        return [_job(r) for r in rows]

    def set_relevance(self, job_id: int, relevant: bool, location_label: str) -> None:
        self._write("UPDATE jobs SET relevant = ?, location_label = ? WHERE id = ?",
                    (int(relevant), location_label if relevant else "", job_id))

    def counts(self, now: str) -> dict[str, int]:
        visible = "j.relevant = 1 AND j.closed = 0 AND j.last_seen_at >= ?"
        stale = _shift(now, days=STALE_DAYS)
        cutoff = _shift(now, hours=24)
        relevant = self._one(f"SELECT COUNT(*) AS n FROM jobs j WHERE {visible}", (stale,))["n"]
        unscored = self._one(f"SELECT COUNT(*) AS n FROM jobs j WHERE {visible} AND j.score IS NULL", (stale,))["n"]
        new_24h = self._one(f"SELECT COUNT(*) AS n FROM jobs j WHERE {visible} AND {NEW_SQL}",
                            (stale, cutoff, cutoff, self.first_run_id() or -1))["n"]
        return {"relevant": relevant, "unscored": unscored, "new_24h": new_24h}

    # --- quota --------------------------------------------------------------------------

    def quota_used(self, source: str, period: str) -> int:
        row = self._one("SELECT calls FROM quota WHERE source = ? AND period = ?", (source, period))
        return int(row["calls"]) if row else 0

    def quota_add(self, source: str, period: str, n: int = 1) -> None:
        self._write(
            "INSERT INTO quota (source, period, calls) VALUES (?, ?, ?) "
            "ON CONFLICT(source, period) DO UPDATE SET calls = calls + excluded.calls",
            (source, period, n),
        )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_db.py -q && .venv/bin/ruff check src tests`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/job_apply_agent/timeutil.py src/job_apply_agent/db.py tests/test_db.py
git commit -m "feat: add SQLite job database with dedupe links, runs and quotas

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Relevance gate and dedupe keys

**Files:**
- Create: `src/job_apply_agent/search/__init__.py` (empty docstring), `src/job_apply_agent/search/dedupe.py`, `src/job_apply_agent/search/filters.py`
- Test: `tests/test_filters_dedupe.py`

**Interfaces:**
- Consumes: `JobPosting` (Task 3), `merge_defaults` (Task 2).
- Produces:
  - `dedupe.fold(text) -> str` (accent-free lowercase), `normalize_company(name) -> str`, `normalize_title(title) -> str`, `primary_city(location, remote) -> str`, `dedupe_key(p: JobPosting) -> str`, `canonical_url(url) -> str`.
  - `filters.role_matches(title: str, role_terms: list[str]) -> bool`, `location_label(p: JobPosting, loc_prefs: dict) -> str | None`, `company_excluded(company, excluded) -> bool`, `evaluate(p: JobPosting, prefs: dict) -> tuple[bool, str]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_filters_dedupe.py`:

```python
import pytest

from job_apply_agent.jobs import JobPosting
from job_apply_agent.preferences import merge_defaults
from job_apply_agent.search.dedupe import canonical_url, dedupe_key, normalize_company, normalize_title
from job_apply_agent.search.filters import evaluate, location_label, role_matches

PREFS = merge_defaults({})


def job(title="Data Analyst", location="Toronto, ON", **kw) -> JobPosting:
    return JobPosting(url="https://x/1", title=title, company=kw.pop("company", "Acme"), location=location, **kw)


@pytest.mark.parametrize(
    ("title", "ok"),
    [
        ("Senior Data Analyst II", True),
        ("Analytics Engineer", True),
        ("BI Developer (Power BI)", True),
        ("Head of Analytics", True),
        ("Data Scientist, Pricing", True),
        ("Machine Learning Engineer", False),
        ("Software Engineer, Big Data Platform", False),
        ("Account Executive", False),
    ],
)
def test_role_terms(title, ok):
    assert role_matches(title, PREFS["role_terms"]) is ok


@pytest.mark.parametrize(
    ("location", "remote", "country", "label"),
    [
        ("Toronto, ON", None, "", "Toronto/GTA"),
        ("Toronto, CA", None, "", "Toronto/GTA"),
        ("Mississauga, Ontario", None, "", "Toronto/GTA"),
        ("Kanata, Ontario - Canada", None, "", "Ottawa"),
        ("Remote (Canada)", True, "Canada", "Remote (Canada)"),
        ("Canada - Remote (ON, AB, BC, or NS Only)", None, "", "Remote (Canada)"),
        ("Remote (United States | Canada)", None, "", "Remote (Canada)"),
        ("KOHO (CAN)", True, "", "Remote (Canada)"),
        ("Canada", None, "", "Remote (Canada)"),
        ("Remote", True, "CA", "Remote (Canada)"),
        ("Remote - US", True, "", None),
        ("San Francisco, CA", None, "", None),
        ("Vancouver, BC", None, "", None),
        ("Montréal, QC", False, "Canada", None),
        ("3 Locations", None, "", None),
        ("", None, "", "Unknown"),
    ],
)
def test_location_cases(location, remote, country, label):
    assert location_label(job(location=location, remote=remote, country=country), PREFS["locations"]) == label


def test_evaluate_combines_role_location_and_exclusions():
    assert evaluate(job(), PREFS) == (True, "Toronto/GTA")
    assert evaluate(job(title="Recruiter"), PREFS) == (False, "")
    assert evaluate(job(location="Austin, TX"), PREFS) == (False, "")
    excluded = merge_defaults({"excluded_companies": ["ACME Inc."]})
    assert evaluate(job(), excluded) == (False, "")
    no_unknown = merge_defaults({"locations": {"include_unknown": False}})
    assert evaluate(job(location=""), no_unknown) == (False, "")


def test_normalizers():
    assert normalize_company("Wealthsimple Technologies Inc.") == "wealthsimple technologies"
    assert normalize_company("TD Bank, Ltd") == "td bank"
    assert normalize_title("Sr. Data Analyst (Remote)") == "senior data analyst"
    assert normalize_title("Data Analyst - Toronto") == "data analyst"
    assert canonical_url("https://Boards.Greenhouse.io/faire/jobs/88?gh_jid=88#x") == "boards.greenhouse.io/faire/jobs/88"
    assert canonical_url("not a url") == ""


def test_dedupe_key_merges_variants():
    a = job(title="Senior Data Analyst", company="Acme Inc.", location="Toronto, Ontario, Canada")
    b = job(title="Sr. Data Analyst (Hybrid)", company="ACME", location="Toronto, ON")
    c = job(title="Data Analyst", company="Acme", location="Toronto, ON")
    d = job(title="Senior Data Analyst", company="Acme", location="Montréal, QC")
    assert dedupe_key(a) == dedupe_key(b)
    assert dedupe_key(a) != dedupe_key(c)  # seniority kept
    assert dedupe_key(a) != dedupe_key(d)  # city kept
    assert dedupe_key(d).endswith("|montreal")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_filters_dedupe.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_apply_agent.search'`.

- [ ] **Step 3: Implement `search/__init__.py` and `search/dedupe.py`**

`src/job_apply_agent/search/__init__.py`:

```python
"""Automatic job search: sources, relevance gate, dedupe, Claude scoring and scheduling."""
```

`src/job_apply_agent/search/dedupe.py`:

```python
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
```

- [ ] **Step 4: Implement `search/filters.py`**

```python
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
```

Note on `"Remote (United States | Canada)"`: it has "remote" and "canada", so it passes.
`"KOHO (CAN)"` passes because `remote=True` and `(can)` matches.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_filters_dedupe.py -q && .venv/bin/ruff check src tests`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/job_apply_agent/search tests/test_filters_dedupe.py
git commit -m "feat: add relevance gate and cross-source dedupe keys

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Source plumbing: HTTP helper, quota guard, companies, source base

**Files:**
- Create: `src/job_apply_agent/search/http.py`, `search/quota.py`, `search/companies.py`, `search/default_companies.yaml`, `search/base.py`
- Create: `tests/fakes.py`
- Test: `tests/test_search_plumbing.py`

**Interfaces:**
- Consumes: `Database` (Task 4), `paths` (Task 2), `JobPosting` (Task 3).
- Produces:
  - `http.HttpError(status: int | None, url: str, message="")` with `.status`, `.url`; `http.RateLimited(HttpError)`; `http.Response(status: int, text: str)` with `.json()`; `http.Http(fetch=urllib_fetch, *, retries=2, backoff=1.0, timeout=25.0, host_delays: dict[str, tuple[float, float]] | None = None, default_delay=0.5, sleep=asyncio.sleep, clock=time.monotonic)` with `async get_json(url, *, params=None, headers=None, retry_429=True)`, `async post_json(url, body, *, headers=None, retry_429=True)`, `async get_text(url, *, params=None, headers=None, retry_429=True)`.
  - `quota.QuotaExceeded`, `quota.period_key(period, now) -> str`, `quota.next_reset(period, now) -> date`, `quota.budgets_from_prefs(prefs) -> dict[str, tuple[int, str]]`, `quota.QuotaGuard(db, budgets, now_fn=now_utc)` with `remaining(source) -> int | None`, `consume(source, n=1)`, `usage() -> dict[str, dict]` (`used`, `budget`, `period`, `resets`).
  - `companies.ATS`, `load_companies(path=None) -> list[dict]`, `save_companies(items, path=None) -> list[dict]`, `validate_companies(items) -> list[dict]`, `board_id(company) -> str`, `async test_company(company: dict, http) -> dict`.
  - `base.SourceResult(postings=[], seen_ids={}, warnings=[], skipped=None)`, `base.SourceContext(prefs, companies, http, quota, env, role_ok, known, last_success, progress)` with `source_prefs(name) -> dict`, `companies_for(ats) -> list[dict]`; `base.Source = Callable[[SourceContext], Awaitable[SourceResult]]`; `async base.gather_companies(ctx, ats, fetch_company, concurrency=4) -> SourceResult` where `fetch_company(ctx, company) -> tuple[list[JobPosting], set[str] | None]`.
  - `tests/fakes.py`: `FakeHttp(routes: dict[str, object])`, `make_ctx(*, prefs=None, companies=(), routes=None, env=None, known=(), last_success=None, db=None) -> SourceContext`.

- [ ] **Step 1: Write the test fakes**

Create `tests/fakes.py`:

```python
"""Shared test doubles for the job search code. No network, no Claude."""

from __future__ import annotations

from datetime import datetime

from job_apply_agent.db import Database
from job_apply_agent.preferences import merge_defaults
from job_apply_agent.search.base import SourceContext
from job_apply_agent.search.filters import role_matches
from job_apply_agent.search.http import HttpError
from job_apply_agent.search.quota import QuotaGuard, budgets_from_prefs


class FakeHttp:
    """Answers requests from ``routes``: {url_prefix: json/text value or Exception}. First matching prefix wins."""

    def __init__(self, routes: dict[str, object] | None = None):
        self.routes = routes or {}
        self.calls: list[tuple] = []

    def _answer(self, url: str):
        for prefix, value in self.routes.items():
            if url.startswith(prefix):
                if isinstance(value, Exception):
                    raise value
                return value
        raise HttpError(404, url)

    async def get_json(self, url, *, params=None, headers=None, retry_429=True):
        self.calls.append(("GET", url, params, headers))
        return self._answer(url)

    async def post_json(self, url, body, *, headers=None, retry_429=True):
        self.calls.append(("POST", url, body, headers))
        return self._answer(url)

    async def get_text(self, url, *, params=None, headers=None, retry_429=True):
        self.calls.append(("GET", url, params, headers))
        return self._answer(url)


def make_ctx(*, prefs=None, companies=(), routes=None, env=None, known=(), last_success=None, db=None,
             now: datetime | None = None) -> SourceContext:
    prefs = merge_defaults(prefs or {})
    db = db or Database(":memory:")
    known_set = set(known)
    quota_kwargs = {"now_fn": (lambda: now)} if now else {}
    return SourceContext(
        prefs=prefs,
        companies=list(companies),
        http=FakeHttp(routes),
        quota=QuotaGuard(db, budgets_from_prefs(prefs), **quota_kwargs),
        env=env or {},
        role_ok=lambda title: role_matches(title, prefs["role_terms"]),
        known=lambda source, external_id: (source, external_id) in known_set,
        last_success=lambda source: (last_success or {}).get(source),
        progress=lambda _msg: None,
    )
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_search_plumbing.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fakes import make_ctx
from job_apply_agent.db import Database
from job_apply_agent.jobs import JobPosting
from job_apply_agent.search import companies as companies_mod
from job_apply_agent.search.base import gather_companies
from job_apply_agent.search.http import Http, HttpError, RateLimited, Response
from job_apply_agent.search.quota import QuotaExceeded, QuotaGuard, next_reset, period_key

NOW = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)


class ScriptedFetch:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url, headers, body))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


async def no_sleep(_seconds):
    return None


async def test_http_retries_5xx_then_succeeds():
    fetch = ScriptedFetch(Response(503, ""), Response(200, '{"ok": true}'))
    http = Http(fetch, sleep=no_sleep, default_delay=0)
    assert await http.get_json("https://api.example/x", params={"q": "data analyst"}) == {"ok": True}
    assert fetch.calls[0][1] == "https://api.example/x?q=data+analyst"
    assert len(fetch.calls) == 2


async def test_http_network_error_after_retries():
    fetch = ScriptedFetch(OSError("down"), OSError("down"), OSError("down"))
    http = Http(fetch, sleep=no_sleep, default_delay=0)
    with pytest.raises(HttpError, match="Couldn't reach"):
        await http.get_text("https://api.example/x")


async def test_http_429_without_retry_raises_rate_limited():
    http = Http(ScriptedFetch(Response(429, "")), sleep=no_sleep, default_delay=0)
    with pytest.raises(RateLimited):
        await http.get_text("https://www.linkedin.com/x", retry_429=False)


async def test_http_4xx_and_bad_json():
    http = Http(ScriptedFetch(Response(404, "nope"), Response(200, "<html>")), sleep=no_sleep, default_delay=0)
    with pytest.raises(HttpError) as err:
        await http.get_json("https://api.example/a")
    assert err.value.status == 404
    with pytest.raises(HttpError, match="JSON"):
        await http.get_json("https://api.example/b")


async def test_http_post_sends_json_body():
    fetch = ScriptedFetch(Response(200, "{}"))
    await Http(fetch, sleep=no_sleep, default_delay=0).post_json("https://wd/x", {"a": 1})
    method, _url, headers, body = fetch.calls[0]
    assert method == "POST" and body == b'{"a": 1}' and headers["Content-Type"] == "application/json"


def test_quota_guard_budget_and_reset():
    db = Database(":memory:")
    guard = QuotaGuard(db, {"jsearch": (2, "month")}, now_fn=lambda: NOW)
    assert guard.remaining("jsearch") == 2 and guard.remaining("greenhouse") is None
    guard.consume("jsearch")
    guard.consume("jsearch")
    with pytest.raises(QuotaExceeded, match="2026-12-01"):
        guard.consume("jsearch")
    assert guard.usage()["jsearch"] == {"used": 2, "budget": 2, "period": "month", "resets": "2026-12-01"}
    assert period_key("day", NOW) == "2026-11-09" and str(next_reset("day", NOW)) == "2026-11-10"


def test_companies_default_file_valid_and_roundtrip(tmp_path: Path):
    items = companies_mod.load_companies(tmp_path / "missing.yaml")
    assert len(items) >= 40
    assert {c["ats"] for c in items} == {"greenhouse", "lever", "ashby", "workday"}
    td = next(c for c in items if c["name"] == "TD Bank")
    assert companies_mod.board_id(td) == "td/TD_Bank_Careers"
    path = tmp_path / "companies.yaml"
    companies_mod.save_companies(items[:2], path)
    assert companies_mod.load_companies(path) == items[:2]


@pytest.mark.parametrize(
    "bad",
    [[{"name": "", "ats": "lever", "board": "x"}], [{"name": "A", "ats": "taleo", "board": "x"}],
     [{"name": "A", "ats": "workday", "host": "h"}], [{"name": "A", "ats": "lever"}]],
)
def test_companies_validation(bad):
    with pytest.raises(ValueError):
        companies_mod.validate_companies(bad)


async def test_gather_companies_isolates_failures():
    companies = [{"name": "Good", "ats": "lever", "board": "good", "enabled": True},
                 {"name": "Bad", "ats": "lever", "board": "bad", "enabled": True},
                 {"name": "Off", "ats": "lever", "board": "off", "enabled": False}]
    ctx = make_ctx(companies=companies)

    async def fetch_company(_ctx, company):
        if company["board"] == "bad":
            raise HttpError(500, "https://api.lever.co/bad")
        return [JobPosting(url="u", title="Data Analyst", source="lever", external_id="1")], {"1", "2"}

    result = await gather_companies(ctx, "lever", fetch_company)
    assert len(result.postings) == 1
    assert result.seen_ids == {"good": {"1", "2"}}
    assert result.warnings == ["Bad: https://api.lever.co/bad returned HTTP 500"]


async def test_gather_companies_skips_when_none_configured():
    result = await gather_companies(make_ctx(), "ashby", None)
    assert result.skipped == "no companies configured"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_search_plumbing.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_apply_agent.search.base'`.

- [ ] **Step 4: Implement `search/http.py`**

```python
"""Polite async HTTP for job sources: timeouts, retries with backoff, and a delay per host.

Uses urllib from the standard library in a worker thread, like the rest of the project.
``fetch`` is injectable so tests never touch the network.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


class HttpError(RuntimeError):
    def __init__(self, status: int | None, url: str, message: str = ""):
        self.status = status
        self.url = url
        super().__init__(message or f"{url} returned HTTP {status}")


class RateLimited(HttpError):
    """The site asked us to slow down (HTTP 429, or LinkedIn's 999)."""


@dataclass
class Response:
    status: int
    text: str

    def json(self) -> Any:
        return json.loads(self.text)


FetchFn = Callable[[str, str, dict[str, str], bytes | None, float], Response]


def urllib_fetch(method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float) -> Response:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return Response(response.status, response.read().decode(charset, errors="replace"))
    except urllib.error.HTTPError as exc:
        try:
            text = exc.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - the body is only informative
            text = ""
        return Response(exc.code, text)


class Http:
    def __init__(
        self,
        fetch: FetchFn = urllib_fetch,
        *,
        retries: int = 2,
        backoff: float = 1.0,
        timeout: float = 25.0,
        host_delays: dict[str, tuple[float, float]] | None = None,
        default_delay: float = 0.5,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._fetch = fetch
        self.retries = retries
        self.backoff = backoff
        self.timeout = timeout
        self._delays = host_delays or {}
        self._default_delay = default_delay
        self._sleep = sleep
        self._clock = clock
        self._last: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def _wait_turn(self, host: str) -> None:
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            low, high = self._delays.get(host, (self._default_delay, self._default_delay))
            last = self._last.get(host)
            if last is not None:
                wait = last + random.uniform(low, high) - self._clock()
                if wait > 0:
                    await self._sleep(wait)
            self._last[host] = self._clock()

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json_body: Any = None,
        retry_429: bool = True,
    ) -> Response:
        if params:
            url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
        all_headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9", **(headers or {})}
        body = None
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            all_headers.setdefault("Content-Type", "application/json")
            all_headers.setdefault("Accept", "application/json")
        host = urllib.parse.urlsplit(url).hostname or ""
        for attempt in range(self.retries + 1):
            await self._wait_turn(host)
            try:
                response = await asyncio.to_thread(self._fetch, method, url, all_headers, body, self.timeout)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempt == self.retries:
                    raise HttpError(None, url, f"Couldn't reach {url}: {exc}") from exc
                await self._sleep(self.backoff * 2**attempt)
                continue
            if response.status == 999 or (response.status == 429 and (not retry_429 or attempt == self.retries)):
                raise RateLimited(response.status, url)
            if response.status == 429 or response.status >= 500:
                if attempt == self.retries:
                    raise HttpError(response.status, url)
                await self._sleep(self.backoff * 2**attempt)
                continue
            if response.status >= 400:
                raise HttpError(response.status, url)
            return response
        raise HttpError(None, url)  # unreachable

    async def get_json(self, url: str, *, params=None, headers=None, retry_429: bool = True) -> Any:
        response = await self.request("GET", url, params=params, headers=headers, retry_429=retry_429)
        return _decode(response, url)

    async def post_json(self, url: str, body: Any, *, headers=None, retry_429: bool = True) -> Any:
        response = await self.request("POST", url, headers=headers, json_body=body, retry_429=retry_429)
        return _decode(response, url)

    async def get_text(self, url: str, *, params=None, headers=None, retry_429: bool = True) -> str:
        return (await self.request("GET", url, params=params, headers=headers, retry_429=retry_429)).text


def _decode(response: Response, url: str) -> Any:
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise HttpError(response.status, url, f"{url} did not return valid JSON") from exc
```

- [ ] **Step 5: Implement `search/quota.py`**

```python
"""Keep paid-tier APIs inside their free quota. Counts calls per source per day or month."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from ..db import Database
from ..timeutil import now_utc


class QuotaExceeded(RuntimeError):
    pass


def period_key(period: str, now: datetime) -> str:
    return now.strftime("%Y-%m-%d") if period == "day" else now.strftime("%Y-%m")


def next_reset(period: str, now: datetime) -> date:
    if period == "day":
        return (now + timedelta(days=1)).date()
    return date(now.year + (now.month == 12), now.month % 12 + 1, 1)


def budgets_from_prefs(prefs: dict[str, Any]) -> dict[str, tuple[int, str]]:
    return {
        name: (int(cfg["budget"]), cfg.get("budget_period", "month"))
        for name, cfg in prefs["sources"].items()
        if "budget" in cfg
    }


class QuotaGuard:
    def __init__(self, db: Database, budgets: dict[str, tuple[int, str]],
                 now_fn: Callable[[], datetime] = now_utc):
        self.db = db
        self.budgets = budgets
        self.now_fn = now_fn

    def remaining(self, source: str) -> int | None:
        if source not in self.budgets:
            return None
        budget, period = self.budgets[source]
        return max(0, budget - self.db.quota_used(source, period_key(period, self.now_fn())))

    def consume(self, source: str, n: int = 1) -> None:
        left = self.remaining(source)
        if left is None:
            return
        _budget, period = self.budgets[source]
        now = self.now_fn()
        if left < n:
            raise QuotaExceeded(f"free quota reached until {next_reset(period, now)}")
        self.db.quota_add(source, period_key(period, now), n)

    def usage(self) -> dict[str, dict[str, Any]]:
        now = self.now_fn()
        return {
            source: {
                "used": self.db.quota_used(source, period_key(period, now)),
                "budget": budget,
                "period": period,
                "resets": str(next_reset(period, now)),
            }
            for source, (budget, period) in self.budgets.items()
        }
```

- [ ] **Step 6: Create `search/default_companies.yaml`**

Every board below was checked live on 2026-11-09 and had Canadian postings.

```yaml
# Canadian employers whose public job boards the app reads. Edit in Settings.
# ats: greenhouse | lever | ashby -> board is the company's board name in the URL.
# ats: workday -> host, tenant and site from the careers URL https://<host>/<site>.
- {name: Wealthsimple, ats: ashby, board: wealthsimple}
- {name: KOHO, ats: ashby, board: koho}
- {name: Benevity, ats: ashby, board: benevity}
- {name: Lightspeed, ats: ashby, board: lightspeedhq}
- {name: Cohere, ats: ashby, board: cohere}
- {name: 1Password, ats: ashby, board: 1password}
- {name: Float, ats: ashby, board: float}
- {name: Hopper, ats: ashby, board: hopper}
- {name: Loopio, ats: ashby, board: loopio}
- {name: Jobber, ats: ashby, board: jobber}
- {name: Neo Financial, ats: ashby, board: neofinancial}
- {name: Trulioo, ats: ashby, board: trulioo}
- {name: Clearco, ats: ashby, board: clearco}
- {name: Miovision, ats: ashby, board: miovision}
- {name: Snowflake, ats: ashby, board: snowflake}
- {name: Faire, ats: greenhouse, board: faire}
- {name: Hootsuite, ats: greenhouse, board: hootsuite}
- {name: D2L, ats: greenhouse, board: d2l}
- {name: Geotab, ats: greenhouse, board: geotab}
- {name: Instacart, ats: greenhouse, board: instacart}
- {name: Coinbase, ats: greenhouse, board: coinbase}
- {name: Databricks, ats: greenhouse, board: databricks}
- {name: Fivetran, ats: greenhouse, board: fivetran}
- {name: Stripe, ats: greenhouse, board: stripe}
- {name: Airbnb, ats: greenhouse, board: airbnb}
- {name: Affirm, ats: greenhouse, board: affirm}
- {name: Pinterest, ats: greenhouse, board: pinterest}
- {name: Robinhood, ats: greenhouse, board: robinhood}
- {name: Samsara, ats: greenhouse, board: samsara}
- {name: Lyft, ats: greenhouse, board: lyft}
- {name: Wattpad, ats: lever, board: wattpad}
- {name: PointClickCare, ats: lever, board: pointclickcare}
- {name: Wave, ats: lever, board: waveapps}
- {name: Fullscript, ats: lever, board: fullscript}
- {name: Achievers, ats: lever, board: achievers}
- {name: RBC, ats: workday, host: rbc.wd3.myworkdayjobs.com, tenant: rbc, site: RBCGLOBAL1}
- {name: TD Bank, ats: workday, host: td.wd3.myworkdayjobs.com, tenant: td, site: TD_Bank_Careers}
- {name: CIBC, ats: workday, host: cibc.wd3.myworkdayjobs.com, tenant: cibc, site: search}
- {name: BMO, ats: workday, host: bmo.wd3.myworkdayjobs.com, tenant: bmo, site: External}
- {name: Manulife, ats: workday, host: manulife.wd3.myworkdayjobs.com, tenant: manulife, site: MFCJH_Jobs}
- {name: Sun Life, ats: workday, host: sunlife.wd3.myworkdayjobs.com, tenant: sunlife, site: Experienced-Jobs}
- {name: Thomson Reuters, ats: workday, host: thomsonreuters.wd5.myworkdayjobs.com, tenant: thomsonreuters, site: External_Career_Site}
```

- [ ] **Step 7: Implement `search/companies.py`**

```python
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
```

- [ ] **Step 8: Implement `search/base.py`**

```python
"""What every job source receives and returns."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..jobs import JobPosting
from .companies import board_id
from .http import HttpError
from .quota import QuotaGuard


@dataclass
class SourceResult:
    postings: list[JobPosting] = field(default_factory=list)
    seen_ids: dict[str, set[str]] = field(default_factory=dict)  # board -> every job ID on it (closed-job tracking)
    warnings: list[str] = field(default_factory=list)
    skipped: str | None = None  # reason, e.g. "no API key"


@dataclass
class SourceContext:
    prefs: dict[str, Any]
    companies: list[dict[str, Any]]
    http: Any  # search.http.Http (or a test fake with the same methods)
    quota: QuotaGuard
    env: Mapping[str, str]
    role_ok: Callable[[str], bool]  # cheap title check, to skip fetching details of unrelated jobs
    known: Callable[[str, str], bool]  # (source, external_id) already stored -> no need to re-fetch details
    last_success: Callable[[str], datetime | None]
    progress: Callable[[str], None] = lambda _msg: None

    def source_prefs(self, name: str) -> dict[str, Any]:
        return self.prefs["sources"].get(name, {})

    def companies_for(self, ats: str) -> list[dict[str, Any]]:
        return [c for c in self.companies if c["ats"] == ats and c.get("enabled", True)]


Source = Callable[[SourceContext], Awaitable[SourceResult]]
FetchCompany = Callable[[SourceContext, dict[str, Any]], Awaitable[tuple[list[JobPosting], set[str] | None]]]


async def gather_companies(ctx: SourceContext, ats: str, fetch_company: FetchCompany,
                           concurrency: int = 4) -> SourceResult:
    """Run ``fetch_company`` for every enabled company on ``ats``; one company failing doesn't stop the rest."""
    companies = ctx.companies_for(ats)
    if not companies:
        return SourceResult(skipped="no companies configured")
    result = SourceResult()
    semaphore = asyncio.Semaphore(concurrency)

    async def one(company: dict[str, Any]) -> None:
        async with semaphore:
            try:
                postings, seen = await fetch_company(ctx, company)
            except HttpError as exc:
                result.warnings.append(f"{company['name']}: {exc}")
                return
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                result.warnings.append(f"{company['name']}: unexpected response ({exc!r})")
                return
            result.postings.extend(postings)
            if seen is not None:
                result.seen_ids[board_id(company)] = seen
            ctx.progress(f"{company['name']}: {len(postings)} matching")

    await asyncio.gather(*(one(c) for c in companies))
    return result
```

- [ ] **Step 9: Run the tests to verify they pass**

`test_company` imports `search.sources`, which doesn't exist until Task 7; nothing calls it yet.

Run: `.venv/bin/pytest tests/test_search_plumbing.py -q && .venv/bin/ruff check src tests`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add src/job_apply_agent/search tests/fakes.py tests/test_search_plumbing.py
git commit -m "feat: add polite HTTP client, quota guard, companies list and source base

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Company career APIs: Greenhouse, Lever, Ashby

**Files:**
- Create: `src/job_apply_agent/search/sources/__init__.py`, `sources/greenhouse.py`, `sources/lever.py`, `sources/ashby.py`
- Test: `tests/test_sources_company_apis.py`

**Interfaces:**
- Consumes: `SourceContext`, `SourceResult`, `gather_companies` (Task 6); `JobPosting`, `html_to_text`, `clean_inline` (Task 3); `iso_or_none` (Task 4).
- Produces: per module `async list_board(http, company) -> list[dict]`, `to_posting(company, item, ...) -> JobPosting`, `async fetch_company(ctx, company)`, `async fetch(ctx) -> SourceResult`. Registry `sources.SOURCES: dict[str, Source]` and `sources.BOARD_LISTERS: dict[str, Callable]` (later tasks add entries).

Real response shapes (checked live 2026-11-09):
- Greenhouse list `GET https://boards-api.greenhouse.io/v1/boards/{board}/jobs` → `{"jobs": [{"id", "title", "location": {"name"}, "absolute_url", "first_published", "updated_at", "metadata": [...]}]}`; detail `.../jobs/{id}` adds `content` (HTML-escaped HTML).
- Lever `GET https://api.lever.co/v0/postings/{board}?mode=json` → list of `{"id", "text", "categories": {"location", "allLocations", "commitment"}, "workplaceType", "createdAt" (ms), "hostedUrl", "country", "descriptionPlain", "lists": [{"text", "content"}], "additionalPlain"}`.
- Ashby `GET https://api.ashbyhq.com/posting-api/job-board/{board}` → `{"jobs": [{"id", "title", "location", "secondaryLocations": [{"location"}], "isRemote", "workplaceType", "publishedAt", "jobUrl", "descriptionPlain", "employmentType", "address": {"postalAddress": {"addressCountry"}}, "isListed"}]}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sources_company_apis.py`:

```python
from fakes import make_ctx
from job_apply_agent.search.http import HttpError
from job_apply_agent.search.sources import BOARD_LISTERS, SOURCES, ashby, greenhouse, lever

GH = {"name": "Faire", "ats": "greenhouse", "board": "faire", "enabled": True}
LV = {"name": "Achievers", "ats": "lever", "board": "achievers", "enabled": True}
AB = {"name": "Wealthsimple", "ats": "ashby", "board": "wealthsimple", "enabled": True}

GH_LIST = {"jobs": [
    {"id": 101, "title": "Senior Data Analyst", "location": {"name": "Toronto, ON"},
     "absolute_url": "https://boards.greenhouse.io/faire/jobs/101?gh_jid=101",
     "first_published": "2026-11-07T15:23:54-04:00", "updated_at": "2026-11-08T09:00:00-04:00",
     "metadata": [{"name": "Employment Type", "value": "Regular"}]},
    {"id": 102, "title": "Account Executive", "location": {"name": "New York, NY"},
     "absolute_url": "https://boards.greenhouse.io/faire/jobs/102", "updated_at": "2026-11-08T09:00:00-04:00"},
    {"id": 103, "title": "Data Engineer", "location": {"name": "Kitchener-Waterloo, ON"},
     "absolute_url": "https://boards.greenhouse.io/faire/jobs/103", "updated_at": "2026-11-08T09:00:00-04:00"},
]}
GH_DETAIL = {"id": 101, "content": "&lt;p&gt;&lt;strong&gt;About&lt;/strong&gt;&lt;/p&gt;&lt;ul&gt;&lt;li&gt;SQL&lt;/li&gt;&lt;/ul&gt;"}


async def test_greenhouse_fetches_details_only_for_matching_titles():
    ctx = make_ctx(companies=[GH], routes={
        "https://boards-api.greenhouse.io/v1/boards/faire/jobs/101": GH_DETAIL,
        "https://boards-api.greenhouse.io/v1/boards/faire/jobs/103": HttpError(404, "gone"),
        "https://boards-api.greenhouse.io/v1/boards/faire/jobs": GH_LIST,
    })
    result = await SOURCES["greenhouse"](ctx)
    assert [p.title for p in result.postings] == ["Senior Data Analyst", "Data Engineer"]
    first, second = result.postings
    assert first.source == "greenhouse" and first.external_id == "101" and first.board == "faire"
    assert first.company == "Faire" and first.location == "Toronto, ON"
    assert first.posted_at == "2026-11-07T19:23:54+00:00" and first.employment_type == "Regular"
    assert "About" in first.description and "- SQL" in first.description
    assert second.description == "" and second.description_is_partial is True  # detail 404 -> partial
    assert result.seen_ids == {"faire": {"101", "102", "103"}}
    detail_calls = [c for c in ctx.http.calls if c[1].endswith("/102")]
    assert detail_calls == []


async def test_greenhouse_skips_detail_for_known_jobs():
    ctx = make_ctx(companies=[GH], known=[("greenhouse", "101"), ("greenhouse", "103")],
                   routes={"https://boards-api.greenhouse.io/v1/boards/faire/jobs": GH_LIST})
    result = await greenhouse.fetch(ctx)
    assert len(result.postings) == 2 and len(ctx.http.calls) == 1


LV_LIST = [
    {"id": "a1", "text": "Data  Analyst", "categories": {"location": "Toronto", "allLocations": ["Toronto", "Remote"],
     "commitment": "Full-time permanent"}, "workplaceType": "hybrid", "createdAt": 1791216082758,
     "hostedUrl": "https://jobs.lever.co/achievers/a1", "country": "CA",
     "descriptionPlain": "We need an analyst.", "lists": [{"text": "What you'll do", "content": "<li>SQL</li><li>Looker</li>"}],
     "additionalPlain": "Benefits..."},
    {"id": "a2", "text": "Customer Success Associate", "categories": {"location": "Toronto"}, "hostedUrl": "x"},
]


async def test_lever_maps_fields():
    ctx = make_ctx(companies=[LV], routes={"https://api.lever.co/v0/postings/achievers": LV_LIST})
    result = await lever.fetch(ctx)
    [p] = result.postings
    assert p.title == "Data Analyst" and p.location == "Toronto; Remote" and p.remote is False
    assert p.country == "CA" and p.employment_type == "Full-time permanent"
    assert "What you'll do\n- SQL\n- Looker" in p.description and p.description.endswith("Benefits...")
    assert p.posted_at.startswith("2026-") and result.seen_ids == {"achievers": {"a1", "a2"}}
    assert ctx.http.calls[0][2] == {"mode": "json"}


AB_LIST = {"jobs": [
    {"id": "u1", "title": "Data Scientist", "location": "Remote (Canada)", "secondaryLocations": [],
     "isRemote": True, "workplaceType": "Remote", "publishedAt": "2026-11-05T17:56:22.425+00:00",
     "jobUrl": "https://jobs.ashbyhq.com/wealthsimple/u1", "descriptionPlain": "Model things.",
     "employmentType": "FullTime", "address": {"postalAddress": {"addressCountry": "Canada"}}, "isListed": True},
    {"id": "u2", "title": "Data Analyst", "location": "Toronto", "secondaryLocations": [{"location": "Montreal"}],
     "isListed": False, "jobUrl": "x"},
]}


async def test_ashby_maps_fields_and_skips_unlisted():
    ctx = make_ctx(companies=[AB], routes={"https://api.ashbyhq.com/posting-api/job-board/wealthsimple": AB_LIST})
    result = await ashby.fetch(ctx)
    [p] = result.postings
    assert p.remote is True and p.country == "Canada" and p.location == "Remote (Canada)"
    assert p.posted_at == "2026-11-05T17:56:22+00:00" and p.url.endswith("/u1")
    assert result.seen_ids == {"wealthsimple": {"u1"}}


async def test_board_listers_for_settings_test_button():
    ctx = make_ctx(routes={"https://api.lever.co/v0/postings/achievers": LV_LIST})
    assert len(await BOARD_LISTERS["lever"](ctx.http, LV)) == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_sources_company_apis.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_apply_agent.search.sources'`.

- [ ] **Step 3: Implement `sources/greenhouse.py`**

```python
"""Greenhouse public job board API (https://developers.greenhouse.io/job-board.html)."""

from __future__ import annotations

import html
from typing import Any

from ...jobs import JobPosting, clean_inline, html_to_text
from ...timeutil import iso_or_none
from ..base import SourceContext, SourceResult, gather_companies
from ..http import HttpError

API = "https://boards-api.greenhouse.io/v1/boards"


async def list_board(http, company: dict[str, Any]) -> list[dict[str, Any]]:
    data = await http.get_json(f"{API}/{company['board']}/jobs")
    return list(data["jobs"])


def to_posting(company: dict[str, Any], item: dict[str, Any], detail: dict[str, Any] | None = None) -> JobPosting:
    content = (detail or {}).get("content") or ""
    employment = next(
        (m.get("value") for m in item.get("metadata") or []
         if (m.get("name") or "").lower() == "employment type" and isinstance(m.get("value"), str)),
        "",
    )
    return JobPosting(
        url=item.get("absolute_url", ""),
        title=clean_inline(item.get("title", "")),
        company=company["name"],
        location=(item.get("location") or {}).get("name") or "",
        description=html_to_text(html.unescape(content)) if content else "",
        description_is_partial=not content,
        source="greenhouse",
        external_id=str(item["id"]),
        posted_at=iso_or_none(item.get("first_published") or item.get("updated_at")),
        employment_type=employment,
        board=company["board"],
    )


async def fetch_company(ctx: SourceContext, company: dict[str, Any]):
    items = await list_board(ctx.http, company)
    postings = []
    for item in items:
        if not ctx.role_ok(item.get("title", "")):
            continue
        detail = None
        if not ctx.known("greenhouse", str(item["id"])):
            try:
                detail = await ctx.http.get_json(f"{API}/{company['board']}/jobs/{item['id']}")
            except HttpError:
                detail = None
        postings.append(to_posting(company, item, detail))
    return postings, {str(item["id"]) for item in items}


async def fetch(ctx: SourceContext) -> SourceResult:
    return await gather_companies(ctx, "greenhouse", fetch_company)
```

- [ ] **Step 4: Implement `sources/lever.py`**

```python
"""Lever public postings API (https://github.com/lever/postings-api)."""

from __future__ import annotations

from typing import Any

from ...jobs import JobPosting, clean_inline, html_to_text
from ...timeutil import iso_or_none
from ..base import SourceContext, SourceResult, gather_companies

API = "https://api.lever.co/v0/postings"


async def list_board(http, company: dict[str, Any]) -> list[dict[str, Any]]:
    data = await http.get_json(f"{API}/{company['board']}", params={"mode": "json"})
    if not isinstance(data, list):
        raise ValueError("Lever returned something other than a list of postings")
    return data


def to_posting(company: dict[str, Any], item: dict[str, Any]) -> JobPosting:
    categories = item.get("categories") or {}
    locations = categories.get("allLocations") or ([categories["location"]] if categories.get("location") else [])
    parts = [item.get("descriptionPlain") or html_to_text(item.get("description", ""))]
    for section in item.get("lists") or []:
        parts.append(f"{clean_inline(section.get('text', ''))}\n{html_to_text(section.get('content', ''))}")
    if item.get("additionalPlain"):
        parts.append(item["additionalPlain"])
    workplace = (item.get("workplaceType") or "").lower()
    remote = True if workplace == "remote" else (False if workplace in ("onsite", "on-site", "hybrid") else None)
    return JobPosting(
        url=item.get("hostedUrl", ""),
        title=clean_inline(item.get("text", "")),
        company=company["name"],
        location="; ".join(locations),
        description="\n\n".join(part.strip() for part in parts if part and part.strip()),
        source="lever",
        external_id=str(item["id"]),
        posted_at=iso_or_none(item.get("createdAt")),
        remote=remote,
        country=item.get("country") or "",
        employment_type=categories.get("commitment") or "",
        board=company["board"],
    )


async def fetch_company(ctx: SourceContext, company: dict[str, Any]):
    items = await list_board(ctx.http, company)
    postings = [to_posting(company, item) for item in items if ctx.role_ok(item.get("text", ""))]
    return postings, {str(item["id"]) for item in items}


async def fetch(ctx: SourceContext) -> SourceResult:
    return await gather_companies(ctx, "lever", fetch_company)
```

- [ ] **Step 5: Implement `sources/ashby.py`**

```python
"""Ashby public job board API (https://developers.ashbyhq.com/docs/public-job-posting-api)."""

from __future__ import annotations

from typing import Any

from ...jobs import JobPosting, clean_inline, html_to_text
from ...timeutil import iso_or_none
from ..base import SourceContext, SourceResult, gather_companies

API = "https://api.ashbyhq.com/posting-api/job-board"


async def list_board(http, company: dict[str, Any]) -> list[dict[str, Any]]:
    data = await http.get_json(f"{API}/{company['board']}")
    return list(data["jobs"])


def to_posting(company: dict[str, Any], item: dict[str, Any]) -> JobPosting:
    locations = [item.get("location") or ""] + [s.get("location", "") for s in item.get("secondaryLocations") or []]
    country = ((item.get("address") or {}).get("postalAddress") or {}).get("addressCountry") or ""
    workplace = (item.get("workplaceType") or "").lower()
    remote = True if item.get("isRemote") or workplace == "remote" else (False if workplace in ("onsite", "hybrid") else None)
    return JobPosting(
        url=item.get("jobUrl", ""),
        title=clean_inline(item.get("title", "")),
        company=company["name"],
        location="; ".join(loc for loc in locations if loc),
        description=(item.get("descriptionPlain") or html_to_text(item.get("descriptionHtml", ""))).strip(),
        source="ashby",
        external_id=str(item["id"]),
        posted_at=iso_or_none(item.get("publishedAt")),
        remote=remote,
        country=country,
        employment_type=item.get("employmentType") or "",
        board=company["board"],
    )


async def fetch_company(ctx: SourceContext, company: dict[str, Any]):
    items = [item for item in await list_board(ctx.http, company) if item.get("isListed", True)]
    postings = [to_posting(company, item) for item in items if ctx.role_ok(item.get("title", ""))]
    return postings, {str(item["id"]) for item in items}


async def fetch(ctx: SourceContext) -> SourceResult:
    return await gather_companies(ctx, "ashby", fetch_company)
```

- [ ] **Step 6: Create the registry `sources/__init__.py`**

```python
"""All job sources. Each module exposes ``async fetch(ctx) -> SourceResult``."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from ..base import Source
from . import ashby, greenhouse, lever

SOURCES: dict[str, Source] = {
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "ashby": ashby.fetch,
}

# For the Settings "Test" button: list a company's board without saving anything.
BOARD_LISTERS: dict[str, Callable[[Any, dict[str, Any]], Awaitable[list]]] = {
    "greenhouse": greenhouse.list_board,
    "lever": lever.list_board,
    "ashby": ashby.list_board,
}
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_sources_company_apis.py -q && .venv/bin/ruff check src tests`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/job_apply_agent/search/sources tests/test_sources_company_apis.py
git commit -m "feat: add Greenhouse, Lever and Ashby job sources

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Workday career sites

**Files:**
- Create: `src/job_apply_agent/search/sources/workday.py`
- Modify: `src/job_apply_agent/search/sources/__init__.py` (register)
- Test: `tests/test_sources_workday.py`

**Interfaces:**
- Consumes: as Task 7, plus `parse_relative_posted`, `now_utc`, `iso` (Task 4), `board_id` (Task 6).
- Produces: `workday.list_board(http, company, search_text="", offset=0) -> dict`, `workday.list_first_page(http, company) -> list[dict]`, `workday.to_posting(company, item, detail, now) -> JobPosting`, `workday.fetch(ctx)`.

Real shapes (checked live 2026-11-09): `POST https://{host}/wday/cxs/{tenant}/{site}/jobs` with `{"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "data analyst"}` → `{"total": 339, "jobPostings": [{"title", "externalPath": "/job/Toronto-Ontario/Sr-IT-Data-Analyst_R_1520114", "locationsText": "Toronto, Ontario" | "3 Locations", "postedOn": "Posted 4 Days Ago"}]}`. Detail `GET https://{host}/wday/cxs/{tenant}/{site}{externalPath}` → `{"jobPostingInfo": {"title", "jobDescription" (HTML), "location", "additionalLocations", "startDate": "2026-11-05", "timeType", "remoteType", "externalUrl", "country": {"descriptor": "Canada"}}}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sources_workday.py`:

```python
from datetime import datetime, timezone

from fakes import make_ctx
from job_apply_agent.search.sources import SOURCES, workday

TD = {"name": "TD Bank", "ats": "workday", "host": "td.wd3.myworkdayjobs.com", "tenant": "td",
      "site": "TD_Bank_Careers", "enabled": True}
BASE = "https://td.wd3.myworkdayjobs.com/wday/cxs/td/TD_Bank_Careers"
PATH = "/job/Toronto-Ontario/Sr-IT-Data-Analyst_R_1520114"
LIST = {"total": 2, "jobPostings": [
    {"title": "Sr. IT Data Analyst", "externalPath": PATH, "locationsText": "3 Locations", "postedOn": "Posted 4 Days Ago"},
    {"title": "Branch Manager", "externalPath": "/job/x/Branch_R_1", "locationsText": "Ottawa", "postedOn": "Posted Today"},
]}
DETAIL = {"jobPostingInfo": {"title": "Sr. IT Data Analyst", "jobDescription": "<p>Build <b>reports</b>.</p>",
                             "location": "Toronto, Ontario", "additionalLocations": ["Ottawa, Ontario"],
                             "startDate": "2026-11-05", "timeType": "Full time", "remoteType": "Office Focused",
                             "externalUrl": f"https://td.wd3.myworkdayjobs.com/TD_Bank_Careers{PATH}",
                             "country": {"descriptor": "Canada"}}}
NOW = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)


async def test_workday_searches_terms_and_fetches_details():
    ctx = make_ctx(companies=[TD], prefs={"sources": {"workday": {"search_terms": ["data analyst", "analytics"]}}},
                   routes={f"{BASE}/jobs": LIST, f"{BASE}{PATH}": DETAIL})
    result = await SOURCES["workday"](ctx)
    [p] = result.postings  # same job found by both terms is fetched once; Branch Manager filtered out
    assert p.location == "Toronto, Ontario; Ottawa, Ontario" and p.country == "Canada"
    assert p.posted_at == "2026-11-05T00:00:00+00:00" and p.description == "Build reports."
    assert p.external_id == PATH and p.board == "td/TD_Bank_Careers" and p.url.endswith(PATH)
    posts = [c for c in ctx.http.calls if c[0] == "POST"]
    assert [c[2]["searchText"] for c in posts] == ["data analyst", "analytics"]
    assert result.seen_ids == {}  # keyword search can't see the whole board


async def test_workday_known_job_uses_list_data_only():
    ctx = make_ctx(companies=[TD], known=[("workday", PATH)], routes={f"{BASE}/jobs": LIST})
    result = await workday.fetch(ctx)
    [p] = result.postings
    assert p.description == "" and p.description_is_partial is True and p.location == "3 Locations"
    assert all(c[0] == "POST" for c in ctx.http.calls)


def test_relative_posted_date_when_no_start_date():
    item = {"title": "Data Analyst", "externalPath": "/job/a", "locationsText": "Toronto", "postedOn": "Posted 4 Days Ago"}
    p = workday.to_posting(TD, item, None, NOW)
    assert p.posted_at == "2026-11-05T12:00:00+00:00"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_sources_workday.py -q`
Expected: FAIL with `ImportError: cannot import name 'workday'`.

- [ ] **Step 3: Implement `sources/workday.py`**

```python
"""Workday career sites (used by most Canadian banks and insurers).

Workday has no public board listing, so we search by keyword on the site's own JSON
endpoint, then fetch details only for new jobs whose title matches.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ...jobs import JobPosting, clean_inline, html_to_text
from ...timeutil import iso, iso_or_none, now_utc, parse_relative_posted
from ..base import SourceContext, SourceResult, gather_companies
from ..companies import board_id
from ..http import HttpError

PAGE_SIZE = 20


def _base(company: dict[str, Any]) -> str:
    return f"https://{company['host']}/wday/cxs/{company['tenant']}/{company['site']}"


async def list_board(http, company: dict[str, Any], search_text: str = "", offset: int = 0) -> dict[str, Any]:
    body = {"appliedFacets": {}, "limit": PAGE_SIZE, "offset": offset, "searchText": search_text}
    return await http.post_json(f"{_base(company)}/jobs", body)


async def list_first_page(http, company: dict[str, Any]) -> list[dict[str, Any]]:
    return list((await list_board(http, company)).get("jobPostings") or [])


def to_posting(company: dict[str, Any], item: dict[str, Any], detail: dict[str, Any] | None,
               now: datetime) -> JobPosting:
    info = (detail or {}).get("jobPostingInfo") or {}
    path = item["externalPath"]
    locations = [info.get("location") or item.get("locationsText") or ""] + list(info.get("additionalLocations") or [])
    posted = iso_or_none(info.get("startDate"))
    if posted is None:
        relative = parse_relative_posted(item.get("postedOn", ""), now)
        posted = iso(relative) if relative else None
    return JobPosting(
        url=info.get("externalUrl") or f"https://{company['host']}/{company['site']}{path}",
        title=clean_inline(info.get("title") or item.get("title", "")),
        company=company["name"],
        location="; ".join(loc for loc in locations if loc),
        description=html_to_text(info.get("jobDescription", "")),
        description_is_partial=not info,
        source="workday",
        external_id=path,
        posted_at=posted,
        remote=True if "remote" in (info.get("remoteType") or "").lower() else None,
        country=(info.get("country") or {}).get("descriptor") or "",
        employment_type=info.get("timeType") or "",
        board=board_id(company),
    )


async def fetch_company(ctx: SourceContext, company: dict[str, Any]):
    prefs = ctx.source_prefs("workday")
    now = now_utc()
    found: dict[str, dict[str, Any]] = {}
    for term in prefs.get("search_terms", []):
        for page in range(int(prefs.get("max_pages", 2))):
            data = await list_board(ctx.http, company, term, page * PAGE_SIZE)
            items = data.get("jobPostings") or []
            for item in items:
                if item.get("externalPath") and ctx.role_ok(item.get("title", "")):
                    found.setdefault(item["externalPath"], item)
            if len(items) < PAGE_SIZE:
                break
    postings = []
    for path, item in found.items():
        detail = None
        if not ctx.known("workday", path):
            try:
                detail = await ctx.http.get_json(f"{_base(company)}{path}")
            except HttpError:
                detail = None
        postings.append(to_posting(company, item, detail, now))
    return postings, None


async def fetch(ctx: SourceContext) -> SourceResult:
    return await gather_companies(ctx, "workday", fetch_company, concurrency=2)
```

- [ ] **Step 4: Register Workday**

In `src/job_apply_agent/search/sources/__init__.py` change the import to `from . import ashby, greenhouse, lever, workday`, add `"workday": workday.fetch,` to `SOURCES`, and `"workday": workday.list_first_page,` to `BOARD_LISTERS`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_sources_workday.py tests/test_sources_company_apis.py -q && .venv/bin/ruff check src tests`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/job_apply_agent/search/sources tests/test_sources_workday.py
git commit -m "feat: add Workday career-site source for Canadian banks and insurers

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Aggregator APIs: JSearch and Adzuna

**Files:**
- Create: `src/job_apply_agent/search/sources/jsearch.py`, `sources/adzuna.py`
- Modify: `src/job_apply_agent/search/sources/__init__.py` (register)
- Test: `tests/test_sources_aggregators.py`

**Interfaces:**
- Consumes: `SourceContext`, `SourceResult` (Task 6), `QuotaExceeded` (Task 6), `HttpError` (Task 6).
- Produces: `jsearch.parse_jsearch(data) -> list[dict]`, `jsearch.to_posting(item) -> JobPosting`, `jsearch.fetch(ctx)`; `adzuna.to_posting(item) -> JobPosting`, `adzuna.fetch(ctx)`.

JSearch (OpenWeb Ninja, on RapidAPI; field names from its OpenAPI spec, 2026-11-09): `GET {base_url}?query=...&country=ca&date_posted=today|3days&num_pages=1` with headers `X-RapidAPI-Key`, `X-RapidAPI-Host`. Each page costs one request. The response's `data` is a list (classic `/search`) or `{"jobs": [...], "cursor": ...}` (`/search-v2`); support both. Job fields: `job_id, job_title, employer_name, job_location, job_city, job_state, job_country, job_is_remote, job_posted_at_datetime_utc, job_posted_at_timestamp, job_apply_link, job_google_link, job_description, job_publisher, job_employment_type`.

Adzuna (developer.adzuna.com): `GET https://api.adzuna.com/v1/api/jobs/ca/search/1?app_id&app_key&what&where&max_days_old&results_per_page&sort_by=date&content-type=application/json` → `{"results": [{"id", "title", "description" (snippet), "redirect_url", "created", "company": {"display_name"}, "location": {"display_name", "area"}, "contract_time"}]}`. Terms: personal job search is allowed; displayed ads must be labeled "Adzuna" with a link (the UI's source chip does this, Task 18). Free-tier limits are shown only in the Adzuna dashboard; the default budget is 100/day, editable.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sources_aggregators.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest

from fakes import make_ctx
from job_apply_agent.search.http import HttpError
from job_apply_agent.search.sources import SOURCES, jsearch

JS_URL = "https://jsearch.p.rapidapi.com/search"
JOB = {"job_id": "js1", "job_title": "Data Analyst", "employer_name": "Shopify", "job_city": "Toronto",
       "job_state": "Ontario", "job_country": "CA", "job_is_remote": False,
       "job_posted_at_datetime_utc": "2026-11-09T08:00:00.000Z", "job_apply_link": "https://apply/js1",
       "job_description": "Full description", "job_publisher": "LinkedIn", "job_employment_type": "Full-time"}
OTHER = {**JOB, "job_id": "js2", "job_title": "Store Associate"}
NOW = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)


def test_parse_jsearch_both_shapes():
    assert jsearch.parse_jsearch({"status": "OK", "data": [JOB]}) == [JOB]
    assert jsearch.parse_jsearch({"status": "OK", "data": {"jobs": [JOB], "cursor": "c"}}) == [JOB]
    with pytest.raises(ValueError):
        jsearch.parse_jsearch({"message": "You are not subscribed"})


def test_jsearch_to_posting():
    p = jsearch.to_posting(JOB)
    assert (p.title, p.company, p.location, p.country) == ("Data Analyst", "Shopify", "Toronto, Ontario", "CA")
    assert p.posted_at == "2026-11-09T08:00:00+00:00" and p.details == {"Publisher": "LinkedIn"}
    assert p.remote is False and p.source == "jsearch" and p.url == "https://apply/js1"


async def test_jsearch_skips_without_key():
    result = await SOURCES["jsearch"](make_ctx())
    assert result.skipped.startswith("no API key")


async def test_jsearch_runs_queries_filters_titles_and_counts_quota():
    prefs = {"sources": {"jsearch": {"queries": ["q1", "q2"], "budget": 5}}}
    ctx = make_ctx(prefs=prefs, env={"JSEARCH_API_KEY": "k"}, routes={JS_URL: {"data": [JOB, OTHER]}},
                   last_success={"jsearch": datetime.now(timezone.utc) - timedelta(hours=2)}, now=NOW)
    result = await jsearch.fetch(ctx)
    assert [p.external_id for p in result.postings] == ["js1", "js1"]  # dedupe happens in the pipeline
    _method, _url, params, headers = ctx.http.calls[0]
    assert params == {"query": "q1", "country": "ca", "date_posted": "today", "num_pages": 1}
    assert headers == {"X-RapidAPI-Key": "k", "X-RapidAPI-Host": "jsearch.p.rapidapi.com"}
    assert ctx.quota.remaining("jsearch") == 3


async def test_jsearch_quota_reached_is_a_skip_not_an_error():
    ctx = make_ctx(prefs={"sources": {"jsearch": {"budget": 0}}}, env={"JSEARCH_API_KEY": "k"}, now=NOW)
    result = await jsearch.fetch(ctx)
    assert result.skipped == "free quota reached until 2026-12-01" and ctx.http.calls == []


async def test_jsearch_bad_key_raises_and_other_errors_warn():
    ctx = make_ctx(env={"JSEARCH_API_KEY": "k"}, routes={JS_URL: HttpError(403, JS_URL)})
    with pytest.raises(HttpError):
        await jsearch.fetch(ctx)
    ctx = make_ctx(prefs={"sources": {"jsearch": {"queries": ["q1"]}}}, env={"JSEARCH_API_KEY": "k"},
                   routes={JS_URL: HttpError(500, JS_URL)})
    result = await jsearch.fetch(ctx)
    assert result.postings == [] and "q1" in result.warnings[0]


AZ_URL = "https://api.adzuna.com/v1/api/jobs/ca/search/1"
AZ = {"results": [
    {"id": "az1", "title": "<strong>Data</strong> Scientist", "description": "Snippet only…",
     "redirect_url": "https://www.adzuna.ca/details/az1", "created": "2026-11-08T18:07:39Z",
     "company": {"display_name": "Sun Life"}, "location": {"display_name": "Toronto, Ontario"},
     "contract_time": "full_time"},
]}


async def test_adzuna_maps_and_marks_partial():
    prefs = {"sources": {"adzuna": {"what": ["data scientist"], "where": ["Toronto"], "budget": 10}}}
    ctx = make_ctx(prefs=prefs, env={"ADZUNA_APP_ID": "id", "ADZUNA_APP_KEY": "key"}, routes={AZ_URL: AZ})
    result = await SOURCES["adzuna"](ctx)
    [p] = result.postings
    assert p.title == "Data Scientist" and p.company == "Sun Life" and p.description_is_partial is True
    params = ctx.http.calls[0][2]
    assert params["app_id"] == "id" and params["what"] == "data scientist" and params["where"] == "Toronto"
    assert params["max_days_old"] == 3 and params["sort_by"] == "date"


async def test_adzuna_skips_without_keys():
    assert (await SOURCES["adzuna"](make_ctx(env={"ADZUNA_APP_ID": "id"}))).skipped.startswith("no API key")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_sources_aggregators.py -q`
Expected: FAIL with `ImportError: cannot import name 'jsearch'`.

- [ ] **Step 3: Implement `sources/jsearch.py`**

```python
"""JSearch (Google for Jobs data: LinkedIn, Indeed, Glassdoor, ZipRecruiter...) via RapidAPI.

Free tier: about 200 requests/month; the guard stops at the configured budget (default 180).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit

from ...jobs import JobPosting, clean_inline
from ...timeutil import iso_or_none, now_utc
from ..base import SourceContext, SourceResult
from ..http import HttpError
from ..quota import QuotaExceeded

DEFAULT_URL = "https://jsearch.p.rapidapi.com/search"


def parse_jsearch(data: Any) -> list[dict[str, Any]]:
    payload = data.get("data") if isinstance(data, dict) else None
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("jobs"), list):
        return payload["jobs"]
    message = data.get("message") if isinstance(data, dict) else None
    raise ValueError(f"unexpected JSearch response{': ' + str(message) if message else ''}")


def to_posting(item: dict[str, Any]) -> JobPosting:
    city, state = item.get("job_city") or "", item.get("job_state") or ""
    location = ", ".join(part for part in (city, state) if part) or item.get("job_location") or ""
    posted = iso_or_none(item.get("job_posted_at_datetime_utc")) or iso_or_none(item.get("job_posted_at_timestamp"))
    remote = item.get("job_is_remote")
    return JobPosting(
        url=item.get("job_apply_link") or item.get("job_google_link") or "",
        title=clean_inline(item.get("job_title", "")),
        company=clean_inline(item.get("employer_name", "")),
        location=location,
        details={"Publisher": item["job_publisher"]} if item.get("job_publisher") else {},
        description=(item.get("job_description") or "").strip(),
        source="jsearch",
        external_id=str(item.get("job_id", "")),
        posted_at=posted,
        remote=None if remote is None else bool(remote),
        country=item.get("job_country") or "",
        employment_type=item.get("job_employment_type") or "",
    )


async def fetch(ctx: SourceContext) -> SourceResult:
    prefs = ctx.source_prefs("jsearch")
    key = ctx.env.get("JSEARCH_API_KEY")
    if not key:
        return SourceResult(skipped="no API key (add JSEARCH_API_KEY to data/.env)")
    base_url = prefs.get("base_url") or DEFAULT_URL
    headers = {"X-RapidAPI-Key": key, "X-RapidAPI-Host": urlsplit(base_url).hostname or ""}
    last = ctx.last_success("jsearch")
    date_posted = "today" if last is not None and now_utc() - last < timedelta(hours=36) else "3days"

    result = SourceResult()
    calls = 0
    for query in prefs.get("queries", []):
        try:
            ctx.quota.consume("jsearch")
        except QuotaExceeded as exc:
            if calls == 0:
                return SourceResult(skipped=str(exc))
            result.warnings.append(str(exc))
            break
        calls += 1
        params = {"query": query, "country": "ca", "date_posted": date_posted, "num_pages": 1}
        try:
            data = await ctx.http.get_json(base_url, params=params, headers=headers)
            items = parse_jsearch(data)
        except HttpError as exc:
            if exc.status in (401, 403):
                raise HttpError(exc.status, exc.url, "JSearch rejected the API key (check JSEARCH_API_KEY)") from exc
            result.warnings.append(f"“{query}”: {exc}")
            continue
        except ValueError as exc:
            result.warnings.append(f"“{query}”: {exc}")
            continue
        result.postings.extend(to_posting(i) for i in items if i.get("job_id") and ctx.role_ok(i.get("job_title", "")))
        ctx.progress(f"“{query}”: {len(items)} results")
    return result
```

- [ ] **Step 4: Implement `sources/adzuna.py`**

```python
"""Adzuna job search API for Canada (descriptions are snippets; the full posting is fetched when tailoring)."""

from __future__ import annotations

from typing import Any

from ...jobs import JobPosting, clean_inline
from ...timeutil import iso_or_none
from ..base import SourceContext, SourceResult
from ..http import HttpError
from ..quota import QuotaExceeded

URL = "https://api.adzuna.com/v1/api/jobs/ca/search/1"


def to_posting(item: dict[str, Any]) -> JobPosting:
    location = item.get("location") or {}
    return JobPosting(
        url=item.get("redirect_url", ""),
        title=clean_inline(item.get("title", "")),
        company=clean_inline((item.get("company") or {}).get("display_name", "")),
        location=location.get("display_name", ""),
        description=clean_inline(item.get("description", "")),
        description_is_partial=True,
        source="adzuna",
        external_id=str(item.get("id", "")),
        posted_at=iso_or_none(item.get("created")),
        country="CA",
        employment_type=item.get("contract_time") or "",
    )


async def fetch(ctx: SourceContext) -> SourceResult:
    prefs = ctx.source_prefs("adzuna")
    app_id, app_key = ctx.env.get("ADZUNA_APP_ID"), ctx.env.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        return SourceResult(skipped="no API key (add ADZUNA_APP_ID and ADZUNA_APP_KEY to data/.env)")
    result = SourceResult()
    calls = 0
    for what in prefs.get("what", []):
        for where in prefs.get("where", []):
            try:
                ctx.quota.consume("adzuna")
            except QuotaExceeded as exc:
                if calls == 0:
                    return SourceResult(skipped=str(exc))
                result.warnings.append(str(exc))
                return result
            calls += 1
            params = {
                "app_id": app_id, "app_key": app_key, "what": what, "where": where,
                "max_days_old": prefs.get("max_days_old", 3), "results_per_page": 50,
                "sort_by": "date", "content-type": "application/json",
            }
            try:
                data = await ctx.http.get_json(URL, params=params)
            except HttpError as exc:
                if exc.status in (401, 403):
                    raise HttpError(exc.status, exc.url, "Adzuna rejected the app ID/key") from exc
                result.warnings.append(f"{what} in {where}: {exc}")
                continue
            items = data.get("results") or []
            result.postings.extend(to_posting(i) for i in items if i.get("id") and ctx.role_ok(clean_inline(i.get("title", ""))))
            ctx.progress(f"{what} in {where}: {len(items)} results")
    return result
```

- [ ] **Step 5: Register both sources**

In `sources/__init__.py`: `from . import adzuna, ashby, greenhouse, jsearch, lever, workday`; add `"jsearch": jsearch.fetch,` and `"adzuna": adzuna.fetch,` to `SOURCES`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_sources_aggregators.py -q && .venv/bin/ruff check src tests`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/job_apply_agent/search/sources tests/test_sources_aggregators.py
git commit -m "feat: add JSearch and Adzuna sources within free-tier budgets

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: LinkedIn guest search

**Files:**
- Create: `src/job_apply_agent/search/sources/linkedin.py`
- Modify: `src/job_apply_agent/search/sources/__init__.py` (register)
- Test: `tests/test_sources_linkedin.py`

**Interfaces:**
- Consumes: `parse_linkedin` from `jobs.py` (existing), `RateLimited`, `HttpError` (Task 6).
- Produces: `linkedin.parse_search(page: str) -> list[dict]` (keys `id`, `title`, `company`, `location`, `posted`), `linkedin.fetch(ctx)`. Final registry: `SOURCES` has all seven names in `SOURCE_NAMES` order.

Endpoint: `GET https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords&location&f_TPR=r86400|r604800&start=0[&f_WT=2]` returns HTML `<li>` cards with `data-entity-urn="urn:li:jobPosting:<id>"`, `base-search-card__title`, `base-search-card__subtitle`, `job-search-card__location`, `<time datetime=...>`. Detail: the existing `jobs-guest/jobs/api/jobPosting/<id>` page parsed by `parse_linkedin`. A live probe on 2026-11-09 got HTTP 429 on the first request, so the parser's selectors must be re-checked in the Task 20 smoke run; the source must fail soft.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sources_linkedin.py`:

```python
from fakes import make_ctx
from job_apply_agent.search.http import RateLimited
from job_apply_agent.search.sources import SOURCES, linkedin
from test_jobs import LINKEDIN_PAGE

SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/"


def card(job_id: str, title: str, company="Example Co", location="Toronto, Ontario, Canada") -> str:
    return f"""<li>
  <div class="base-card relative base-search-card job-search-card" data-entity-urn="urn:li:jobPosting:{job_id}">
    <a class="base-card__full-link" href="https://ca.linkedin.com/jobs/view/x-{job_id}"></a>
    <div class="base-search-card__info">
      <h3 class="base-search-card__title">
            {title}
      </h3>
      <h4 class="base-search-card__subtitle"><a class="hidden-nested-link" href="#">{company}</a></h4>
      <div class="base-search-card__metadata">
        <span class="job-search-card__location">{location}</span>
        <time class="job-search-card__listdate--new" datetime="2026-11-08">1 day ago</time>
      </div>
    </div>
  </div>
</li>"""


PAGE = card("111", "Data Analyst") + card("222", "Nurse") + card("111", "Data Analyst")


def test_parse_search_cards():
    cards = linkedin.parse_search(PAGE)
    assert [c["id"] for c in cards] == ["111", "222"]
    assert cards[0] == {"id": "111", "title": "Data Analyst", "company": "Example Co",
                        "location": "Toronto, Ontario, Canada", "posted": "2026-11-08"}


async def test_linkedin_fetches_details_for_matching_titles():
    prefs = {"sources": {"linkedin": {"keywords": ["data analyst"], "locations": ["Toronto, Ontario, Canada"],
                                      "remote_canada": False, "max_pages": 1}}}
    ctx = make_ctx(prefs=prefs, routes={SEARCH: PAGE, DETAIL: LINKEDIN_PAGE})
    result = await SOURCES["linkedin"](ctx)
    [p] = result.postings
    assert p.source == "linkedin" and p.external_id == "111" and p.company == "Example Co"
    assert p.posted_at == "2026-11-08T00:00:00+00:00" and "Power BI" in p.description
    assert p.url == "https://www.linkedin.com/jobs/view/111/"
    _m, _u, params, _h = ctx.http.calls[0]
    assert params["keywords"] == "data analyst" and params["f_TPR"] == "r604800"


async def test_linkedin_rate_limit_keeps_found_cards_as_partial():
    prefs = {"sources": {"linkedin": {"keywords": ["data analyst"], "locations": ["Toronto, Ontario, Canada"],
                                      "remote_canada": False, "max_pages": 1}}}
    ctx = make_ctx(prefs=prefs, routes={SEARCH: PAGE, DETAIL: RateLimited(429, DETAIL)})
    result = await linkedin.fetch(ctx)
    [p] = result.postings
    assert p.description_is_partial is True and p.title == "Data Analyst"
    assert "limiting requests" in result.warnings[0]


async def test_linkedin_blocked_immediately_is_a_warning():
    ctx = make_ctx(routes={SEARCH: RateLimited(429, SEARCH)})
    result = await linkedin.fetch(ctx)
    assert result.postings == [] and result.warnings


async def test_remote_canada_search_uses_work_type_filter():
    prefs = {"sources": {"linkedin": {"keywords": ["data analyst"], "locations": [], "remote_canada": True,
                                      "max_pages": 1}}}
    ctx = make_ctx(prefs=prefs, known=[("linkedin", "111")], routes={SEARCH: PAGE})
    result = await linkedin.fetch(ctx)
    assert ctx.http.calls[0][2]["f_WT"] == "2" and ctx.http.calls[0][2]["location"] == "Canada"
    assert result.postings[0].remote is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_sources_linkedin.py -q`
Expected: FAIL with `ImportError: cannot import name 'linkedin'`.

- [ ] **Step 3: Implement `sources/linkedin.py`**

```python
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
```

- [ ] **Step 4: Register LinkedIn; final registry**

Replace `src/job_apply_agent/search/sources/__init__.py` with:

```python
"""All job sources. Each module exposes ``async fetch(ctx) -> SourceResult``."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from ..base import Source
from . import adzuna, ashby, greenhouse, jsearch, lever, linkedin, workday

SOURCES: dict[str, Source] = {
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "ashby": ashby.fetch,
    "workday": workday.fetch,
    "jsearch": jsearch.fetch,
    "adzuna": adzuna.fetch,
    "linkedin": linkedin.fetch,
}

# For the Settings "Test" button: list a company's board without saving anything.
BOARD_LISTERS: dict[str, Callable[[Any, dict[str, Any]], Awaitable[list]]] = {
    "greenhouse": greenhouse.list_board,
    "lever": lever.list_board,
    "ashby": ashby.list_board,
    "workday": workday.list_first_page,
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_sources_linkedin.py -q && .venv/bin/pytest -q && .venv/bin/ruff check src tests`
Expected: PASS (whole suite).

- [ ] **Step 6: Commit**

```bash
git add src/job_apply_agent/search/sources tests/test_sources_linkedin.py
git commit -m "feat: add slow LinkedIn guest search source that stops when rate-limited

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Claude match scoring

**Files:**
- Create: `src/job_apply_agent/search/scoring.py`
- Test: `tests/test_scoring.py`

**Interfaces:**
- Consumes: `claude_agent_sdk.query`, `ClaudeAgentOptions`, `ResultMessage` (as `tailor.py` does).
- Produces:
  - `scoring.JobScore(job_id: int, score: int, summary: str, reasons: list[str], gaps: list[str], seniority_fit: str)`.
  - `scoring.ScoreOutcome(scores: list[JobScore], failed: list[int], errors: list[str], usage_limited: bool)`.
  - `scoring.profile_hash(resume: str, profile: str, answers: str) -> str` (16 hex chars).
  - `scoring.trim_description(text: str, limit: int = 8000) -> str`.
  - `scoring.build_options(model: str) -> ClaudeAgentOptions`.
  - `async scoring.score_jobs(jobs: list[dict], *, resume, profile, answers, model, batch_size=5, concurrency=2, on_progress: Callable[[int, int], None] | None = None, query_fn=None) -> ScoreOutcome`. `jobs` items have `id, title, company, location, description` (from `Database.jobs_to_score`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scoring.py`:

```python
import re

from job_apply_agent.search import scoring
from job_apply_agent.search.scoring import build_options, profile_hash, score_jobs, trim_description
from test_tailor import make_result

JOBS = [{"id": i, "title": f"Data Analyst {i}", "company": "Acme", "location": "Toronto", "description": "SQL. " * 20}
        for i in range(1, 8)]


class ScoringQuery:
    """Fake SDK query: scores every <job id="N"> in the prompt; can fail chosen calls."""

    def __init__(self, fail_calls=(), error_text="boom"):
        self.prompts = []
        self.fail_calls = set(fail_calls)
        self.error_text = error_text

    def __call__(self, *, prompt, options):
        self.prompts.append((prompt, options))
        call_no = len(self.prompts)
        ids = [int(x) for x in re.findall(r'<job id="(\d+)">', prompt)]

        async def gen():
            if call_no in self.fail_calls:
                yield make_result(subtype="error_during_execution", is_error=True, structured_output=None,
                                  result=self.error_text)
                return
            yield make_result(structured_output={"results": [
                {"job_id": i, "score": 70 + i, "summary": f"fit {i}", "reasons": ["SQL", "dashboards", "x", "y"],
                 "gaps": ["dbt"], "seniority_fit": "fit"} for i in ids
            ] + [{"job_id": 999, "score": 1, "summary": "", "reasons": [], "gaps": [], "seniority_fit": "fit"}]})

        return gen()


def test_profile_hash_changes_with_any_document():
    base = profile_hash("resume", "profile", "answers")
    assert len(base) == 16
    assert base != profile_hash("resume2", "profile", "answers")
    assert base != profile_hash("resume", "profile", "answers2")


def test_trim_description_cuts_late_boilerplate_only():
    text = "About us\nWe build things.\n" + "Requirements: SQL.\n" * 30 + "Benefits\nDental.\nEqual opportunity employer."
    trimmed = trim_description(text)
    assert trimmed.startswith("About us") and "Requirements" in trimmed and "Dental" not in trimmed
    assert trim_description("x" * 9000, limit=100).endswith("…")


def test_options_are_locked_down():
    options = build_options("claude-haiku-5-5")
    assert options.model == "claude-haiku-5-5" and options.tools == [] and options.setting_sources == []
    assert options.permission_mode == "dontAsk" and options.output_format["type"] == "json_schema"


async def test_score_jobs_batches_and_parses():
    fq = ScoringQuery()
    progress = []
    outcome = await score_jobs(JOBS, resume="R", profile="P", answers="A", model="m", batch_size=3,
                               concurrency=1, on_progress=lambda done, total: progress.append((done, total)),
                               query_fn=fq)
    assert len(fq.prompts) == 3  # 3 + 3 + 1
    assert sorted(s.job_id for s in outcome.scores) == list(range(1, 8))  # stray id 999 ignored
    assert outcome.scores[0].reasons == ["SQL", "dashboards", "x"]  # capped at 3
    assert progress[-1] == (7, 7) and not outcome.failed
    prompt = fq.prompts[0][0]
    assert "<candidate_resume>\nR\n</candidate_resume>" in prompt and "Data Analyst 1" in prompt


async def test_failed_batch_leaves_jobs_unscored():
    outcome = await score_jobs(JOBS, resume="R", profile="", answers="", model="m", batch_size=3, concurrency=1,
                               query_fn=ScoringQuery(fail_calls={2}))
    assert sorted(outcome.failed) == [4, 5, 6] and len(outcome.scores) == 4
    assert outcome.usage_limited is False and "boom" in outcome.errors[0]


async def test_usage_limit_stops_remaining_batches():
    fq = ScoringQuery(fail_calls={1}, error_text="Claude AI usage limit reached|1731200000")
    outcome = await score_jobs(JOBS, resume="R", profile="", answers="", model="m", batch_size=3, concurrency=1,
                               query_fn=fq)
    assert outcome.usage_limited is True and len(fq.prompts) == 1
    assert sorted(outcome.failed) == list(range(1, 8)) and outcome.scores == []


async def test_default_query_is_looked_up_at_call_time(monkeypatch):
    fq = ScoringQuery()
    monkeypatch.setattr(scoring, "query", fq)
    outcome = await score_jobs(JOBS[:1], resume="R", profile="", answers="", model="m")
    assert len(outcome.scores) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_scoring.py -q`
Expected: FAIL with `ImportError: cannot import name 'scoring'`.

- [ ] **Step 3: Implement `search/scoring.py`**

```python
"""Claude match scoring for found jobs.

Uses Claude Haiku 5.5 by default: fast and light on subscription usage limits. Each job is
scored once per version of the candidate's documents (tracked by ``profile_hash``).
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

SCORE_SYSTEM_PROMPT = """You are a careful recruiter. You rate how well one candidate fits each job posting.

Rules:
- Judge only from the candidate's documents. Never assume skills or experience that are not shown.
- score is 0-100: 85+ strong fit (meets nearly all core requirements), 70-84 good fit with minor gaps,
  50-69 partial fit, below 50 weak fit.
- seniority_fit compares the level and years the job asks for with the candidate's:
  "under" = the job is more senior than the candidate, "over" = the job is more junior, "fit" = about right.
  A seniority mismatch is a gap: lower the score for it and say so; don't hide it.
- reasons: up to 3 short, specific reasons the candidate fits, citing their real experience.
- gaps: up to 3 short, specific requirements the candidate's documents don't show.
- summary: one plain sentence a busy person can scan.
- Return exactly one result per job, using each job's id exactly as given."""

SCORE_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "integer"},
                    "score": {"type": "integer", "minimum": 0, "maximum": 100},
                    "summary": {"type": "string"},
                    "reasons": {"type": "array", "items": {"type": "string"}},
                    "gaps": {"type": "array", "items": {"type": "string"}},
                    "seniority_fit": {"type": "string", "enum": ["under", "fit", "over"]},
                },
                "required": ["job_id", "score", "summary", "reasons", "gaps", "seniority_fit"],
            },
        }
    },
    "required": ["results"],
}

USAGE_LIMIT = re.compile(r"usage limit|rate[ _-]?limit|\b429\b|limit reached|overloaded|quota", re.I)
BOILERPLATE = re.compile(
    r"^\s*(?:#+\s*)?(?:benefits|perks|what we offer|why join us|equal (?:employment )?opportunity|eeo\b"
    r"|accommodation|accessibility|our commitment to diversity|diversity,? equity)",
    re.I | re.M,
)
MAX_DESCRIPTION_CHARS = 8000


class ScoringError(RuntimeError):
    pass


@dataclass
class JobScore:
    job_id: int
    score: int
    summary: str
    reasons: list[str]
    gaps: list[str]
    seniority_fit: str


@dataclass
class ScoreOutcome:
    scores: list[JobScore] = field(default_factory=list)
    failed: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    usage_limited: bool = False


def profile_hash(resume: str, profile: str, answers: str) -> str:
    return hashlib.sha256("\x1e".join((resume, profile, answers)).encode("utf-8")).hexdigest()[:16]


def trim_description(text: str, limit: int = MAX_DESCRIPTION_CHARS) -> str:
    """Drop benefits/EEO boilerplate near the end (never the start), then cap the length."""
    text = (text or "").strip()
    for match in BOILERPLATE.finditer(text):
        if match.start() > len(text) * 0.4:
            text = text[: match.start()].rstrip()
            break
    if len(text) > limit:
        text = text[:limit].rstrip() + " …"
    return text


def build_prompt(jobs: list[dict[str, Any]], *, resume: str, profile: str, answers: str) -> str:
    parts = [f"<candidate_resume>\n{resume.strip()}\n</candidate_resume>"]
    if profile.strip():
        parts.append(f"<candidate_profile>\n{profile.strip()}\n</candidate_profile>")
    if answers.strip():
        parts.append(f"<candidate_answers>\n{answers.strip()}\n</candidate_answers>")
    parts.append("Rate the candidate against each job below.")
    for job in jobs:
        parts.append(
            f'<job id="{job["id"]}">\nTitle: {job["title"]}\nCompany: {job["company"]}\n'
            f'Location: {job["location"] or "not stated"}\n\n{trim_description(job["description"]) or "(no description)"}\n</job>'
        )
    return "\n\n".join(parts)


def build_options(model: str) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=SCORE_SYSTEM_PROMPT,
        tools=[],
        allowed_tools=[],
        permission_mode="dontAsk",
        setting_sources=[],
        output_format={"type": "json_schema", "schema": SCORE_OUTPUT_SCHEMA},
        max_turns=3,
        model=model,
    )


async def _score_batch(jobs, *, resume, profile, answers, model, query_fn) -> list[JobScore]:
    result: ResultMessage | None = None
    async for message in query_fn(prompt=build_prompt(jobs, resume=resume, profile=profile, answers=answers),
                                  options=build_options(model)):
        if isinstance(message, ResultMessage):
            result = message
    if result is None:
        raise ScoringError("Claude finished without a result.")
    if result.is_error or result.subtype != "success":
        raise ScoringError("; ".join(result.errors or []) or result.result or result.stop_reason or result.subtype)
    data = result.structured_output
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ScoringError("Claude did not return scores in the expected format.")
    wanted = {job["id"] for job in jobs}
    scores = []
    for item in data["results"]:
        try:
            job_id = int(item["job_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if job_id not in wanted:
            continue
        wanted.discard(job_id)
        scores.append(JobScore(
            job_id=job_id,
            score=max(0, min(100, int(item.get("score", 0)))),
            summary=str(item.get("summary", "")).strip(),
            reasons=[str(r) for r in item.get("reasons", [])][:3],
            gaps=[str(g) for g in item.get("gaps", [])][:3],
            seniority_fit=item.get("seniority_fit") if item.get("seniority_fit") in ("under", "fit", "over") else "fit",
        ))
    return scores


async def score_jobs(
    jobs: list[dict[str, Any]],
    *,
    resume: str,
    profile: str,
    answers: str,
    model: str,
    batch_size: int = 5,
    concurrency: int = 2,
    on_progress: Callable[[int, int], None] | None = None,
    query_fn=None,
) -> ScoreOutcome:
    query_fn = query_fn or query
    outcome = ScoreOutcome()
    batches = [jobs[i: i + max(1, batch_size)] for i in range(0, len(jobs), max(1, batch_size))]
    semaphore = asyncio.Semaphore(max(1, concurrency))
    stop = asyncio.Event()
    done = 0

    async def run(batch: list[dict[str, Any]]) -> None:
        nonlocal done
        ids = [job["id"] for job in batch]
        async with semaphore:
            if stop.is_set():
                outcome.failed.extend(ids)
                return
            try:
                scores = await _score_batch(batch, resume=resume, profile=profile, answers=answers, model=model,
                                            query_fn=query_fn)
            except Exception as exc:  # noqa: BLE001 - any failure leaves the batch unscored for next time
                message = str(exc) or exc.__class__.__name__
                outcome.errors.append(message)
                outcome.failed.extend(ids)
                if USAGE_LIMIT.search(message):
                    outcome.usage_limited = True
                    stop.set()
                return
        outcome.scores.extend(scores)
        returned = {s.job_id for s in scores}
        outcome.failed.extend(i for i in ids if i not in returned)
        done += len(batch)
        if on_progress:
            on_progress(done, len(jobs))

    await asyncio.gather(*(run(batch) for batch in batches))
    return outcome
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_scoring.py -q && .venv/bin/ruff check src tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/job_apply_agent/search/scoring.py tests/test_scoring.py
git commit -m "feat: score jobs against the candidate's documents with Claude Haiku 5.5

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Events and the search pipeline

**Files:**
- Create: `src/job_apply_agent/search/events.py`, `src/job_apply_agent/search/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: everything from Tasks 4–11.
- Produces:
  - `events.EventBus()` with `subscribe() -> asyncio.Queue`, `unsubscribe(queue)`, `publish(event: dict)`. Event types: `run.started {run_id, trigger, sources}`, `run.source {run_id, source, stat}`, `run.progress {run_id, message}`, `run.scoring {run_id, done, total}`, `run.finished {run_id, run}`.
  - `pipeline.SearchAlreadyRunning`, `pipeline.CandidateDocs(resume: str, profile: str = "", answers: str = "")`.
  - `pipeline.SearchRunner(db, *, events, load_prefs, load_companies, load_env, load_docs, http_factory, scorer=None, sources=None, now_fn=now_utc)` with `.running: bool` and `async run(*, trigger: str, sources: list[str] | None = None, score: bool = True) -> int` (run id). `sources=None` = all enabled; `[]` = score only. Unknown names raise `ValueError`.
  - Run record `sources` JSON: one entry per source (`{"status": "ok"|"partial"|"error"|"skipped", "fetched", "relevant", "new", "warnings"}` / `{"status": "error", "error"}` / `{"status": "skipped", "reason"}`) plus `"scoring": {"status": "ok"|"partial"|"limited"|"skipped", "scored", "failed", "message"}`.
  - `pipeline.refilter_jobs(db, prefs) -> int` (number of jobs whose relevance changed).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pipeline.py`:

```python
import asyncio
from datetime import datetime, timezone

import pytest

from fakes import FakeHttp
from job_apply_agent.db import Database
from job_apply_agent.jobs import JobPosting
from job_apply_agent.preferences import merge_defaults
from job_apply_agent.search.base import SourceResult
from job_apply_agent.search.events import EventBus
from job_apply_agent.search.pipeline import CandidateDocs, SearchAlreadyRunning, SearchRunner, refilter_jobs
from job_apply_agent.search.scoring import JobScore, ScoreOutcome
from job_apply_agent.timeutil import iso

NOW = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)


def jobs_a():
    return [
        JobPosting(url="https://gh/1", title="Data Analyst", company="Acme", location="Toronto, ON",
                   description="SQL " * 100, external_id="1", board="acme"),
        JobPosting(url="https://gh/2", title="Sales Rep", company="Acme", location="Toronto, ON", external_id="2"),
        JobPosting(url="https://gh/3", title="Data Analyst", company="Acme", location="Austin, TX", external_id="3"),
    ]


def source(make=jobs_a, *, error=None, skipped=None, seen=None, gate: asyncio.Event | None = None):
    async def fetch(_ctx):
        if gate is not None:
            await gate.wait()
        if error:
            raise error
        return SourceResult(postings=make(), seen_ids=seen or {}, skipped=skipped)
    return fetch


class FakeScorer:
    def __init__(self, outcome_fn=None):
        self.calls = []
        self.outcome_fn = outcome_fn

    async def __call__(self, jobs, **kwargs):
        self.calls.append((jobs, kwargs))
        kwargs["on_progress"](len(jobs), len(jobs))
        if self.outcome_fn:
            return self.outcome_fn(jobs)
        return ScoreOutcome(scores=[JobScore(j["id"], 80, "good", ["SQL"], [], "fit") for j in jobs])


def make_runner(db, sources, *, docs=CandidateDocs("my resume"), scorer=None, prefs=None, events=None):
    return SearchRunner(
        db, events=events or EventBus(), load_prefs=lambda: merge_defaults(prefs or {}), load_companies=lambda: [],
        load_env=lambda: {}, load_docs=lambda: docs, http_factory=FakeHttp, scorer=scorer or FakeScorer(),
        sources=sources, now_fn=lambda: NOW,
    )


@pytest.fixture
def db():
    d = Database(":memory:")
    yield d
    d.close()


async def test_run_stores_relevant_jobs_and_scores_them(db):
    scorer = FakeScorer()
    runner = make_runner(db, {"greenhouse": source()}, scorer=scorer)
    run_id = await runner.run(trigger="manual")
    [job] = db.list_jobs(now=iso(NOW))
    assert job["title"] == "Data Analyst" and job["location_label"] == "Toronto/GTA" and job["score"] == 80
    run = db.get_run(run_id)
    assert run["sources"]["greenhouse"] == {"status": "ok", "fetched": 3, "relevant": 1, "new": 1, "warnings": []}
    assert run["sources"]["scoring"]["status"] == "ok" and run["scored"] == 1
    assert scorer.calls[0][1]["model"] == "claude-haiku-5-5"
    assert db.source_states()["greenhouse"]["last_success_at"] == iso(NOW)


async def test_second_run_scores_nothing(db):
    scorer = FakeScorer()
    runner = make_runner(db, {"greenhouse": source()}, scorer=scorer)
    await runner.run(trigger="manual")
    second = await runner.run(trigger="schedule")
    assert len(scorer.calls) == 1
    assert db.get_run(second)["sources"]["scoring"]["message"] == "Nothing new to score."
    assert db.get_run(second)["sources"]["greenhouse"]["new"] == 0


async def test_resume_change_rescores_everything(db):
    scorer = FakeScorer()
    docs = {"value": CandidateDocs("v1")}
    runner = SearchRunner(db, events=EventBus(), load_prefs=lambda: merge_defaults({}), load_companies=lambda: [],
                          load_env=lambda: {}, load_docs=lambda: docs["value"], http_factory=FakeHttp,
                          scorer=scorer, sources={"greenhouse": source()}, now_fn=lambda: NOW)
    await runner.run(trigger="manual")
    docs["value"] = CandidateDocs("v2")
    await runner.run(trigger="manual", sources=[])  # score-only run
    assert len(scorer.calls) == 2 and len(scorer.calls[1][0]) == 1


async def test_missing_resume_skips_scoring(db):
    scorer = FakeScorer()
    run_id = await make_runner(db, {"greenhouse": source()}, docs=None, scorer=scorer).run(trigger="manual")
    assert scorer.calls == []
    assert db.get_run(run_id)["sources"]["scoring"]["status"] == "skipped"
    assert db.list_jobs(now=iso(NOW))[0]["score"] is None


async def test_failing_source_does_not_stop_others(db):
    runner = make_runner(db, {"greenhouse": source(), "lever": source(error=RuntimeError("HTML instead of JSON"))})
    run = db.get_run(await runner.run(trigger="manual"))
    assert run["sources"]["lever"] == {"status": "error", "error": "HTML instead of JSON"}
    assert run["sources"]["greenhouse"]["status"] == "ok" and run["error"] is None
    assert db.source_states()["lever"]["last_success_at"] is None


async def test_skipped_and_partial_sources(db):
    def with_warning():
        return jobs_a()[:1]

    async def warn(_ctx):
        return SourceResult(postings=with_warning(), warnings=["Shopify: HTTP 404"])

    runner = make_runner(db, {"jsearch": source(skipped="no API key"), "ashby": warn})
    run = db.get_run(await runner.run(trigger="manual"))
    assert run["sources"]["jsearch"] == {"status": "skipped", "reason": "no API key"}
    assert run["sources"]["ashby"]["status"] == "partial"


async def test_usage_limit_reported(db):
    scorer = FakeScorer(lambda jobs: ScoreOutcome(failed=[j["id"] for j in jobs], usage_limited=True,
                                                  errors=["usage limit"]))
    run = db.get_run(await make_runner(db, {"greenhouse": source()}, scorer=scorer).run(trigger="manual"))
    assert run["sources"]["scoring"]["status"] == "limited"


async def test_only_one_run_at_a_time(db):
    gate = asyncio.Event()
    runner = make_runner(db, {"greenhouse": source(gate=gate)})
    first = asyncio.create_task(runner.run(trigger="manual"))
    await asyncio.sleep(0)
    assert runner.running
    with pytest.raises(SearchAlreadyRunning):
        await runner.run(trigger="schedule")
    gate.set()
    await first
    assert not runner.running


async def test_explicit_sources_and_unknown_names(db):
    called = []

    async def lever(_ctx):
        called.append("lever")
        return SourceResult()

    runner = make_runner(db, {"greenhouse": source(), "lever": lever})
    run = db.get_run(await runner.run(trigger="manual", sources=["lever"]))
    assert called == ["lever"] and "greenhouse" not in run["sources"]
    with pytest.raises(ValueError):
        await runner.run(trigger="manual", sources=["monster"])


async def test_disabled_sources_are_skipped_by_default(db):
    runner = make_runner(db, {"greenhouse": source()}, prefs={"sources": {"greenhouse": {"enabled": False}}})
    run = db.get_run(await runner.run(trigger="manual"))
    assert "greenhouse" not in run["sources"]


async def test_events_are_published(db):
    events = EventBus()
    queue = events.subscribe()
    await make_runner(db, {"greenhouse": source()}, events=events).run(trigger="manual")
    types = []
    while not queue.empty():
        types.append(queue.get_nowait()["type"])
    assert types[0] == "run.started" and types[-1] == "run.finished"
    assert "run.source" in types and "run.scoring" in types


async def test_closed_jobs_tracked_from_seen_ids(db):
    runner = make_runner(db, {"greenhouse": source(seen={"acme": {"1"}})})
    await runner.run(trigger="manual")
    runner.sources["greenhouse"] = source(make=lambda: [], seen={"acme": set()})
    await runner.run(trigger="manual")
    await runner.run(trigger="manual")
    assert db.list_jobs(now=iso(NOW)) == []


async def test_refilter_after_role_change(db):
    await make_runner(db, {"greenhouse": source()}).run(trigger="manual")
    changed = refilter_jobs(db, merge_defaults({"role_terms": ["data scientist"]}))
    assert changed == 1 and db.list_jobs(now=iso(NOW)) == []
    assert refilter_jobs(db, merge_defaults({})) == 1


def test_event_bus_drops_when_full():
    bus = EventBus(maxsize=1)
    queue = bus.subscribe()
    bus.publish({"type": "a"})
    bus.publish({"type": "b"})  # dropped, no exception
    assert queue.qsize() == 1
    bus.unsubscribe(queue)
    bus.publish({"type": "c"})
    assert queue.qsize() == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_pipeline.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_apply_agent.search.events'`.

- [ ] **Step 3: Implement `search/events.py`**

```python
"""Tiny in-process publish/subscribe used to stream progress to the browser (SSE)."""

from __future__ import annotations

import asyncio
from typing import Any


class EventBus:
    def __init__(self, maxsize: int = 500):
        self._subscribers: set[asyncio.Queue] = set()
        self._maxsize = maxsize

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def publish(self, event: dict[str, Any]) -> None:
        """Call from the event loop thread. Slow subscribers lose events instead of blocking."""
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass
```

- [ ] **Step 4: Implement `search/pipeline.py`**

```python
"""One search run: fetch every source in parallel, store and dedupe, gate, then score new jobs."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..db import Database
from ..jobs import JobPosting
from ..preferences import SOURCE_NAMES
from ..timeutil import iso, now_utc, parse_datetime
from .base import Source, SourceContext
from .dedupe import canonical_url, dedupe_key
from .events import EventBus
from .filters import evaluate, role_matches
from .quota import QuotaGuard, budgets_from_prefs
from .scoring import profile_hash, score_jobs

logger = logging.getLogger(__name__)


class SearchAlreadyRunning(RuntimeError):
    pass


@dataclass
class CandidateDocs:
    resume: str
    profile: str = ""
    answers: str = ""


class SearchRunner:
    def __init__(
        self,
        db: Database,
        *,
        events: EventBus,
        load_prefs: Callable[[], dict[str, Any]],
        load_companies: Callable[[], list[dict[str, Any]]],
        load_env: Callable[[], dict[str, str]],
        load_docs: Callable[[], CandidateDocs | None],
        http_factory: Callable[[], Any],
        scorer=None,
        sources: dict[str, Source] | None = None,
        now_fn: Callable[[], datetime] = now_utc,
    ):
        if sources is None:
            from .sources import SOURCES

            sources = dict(SOURCES)
        self.db = db
        self.events = events
        self.load_prefs = load_prefs
        self.load_companies = load_companies
        self.load_env = load_env
        self.load_docs = load_docs
        self.http_factory = http_factory
        self.scorer = scorer or score_jobs
        self.sources = sources
        self.now_fn = now_fn
        self._lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._lock.locked()

    async def run(self, *, trigger: str, sources: list[str] | None = None, score: bool = True) -> int:
        if self._lock.locked():
            raise SearchAlreadyRunning("A search is already running.")
        async with self._lock:
            return await self._run(trigger, sources, score)

    def _names(self, prefs: dict[str, Any], requested: list[str] | None) -> list[str]:
        if requested is None:
            return [n for n in SOURCE_NAMES if prefs["sources"].get(n, {}).get("enabled") and n in self.sources]
        unknown = [n for n in requested if n not in SOURCE_NAMES]
        if unknown:
            raise ValueError(f"Unknown source(s): {', '.join(unknown)}. Choose from {', '.join(SOURCE_NAMES)}.")
        return [n for n in requested if n in self.sources]

    async def _run(self, trigger: str, requested: list[str] | None, score: bool) -> int:
        prefs = self.load_prefs()
        names = self._names(prefs, requested)
        run_id = self.db.start_run(trigger, iso(self.now_fn()))
        self.events.publish({"type": "run.started", "run_id": run_id, "trigger": trigger, "sources": names})
        stats: dict[str, Any] = {}
        scored = 0
        error = None
        try:
            if names:
                ctx = self._context(prefs, run_id)
                await asyncio.gather(*(self._run_source(name, ctx, prefs, run_id, stats) for name in names))
            if score:
                stats["scoring"] = await self._score(prefs, run_id)
            else:
                stats["scoring"] = {"status": "skipped", "scored": 0, "message": "Scoring was turned off for this run."}
            scored = int(stats["scoring"].get("scored", 0))
        except Exception as exc:  # noqa: BLE001 - recorded on the run and shown in the UI
            logger.exception("Search run %s failed", run_id)
            error = str(exc) or exc.__class__.__name__
        finally:
            self.db.finish_run(run_id, sources=stats, scored=scored, error=error, now=iso(self.now_fn()))
            self.events.publish({"type": "run.finished", "run_id": run_id, "run": self.db.get_run(run_id)})
        return run_id

    def _context(self, prefs: dict[str, Any], run_id: int) -> SourceContext:
        states = self.db.source_states()
        return SourceContext(
            prefs=prefs,
            companies=self.load_companies(),
            http=self.http_factory(),
            quota=QuotaGuard(self.db, budgets_from_prefs(prefs), self.now_fn),
            env=self.load_env(),
            role_ok=lambda title: role_matches(title, prefs["role_terms"]),
            known=self.db.has_link,
            last_success=lambda name: parse_datetime((states.get(name) or {}).get("last_success_at")),
            progress=lambda message: self.events.publish({"type": "run.progress", "run_id": run_id, "message": message}),
        )

    async def _run_source(self, name: str, ctx: SourceContext, prefs: dict[str, Any], run_id: int,
                          stats: dict[str, Any]) -> None:
        self.events.publish({"type": "run.source", "run_id": run_id, "source": name, "stat": {"status": "running"}})
        now = iso(self.now_fn())
        try:
            result = await self.sources[name](ctx)
        except Exception as exc:  # noqa: BLE001 - one source failing must not stop the others
            logger.warning("Source %s failed: %s", name, exc)
            stats[name] = {"status": "error", "error": (str(exc) or exc.__class__.__name__)[:300]}
            self.db.mark_source_attempt(name, now, success=False)
        else:
            if result.skipped:
                stats[name] = {"status": "skipped", "reason": result.skipped}
                self.db.mark_source_attempt(name, now, success=False)
            else:
                relevant = new = 0
                for posting in result.postings:
                    posting.source = posting.source or name
                    ok, label = evaluate(posting, prefs)
                    _job_id, created = self.db.upsert_posting(
                        posting, dedupe_key=dedupe_key(posting), canonical_url=canonical_url(posting.url),
                        relevant=ok, location_label=label, run_id=run_id, now=now,
                    )
                    relevant += int(ok)
                    new += int(created and ok)
                for board, ids in result.seen_ids.items():
                    self.db.mark_missing(name, board, ids)
                stats[name] = {
                    "status": "partial" if result.warnings else "ok",
                    "fetched": len(result.postings),
                    "relevant": relevant,
                    "new": new,
                    "warnings": result.warnings[:10],
                }
                self.db.mark_source_attempt(name, now, success=True)
        self.events.publish({"type": "run.source", "run_id": run_id, "source": name, "stat": stats[name]})

    async def _score(self, prefs: dict[str, Any], run_id: int) -> dict[str, Any]:
        docs = self.load_docs()
        if docs is None:
            return {"status": "skipped", "scored": 0,
                    "message": "No resume yet, so jobs were not scored. Add it in Settings."}
        phash = profile_hash(docs.resume, docs.profile, docs.answers)
        pending = self.db.jobs_to_score(phash)
        if not pending:
            return {"status": "ok", "scored": 0, "failed": 0, "message": "Nothing new to score."}
        model = prefs["models"]["scoring"]

        def progress(done: int, total: int) -> None:
            self.events.publish({"type": "run.scoring", "run_id": run_id, "done": done, "total": total})

        progress(0, len(pending))
        outcome = await self.scorer(
            pending, resume=docs.resume, profile=docs.profile, answers=docs.answers, model=model,
            batch_size=prefs["scoring"]["batch_size"], concurrency=prefs["scoring"]["concurrency"],
            on_progress=progress,
        )
        now = iso(self.now_fn())
        for s in outcome.scores:
            self.db.save_score(s.job_id, score=s.score, summary=s.summary, reasons=s.reasons, gaps=s.gaps,
                               seniority_fit=s.seniority_fit, model=model, profile_hash=phash, now=now)
        if outcome.usage_limited:
            status, message = "limited", "Claude usage limit reached; the rest will be scored on the next run."
        elif outcome.failed:
            status, message = "partial", f"{len(outcome.failed)} job(s) couldn't be scored this time; they'll be retried."
        else:
            status, message = "ok", f"Scored {len(outcome.scores)} job(s)."
        return {"status": status, "scored": len(outcome.scores), "failed": len(outcome.failed),
                "message": message, "errors": outcome.errors[:3]}


def refilter_jobs(db: Database, prefs: dict[str, Any]) -> int:
    """Re-run the relevance gate over stored jobs after role/location/exclusion settings change."""
    changed = 0
    for job in db.all_jobs_for_refilter():
        posting = JobPosting(url="", title=job["title"], company=job["company"], location=job["location"],
                             remote=job["remote"], country=job["country"])
        ok, label = evaluate(posting, prefs)
        if ok != job["relevant"] or (ok and label != job["location_label"]):
            db.set_relevance(job["id"], ok, label)
            changed += 1
    return changed
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_pipeline.py -q && .venv/bin/ruff check src tests`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/job_apply_agent/search/events.py src/job_apply_agent/search/pipeline.py tests/test_pipeline.py
git commit -m "feat: add search pipeline that fetches, dedupes, gates and scores jobs

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Scheduler, runtime wiring and `job-agent search`

**Files:**
- Create: `src/job_apply_agent/search/scheduler.py`, `src/job_apply_agent/runtime.py`
- Modify: `src/job_apply_agent/cli.py` (add `search` command)
- Test: `tests/test_scheduler_runtime.py`

**Interfaces:**
- Consumes: `SearchRunner`, `SearchAlreadyRunning`, `CandidateDocs` (Task 12); loaders from Tasks 2 and 6.
- Produces:
  - `scheduler.Scheduler(runner, db, load_prefs, *, now_fn=now_utc, tick_seconds=60, sleep=asyncio.sleep)` with `due_sources(now) -> list[str]`, `async tick() -> int | None`, `async run_forever()`.
  - `runtime.Runtime(db, events, runner, scheduler, now)` dataclass (Task 15 adds `tailor`); `runtime.default_http() -> Http`; `runtime.load_candidate_docs() -> CandidateDocs | None`; `runtime.build_runtime(*, db=None, sources=None, scorer=None, http_factory=None, now_fn=now_utc) -> Runtime`.
  - CLI: `job-agent search [--sources a,b] [--no-score]`; `cli.format_stat(name, stat) -> str`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scheduler_runtime.py`:

```python
from datetime import datetime, timedelta, timezone
from pathlib import Path

from job_apply_agent import cli, runtime
from job_apply_agent.db import Database
from job_apply_agent.jobs import JobPosting
from job_apply_agent.preferences import merge_defaults
from job_apply_agent.search.base import SourceResult
from job_apply_agent.search.scheduler import Scheduler
from job_apply_agent.timeutil import iso

NOW = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)


class FakeRunner:
    def __init__(self):
        self.running = False
        self.calls = []

    async def run(self, *, trigger, sources=None, score=True):
        self.calls.append((trigger, sources))
        return 1


def test_due_sources_by_interval():
    db = Database(":memory:")
    db.mark_source_attempt("greenhouse", iso(NOW - timedelta(minutes=30)), success=True)  # 1h interval: not due
    db.mark_source_attempt("lever", iso(NOW - timedelta(hours=2)), success=True)  # due
    db.mark_source_attempt("jsearch", iso(NOW - timedelta(hours=5)), success=False)  # 24h interval: not due
    prefs = merge_defaults({"sources": {"linkedin": {"enabled": False}}})
    due = Scheduler(FakeRunner(), db, lambda: prefs, now_fn=lambda: NOW).due_sources(NOW)
    assert due == ["lever", "ashby", "workday", "adzuna"]  # never-run sources are due; linkedin disabled


async def test_tick_runs_due_sources_and_respects_running_and_disabled():
    db = Database(":memory:")
    runner = FakeRunner()
    prefs = {"value": merge_defaults({})}
    scheduler = Scheduler(runner, db, lambda: prefs["value"], now_fn=lambda: NOW)
    assert await scheduler.tick() == 1
    assert runner.calls[0][0] == "schedule" and "greenhouse" in runner.calls[0][1]
    runner.running = True
    assert await scheduler.tick() is None
    runner.running = False
    prefs["value"] = merge_defaults({"schedule": {"enabled": False}})
    assert await scheduler.tick() is None and len(runner.calls) == 1


def test_load_candidate_docs(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("JOB_AGENT_DATA_DIR", str(tmp_path))
    assert runtime.load_candidate_docs() is None
    (tmp_path / "my_resume.docx").write_bytes(b"")  # placeholder; read_resume is patched below
    monkeypatch.setattr(runtime, "read_resume", lambda path: "RESUME TEXT")
    docs = runtime.load_candidate_docs()
    assert docs.resume == "RESUME TEXT" and docs.profile == "" and docs.answers == ""


def test_cli_search_command(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.setenv("JOB_AGENT_DATA_DIR", str(tmp_path))

    async def fake_source(_ctx):
        return SourceResult(postings=[JobPosting(url="https://gh/1", title="Data Analyst", company="Acme",
                                                 location="Toronto, ON", external_id="1")])

    real_build = runtime.build_runtime
    monkeypatch.setattr(runtime, "build_runtime",
                        lambda: real_build(db=Database(":memory:"), sources={"greenhouse": fake_source}))
    assert cli.main(["search", "--sources", "greenhouse", "--no-score"]) == 0
    out = capsys.readouterr().out
    assert "greenhouse: 1 fetched, 1 relevant, 1 new" in out
    assert "scoring: Scoring was turned off for this run." in out


def test_format_stat_variants():
    assert cli.format_stat("jsearch", {"status": "skipped", "reason": "no API key"}) == "jsearch: skipped (no API key)"
    assert cli.format_stat("lever", {"status": "error", "error": "boom"}) == "lever: error: boom"
    line = cli.format_stat("ashby", {"status": "partial", "fetched": 2, "relevant": 1, "new": 0, "warnings": ["X: 404"]})
    assert line == "ashby: 2 fetched, 1 relevant, 0 new (1 warning(s), first: X: 404)"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_scheduler_runtime.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_apply_agent.search.scheduler'`.

- [ ] **Step 3: Implement `search/scheduler.py`**

```python
"""Runs each source on its own interval while the app is open (hourly company sites, daily JSearch...)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from ..db import Database
from ..preferences import SOURCE_NAMES
from ..timeutil import now_utc, parse_datetime
from .pipeline import SearchAlreadyRunning

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(
        self,
        runner,
        db: Database,
        load_prefs: Callable[[], dict[str, Any]],
        *,
        now_fn: Callable[[], datetime] = now_utc,
        tick_seconds: float = 60,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.runner = runner
        self.db = db
        self.load_prefs = load_prefs
        self.now_fn = now_fn
        self.tick_seconds = tick_seconds
        self._sleep = sleep

    def due_sources(self, now: datetime) -> list[str]:
        prefs = self.load_prefs()
        states = self.db.source_states()
        due = []
        for name in SOURCE_NAMES:
            cfg = prefs["sources"].get(name, {})
            if not cfg.get("enabled"):
                continue
            last = parse_datetime((states.get(name) or {}).get("last_attempt_at"))
            if last is None or now - last >= timedelta(hours=float(cfg["interval_hours"])):
                due.append(name)
        return due

    async def tick(self) -> int | None:
        if self.runner.running or not self.load_prefs()["schedule"]["enabled"]:
            return None
        due = self.due_sources(self.now_fn())
        if not due:
            return None
        try:
            return await self.runner.run(trigger="schedule", sources=due)
        except SearchAlreadyRunning:
            return None

    async def run_forever(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:  # noqa: BLE001 - keep the scheduler alive; the run is logged
                logger.exception("Scheduled search failed")
            await self._sleep(self.tick_seconds)
```

- [ ] **Step 4: Implement `runtime.py`**

```python
"""Builds the long-lived app objects (database, search runner, scheduler) from the data folder."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from . import paths
from .career_profile import load_answers, load_profile
from .db import Database
from .documents import read_resume
from .envfile import load_env
from .preferences import load_preferences, resume_path
from .search.companies import load_companies
from .search.events import EventBus
from .search.http import Http
from .search.pipeline import CandidateDocs, SearchRunner
from .search.scheduler import Scheduler
from .timeutil import now_utc


@dataclass
class Runtime:
    db: Database
    events: EventBus
    runner: SearchRunner
    scheduler: Scheduler
    now: Callable[[], datetime]


def default_http() -> Http:
    return Http(host_delays={"www.linkedin.com": (3.0, 6.0)})


def load_candidate_docs() -> CandidateDocs | None:
    path = resume_path(load_preferences())
    if not path.is_file():
        return None
    return CandidateDocs(
        resume=read_resume(path),
        profile=load_profile(paths.profile_dir()),
        answers=load_answers(paths.profile_dir()),
    )


def build_runtime(*, db: Database | None = None, sources=None, scorer=None, http_factory=None,
                  now_fn: Callable[[], datetime] = now_utc) -> Runtime:
    db = db or Database(paths.db_path())
    events = EventBus()
    runner = SearchRunner(
        db,
        events=events,
        load_prefs=load_preferences,
        load_companies=load_companies,
        load_env=load_env,
        load_docs=load_candidate_docs,
        http_factory=http_factory or default_http,
        scorer=scorer,
        sources=sources,
        now_fn=now_fn,
    )
    scheduler = Scheduler(runner, db, load_preferences, now_fn=now_fn)
    return Runtime(db=db, events=events, runner=runner, scheduler=scheduler, now=now_fn)
```

- [ ] **Step 5: Add `job-agent search` to `cli.py`**

In `build_parser`, before `return parser`:

```python
    se = sub.add_parser("search", help="Search all job sources once and score new jobs (no web UI needed).")
    se.add_argument(
        "--sources",
        type=lambda v: [s.strip() for s in v.split(",") if s.strip()],
        help="Comma-separated sources, e.g. greenhouse,lever (default: all enabled).",
    )
    se.add_argument("--no-score", action="store_true", help="Collect jobs without Claude scoring.")
```

Add these functions above `main`:

```python
def format_stat(name: str, stat: dict) -> str:
    status = stat.get("status")
    if status == "skipped" and name != "scoring":
        return f"{name}: skipped ({stat.get('reason')})"
    if status == "error":
        return f"{name}: error: {stat.get('error')}"
    if name == "scoring":
        return f"scoring: {stat.get('message', '')}"
    line = f"{name}: {stat.get('fetched', 0)} fetched, {stat.get('relevant', 0)} relevant, {stat.get('new', 0)} new"
    if stat.get("warnings"):
        line += f" ({len(stat['warnings'])} warning(s), first: {stat['warnings'][0]})"
    return line


def run_search(args: argparse.Namespace) -> int:
    from . import runtime

    rt = runtime.build_runtime()
    run_id = asyncio.run(rt.runner.run(trigger="cli", sources=args.sources, score=not args.no_score))
    run = rt.db.get_run(run_id)
    for name, stat in run["sources"].items():
        print(format_stat(name, stat))
    if run["error"]:
        print(f"Error: {run['error']}", file=sys.stderr)
        return 1
    print("Open the app to see the ranked list: job-agent serve")
    return 0
```

In `main`, add the dispatch line next to the others:

```python
        if args.command == "search":
            return run_search(args)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check src tests`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/job_apply_agent/search/scheduler.py src/job_apply_agent/runtime.py src/job_apply_agent/cli.py tests/test_scheduler_runtime.py
git commit -m "feat: add per-source scheduler, runtime wiring and job-agent search

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: FastAPI app: jobs, search, runs, settings, profile, status

**Files:**
- Create: `src/job_apply_agent/web/__init__.py` (docstring only), `src/job_apply_agent/web/app.py`
- Test: `tests/test_web_api.py`

**Interfaces:**
- Consumes: `Runtime`, `build_runtime` (Task 13); `refilter_jobs`, `SearchAlreadyRunning` (Task 12); preferences/companies/env loaders; `QuotaGuard`; `auth_warning`; `documents._find_soffice`.
- Produces: `web.app.create_app(runtime: Runtime | None = None, *, start_scheduler: bool = True) -> FastAPI` with routes:
  - `GET /api/jobs?tab&sort&order&role&location&source&status&min_score&include_closed&hide_done` → `{"jobs": [...], "counts": {...}}`
  - `GET /api/jobs/{id}` → job detail; `PATCH /api/jobs/{id}` body `{"status"?, "notes"?}`
  - `POST /api/search` body `{"sources": [...] | null}` → 202 `{"started": true}`; 409 if running
  - `GET /api/runs?limit=10`, `GET /api/runs/{id}`
  - `GET /api/events` (SSE: `data: <json>\n\n`, `: ping` every 15 s)
  - `GET /api/preferences`, `PUT /api/preferences` (full preferences object) → `{"preferences", "refiltered"}`
  - `GET /api/companies`, `PUT /api/companies` (list) → list, `POST /api/companies/test` (one company) → `{"ok", "jobs"?, "error"?}`
  - `GET /api/profile`, `POST /api/profile/resume` (multipart `file`), `POST /api/profile/documents` (multipart `file`), `DELETE /api/profile/documents/{name}` → profile `{"resume": {"path", "name", "exists"}, "documents": [{"name", "size"}]}`
  - `GET /api/status` → `{"resume", "auth_warning", "keys": {"jsearch", "adzuna"}, "libreoffice", "quota", "search_running", "schedule_enabled", "last_run", "counts"}`
  - `/` serves `web/static/index.html` when built, else a JSON hint.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_api.py`:

```python
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from job_apply_agent.db import Database
from job_apply_agent.jobs import JobPosting
from job_apply_agent.runtime import build_runtime
from job_apply_agent.search.base import SourceResult
from job_apply_agent.web.app import create_app


async def fake_source(_ctx):
    return SourceResult(postings=[
        JobPosting(url="https://gh/1", title="Data Analyst", company="Acme", location="Toronto, ON",
                   description="SQL " * 100, external_id="1"),
        JobPosting(url="https://gh/2", title="Data Scientist", company="Beta", location="Ottawa, ON",
                   description="Python " * 100, external_id="2"),
    ])


@pytest.fixture
def client(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("JOB_AGENT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("JOB_AGENT_OUTPUT_DIR", str(tmp_path / "output"))
    for key in ("JSEARCH_API_KEY", "ADZUNA_APP_ID", "ADZUNA_APP_KEY"):
        monkeypatch.delenv(key, raising=False)
    rt = build_runtime(db=Database(":memory:"), sources={"greenhouse": fake_source})
    with TestClient(create_app(rt, start_scheduler=False)) as c:
        c.rt = rt
        yield c


def wait_for_run(client, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        runs = client.get("/api/runs").json()
        if runs and runs[0]["finished_at"]:
            return runs[0]
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_search_then_list_and_filter(client):
    assert client.post("/api/search", json={"sources": ["greenhouse"]}).status_code == 202
    run = wait_for_run(client)
    assert run["sources"]["greenhouse"]["relevant"] == 2
    body = client.get("/api/jobs").json()
    assert len(body["jobs"]) == 2 and all(j["score"] is None for j in body["jobs"])  # no resume yet -> unscored
    assert body["counts"]["relevant"] == 2
    ottawa = client.get("/api/jobs", params={"location": "Ottawa"}).json()["jobs"]
    assert [j["company"] for j in ottawa] == ["Beta"]
    by_company = client.get("/api/jobs", params={"sort": "company", "order": "asc"}).json()["jobs"]
    assert [j["company"] for j in by_company] == ["Acme", "Beta"]
    assert client.get("/api/jobs", params={"sort": "salary"}).status_code == 422


def test_job_detail_update_and_404(client):
    client.post("/api/search", json={"sources": ["greenhouse"]})
    wait_for_run(client)
    job_id = client.get("/api/jobs").json()["jobs"][0]["id"]
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["links"][0]["source"] == "greenhouse" and "description" in detail
    updated = client.patch(f"/api/jobs/{job_id}", json={"status": "applied", "notes": "sent Monday"}).json()
    assert updated["status"] == "applied" and updated["notes"] == "sent Monday"
    assert client.patch(f"/api/jobs/{job_id}", json={"status": "bogus"}).status_code == 422
    assert client.get("/api/jobs/9999").status_code == 404


def test_search_conflict_when_running(client):
    client.rt.runner._lock._locked = True  # simulate a run in progress
    try:
        assert client.post("/api/search", json={}).status_code == 409
    finally:
        client.rt.runner._lock._locked = False


def test_preferences_roundtrip_and_validation(client):
    prefs = client.get("/api/preferences").json()
    assert prefs["models"]["scoring"] == "claude-haiku-5-5"
    prefs["excluded_companies"] = ["Acme"]
    result = client.put("/api/preferences", json=prefs).json()
    assert result["preferences"]["excluded_companies"] == ["Acme"] and result["refiltered"] == 0
    prefs["target_score"] = 500
    assert client.put("/api/preferences", json=prefs).status_code == 422


def test_preferences_change_refilters_stored_jobs(client):
    client.post("/api/search", json={"sources": ["greenhouse"]})
    wait_for_run(client)
    prefs = client.get("/api/preferences").json()
    prefs["role_terms"] = ["data scientist"]
    assert client.put("/api/preferences", json=prefs).json()["refiltered"] == 1
    assert [j["title"] for j in client.get("/api/jobs").json()["jobs"]] == ["Data Scientist"]


def test_companies_get_put_and_validation(client):
    companies = client.get("/api/companies").json()
    assert len(companies) >= 40
    saved = client.put("/api/companies", json=companies[:3]).json()
    assert len(saved) == 3 and len(client.get("/api/companies").json()) == 3
    assert client.put("/api/companies", json=[{"name": "X", "ats": "taleo"}]).status_code == 422


def test_profile_uploads(client, tmp_path: Path):
    assert client.get("/api/profile").json()["resume"]["exists"] is False
    r = client.post("/api/profile/resume", files={"file": ("cv.md", b"# Jane Doe\nSQL", "text/markdown")})
    assert r.status_code == 200 and r.json()["resume"]["exists"] is True
    assert r.json()["resume"]["name"] == "my_resume.md"
    assert client.post("/api/profile/resume", files={"file": ("cv.pdf", b"%PDF", "application/pdf")}).status_code == 422
    doc = client.post("/api/profile/documents", files={"file": ("../skills.md", b"Looker", "text/markdown")})
    assert [d["name"] for d in doc.json()["documents"]] == ["skills.md"]  # path stripped
    assert client.post("/api/profile/documents", files={"file": ("answers.md", b"x", "text/markdown")}).status_code == 422
    assert client.delete("/api/profile/documents/skills.md").json()["documents"] == []
    assert client.delete("/api/profile/documents/skills.md").status_code == 404


def test_status_without_resume(client):
    status = client.get("/api/status").json()
    assert status["resume"] is False and status["keys"] == {"jsearch": False, "adzuna": False}
    assert status["quota"]["jsearch"]["budget"] == 180 and status["search_running"] is False
    assert status["last_run"] is None and status["counts"]["relevant"] == 0


def test_root_without_built_ui_or_with(client):
    r = client.get("/")
    assert r.status_code == 200
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_web_api.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_apply_agent.web'`.

- [ ] **Step 3: Implement `web/__init__.py` and `web/app.py`**

`src/job_apply_agent/web/__init__.py`:

```python
"""Local web app (FastAPI). Start it with ``job-agent serve``."""
```

`src/job_apply_agent/web/app.py`:

```python
"""FastAPI backend for the local job app. Binds to 127.0.0.1 only (see cli.run_serve)."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import paths
from ..documents import _find_soffice
from ..envfile import load_env
from ..preferences import load_preferences, merge_defaults, resume_path, save_preferences, validate_preferences
from ..runtime import Runtime, build_runtime, default_http
from ..search.companies import load_companies, save_companies, test_company, validate_companies
from ..search.pipeline import refilter_jobs
from ..search.quota import QuotaGuard, budgets_from_prefs
from ..tailor import auth_warning
from ..timeutil import iso

STATIC_DIR = Path(__file__).with_name("static")
RESUME_SUFFIXES = {".docx", ".md", ".txt"}
PROFILE_SUFFIXES = {".docx", ".md", ".markdown", ".txt"}
Status = Literal["new", "saved", "applied", "interview", "offer", "rejected"]


class JobUpdate(BaseModel):
    status: Status | None = None
    notes: str | None = None


class SearchRequest(BaseModel):
    sources: list[str] | None = None


def create_app(runtime: Runtime | None = None, *, start_scheduler: bool = True) -> FastAPI:
    rt = runtime or build_runtime()
    background: set[asyncio.Task] = set()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        task = asyncio.create_task(rt.scheduler.run_forever()) if start_scheduler else None
        yield
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="job-apply-agent", lifespan=lifespan)
    app.state.runtime = rt

    def now() -> str:
        return iso(rt.now())

    def keep(task: asyncio.Task) -> None:
        background.add(task)
        task.add_done_callback(lambda t: (background.discard(t), t.cancelled() or t.exception()))

    # --- jobs --------------------------------------------------------------------------

    @app.get("/api/jobs")
    def list_jobs(
        tab: Literal["new", "all"] = "all",
        sort: Literal["score", "posted", "company", "title"] = "score",
        order: Literal["asc", "desc"] = "desc",
        role: str | None = None,
        location: str | None = None,
        source: str | None = None,
        status: Status | None = None,
        min_score: int | None = None,
        include_closed: bool = False,
        hide_done: bool = False,
    ) -> dict[str, Any]:
        jobs = rt.db.list_jobs(now=now(), tab=tab, sort=sort, order=order, role=role, location=location,
                               source=source, status=status, min_score=min_score, include_closed=include_closed,
                               hide_done=hide_done)
        return {"jobs": jobs, "counts": rt.db.counts(now())}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: int) -> dict[str, Any]:
        job = rt.db.get_job(job_id)
        if job is None:
            raise HTTPException(404, "Job not found.")
        return job

    @app.patch("/api/jobs/{job_id}")
    def update_job(job_id: int, body: JobUpdate) -> dict[str, Any]:
        fields = body.model_dump(exclude_none=True)
        job = rt.db.update_job(job_id, **fields)
        if job is None:
            raise HTTPException(404, "Job not found.")
        return job

    # --- search runs -------------------------------------------------------------------

    @app.post("/api/search", status_code=202)
    async def start_search(body: SearchRequest | None = None) -> dict[str, bool]:
        if rt.runner.running:
            raise HTTPException(409, "A search is already running.")
        sources = body.sources if body else None
        keep(asyncio.create_task(rt.runner.run(trigger="manual", sources=sources)))
        await asyncio.sleep(0)  # let the run take the lock before we answer
        return {"started": True}

    @app.get("/api/runs")
    def list_runs(limit: int = 10) -> list[dict[str, Any]]:
        return rt.db.list_runs(max(1, min(limit, 100)))

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: int) -> dict[str, Any]:
        run = rt.db.get_run(run_id)
        if run is None:
            raise HTTPException(404, "Run not found.")
        return run

    @app.get("/api/events")
    async def events(request: Request) -> StreamingResponse:
        queue = rt.events.subscribe()

        async def stream():
            try:
                yield "retry: 3000\n\n"
                while not await request.is_disconnected():
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"
                        continue
                    yield f"data: {json.dumps(event)}\n\n"
            finally:
                rt.events.unsubscribe(queue)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # --- settings ------------------------------------------------------------------------

    @app.get("/api/preferences")
    def get_preferences() -> dict[str, Any]:
        return load_preferences()

    @app.put("/api/preferences")
    def put_preferences(body: dict[str, Any]) -> dict[str, Any]:
        try:
            prefs = validate_preferences(merge_defaults(body))
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise HTTPException(422, str(exc)) from None
        old = load_preferences()
        save_preferences(prefs)
        gate_keys = ("role_terms", "locations", "excluded_companies")
        refiltered = refilter_jobs(rt.db, prefs) if any(old[k] != prefs[k] for k in gate_keys) else 0
        return {"preferences": prefs, "refiltered": refiltered}

    @app.get("/api/companies")
    def get_companies() -> list[dict[str, Any]]:
        return load_companies()

    @app.put("/api/companies")
    def put_companies(body: list[dict[str, Any]]) -> list[dict[str, Any]]:
        try:
            return save_companies(body)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post("/api/companies/test")
    async def check_company(body: dict[str, Any]) -> dict[str, Any]:
        try:
            validate_companies([body])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return await test_company(body, default_http())

    # --- profile -------------------------------------------------------------------------

    def profile_info() -> dict[str, Any]:
        resume = resume_path(load_preferences())
        folder = paths.profile_dir()
        documents = [
            {"name": p.name, "size": p.stat().st_size}
            for p in sorted(folder.iterdir())
            if p.is_file() and p.suffix.lower() in PROFILE_SUFFIXES
        ] if folder.is_dir() else []
        return {"resume": {"path": str(resume), "name": resume.name, "exists": resume.is_file()},
                "documents": documents}

    @app.get("/api/profile")
    def get_profile() -> dict[str, Any]:
        return profile_info()

    @app.post("/api/profile/resume")
    async def upload_resume(file: UploadFile) -> dict[str, Any]:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in RESUME_SUFFIXES:
            raise HTTPException(422, "Upload your resume as .docx, .md or .txt.")
        target = paths.data_dir() / f"my_resume{suffix}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(await file.read())
        prefs = load_preferences()
        prefs["resume_path"] = str(target)
        save_preferences(prefs)
        return profile_info()

    @app.post("/api/profile/documents")
    async def upload_document(file: UploadFile) -> dict[str, Any]:
        name = Path(file.filename or "").name
        if Path(name).suffix.lower() not in PROFILE_SUFFIXES:
            raise HTTPException(422, "Profile documents must be .docx, .md or .txt.")
        if name.lower() == "answers.md":
            raise HTTPException(422, "answers.md is managed by the app; pick another file name.")
        folder = paths.profile_dir()
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(await file.read())
        return profile_info()

    @app.delete("/api/profile/documents/{name}")
    def delete_document(name: str) -> dict[str, Any]:
        target = paths.profile_dir() / Path(name).name
        if not target.is_file():
            raise HTTPException(404, "Document not found.")
        target.unlink()
        return profile_info()

    # --- status ----------------------------------------------------------------------------

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        prefs = load_preferences()
        env = load_env()
        runs = rt.db.list_runs(1)
        return {
            "resume": resume_path(prefs).is_file(),
            "auth_warning": auth_warning(),
            "keys": {"jsearch": bool(env.get("JSEARCH_API_KEY")),
                     "adzuna": bool(env.get("ADZUNA_APP_ID") and env.get("ADZUNA_APP_KEY"))},
            "libreoffice": _find_soffice() is not None,
            "quota": QuotaGuard(rt.db, budgets_from_prefs(prefs), rt.now).usage(),
            "search_running": rt.runner.running,
            "schedule_enabled": bool(prefs["schedule"]["enabled"]),
            "last_run": runs[0] if runs else None,
            "counts": rt.db.counts(now()),
        }

    # --- UI ------------------------------------------------------------------------------

    if (STATIC_DIR / "index.html").is_file():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
    else:

        @app.get("/")
        def no_ui() -> dict[str, str]:
            return {"message": "The UI isn't built yet. Run: cd frontend && npm install && npm run build"}

    return app
```

`test_search_conflict_when_running` sets the private `_locked` flag of `asyncio.Lock`; this works on CPython 3.10–3.13. If it ever breaks, replace it with a source that waits on an `asyncio.Event`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_web_api.py -q && .venv/bin/ruff check src tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/job_apply_agent/web tests/test_web_api.py
git commit -m "feat: add FastAPI backend for jobs, search runs, settings and profile

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: Tailoring from the browser

**Files:**
- Create: `src/job_apply_agent/tailor_sessions.py`
- Modify: `src/job_apply_agent/runtime.py` (add `tailor` to `Runtime`), `src/job_apply_agent/web/app.py` (tailor + files routes)
- Test: `tests/test_tailor_sessions.py`

**Interfaces:**
- Consumes: `run_tailor_flow`, `TailorRequest`, `TailorOutcome` (Task 3); `fetch_job`, `JobFetchError`, `JobPosting`; `Database.get_job/update_job`; `EventBus`.
- Produces:
  - `tailor_sessions.MissingResume`, `tailor_sessions.NotWaiting`.
  - `tailor_sessions.TailorSession` with `to_dict() -> {"id", "job_id", "state": "running"|"waiting"|"done"|"error", "questions", "progress", "result", "error"}`; `result = {"match_score", "job_title", "company", "missing_keywords", "files" (paths relative to OUTPUT_DIR), "warnings", "folder"}`.
  - `tailor_sessions.TailorManager(db, events, *, load_prefs, answer_timeout=1800, flow=run_tailor_flow, fetch=fetch_job)` with `sessions: dict[str, TailorSession]`, `start(job_id) -> TailorSession` (raises `KeyError`, `MissingResume`), `answer(session_id, answers: list[tuple[str, str]])` (raises `KeyError`, `NotWaiting`), `async wait(session_id)` (test helper: awaits the task).
  - `Runtime.tailor: TailorManager`.
  - Routes: `POST /api/jobs/{id}/tailor` → 202 session; `GET /api/tailor/{sid}`; `POST /api/tailor/{sid}/answers` body `{"answers": [{"question", "answer"}]}`; `GET /api/files/{path}` (only under OUTPUT_DIR).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tailor_sessions.py`:

```python
import asyncio
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from job_apply_agent.db import Database
from job_apply_agent.jobs import JobFetchError, JobPosting
from job_apply_agent.preferences import merge_defaults
from job_apply_agent.runtime import build_runtime
from job_apply_agent.search.events import EventBus
from job_apply_agent.tailor import TailoredResume
from job_apply_agent.tailor_flow import TailorOutcome
from job_apply_agent.tailor_sessions import MissingResume, NotWaiting, TailorManager
from job_apply_agent.web.app import create_app
from test_tailor import STRUCTURED


@pytest.fixture
def env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("JOB_AGENT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("JOB_AGENT_OUTPUT_DIR", str(tmp_path / "output"))
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "my_resume.md").write_text("# Alex\nSQL", encoding="utf-8")
    prefs = merge_defaults({"resume_path": str(tmp_path / "data" / "my_resume.md")})
    return tmp_path, prefs


def add_job(db: Database, description="Full posting " * 40, partial=False) -> int:
    job_id, _ = db.upsert_posting(
        JobPosting(url="https://jobs.example/1", title="Data Analyst", company="Acme", location="Toronto",
                   description=description, description_is_partial=partial, source="adzuna", external_id="1"),
        dedupe_key="k", canonical_url="jobs.example/1", relevant=True, location_label="Toronto/GTA",
        run_id=None, now="2026-11-09T12:00:00+00:00")
    return job_id


def fake_flow(tmp_path: Path, asks: list):
    async def flow(req, *, ask=None, progress=None, status=None):
        status("Round 1: tailoring")
        progress("Reading the posting")
        answers = await ask(["Used dbt?"])
        asks.append((req, answers))
        folder = tmp_path / "output" / "2026-11-09_Acme_Data-Analyst"
        folder.mkdir(parents=True)
        md = folder / "Alex_Resume_Acme.md"
        md.write_text("# Alex", encoding="utf-8")
        tailored = TailoredResume.from_structured_output({**STRUCTURED, "company": "Acme", "job_title": "Data Analyst"})
        return TailorOutcome(tailored=tailored, folder=folder, files=[md], warnings=["PDF skipped: no LibreOffice"],
                             rounds=2)
    return flow


async def test_session_asks_waits_for_answers_and_finishes(env):
    tmp_path, prefs = env
    db = Database(":memory:")
    job_id = add_job(db)
    asks = []
    manager = TailorManager(db, EventBus(), load_prefs=lambda: prefs, flow=fake_flow(tmp_path, asks))
    session = manager.start(job_id)
    for _ in range(20):
        await asyncio.sleep(0)
        if session.state == "waiting":
            break
    assert session.state == "waiting" and session.questions == ["Used dbt?"]
    assert session.progress[:2] == ["Round 1: tailoring", "Reading the posting"]
    manager.answer(session.id, [("Used dbt?", "Yes, 6 months"), ("Other", "  ")])
    await manager.wait(session.id)
    assert session.state == "done"
    req, answers = asks[0]
    assert answers == [("Used dbt?", "Yes, 6 months")]  # blank answers dropped
    assert req.job_text.startswith("Source: https://jobs.example/1") and req.job_url is None
    assert session.result["files"] == ["2026-11-09_Acme_Data-Analyst/Alex_Resume_Acme.md"]
    assert db.get_job(job_id)["tailored_folder"] == "2026-11-09_Acme_Data-Analyst"
    with pytest.raises(NotWaiting):
        manager.answer(session.id, [])


async def test_answer_timeout_continues_with_no_answers(env):
    tmp_path, prefs = env
    db = Database(":memory:")
    asks = []
    manager = TailorManager(db, EventBus(), load_prefs=lambda: prefs, answer_timeout=0.01,
                            flow=fake_flow(tmp_path, asks))
    session = manager.start(add_job(db))
    await manager.wait(session.id)
    assert session.state == "done" and asks[0][1] == []


async def test_partial_description_fetches_full_posting_or_falls_back_to_url(env):
    tmp_path, prefs = env
    db = Database(":memory:")
    job_id = add_job(db, description="snippet", partial=True)
    asks = []

    def fetch_ok(url):
        return JobPosting(url=url, title="Data Analyst", company="Acme", description="The full text " * 50)

    manager = TailorManager(db, EventBus(), load_prefs=lambda: prefs, answer_timeout=0.01,
                            flow=fake_flow(tmp_path, asks), fetch=fetch_ok)
    await manager.wait(manager.start(job_id).id)
    assert "The full text" in asks[0][0].job_text

    def fetch_fail(url):
        raise JobFetchError("blocked")

    db2 = Database(":memory:")
    job2 = add_job(db2, description="", partial=True)
    asks2 = []
    (tmp_path / "output").rename(tmp_path / "output_old")
    manager2 = TailorManager(db2, EventBus(), load_prefs=lambda: prefs, answer_timeout=0.01,
                             flow=fake_flow(tmp_path, asks2), fetch=fetch_fail)
    await manager2.wait(manager2.start(job2).id)
    assert asks2[0][0].job_text is None and asks2[0][0].job_url == "https://jobs.example/1"


async def test_errors_and_missing_resume(env):
    tmp_path, prefs = env
    db = Database(":memory:")

    async def broken(req, **_kw):
        raise RuntimeError("agent failed")

    manager = TailorManager(db, EventBus(), load_prefs=lambda: prefs, flow=broken)
    session = manager.start(add_job(db))
    await manager.wait(session.id)
    assert session.state == "error" and session.error == "agent failed"
    with pytest.raises(KeyError):
        manager.start(999)
    no_resume = TailorManager(db, EventBus(), load_prefs=lambda: merge_defaults({"resume_path": "/nope.docx"}))
    with pytest.raises(MissingResume):
        no_resume.start(1)


def test_tailor_routes_and_file_download(env):
    tmp_path, prefs = env
    from job_apply_agent.preferences import save_preferences

    save_preferences(prefs)
    rt = build_runtime(db=Database(":memory:"), sources={})
    asks = []
    rt.tailor.flow = fake_flow(tmp_path, asks)
    rt.tailor.answer_timeout = 5
    job_id = add_job(rt.db)
    with TestClient(create_app(rt, start_scheduler=False)) as client:
        started = client.post(f"/api/jobs/{job_id}/tailor")
        assert started.status_code == 202
        sid = started.json()["id"]
        for _ in range(100):
            state = client.get(f"/api/tailor/{sid}").json()
            if state["state"] == "waiting":
                break
            time.sleep(0.02)
        assert state["questions"] == ["Used dbt?"]
        client.post(f"/api/tailor/{sid}/answers", json={"answers": [{"question": "Used dbt?", "answer": "Yes"}]})
        for _ in range(100):
            state = client.get(f"/api/tailor/{sid}").json()
            if state["state"] == "done":
                break
            time.sleep(0.02)
        assert state["state"] == "done"
        path = state["result"]["files"][0]
        assert client.get(f"/api/files/{path}").text == "# Alex"
        assert client.get("/api/files/../data/my_resume.md").status_code == 404
        assert client.get("/api/tailor/nope").status_code == 404
        assert client.post("/api/jobs/999/tailor").status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_tailor_sessions.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_apply_agent.tailor_sessions'`.

- [ ] **Step 3: Implement `tailor_sessions.py`**

```python
"""Resume tailoring started from the browser. The agent's questions wait for answers from the UI."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import paths
from .db import Database
from .jobs import JobFetchError, JobPosting, fetch_job
from .preferences import resume_path
from .search.events import EventBus
from .tailor_flow import TailorRequest, run_tailor_flow

MIN_FULL_DESCRIPTION = 300


class MissingResume(RuntimeError):
    pass


class NotWaiting(RuntimeError):
    pass


@dataclass
class TailorSession:
    id: str
    job_id: int
    state: str = "running"  # running | waiting | done | error
    questions: list[str] = field(default_factory=list)
    progress: list[str] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    answers_future: asyncio.Future | None = None
    task: asyncio.Task | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "job_id": self.job_id, "state": self.state, "questions": self.questions,
                "progress": self.progress[-20:], "result": self.result, "error": self.error}


class TailorManager:
    def __init__(self, db: Database, events: EventBus, *, load_prefs: Callable[[], dict[str, Any]],
                 answer_timeout: float = 1800, flow=run_tailor_flow, fetch=fetch_job):
        self.db = db
        self.events = events
        self.load_prefs = load_prefs
        self.answer_timeout = answer_timeout
        self.flow = flow
        self.fetch = fetch
        self.sessions: dict[str, TailorSession] = {}

    def start(self, job_id: int) -> TailorSession:
        job = self.db.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        prefs = self.load_prefs()
        resume = resume_path(prefs)
        if not resume.is_file():
            raise MissingResume("Add your master resume in Settings first.")
        session = TailorSession(id=uuid.uuid4().hex[:12], job_id=job_id)
        self.sessions[session.id] = session
        session.task = asyncio.create_task(self._run(session, job, prefs, resume))
        return session

    async def wait(self, session_id: str) -> None:
        task = self.sessions[session_id].task
        if task:
            await task

    def answer(self, session_id: str, answers: list[tuple[str, str]]) -> None:
        session = self.sessions[session_id]
        if session.state != "waiting" or session.answers_future is None or session.answers_future.done():
            raise NotWaiting("This tailoring run isn't waiting for answers.")
        session.answers_future.set_result([(q, a.strip()) for q, a in answers if a and a.strip()])

    # --- internals -------------------------------------------------------------------------

    def _publish(self, session: TailorSession, kind: str) -> None:
        self.events.publish({"type": f"tailor.{kind}", "session": session.to_dict()})

    def _note(self, session: TailorSession, message: str) -> None:
        session.progress.append(message)
        del session.progress[:-50]
        self._publish(session, "progress")

    async def _ask(self, session: TailorSession, questions: list[str]) -> list[tuple[str, str]]:
        session.questions = list(questions)
        session.state = "waiting"
        session.answers_future = asyncio.get_running_loop().create_future()
        self._publish(session, "questions")
        try:
            answers = await asyncio.wait_for(session.answers_future, self.answer_timeout)
        except asyncio.TimeoutError:
            answers = []
            self._note(session, "No answers within the time limit; finishing with the current version.")
        session.state, session.questions, session.answers_future = "running", [], None
        return answers

    async def _job_input(self, job: dict[str, Any]) -> tuple[str | None, str | None]:
        url = job["links"][0]["url"] if job["links"] else ""
        posting = JobPosting(url=url, title=job["title"], company=job["company"], location=job["location"],
                             description=job["description"])
        if not job["description_is_partial"] and len(job["description"]) >= MIN_FULL_DESCRIPTION:
            return posting.to_text(), None
        try:
            full = await asyncio.to_thread(self.fetch, url)
            return full.to_text(), None
        except (JobFetchError, ValueError, OSError):
            if job["description"]:
                return posting.to_text(), None
            return None, url or None

    async def _run(self, session: TailorSession, job: dict[str, Any], prefs: dict[str, Any], resume) -> None:
        try:
            job_text, job_url = await self._job_input(job)
            if not job_text and not job_url:
                raise RuntimeError("This job has no description or link to tailor against.")
            out_dir = paths.output_dir()
            req = TailorRequest(
                resume_path=resume, job_text=job_text, job_url=job_url, profile_dir=paths.profile_dir(),
                target_score=prefs["target_score"], max_rounds=3, model=prefs["models"]["tailoring"],
                formats=["md", "docx", "pdf"], out_dir=out_dir,
            )
            outcome = await self.flow(
                req,
                ask=lambda questions: self._ask(session, questions),
                progress=lambda message: self._note(session, message),
                status=lambda message: self._note(session, message),
            )
            root = out_dir.resolve()
            folder = os.path.relpath(outcome.folder.resolve(), root).replace(os.sep, "/")
            session.result = {
                "match_score": outcome.tailored.match_score,
                "job_title": outcome.tailored.job_title,
                "company": outcome.tailored.company,
                "missing_keywords": outcome.tailored.missing_keywords,
                "files": [os.path.relpath(p.resolve(), root).replace(os.sep, "/") for p in outcome.files],
                "warnings": outcome.warnings,
                "folder": folder,
            }
            session.state = "done"
            self.db.update_job(session.job_id, tailored_folder=folder)
            self._publish(session, "done")
        except Exception as exc:  # noqa: BLE001 - shown in the job panel
            session.state = "error"
            session.error = str(exc) or exc.__class__.__name__
            self._publish(session, "error")
```

- [ ] **Step 4: Add the tailor manager to `Runtime`**

In `src/job_apply_agent/runtime.py`: import `from .tailor_sessions import TailorManager`, add the field `tailor: TailorManager` to `Runtime` (after `scheduler`), and in `build_runtime` create it before returning:

```python
    tailor = TailorManager(db, events, load_prefs=load_preferences)
    return Runtime(db=db, events=events, runner=runner, scheduler=scheduler, tailor=tailor, now=now_fn)
```

- [ ] **Step 5: Add tailor and file routes to `web/app.py`**

Add the imports `from ..tailor_sessions import MissingResume, NotWaiting`, and this model near the others:

```python
class Answer(BaseModel):
    question: str
    answer: str


class AnswersBody(BaseModel):
    answers: list[Answer]
```

Add these routes inside `create_app`, before the `# --- UI ---` block:

```python
    # --- tailoring -------------------------------------------------------------------------

    @app.post("/api/jobs/{job_id}/tailor", status_code=202)
    async def start_tailor(job_id: int) -> dict[str, Any]:
        try:
            session = rt.tailor.start(job_id)
        except KeyError:
            raise HTTPException(404, "Job not found.") from None
        except MissingResume as exc:
            raise HTTPException(409, str(exc)) from None
        return session.to_dict()

    @app.get("/api/tailor/{session_id}")
    def get_tailor(session_id: str) -> dict[str, Any]:
        session = rt.tailor.sessions.get(session_id)
        if session is None:
            raise HTTPException(404, "Tailoring run not found.")
        return session.to_dict()

    @app.post("/api/tailor/{session_id}/answers")
    async def answer_tailor(session_id: str, body: AnswersBody) -> dict[str, Any]:
        try:
            rt.tailor.answer(session_id, [(a.question, a.answer) for a in body.answers])
        except KeyError:
            raise HTTPException(404, "Tailoring run not found.") from None
        except NotWaiting as exc:
            raise HTTPException(409, str(exc)) from None
        await asyncio.sleep(0)
        return rt.tailor.sessions[session_id].to_dict()

    @app.get("/api/files/{file_path:path}")
    def download(file_path: str) -> FileResponse:
        root = paths.output_dir().resolve()
        target = (root / file_path).resolve()
        if root not in target.parents or not target.is_file():
            raise HTTPException(404, "File not found.")
        return FileResponse(target, filename=target.name)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check src tests`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/job_apply_agent/tailor_sessions.py src/job_apply_agent/runtime.py src/job_apply_agent/web/app.py tests/test_tailor_sessions.py
git commit -m "feat: run resume tailoring from the browser with in-app questions

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 16: `job-agent serve`

**Files:**
- Modify: `src/job_apply_agent/cli.py`
- Test: `tests/test_cli_serve.py`

**Interfaces:**
- Consumes: `create_app` (Task 14).
- Produces: `job-agent serve [--port 8000] [--no-browser] [--no-schedule]`; `cli.run_serve(args) -> int`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_serve.py`:

```python
from job_apply_agent import cli


def test_serve_binds_localhost_and_can_skip_browser(monkeypatch):
    calls = {}

    def fake_run(app, host, port, log_level):
        calls.update(host=host, port=port, app=app)

    monkeypatch.setattr("uvicorn.run", fake_run)
    monkeypatch.setattr("job_apply_agent.web.app.create_app", lambda start_scheduler=True: ("app", start_scheduler))
    opened = []
    monkeypatch.setattr("webbrowser.open", opened.append)
    assert cli.main(["serve", "--port", "8123", "--no-browser", "--no-schedule"]) == 0
    assert calls == {"host": "127.0.0.1", "port": 8123, "app": ("app", False)}
    assert opened == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_cli_serve.py -q`
Expected: FAIL (`invalid choice: 'serve'`, SystemExit).

- [ ] **Step 3: Add the `serve` command**

In `build_parser`, before `return parser`:

```python
    sv = sub.add_parser("serve", help="Open the job app in your browser (http://127.0.0.1:8000).")
    sv.add_argument("--port", type=int, default=8000, help="Port (default: 8000).")
    sv.add_argument("--no-browser", action="store_true", help="Don't open the browser automatically.")
    sv.add_argument("--no-schedule", action="store_true", help="Don't run scheduled searches while the app is open.")
```

Add above `main`:

```python
def run_serve(args: argparse.Namespace) -> int:
    import threading
    import webbrowser

    import uvicorn

    from .web import app as web_app

    application = web_app.create_app(start_scheduler=not args.no_schedule)
    url = f"http://127.0.0.1:{args.port}"
    print(f"Job app running at {url} (press Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    uvicorn.run(application, host="127.0.0.1", port=args.port, log_level="info")
    return 0
```

In `main`, add:

```python
        if args.command == "serve":
            return run_serve(args)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check src tests`
Expected: PASS.

- [ ] **Step 5: Smoke-test the real server (manual)**

```bash
JOB_AGENT_DATA_DIR=/tmp/claude-1000/-home-mohammad/ac20046b-bcd1-4604-93a0-54df1829f833/scratchpad/smoke-data \
  .venv/bin/job-agent serve --no-browser --no-schedule --port 8765 &
sleep 3
curl -s http://127.0.0.1:8765/api/status
curl -s http://127.0.0.1:8765/
kill %1
```
Expected: status JSON with `"resume": false`; `/` returns the "UI isn't built yet" hint.

- [ ] **Step 6: Commit**

```bash
git add src/job_apply_agent/cli.py tests/test_cli_serve.py
git commit -m "feat: add job-agent serve to start the local web app

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 17: Frontend scaffold, typed API client, helpers, styles, CI

**Files:**
- Create: `frontend/package.json`, `frontend/tsconfig.json`, `frontend/vite.config.ts`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/App.tsx` (placeholder, replaced in Task 18), `frontend/src/types.ts`, `frontend/src/api.ts`, `frontend/src/lib/format.ts`, `frontend/src/lib/runs.ts`, `frontend/src/styles.css`
- Test: `frontend/src/lib/format.test.ts`, `frontend/src/lib/runs.test.ts`, `frontend/src/api.test.ts`
- Modify: `.github/workflows/ci.yml` (frontend job)

**Interfaces:**
- Consumes: the JSON shapes listed in Tasks 4, 12, 14, 15.
- Produces (used by Tasks 18–19):
  - `types.ts`: `JobStatus`, `STATUSES`, `SortKey`, `SortOrder`, `SortState`, `JobRow`, `JobLink`, `JobDetail`, `Counts`, `SourceStat`, `Run`, `TailorResult`, `TailorState`, `SourcePrefs`, `Preferences`, `Ats`, `Company`, `Profile`, `QuotaInfo`, `Status`, `AppEvent`.
  - `api.ts`: `ApiError`, `JobQuery`, `jobsQueryString(q)`, `fileUrl(path)`, and `api.{jobs, job, updateJob, startSearch, runs, status, startTailor, tailor, answer, preferences, savePreferences, companies, saveCompanies, testCompany, profile, uploadResume, uploadDocument, deleteDocument}`.
  - `lib/format.ts`: `scoreBand(score)`, `relativeTime(iso, now?)`, `SOURCE_LABELS`, `sourceLabel(name)`, `nextSort(state, key)`, `describeStat(name, stat)`, `newJobsInRun(run)`.
  - `lib/runs.ts`: `LiveRun`, `emptyRun()`, `applyRunEvent(prev, event)`.

- [ ] **Step 1: Create the project files**

`frontend/package.json`:

```json
{
  "name": "job-apply-agent-ui",
  "private": true,
  "version": "0.2.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "build": "tsc --noEmit && vite build"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.4",
    "typescript": "~5.6.3",
    "vite": "^5.4.11",
    "vitest": "^2.1.8"
  }
}
```

`frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "skipLibCheck": true,
    "isolatedModules": true,
    "noEmit": true,
    "types": ["vite/client"]
  },
  "include": ["src", "vite.config.ts"]
}
```

`frontend/vite.config.ts`:

```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// `npm run build` writes into the Python package so `job-agent serve` can serve the UI without Node.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "../src/job_apply_agent/web/static", emptyOutDir: true },
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
  test: { environment: "node" },
});
```

`frontend/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Job Agent</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`frontend/src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

`frontend/src/App.tsx` (placeholder until Task 18):

```tsx
export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">Job Agent</div>
      </header>
    </div>
  );
}
```

- [ ] **Step 2: Create `src/types.ts`**

```ts
export type JobStatus = "new" | "saved" | "applied" | "interview" | "offer" | "rejected";
export const STATUSES: JobStatus[] = ["new", "saved", "applied", "interview", "offer", "rejected"];
export type SortKey = "score" | "posted" | "company" | "title";
export type SortOrder = "asc" | "desc";
export interface SortState {
  sort: SortKey;
  order: SortOrder;
}

export interface JobRow {
  id: number;
  title: string;
  company: string;
  location: string;
  location_label: string;
  remote: boolean | null;
  posted_at: string | null;
  first_seen_at: string;
  last_seen_at: string;
  score: number | null;
  summary: string | null;
  seniority_fit: "under" | "fit" | "over" | null;
  status: JobStatus;
  closed: boolean;
  tailored_folder: string | null;
  sources: string[];
}

export interface JobLink {
  source: string;
  url: string;
}

export interface JobDetail extends JobRow {
  description: string;
  description_is_partial: boolean;
  reasons: string[];
  gaps: string[];
  notes: string;
  employment_type: string;
  links: JobLink[];
}

export interface Counts {
  relevant: number;
  unscored: number;
  new_24h: number;
}

export interface SourceStat {
  status: "running" | "ok" | "partial" | "error" | "skipped" | "limited";
  fetched?: number;
  relevant?: number;
  new?: number;
  warnings?: string[];
  error?: string;
  reason?: string;
  scored?: number;
  failed?: number;
  message?: string;
}

export interface Run {
  id: number;
  started_at: string;
  finished_at: string | null;
  trigger: string;
  sources: Record<string, SourceStat>;
  scored: number;
  error: string | null;
}

export interface TailorResult {
  match_score: number;
  job_title: string;
  company: string;
  missing_keywords: string[];
  files: string[];
  warnings: string[];
  folder: string;
}

export interface TailorState {
  id: string;
  job_id: number;
  state: "running" | "waiting" | "done" | "error";
  questions: string[];
  progress: string[];
  result: TailorResult | null;
  error: string | null;
}

export interface SourcePrefs {
  enabled: boolean;
  interval_hours: number;
  budget?: number;
  budget_period?: "day" | "month";
  [key: string]: unknown;
}

export interface Preferences {
  resume_path: string;
  role_terms: string[];
  locations: { cities: Record<string, string[]>; remote_canada: boolean; include_unknown: boolean };
  excluded_companies: string[];
  sources: Record<string, SourcePrefs>;
  models: { scoring: string; tailoring: string | null };
  scoring: { batch_size: number; concurrency: number };
  target_score: number;
  schedule: { enabled: boolean };
}

export type Ats = "greenhouse" | "lever" | "ashby" | "workday";

export interface Company {
  name: string;
  ats: Ats;
  enabled: boolean;
  board?: string;
  host?: string;
  tenant?: string;
  site?: string;
}

export interface Profile {
  resume: { path: string; name: string; exists: boolean };
  documents: { name: string; size: number }[];
}

export interface QuotaInfo {
  used: number;
  budget: number;
  period: string;
  resets: string;
}

export interface Status {
  resume: boolean;
  auth_warning: string | null;
  keys: { jsearch: boolean; adzuna: boolean };
  libreoffice: boolean;
  quota: Record<string, QuotaInfo>;
  search_running: boolean;
  schedule_enabled: boolean;
  last_run: Run | null;
  counts: Counts;
}

export interface AppEvent {
  type: string;
  [key: string]: unknown;
}
```

- [ ] **Step 3: Write the failing helper tests**

`frontend/src/lib/format.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { Run } from "../types";
import { describeStat, newJobsInRun, nextSort, relativeTime, scoreBand, sourceLabel } from "./format";

describe("format helpers", () => {
  it("bands scores", () => {
    expect(scoreBand(null)).toBe("none");
    expect(scoreBand(75)).toBe("high");
    expect(scoreBand(50)).toBe("mid");
    expect(scoreBand(49)).toBe("low");
  });

  it("formats relative time", () => {
    const now = new Date("2026-11-09T12:00:00Z");
    expect(relativeTime(null, now)).toBe("—");
    expect(relativeTime("2026-11-09T11:59:40Z", now)).toBe("just now");
    expect(relativeTime("2026-11-09T11:15:00Z", now)).toBe("45m ago");
    expect(relativeTime("2026-11-09T07:00:00Z", now)).toBe("5h ago");
    expect(relativeTime("2026-11-06T12:00:00Z", now)).toBe("3d ago");
    expect(relativeTime("not a date", now)).toBe("—");
  });

  it("labels sources", () => {
    expect(sourceLabel("linkedin")).toBe("LinkedIn");
    expect(sourceLabel("scoring")).toBe("Claude scoring");
    expect(sourceLabel("other")).toBe("other");
  });

  it("toggles sort order and picks sensible defaults", () => {
    expect(nextSort({ sort: "score", order: "desc" }, "score")).toEqual({ sort: "score", order: "asc" });
    expect(nextSort({ sort: "score", order: "desc" }, "company")).toEqual({ sort: "company", order: "asc" });
    expect(nextSort({ sort: "company", order: "asc" }, "posted")).toEqual({ sort: "posted", order: "desc" });
  });

  it("describes source stats", () => {
    expect(describeStat("lever", { status: "ok", fetched: 5, relevant: 2, new: 1 })).toBe("5 fetched · 2 relevant · 1 new");
    expect(describeStat("jsearch", { status: "skipped", reason: "no API key" })).toBe("Skipped: no API key");
    expect(describeStat("ashby", { status: "error", error: "boom" })).toBe("Error: boom");
    expect(describeStat("ashby", { status: "partial", fetched: 1, relevant: 1, new: 0, warnings: ["x"] })).toBe(
      "1 fetched · 1 relevant · 0 new · 1 warning(s)",
    );
    expect(describeStat("scoring", { status: "ok", message: "Scored 3 job(s)." })).toBe("Scored 3 job(s).");
  });

  it("counts new jobs in a run", () => {
    const run: Run = {
      id: 1, started_at: "", finished_at: "", trigger: "manual", scored: 0, error: null,
      sources: { lever: { status: "ok", new: 2 }, ashby: { status: "ok", new: 3 }, scoring: { status: "ok" } },
    };
    expect(newJobsInRun(run)).toBe(5);
  });
});
```

`frontend/src/lib/runs.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { applyRunEvent } from "./runs";

describe("applyRunEvent", () => {
  it("tracks a run from start to finish", () => {
    let live = applyRunEvent(null, { type: "run.started", run_id: 7, sources: ["lever", "ashby"] });
    expect(live.running).toBe(true);
    expect(live.sources.lever.status).toBe("running");
    live = applyRunEvent(live, { type: "run.source", source: "lever", stat: { status: "ok", new: 2 } });
    live = applyRunEvent(live, { type: "run.progress", message: "Wealthsimple: 3 matching" });
    live = applyRunEvent(live, { type: "run.scoring", done: 2, total: 4 });
    expect(live.sources.lever.new).toBe(2);
    expect(live.messages).toEqual(["Wealthsimple: 3 matching"]);
    expect(live.scoring).toEqual({ done: 2, total: 4 });
    const run = { id: 7, started_at: "a", finished_at: "b", trigger: "manual", sources: {}, scored: 2, error: null };
    live = applyRunEvent(live, { type: "run.finished", run });
    expect(live.running).toBe(false);
    expect(live.finished).toEqual(run);
  });

  it("ignores unrelated events", () => {
    const live = applyRunEvent(null, { type: "tailor.progress" });
    expect(live.running).toBe(false);
  });
});
```

`frontend/src/api.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { fileUrl, jobsQueryString } from "./api";

describe("api helpers", () => {
  it("builds job queries without empty values", () => {
    const qs = jobsQueryString({ tab: "new", sort: "score", order: "desc", role: undefined, min_score: 70, hide_done: true, include_closed: false });
    expect(qs).toBe("tab=new&sort=score&order=desc&min_score=70&hide_done=true");
  });

  it("encodes file paths segment by segment", () => {
    expect(fileUrl("2026-11-09_Acme/Jane Doe.pdf")).toBe("/api/files/2026-11-09_Acme/Jane%20Doe.pdf");
  });
});
```

- [ ] **Step 4: Install and run to verify the tests fail**

```bash
cd frontend && npm install && npm test
```
Expected: FAIL (`Failed to resolve import "./format"`, `"./runs"`, `"./api"`).

- [ ] **Step 5: Implement `src/lib/format.ts`, `src/lib/runs.ts`, `src/api.ts`**

`frontend/src/lib/format.ts`:

```ts
import type { Run, SortKey, SortState, SourceStat } from "../types";

export type ScoreBand = "high" | "mid" | "low" | "none";

export function scoreBand(score: number | null): ScoreBand {
  if (score === null) return "none";
  if (score >= 75) return "high";
  if (score >= 50) return "mid";
  return "low";
}

export function relativeTime(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const minutes = Math.max(0, Math.round((now.getTime() - then) / 60000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return days < 30 ? `${days}d ago` : new Date(iso).toLocaleDateString();
}

export const SOURCE_LABELS: Record<string, string> = {
  greenhouse: "Greenhouse",
  lever: "Lever",
  ashby: "Ashby",
  workday: "Workday",
  jsearch: "JSearch",
  adzuna: "Adzuna",
  linkedin: "LinkedIn",
};

export function sourceLabel(name: string): string {
  if (name === "scoring") return "Claude scoring";
  return SOURCE_LABELS[name] ?? name;
}

export function nextSort(current: SortState, clicked: SortKey): SortState {
  if (current.sort === clicked) return { sort: clicked, order: current.order === "desc" ? "asc" : "desc" };
  return { sort: clicked, order: clicked === "company" || clicked === "title" ? "asc" : "desc" };
}

export function describeStat(name: string, stat: SourceStat): string {
  if (name === "scoring") return stat.message ?? (stat.status === "running" ? "Scoring…" : "");
  switch (stat.status) {
    case "running":
      return "Searching…";
    case "skipped":
      return `Skipped: ${stat.reason ?? ""}`.trim();
    case "error":
      return `Error: ${stat.error ?? "unknown"}`;
    default: {
      const base = `${stat.fetched ?? 0} fetched · ${stat.relevant ?? 0} relevant · ${stat.new ?? 0} new`;
      return stat.warnings?.length ? `${base} · ${stat.warnings.length} warning(s)` : base;
    }
  }
}

export function newJobsInRun(run: Run): number {
  return Object.entries(run.sources)
    .filter(([name]) => name !== "scoring")
    .reduce((sum, [, stat]) => sum + (stat.new ?? 0), 0);
}
```

`frontend/src/lib/runs.ts`:

```ts
import type { AppEvent, Run, SourceStat } from "../types";

export interface LiveRun {
  runId: number | null;
  running: boolean;
  sources: Record<string, SourceStat>;
  scoring: { done: number; total: number } | null;
  messages: string[];
  finished: Run | null;
}

export const emptyRun = (): LiveRun => ({
  runId: null, running: false, sources: {}, scoring: null, messages: [], finished: null,
});

export function applyRunEvent(prev: LiveRun | null, event: AppEvent): LiveRun {
  const base = prev ?? emptyRun();
  switch (event.type) {
    case "run.started": {
      const names = (event.sources as string[] | undefined) ?? [];
      const sources = Object.fromEntries(names.map((n) => [n, { status: "running" } as SourceStat]));
      return { ...emptyRun(), runId: event.run_id as number, running: true, sources };
    }
    case "run.source":
      return { ...base, sources: { ...base.sources, [event.source as string]: event.stat as SourceStat } };
    case "run.progress":
      return { ...base, messages: [...base.messages, event.message as string].slice(-30) };
    case "run.scoring":
      return { ...base, scoring: { done: event.done as number, total: event.total as number } };
    case "run.finished":
      return { ...base, running: false, finished: event.run as Run };
    default:
      return base;
  }
}
```

`frontend/src/api.ts`:

```ts
import type {
  Company, Counts, JobDetail, JobRow, JobStatus, Preferences, Profile, Run, SortKey, SortOrder, Status, TailorState,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    let message = response.statusText || `HTTP ${response.status}`;
    try {
      const body = await response.json();
      message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      // not JSON; keep the status text
    }
    throw new ApiError(response.status, message);
  }
  return (await response.json()) as T;
}

const sendJson = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

function upload(path: string, file: File): Promise<Profile> {
  const form = new FormData();
  form.append("file", file);
  return request<Profile>(path, { method: "POST", body: form });
}

export interface JobQuery {
  tab: "new" | "all";
  sort: SortKey;
  order: SortOrder;
  role?: string;
  location?: string;
  source?: string;
  status?: string;
  min_score?: number;
  hide_done?: boolean;
  include_closed?: boolean;
}

export function jobsQueryString(query: JobQuery): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === "" || value === false) continue;
    params.set(key, String(value));
  }
  return params.toString();
}

export const fileUrl = (path: string) => `/api/files/${path.split("/").map(encodeURIComponent).join("/")}`;

export const api = {
  jobs: (query: JobQuery) => request<{ jobs: JobRow[]; counts: Counts }>(`/api/jobs?${jobsQueryString(query)}`),
  job: (id: number) => request<JobDetail>(`/api/jobs/${id}`),
  updateJob: (id: number, patch: { status?: JobStatus; notes?: string }) =>
    request<JobDetail>(`/api/jobs/${id}`, sendJson("PATCH", patch)),
  startSearch: (sources?: string[]) =>
    request<{ started: boolean }>("/api/search", sendJson("POST", { sources: sources ?? null })),
  runs: (limit = 10) => request<Run[]>(`/api/runs?limit=${limit}`),
  status: () => request<Status>("/api/status"),
  startTailor: (jobId: number) => request<TailorState>(`/api/jobs/${jobId}/tailor`, { method: "POST" }),
  tailor: (id: string) => request<TailorState>(`/api/tailor/${id}`),
  answer: (id: string, answers: { question: string; answer: string }[]) =>
    request<TailorState>(`/api/tailor/${id}/answers`, sendJson("POST", { answers })),
  preferences: () => request<Preferences>("/api/preferences"),
  savePreferences: (prefs: Preferences) =>
    request<{ preferences: Preferences; refiltered: number }>("/api/preferences", sendJson("PUT", prefs)),
  companies: () => request<Company[]>("/api/companies"),
  saveCompanies: (companies: Company[]) => request<Company[]>("/api/companies", sendJson("PUT", companies)),
  testCompany: (company: Company) =>
    request<{ ok: boolean; jobs?: number; error?: string }>("/api/companies/test", sendJson("POST", company)),
  profile: () => request<Profile>("/api/profile"),
  uploadResume: (file: File) => upload("/api/profile/resume", file),
  uploadDocument: (file: File) => upload("/api/profile/documents", file),
  deleteDocument: (name: string) =>
    request<Profile>(`/api/profile/documents/${encodeURIComponent(name)}`, { method: "DELETE" }),
};
```

- [ ] **Step 6: Add the stylesheet `src/styles.css`**

```css
:root {
  --bg: #f6f7f9;
  --surface: #ffffff;
  --text: #1c2430;
  --muted: #5f6b7a;
  --border: #dde2e8;
  --accent: #2457d6;
  --accent-text: #ffffff;
  --high: #1d7f4e;
  --mid: #a86b00;
  --low: #7a8594;
  --error: #b42318;
  --warn-bg: #fff6e0;
  --info-bg: #eaf1ff;
  --row-hover: #f0f4fb;
  --radius: 8px;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  color: var(--text);
  background: var(--bg);
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #11151b;
    --surface: #181e26;
    --text: #e6eaf0;
    --muted: #98a3b3;
    --border: #2a323d;
    --accent: #6c93ff;
    --accent-text: #0b0f15;
    --high: #4cc38a;
    --mid: #f0b54a;
    --low: #8592a3;
    --error: #ff7a6e;
    --warn-bg: #3a2f14;
    --info-bg: #1b2a47;
    --row-hover: #1f2732;
  }
}

* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); }
button, input, select, textarea { font: inherit; color: inherit; }
button {
  border: 1px solid var(--border); background: var(--surface); border-radius: 6px;
  padding: 6px 12px; cursor: pointer;
}
button:disabled { opacity: 0.6; cursor: default; }
button.primary { background: var(--accent); border-color: var(--accent); color: var(--accent-text); }
button.link-button { border: none; background: none; color: var(--accent); padding: 0 4px; }
button.icon { border: none; background: none; font-size: 22px; line-height: 1; padding: 0 6px; }
input, select, textarea {
  border: 1px solid var(--border); border-radius: 6px; padding: 5px 8px; background: var(--surface);
}
a { color: var(--accent); }

.topbar {
  display: flex; align-items: center; gap: 16px; padding: 10px 20px; background: var(--surface);
  border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 5;
}
.brand { font-weight: 700; font-size: 18px; }
.nav { display: flex; gap: 4px; }
.nav-link { border: none; background: none; color: var(--muted); }
.nav-link.active { color: var(--text); font-weight: 600; }
.topbar-right { margin-left: auto; display: flex; align-items: center; gap: 12px; }
main { padding: 16px 20px; }

.banner { margin: 12px 20px 0; padding: 10px 14px; border-radius: var(--radius); background: var(--info-bg); }
.banner-warn { background: var(--warn-bg); }
.banner-error { background: var(--warn-bg); color: var(--error); display: flex; gap: 12px; align-items: center; }
.error { color: var(--error); }
.muted, .hint { color: var(--muted); font-size: 0.9em; }

.tabs { display: flex; gap: 4px; margin-bottom: 12px; border-bottom: 1px solid var(--border); }
.tab { border: none; border-bottom: 2px solid transparent; border-radius: 0; background: none; padding: 8px 14px; }
.tab.active { border-bottom-color: var(--accent); font-weight: 600; }
.count { margin-left: 6px; padding: 1px 7px; border-radius: 999px; background: var(--row-hover); font-size: 0.85em; }

.filters { display: flex; flex-wrap: wrap; gap: 12px; align-items: end; margin-bottom: 12px; }
.filters label { display: flex; flex-direction: column; gap: 3px; font-size: 0.85em; color: var(--muted); }
.filters input[type="number"] { width: 80px; }
label.check { flex-direction: row; align-items: center; gap: 6px; display: flex; }

.jobs-layout { display: grid; grid-template-columns: 1fr; gap: 16px; }
.jobs-layout.with-panel { grid-template-columns: minmax(0, 1fr) minmax(360px, 42%); }
.jobs-table { width: 100%; border-collapse: collapse; background: var(--surface); border-radius: var(--radius); overflow: hidden; }
.jobs-table th, .jobs-table td { text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
.jobs-table th { font-size: 0.85em; color: var(--muted); font-weight: 600; }
.jobs-table th button.sort { border: none; background: none; padding: 0; color: inherit; font-weight: inherit; }
.jobs-table tbody tr { cursor: pointer; }
.jobs-table tbody tr:hover, .jobs-table tbody tr.selected { background: var(--row-hover); }
.job-title { font-weight: 600; }
.job-summary { color: var(--muted); font-size: 0.88em; margin-top: 2px; }
.chip { display: inline-block; margin: 0 4px 4px 0; padding: 1px 7px; border: 1px solid var(--border); border-radius: 999px; font-size: 0.8em; }
.status { font-size: 0.85em; text-transform: capitalize; }
.empty { color: var(--muted); padding: 24px 0; }

.score { display: inline-block; min-width: 38px; text-align: center; padding: 3px 6px; border-radius: 6px; font-weight: 700; color: #fff; }
.score-high { background: var(--high); }
.score-mid { background: var(--mid); }
.score-low { background: var(--low); }
.score-none { background: transparent; color: var(--muted); border: 1px dashed var(--border); }

.panel, .drawer {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px;
  align-self: start; position: sticky; top: 64px; max-height: calc(100vh - 80px); overflow: auto;
}
.drawer { position: fixed; right: 16px; top: 64px; width: min(440px, calc(100vw - 32px)); z-index: 10; box-shadow: 0 8px 30px rgb(0 0 0 / 0.18); }
.panel-head { display: flex; justify-content: space-between; align-items: start; gap: 8px; }
.panel-head h2 { margin: 0 0 4px; font-size: 1.15em; }
.panel-head p { margin: 0; color: var(--muted); }
.panel-score { display: flex; gap: 10px; align-items: center; margin: 12px 0; }
.panel-score p { margin: 0; }
.panel-row { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin: 12px 0; }
.links { display: flex; flex-wrap: wrap; gap: 10px; }
.notes { display: flex; flex-direction: column; gap: 4px; }
.description { white-space: pre-wrap; line-height: 1.5; font-size: 0.93em; }
.tailor { border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); margin: 14px 0; padding: 10px 0; }
.questions label { display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; }
.progress-log { color: var(--muted); font-size: 0.88em; padding-left: 18px; }
.row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.source-list, .run-list { list-style: none; padding: 0; }
.source-list li { display: flex; justify-content: space-between; gap: 12px; padding: 4px 0; border-bottom: 1px solid var(--border); }
.stat-error { color: var(--error); }
.stat-skipped { color: var(--muted); }

.settings { display: flex; flex-direction: column; gap: 16px; max-width: 980px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; }
.card h2 { margin-top: 0; font-size: 1.1em; }
.field { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }
.sources-table, .companies-table { width: 100%; border-collapse: collapse; }
.sources-table td, .companies-table td, .sources-table th, .companies-table th { padding: 6px; border-bottom: 1px solid var(--border); text-align: left; }
.sources-table input[type="number"] { width: 90px; }
.workday-fields { display: flex; flex-wrap: wrap; gap: 4px; }
.doc-list { padding-left: 18px; }

@media (max-width: 900px) {
  .jobs-layout.with-panel { grid-template-columns: 1fr; }
  .panel { position: static; max-height: none; }
  .jobs-table .hide-narrow { display: none; }
}
```

- [ ] **Step 7: Run tests, typecheck and build**

```bash
cd frontend && npm test && npm run build
```
Expected: 3 test files pass; build writes `src/job_apply_agent/web/static/index.html`.

- [ ] **Step 8: Add the frontend CI job**

Append to `.github/workflows/ci.yml` under `jobs:`:

```yaml
  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm test
      - run: npm run build
```

- [ ] **Step 9: Commit (source only; the build output is committed in Task 20)**

```bash
cd /home/mohammad/job-apply-agent
git add frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/vite.config.ts frontend/index.html frontend/src .github/workflows/ci.yml
git commit -m "feat(ui): scaffold React + TypeScript app with typed API client and helpers

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 18: Jobs page: tabs, ranked table, filters, job panel, tailoring, search drawer

**Files:**
- Create: `frontend/src/hooks/useEvents.ts`, `frontend/src/components/TopBar.tsx`, `FiltersBar.tsx`, `ScoreBadge.tsx`, `JobsTable.tsx`, `JobPanel.tsx`, `TailorPanel.tsx`, `SearchDrawer.tsx`, `JobsPage.tsx`
- Modify: `frontend/src/App.tsx` (real app; Settings page arrives in Task 19, so `App` shows a placeholder for it here)

**Interfaces:**
- Consumes: Task 17 modules; backend routes from Tasks 14–15.
- Produces: `App` with `page` state `"jobs" | "settings"`; `TopBar`, `SetupBanners`, `JobsPage({ refreshKey })`, `SearchDrawer({ live, onClose })`.

- [ ] **Step 1: `src/hooks/useEvents.ts`**

```ts
import { useEffect, useRef } from "react";
import type { AppEvent } from "../types";

/** Subscribe to the backend's server-sent events for the lifetime of the component. */
export function useEvents(onEvent: (event: AppEvent) => void): void {
  const handler = useRef(onEvent);
  handler.current = onEvent;
  useEffect(() => {
    const source = new EventSource("/api/events");
    source.onmessage = (message) => {
      try {
        handler.current(JSON.parse(message.data) as AppEvent);
      } catch {
        // ignore malformed events
      }
    };
    return () => source.close();
  }, []);
}
```

- [ ] **Step 2: `src/components/TopBar.tsx`**

```tsx
import { newJobsInRun, relativeTime } from "../lib/format";
import type { LiveRun } from "../lib/runs";
import type { Status } from "../types";

export type Page = "jobs" | "settings";

interface TopBarProps {
  page: Page;
  onNavigate: (page: Page) => void;
  status: Status | null;
  live: LiveRun | null;
  onSearch: () => void;
  onShowRuns: () => void;
}

export function TopBar({ page, onNavigate, status, live, onSearch, onShowRuns }: TopBarProps) {
  const running = Boolean(live?.running || status?.search_running);
  const last = live?.finished ?? status?.last_run ?? null;
  const summary = running
    ? "Searching…"
    : last
      ? `Last run ${relativeTime(last.finished_at ?? last.started_at)} · ${newJobsInRun(last)} new`
      : "No searches yet";
  return (
    <header className="topbar">
      <div className="brand">Job Agent</div>
      <nav className="nav">
        <button className={page === "jobs" ? "nav-link active" : "nav-link"} onClick={() => onNavigate("jobs")}>
          Jobs
        </button>
        <button className={page === "settings" ? "nav-link active" : "nav-link"} onClick={() => onNavigate("settings")}>
          Settings
        </button>
      </nav>
      <div className="topbar-right">
        <button className="link-button" onClick={onShowRuns}>{summary}</button>
        <button className="primary" onClick={onSearch} disabled={running}>
          {running ? "Searching…" : "Search now"}
        </button>
      </div>
    </header>
  );
}

export function SetupBanners({ status, onOpenSettings }: { status: Status; onOpenSettings: () => void }) {
  return (
    <>
      {!status.resume && (
        <div className="banner">
          Add your master resume so jobs get match scores.{" "}
          <button className="link-button" onClick={onOpenSettings}>Open Settings</button>
        </div>
      )}
      {status.auth_warning && <div className="banner banner-warn">{status.auth_warning}</div>}
    </>
  );
}
```

- [ ] **Step 3: `src/components/FiltersBar.tsx` and `ScoreBadge.tsx`**

`FiltersBar.tsx`:

```tsx
import { SOURCE_LABELS } from "../lib/format";
import { STATUSES } from "../types";

export interface Filters {
  role: string;
  location: string;
  source: string;
  status: string;
  minScore: string;
  hideDone: boolean;
  includeClosed: boolean;
}

export const DEFAULT_FILTERS: Filters = {
  role: "", location: "", source: "", status: "", minScore: "", hideDone: true, includeClosed: false,
};

export function FiltersBar({ value, onChange }: { value: Filters; onChange: (filters: Filters) => void }) {
  const set = <K extends keyof Filters>(key: K, v: Filters[K]) => onChange({ ...value, [key]: v });
  return (
    <div className="filters">
      <label>
        Role
        <select value={value.role} onChange={(e) => set("role", e.target.value)}>
          <option value="">All</option>
          <option value="analyst">Analyst</option>
          <option value="scientist">Scientist</option>
          <option value="engineer">Engineer</option>
        </select>
      </label>
      <label>
        Location
        <select value={value.location} onChange={(e) => set("location", e.target.value)}>
          <option value="">All</option>
          <option value="Toronto/GTA">Toronto/GTA</option>
          <option value="Remote (Canada)">Remote (Canada)</option>
          <option value="Ottawa">Ottawa</option>
          <option value="Unknown">Unknown</option>
        </select>
      </label>
      <label>
        Source
        <select value={value.source} onChange={(e) => set("source", e.target.value)}>
          <option value="">All</option>
          {Object.entries(SOURCE_LABELS).map(([key, label]) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </select>
      </label>
      <label>
        Status
        <select value={value.status} onChange={(e) => set("status", e.target.value)}>
          <option value="">All</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </label>
      <label>
        Min score
        <input type="number" min={0} max={100} value={value.minScore} onChange={(e) => set("minScore", e.target.value)} />
      </label>
      <label className="check">
        <input type="checkbox" checked={value.hideDone} onChange={(e) => set("hideDone", e.target.checked)} />
        Hide applied/rejected
      </label>
      <label className="check">
        <input type="checkbox" checked={value.includeClosed} onChange={(e) => set("includeClosed", e.target.checked)} />
        Show closed
      </label>
    </div>
  );
}
```

`ScoreBadge.tsx`:

```tsx
import { scoreBand } from "../lib/format";

export function ScoreBadge({ score }: { score: number | null }) {
  return (
    <span className={`score score-${scoreBand(score)}`} title={score === null ? "Not scored yet" : `Match ${score}/100`}>
      {score ?? "…"}
    </span>
  );
}
```

- [ ] **Step 4: `src/components/JobsTable.tsx`**

```tsx
import { relativeTime, sourceLabel } from "../lib/format";
import type { JobRow, SortKey, SortState } from "../types";
import { ScoreBadge } from "./ScoreBadge";

const COLUMNS: { key: SortKey | null; label: string; className?: string }[] = [
  { key: "score", label: "Match" },
  { key: "title", label: "Job" },
  { key: "company", label: "Company" },
  { key: null, label: "Location" },
  { key: "posted", label: "Posted" },
  { key: null, label: "Found on", className: "hide-narrow" },
  { key: null, label: "Status", className: "hide-narrow" },
];

interface JobsTableProps {
  jobs: JobRow[];
  sort: SortState;
  onSort: (key: SortKey) => void;
  selectedId: number | null;
  onSelect: (id: number) => void;
  emptyText: string;
}

export function JobsTable({ jobs, sort, onSort, selectedId, onSelect, emptyText }: JobsTableProps) {
  if (jobs.length === 0) return <p className="empty">{emptyText}</p>;
  return (
    <table className="jobs-table">
      <thead>
        <tr>
          {COLUMNS.map((col) => (
            <th
              key={col.label}
              className={col.className}
              aria-sort={col.key && sort.sort === col.key ? (sort.order === "asc" ? "ascending" : "descending") : undefined}
            >
              {col.key ? (
                <button className="sort" onClick={() => onSort(col.key as SortKey)}>
                  {col.label}
                  {sort.sort === col.key ? (sort.order === "asc" ? " ▲" : " ▼") : ""}
                </button>
              ) : (
                col.label
              )}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {jobs.map((job) => (
          <tr
            key={job.id}
            className={job.id === selectedId ? "selected" : undefined}
            onClick={() => onSelect(job.id)}
            onKeyDown={(e) => {
              if (e.key === "Enter") onSelect(job.id);
            }}
            tabIndex={0}
          >
            <td><ScoreBadge score={job.score} /></td>
            <td>
              <div className="job-title">{job.title}</div>
              {job.summary && <div className="job-summary">{job.summary}</div>}
            </td>
            <td>{job.company}</td>
            <td>
              {job.location_label === "Unknown" ? "Location not listed" : job.location_label || job.location}
              {job.remote ? " · Remote" : ""}
            </td>
            <td title={job.posted_at ?? `First seen ${job.first_seen_at}`}>{relativeTime(job.posted_at ?? job.first_seen_at)}</td>
            <td className="hide-narrow">
              {job.sources.map((s) => (
                <span key={s} className="chip">{sourceLabel(s)}</span>
              ))}
            </td>
            <td className="hide-narrow">
              <span className="status">{job.tailored_folder && job.status === "new" ? "resume ready" : job.status}</span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 5: `src/components/TailorPanel.tsx`**

```tsx
import { useEffect, useRef, useState } from "react";
import { api, fileUrl } from "../api";
import type { TailorState } from "../types";

export function TailorPanel({ jobId, onDone }: { jobId: number; onDone: () => void }) {
  const [state, setState] = useState<TailorState | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;
  const sessionId = state?.id;
  const active = state?.state === "running" || state?.state === "waiting";

  useEffect(() => {
    if (!active || !sessionId) return;
    const timer = window.setInterval(() => {
      api
        .tailor(sessionId)
        .then((next) => {
          setState(next);
          if (next.state === "done") onDoneRef.current();
        })
        .catch((e: Error) => setError(e.message));
    }, 1500);
    return () => window.clearInterval(timer);
  }, [active, sessionId]);

  const start = async () => {
    setError(null);
    setAnswers({});
    try {
      setState(await api.startTailor(jobId));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const send = async (skip: boolean) => {
    if (!state) return;
    const list = skip ? [] : state.questions.map((q) => ({ question: q, answer: answers[q] ?? "" }));
    try {
      setState(await api.answer(state.id, list));
      setAnswers({});
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <section className="tailor" aria-live="polite">
      <h3>Tailored resume</h3>
      {error && <p className="error" role="alert">{error}</p>}
      {!state && (
        <button className="primary" onClick={() => void start()}>Tailor my resume for this job</button>
      )}
      {state?.state === "running" && (
        <div>
          <p className="muted">Working… this usually takes a minute or two.</p>
          <ul className="progress-log">
            {state.progress.slice(-5).map((message, i) => (
              <li key={i}>{message}</li>
            ))}
          </ul>
        </div>
      )}
      {state?.state === "waiting" && (
        <form
          className="questions"
          onSubmit={(e) => {
            e.preventDefault();
            void send(false);
          }}
        >
          <p>Answer truthfully to raise the match, or skip. Answers are saved and reused for future jobs.</p>
          {state.questions.map((question) => (
            <label key={question}>
              {question}
              <textarea
                rows={2}
                value={answers[question] ?? ""}
                onChange={(e) => setAnswers({ ...answers, [question]: e.target.value })}
              />
            </label>
          ))}
          <div className="row">
            <button type="submit" className="primary">Send answers</button>
            <button type="button" onClick={() => void send(true)}>Skip</button>
          </div>
        </form>
      )}
      {state?.state === "done" && state.result && (
        <div>
          <p>
            <strong>Match {state.result.match_score}/100</strong> for {state.result.job_title}
            {state.result.company ? ` at ${state.result.company}` : ""}.
          </p>
          {state.result.missing_keywords.length > 0 && (
            <p className="muted">Not in your documents, so not added: {state.result.missing_keywords.join(", ")}</p>
          )}
          <ul>
            {state.result.files.map((file) => (
              <li key={file}>
                <a href={fileUrl(file)} download>{file.split("/").pop()}</a>
              </li>
            ))}
          </ul>
          {state.result.warnings.map((w) => (
            <p key={w} className="muted">{w}</p>
          ))}
          <p className="muted">Review every line before sending: it must be true and sound like you.</p>
          <button onClick={() => void start()}>Tailor again</button>
        </div>
      )}
      {state?.state === "error" && (
        <div>
          <p className="error">{state.error}</p>
          <button onClick={() => void start()}>Try again</button>
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 6: `src/components/JobPanel.tsx`**

```tsx
import { useEffect, useState } from "react";
import { api } from "../api";
import { sourceLabel } from "../lib/format";
import { STATUSES, type JobDetail, type JobStatus } from "../types";
import { ScoreBadge } from "./ScoreBadge";
import { TailorPanel } from "./TailorPanel";

interface JobPanelProps {
  jobId: number;
  onClose: () => void;
  onChanged: () => void;
}

export function JobPanel({ jobId, onClose, onChanged }: JobPanelProps) {
  const [job, setJob] = useState<JobDetail | null>(null);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .job(jobId)
      .then((j) => {
        setJob(j);
        setNotes(j.notes);
      })
      .catch((e: Error) => setError(e.message));
  }, [jobId]);

  const update = async (patch: { status?: JobStatus; notes?: string }) => {
    try {
      setJob(await api.updateJob(jobId, patch));
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  if (!job) {
    return (
      <aside className="panel">
        <button className="icon" aria-label="Close" onClick={onClose}>×</button>
        <p className={error ? "error" : "muted"}>{error ?? "Loading…"}</p>
      </aside>
    );
  }

  return (
    <aside className="panel" aria-label="Job details">
      <header className="panel-head">
        <div>
          <h2>{job.title}</h2>
          <p>{job.company} · {job.location || "Location not listed"}{job.employment_type ? ` · ${job.employment_type}` : ""}</p>
        </div>
        <button className="icon" aria-label="Close" onClick={onClose}>×</button>
      </header>
      {error && <p className="error" role="alert">{error}</p>}

      <div className="panel-score">
        <ScoreBadge score={job.score} />
        <div>
          {job.summary && <p>{job.summary}</p>}
          {job.seniority_fit && job.seniority_fit !== "fit" && (
            <p className="muted">
              Seniority: this job looks {job.seniority_fit === "under" ? "more senior" : "more junior"} than your background.
            </p>
          )}
        </div>
      </div>
      {job.reasons.length > 0 && (
        <>
          <h3>Why you fit</h3>
          <ul>{job.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
        </>
      )}
      {job.gaps.length > 0 && (
        <>
          <h3>Gaps</h3>
          <ul>{job.gaps.map((g) => <li key={g}>{g}</li>)}</ul>
        </>
      )}

      <div className="panel-row">
        <label>
          Status{" "}
          <select value={job.status} onChange={(e) => void update({ status: e.target.value as JobStatus })}>
            {STATUSES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
        <span className="links">
          {job.links.map((link) => (
            <a key={link.url} href={link.url} target="_blank" rel="noreferrer">
              Open on {sourceLabel(link.source)}
            </a>
          ))}
        </span>
      </div>
      <label className="notes">
        Notes
        <textarea
          rows={3}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          onBlur={() => {
            if (notes !== job.notes) void update({ notes });
          }}
        />
      </label>

      <TailorPanel jobId={job.id} onDone={onChanged} />

      <h3>
        Description
        {job.description_is_partial && <span className="muted"> (preview; the full posting is fetched when tailoring)</span>}
      </h3>
      <div className="description">{job.description || "No description available."}</div>
    </aside>
  );
}
```

- [ ] **Step 7: `src/components/SearchDrawer.tsx`**

```tsx
import { useEffect, useState } from "react";
import { api } from "../api";
import { describeStat, relativeTime, sourceLabel } from "../lib/format";
import type { LiveRun } from "../lib/runs";
import type { Run } from "../types";

export function SearchDrawer({ live, onClose }: { live: LiveRun | null; onClose: () => void }) {
  const [runs, setRuns] = useState<Run[]>([]);
  const finishedId = live?.finished?.id;

  useEffect(() => {
    api.runs(5).then(setRuns).catch(() => setRuns([]));
  }, [finishedId]);

  const current = live && (live.running || live.finished) ? live : null;
  return (
    <aside className="drawer" aria-label="Search progress">
      <header className="panel-head">
        <h2>Search</h2>
        <button className="icon" aria-label="Close" onClick={onClose}>×</button>
      </header>
      {current && (
        <section>
          <h3>{current.running ? "Running now" : "Latest run"}</h3>
          <ul className="source-list">
            {Object.entries(current.sources).map(([name, stat]) => (
              <li key={name} className={`stat-${stat.status}`}>
                <span>{sourceLabel(name)}</span>
                <span>{describeStat(name, stat)}</span>
              </li>
            ))}
          </ul>
          {current.running && current.messages.length > 0 && (
            <p className="muted">{current.messages[current.messages.length - 1]}</p>
          )}
          {current.scoring && current.running && <p>Scoring {current.scoring.done}/{current.scoring.total}…</p>}
          {current.finished?.sources.scoring && (
            <p className="muted">{describeStat("scoring", current.finished.sources.scoring)}</p>
          )}
          {current.finished?.error && <p className="error">{current.finished.error}</p>}
        </section>
      )}
      <section>
        <h3>Recent runs</h3>
        {runs.length === 0 && <p className="muted">No searches yet.</p>}
        <ul className="run-list">
          {runs.map((run) => (
            <li key={run.id}>
              <details>
                <summary>
                  {relativeTime(run.started_at)} · {run.trigger} · {run.scored} scored{run.error ? " · failed" : ""}
                </summary>
                <ul>
                  {Object.entries(run.sources).map(([name, stat]) => (
                    <li key={name}>
                      {sourceLabel(name)}: {describeStat(name, stat)}
                      {stat.warnings && stat.warnings.length > 0 && (
                        <ul>{stat.warnings.map((w) => <li key={w} className="muted">{w}</li>)}</ul>
                      )}
                    </li>
                  ))}
                </ul>
              </details>
            </li>
          ))}
        </ul>
      </section>
    </aside>
  );
}
```

- [ ] **Step 8: `src/components/JobsPage.tsx`**

```tsx
import { useEffect, useState } from "react";
import { api, type JobQuery } from "../api";
import { nextSort } from "../lib/format";
import type { Counts, JobRow, SortState } from "../types";
import { DEFAULT_FILTERS, FiltersBar, type Filters } from "./FiltersBar";
import { JobPanel } from "./JobPanel";
import { JobsTable } from "./JobsTable";

export function JobsPage({ refreshKey }: { refreshKey: number }) {
  const [tab, setTab] = useState<"new" | "all">("new");
  const [sort, setSort] = useState<SortState>({ sort: "score", order: "desc" });
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [data, setData] = useState<{ jobs: JobRow[]; counts: Counts } | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [localRefresh, setLocalRefresh] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const query: JobQuery = {
      tab,
      ...sort,
      role: filters.role || undefined,
      location: filters.location || undefined,
      source: filters.source || undefined,
      status: filters.status || undefined,
      min_score: filters.minScore === "" ? undefined : Number(filters.minScore),
      hide_done: filters.hideDone,
      include_closed: filters.includeClosed,
    };
    api
      .jobs(query)
      .then((d) => {
        if (!cancelled) {
          setData(d);
          setError(null);
        }
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [tab, sort, filters, refreshKey, localRefresh]);

  const counts = data?.counts;
  return (
    <div className={selected === null ? "jobs-layout" : "jobs-layout with-panel"}>
      <section>
        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === "new"} className={tab === "new" ? "tab active" : "tab"} onClick={() => setTab("new")}>
            New (24h){counts && <span className="count">{counts.new_24h}</span>}
          </button>
          <button role="tab" aria-selected={tab === "all"} className={tab === "all" ? "tab active" : "tab"} onClick={() => setTab("all")}>
            All jobs{counts && <span className="count">{counts.relevant}</span>}
          </button>
        </div>
        <FiltersBar value={filters} onChange={setFilters} />
        {counts && counts.unscored > 0 && <p className="muted">{counts.unscored} job(s) waiting for a match score.</p>}
        {error && <p className="error" role="alert">{error}</p>}
        {data && (
          <JobsTable
            jobs={data.jobs}
            sort={sort}
            onSort={(key) => setSort((s) => nextSort(s, key))}
            selectedId={selected}
            onSelect={setSelected}
            emptyText={tab === "new" ? "No new jobs in the last 24 hours." : "No jobs yet. Click “Search now” to look for some."}
          />
        )}
      </section>
      {selected !== null && (
        <JobPanel key={selected} jobId={selected} onClose={() => setSelected(null)} onChanged={() => setLocalRefresh((n) => n + 1)} />
      )}
    </div>
  );
}
```

- [ ] **Step 9: Replace `src/App.tsx`**

```tsx
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { JobsPage } from "./components/JobsPage";
import { SearchDrawer } from "./components/SearchDrawer";
import { SetupBanners, TopBar, type Page } from "./components/TopBar";
import { useEvents } from "./hooks/useEvents";
import { applyRunEvent, type LiveRun } from "./lib/runs";
import type { AppEvent, Status } from "./types";

export default function App() {
  const [page, setPage] = useState<Page>("jobs");
  const [status, setStatus] = useState<Status | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [live, setLive] = useState<LiveRun | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const loadStatus = useCallback(() => {
    api.status().then(setStatus).catch((e: Error) => setError(e.message));
  }, []);
  useEffect(loadStatus, [loadStatus]);

  useEvents(
    useCallback(
      (event: AppEvent) => {
        if (!event.type.startsWith("run.")) return;
        setLive((prev) => applyRunEvent(prev, event));
        if (event.type === "run.source" || event.type === "run.finished") setRefreshKey((k) => k + 1);
        if (event.type === "run.finished") loadStatus();
      },
      [loadStatus],
    ),
  );

  const startSearch = async () => {
    setError(null);
    setDrawerOpen(true);
    try {
      await api.startSearch();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="app">
      <TopBar page={page} onNavigate={setPage} status={status} live={live} onSearch={() => void startSearch()} onShowRuns={() => setDrawerOpen(true)} />
      {error && (
        <div className="banner banner-error" role="alert">
          {error}
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}
      {status && <SetupBanners status={status} onOpenSettings={() => setPage("settings")} />}
      <main>
        {page === "jobs" ? <JobsPage refreshKey={refreshKey} /> : <p className="muted">Settings arrive in the next step.</p>}
      </main>
      {drawerOpen && <SearchDrawer live={live} onClose={() => setDrawerOpen(false)} />}
    </div>
  );
}
```

- [ ] **Step 10: Typecheck, test, build**

```bash
cd frontend && npm test && npm run build
```
Expected: tests pass, build succeeds with no TypeScript errors.

- [ ] **Step 11: Check it in a browser against real data**

```bash
cd /home/mohammad/job-apply-agent
export JOB_AGENT_DATA_DIR=/tmp/claude-1000/-home-mohammad/ac20046b-bcd1-4604-93a0-54df1829f833/scratchpad/ui-data
.venv/bin/job-agent search --sources greenhouse,lever,ashby --no-score
.venv/bin/job-agent serve --no-browser --no-schedule --port 8765
```
Open `http://127.0.0.1:8765`. Check: both tabs list jobs; clicking a column header re-sorts; filters narrow the list; clicking a row opens the panel with description and links; status change persists after reload; "Search now" opens the drawer with live per-source rows. Use the `run` skill (or a browser automation tool if available) to capture a screenshot. Stop the server with Ctrl+C.

- [ ] **Step 12: Commit**

```bash
git add frontend/src
git commit -m "feat(ui): jobs page with ranked tabs, filters, job panel, tailoring and search progress

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 19: Settings page

**Files:**
- Create: `frontend/src/components/SettingsPage.tsx`
- Modify: `frontend/src/App.tsx` (render it)

**Interfaces:**
- Consumes: `api.preferences/savePreferences/companies/saveCompanies/testCompany/profile/uploadResume/uploadDocument/deleteDocument/status`.
- Produces: `SettingsPage({ onSaved })`.

- [ ] **Step 1: `src/components/SettingsPage.tsx`**

```tsx
import { useEffect, useState, type ChangeEvent } from "react";
import { api } from "../api";
import { SOURCE_LABELS } from "../lib/format";
import type { Ats, Company, Preferences, Profile, SourcePrefs, Status } from "../types";

const ATS_OPTIONS: Ats[] = ["greenhouse", "lever", "ashby", "workday"];
const toLines = (items: string[]) => items.join("\n");
const fromLines = (text: string) => text.split("\n").map((s) => s.trim()).filter(Boolean);

interface LinesFieldProps {
  label: string;
  value: string[];
  onChange: (value: string[]) => void;
  rows?: number;
  hint?: string;
}

function LinesField({ label, value, onChange, rows = 4, hint }: LinesFieldProps) {
  const [text, setText] = useState(toLines(value));
  useEffect(() => setText(toLines(value)), [value]);
  return (
    <label className="field">
      {label}
      {hint && <span className="hint">{hint}</span>}
      <textarea rows={rows} value={text} onChange={(e) => setText(e.target.value)} onBlur={() => onChange(fromLines(text))} />
    </label>
  );
}

export function SettingsPage({ onSaved }: { onSaved: () => void }) {
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tests, setTests] = useState<Record<number, string>>({});

  useEffect(() => {
    Promise.all([api.preferences(), api.companies(), api.profile(), api.status()])
      .then(([p, c, pr, s]) => {
        setPrefs(p);
        setCompanies(c);
        setProfile(pr);
        setStatus(s);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  if (!prefs || !profile) return <p className={error ? "error" : "muted"}>{error ?? "Loading settings…"}</p>;

  const act = async (action: () => Promise<string>) => {
    setError(null);
    setMessage(null);
    try {
      setMessage(await action());
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const update = (patch: Partial<Preferences>) => setPrefs({ ...prefs, ...patch });
  const updateSource = (name: string, patch: Partial<SourcePrefs>) =>
    setPrefs({ ...prefs, sources: { ...prefs.sources, [name]: { ...prefs.sources[name], ...patch } } });
  const updateCompany = (index: number, patch: Partial<Company>) =>
    setCompanies(companies.map((c, i) => (i === index ? { ...c, ...patch } : c)));
  const testCompany = async (index: number) => {
    setTests((t) => ({ ...t, [index]: "Testing…" }));
    try {
      const result = await api.testCompany(companies[index]);
      setTests((t) => ({ ...t, [index]: result.ok ? `OK: ${result.jobs} open jobs` : `Failed: ${result.error}` }));
    } catch (e) {
      setTests((t) => ({ ...t, [index]: `Failed: ${(e as Error).message}` }));
    }
  };
  const onFile = (handler: (file: File) => Promise<string>) => (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) void act(() => handler(file));
  };

  return (
    <div className="settings">
      {message && <div className="banner">{message}</div>}
      {error && <div className="banner banner-error" role="alert">{error}</div>}

      <section className="card">
        <h2>Resume and profile</h2>
        <p>
          Master resume: {profile.resume.exists ? <strong>{profile.resume.name}</strong> : <em>not added yet</em>}
        </p>
        <label className="field">
          Upload resume (.docx, .md or .txt)
          <input type="file" accept=".docx,.md,.txt" onChange={onFile(async (file) => {
            setProfile(await api.uploadResume(file));
            return "Resume saved. Jobs will be re-scored on the next search.";
          })} />
        </label>
        <h3>Profile documents</h3>
        <p className="hint">Extra details the agent may use: full work history, projects, certificates.</p>
        <ul className="doc-list">
          {profile.documents.map((doc) => (
            <li key={doc.name}>
              {doc.name} <span className="muted">({Math.max(1, Math.ceil(doc.size / 1024))} KB)</span>
              {doc.name !== "answers.md" && (
                <button className="link-button" onClick={() => void act(async () => {
                  setProfile(await api.deleteDocument(doc.name));
                  return `Removed ${doc.name}.`;
                })}>Remove</button>
              )}
            </li>
          ))}
        </ul>
        <label className="field">
          Add a document
          <input type="file" accept=".docx,.md,.markdown,.txt" onChange={onFile(async (file) => {
            setProfile(await api.uploadDocument(file));
            return `Added ${file.name}. Jobs will be re-scored on the next search.`;
          })} />
        </label>
      </section>

      <section className="card">
        <h2>What to look for</h2>
        <LinesField label="Job title terms (one per line)" hint="A job is considered when its title contains one of these."
          value={prefs.role_terms} rows={8} onChange={(v) => update({ role_terms: v })} />
        {Object.entries(prefs.locations.cities).map(([label, cities]) => (
          <LinesField key={label} label={`${label}: city names`} value={cities} rows={3}
            onChange={(v) => update({ locations: { ...prefs.locations, cities: { ...prefs.locations.cities, [label]: v } } })} />
        ))}
        <label className="check">
          <input type="checkbox" checked={prefs.locations.remote_canada}
            onChange={(e) => update({ locations: { ...prefs.locations, remote_canada: e.target.checked } })} />
          Include remote jobs open to Canada
        </label>
        <label className="check">
          <input type="checkbox" checked={prefs.locations.include_unknown}
            onChange={(e) => update({ locations: { ...prefs.locations, include_unknown: e.target.checked } })} />
          Include jobs with no location listed
        </label>
        <LinesField label="Companies to exclude (one per line)" value={prefs.excluded_companies} rows={3}
          onChange={(v) => update({ excluded_companies: v })} />
      </section>

      <section className="card">
        <h2>Sources and schedule</h2>
        <label className="check">
          <input type="checkbox" checked={prefs.schedule.enabled} onChange={(e) => update({ schedule: { enabled: e.target.checked } })} />
          Search automatically while the app is open
        </label>
        <table className="sources-table">
          <thead>
            <tr><th>Source</th><th>On</th><th>Every (hours)</th><th>Free quota</th></tr>
          </thead>
          <tbody>
            {Object.entries(prefs.sources).map(([name, cfg]) => {
              const quota = status?.quota[name];
              const missingKey = (name === "jsearch" && !status?.keys.jsearch) || (name === "adzuna" && !status?.keys.adzuna);
              return (
                <tr key={name}>
                  <td>
                    {SOURCE_LABELS[name] ?? name}
                    {missingKey && <span className="hint"> · no API key in data/.env</span>}
                  </td>
                  <td>
                    <input type="checkbox" aria-label={`Enable ${name}`} checked={cfg.enabled}
                      onChange={(e) => updateSource(name, { enabled: e.target.checked })} />
                  </td>
                  <td>
                    <input type="number" min={0.25} step={0.25} value={cfg.interval_hours}
                      onChange={(e) => updateSource(name, { interval_hours: Number(e.target.value) })} />
                  </td>
                  <td>{quota ? `${quota.used}/${quota.budget} this ${quota.period} (resets ${quota.resets})` : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h2>Claude</h2>
        <label className="field">
          Scoring model
          <input value={prefs.models.scoring} onChange={(e) => update({ models: { ...prefs.models, scoring: e.target.value } })} />
        </label>
        <label className="field">
          Tailoring model (leave empty for your account default)
          <input value={prefs.models.tailoring ?? ""}
            onChange={(e) => update({ models: { ...prefs.models, tailoring: e.target.value || null } })} />
        </label>
        <label className="field">
          Target match score for tailoring
          <input type="number" min={0} max={100} value={prefs.target_score}
            onChange={(e) => update({ target_score: Number(e.target.value) })} />
        </label>
        {status && !status.libreoffice && (
          <p className="hint">LibreOffice isn't installed, so tailored resumes are saved as Word and Markdown (no PDF).</p>
        )}
      </section>

      <div className="row">
        <button className="primary" onClick={() => void act(async () => {
          const result = await api.savePreferences(prefs);
          setPrefs(result.preferences);
          return result.refiltered ? `Saved. ${result.refiltered} job(s) re-checked against the new filters.` : "Saved.";
        })}>Save settings</button>
      </div>

      <section className="card">
        <h2>Company career sites</h2>
        <table className="companies-table">
          <thead>
            <tr><th>Name</th><th>System</th><th>Board / Workday site</th><th>On</th><th></th></tr>
          </thead>
          <tbody>
            {companies.map((c, i) => (
              <tr key={i}>
                <td><input aria-label="Company name" value={c.name} onChange={(e) => updateCompany(i, { name: e.target.value })} /></td>
                <td>
                  <select aria-label="Hiring system" value={c.ats} onChange={(e) => updateCompany(i, { ats: e.target.value as Ats })}>
                    {ATS_OPTIONS.map((a) => <option key={a} value={a}>{SOURCE_LABELS[a]}</option>)}
                  </select>
                </td>
                <td>
                  {c.ats === "workday" ? (
                    <div className="workday-fields">
                      <input aria-label="Workday host" placeholder="td.wd3.myworkdayjobs.com" value={c.host ?? ""} onChange={(e) => updateCompany(i, { host: e.target.value })} />
                      <input aria-label="Workday tenant" placeholder="td" value={c.tenant ?? ""} onChange={(e) => updateCompany(i, { tenant: e.target.value })} />
                      <input aria-label="Workday site" placeholder="TD_Bank_Careers" value={c.site ?? ""} onChange={(e) => updateCompany(i, { site: e.target.value })} />
                    </div>
                  ) : (
                    <input aria-label="Board name" value={c.board ?? ""} onChange={(e) => updateCompany(i, { board: e.target.value })} />
                  )}
                </td>
                <td>
                  <input type="checkbox" aria-label={`Enable ${c.name}`} checked={c.enabled} onChange={(e) => updateCompany(i, { enabled: e.target.checked })} />
                </td>
                <td>
                  <div className="row">
                    <button onClick={() => void testCompany(i)}>Test</button>
                    <button className="link-button" onClick={() => setCompanies(companies.filter((_, j) => j !== i))}>Remove</button>
                    {tests[i] && <span className="hint">{tests[i]}</span>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="row">
          <button onClick={() => setCompanies([...companies, { name: "", ats: "greenhouse", board: "", enabled: true }])}>Add company</button>
          <button className="primary" onClick={() => void act(async () => {
            setCompanies(await api.saveCompanies(companies));
            return "Companies saved.";
          })}>Save companies</button>
        </div>
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Render it from `App.tsx`**

Add `import { SettingsPage } from "./components/SettingsPage";` and replace the `<main>` contents with:

```tsx
        {page === "jobs" ? (
          <JobsPage refreshKey={refreshKey} />
        ) : (
          <SettingsPage
            onSaved={() => {
              loadStatus();
              setRefreshKey((k) => k + 1);
            }}
          />
        )}
```

- [ ] **Step 3: Typecheck, test, build**

```bash
cd frontend && npm test && npm run build
```
Expected: PASS.

- [ ] **Step 4: Check in the browser**

Start the server as in Task 18 Step 11. In Settings: upload `examples/sample_resume.md` as the resume (banner disappears); add and remove a profile document; change a role term and save (message shows how many jobs were re-checked); click "Test" on Wealthsimple (shows "OK: N open jobs"); toggle LinkedIn off and save; reload and confirm the changes stuck.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(ui): settings page for resume, search filters, sources, models and companies

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 20: Ship the built UI, docs, and end-to-end verification

**Files:**
- Create/commit: `src/job_apply_agent/web/static/**` (Vite build output)
- Modify: `README.md`, `ROADMAP.md`
- Create: `data/.env.example` is **not** possible (`data/` is ignored), so document the keys in the README instead.

**Interfaces:**
- Consumes: everything.
- Produces: a branch ready for review; a PR only after the user says so.

- [ ] **Step 1: Build the UI into the package and check it's served**

```bash
cd frontend && npm ci && npm run build && cd ..
.venv/bin/pytest -q tests/test_web_api.py::test_root_without_built_ui_or_with
ls src/job_apply_agent/web/static
```
Expected: `index.html` and an `assets/` folder.

- [ ] **Step 2: Update `README.md`**

Make these edits:
1. Replace the opening paragraph block (the "Phase 1 feature" paragraph) with:

```markdown
**What it does:**

- **Finds jobs for you.** On demand or on a schedule, it searches Canadian company career sites
  (Greenhouse, Lever, Ashby, Workday), JSearch (Google for Jobs: LinkedIn, Indeed, Glassdoor...),
  Adzuna and LinkedIn's public job search for Data Analyst, Data Scientist and Data Engineer roles
  in Toronto/GTA, Remote (Canada) and Ottawa.
- **Ranks every job by fit.** Claude Haiku 5.5 reads each relevant posting with your resume and
  profile and gives a match score, the reasons you fit, and the gaps.
- **Tailors your resume** to any job in one click: Markdown, Word (.docx) and PDF, plus a report
  of what changed and what's missing. It asks you about gaps and never invents experience.
```

2. After the "Setup" section, add:

````markdown
## The app

```bash
job-agent serve            # opens http://127.0.0.1:8000 in your browser
```

- **New (24h)** and **All jobs** tabs, both ranked by match score. Click a column to re-sort;
  filter by role, location, source, status or minimum score.
- Click a job for the score, reasons, gaps, full description and links. Set its status
  (saved, applied, interview...), add notes, or click **Tailor my resume for this job**.
- **Search now** runs every enabled source. While the app is open it also searches on a
  schedule: company sites hourly, JSearch daily, Adzuna every 8 hours, LinkedIn twice a day.
  Change this in **Settings**, where you also upload your resume and profile documents, edit the
  job title terms, locations and excluded companies, and manage the company list.

Run a search without the UI (for cron or Task Scheduler):

```bash
job-agent search                         # all enabled sources, then Claude scoring
job-agent search --sources greenhouse,lever --no-score
```

### Optional API keys (free tiers)

Create `data/.env` (git-ignored):

```bash
JSEARCH_API_KEY=...      # https://rapidapi.com -> JSearch, Basic (free) plan
ADZUNA_APP_ID=...        # https://developer.adzuna.com -> free key
ADZUNA_APP_KEY=...
```

Without keys those two sources are skipped and everything else works. The app counts calls and
stops at a budget under each free tier (JSearch 180/month, Adzuna 100/day; editable in
`data/preferences.yaml`).

### How searching stays light on your Claude usage

Only jobs whose title matches your role terms and whose location is in your target areas are
scored, and each job is scored once (again only if you change your resume or profile).
Scoring uses Claude Haiku 5.5, the smallest current model.
````

3. In the "Usage" section, note that `--resume` is optional once a resume is set in the app.

- [ ] **Step 3: Update `ROADMAP.md`**

Move Phase 2 into "Done" with these checked items, and keep the open items that remain:

```markdown
- [x] **Local web app.** `job-agent serve`: FastAPI backend + React/TypeScript UI.
- [x] **Job search.** Greenhouse, Lever, Ashby, Workday, JSearch, Adzuna and LinkedIn guest search,
  deduplicated in SQLite, with a relevance gate and free-tier quota budgets.
- [x] **Claude ranking.** Every relevant job scored by Claude Haiku 5.5 with reasons and gaps.
- [x] **Schedule + tracker.** Per-source intervals while the app is open; status and notes per job.
```

- [ ] **Step 4: Full automated verification**

```bash
.venv/bin/ruff check src tests
.venv/bin/pytest -q
cd frontend && npm test && npm run typecheck && cd ..
git status --short
```
Expected: lint clean, all Python and frontend tests pass; `git status` shows only the intended changes.

- [ ] **Step 5: Live smoke test against real sources (no Claude)**

```bash
export JOB_AGENT_DATA_DIR=/tmp/claude-1000/-home-mohammad/ac20046b-bcd1-4604-93a0-54df1829f833/scratchpad/live-data
.venv/bin/job-agent search --sources greenhouse,lever,ashby,workday,linkedin --no-score
```
Expected: each company-API source reports `N fetched, M relevant` with few or no warnings. LinkedIn
may report "limiting requests"; if it fetched cards, open one job in the UI and check that title,
company and location parsed correctly. If a company in the default list fails, remove it from
`default_companies.yaml` and note it in the commit.

- [ ] **Step 6: One real scored run and one real tailoring run (uses the Claude subscription)**

Ask the user before this step: it uses their Claude login and usage limits (one Haiku scoring
pass over the relevant jobs plus one tailoring run).

```bash
cp examples/sample_resume.md "$JOB_AGENT_DATA_DIR/my_resume.md"
printf 'resume_path: %s/my_resume.md\n' "$JOB_AGENT_DATA_DIR" > "$JOB_AGENT_DATA_DIR/preferences.yaml"
.venv/bin/job-agent search --sources greenhouse,lever,ashby
.venv/bin/job-agent serve --no-browser --no-schedule --port 8765
```
Expected: the run prints `scoring: Scored N job(s).`; in the UI the jobs have scores, reasons and
gaps; tailoring one job from the panel produces downloadable files (PDF only if LibreOffice is
installed).

- [ ] **Step 7: Commit**

```bash
git add src/job_apply_agent/web/static README.md ROADMAP.md
git commit -m "docs: document the app and ship the built UI

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 8: Finish the branch**

Use superpowers:finishing-a-development-branch. Do not push or open a PR on
`sanamehrabbeigi/job-apply-agent` until the user confirms; when they do, open a PR from
`feature/web-app-job-search` to `main` whose description summarizes the features, the live
smoke-test results, and the known limits (LinkedIn rate limiting; JSearch/Adzuna need keys; PDF
needs LibreOffice), ending with the attribution line from the session instructions.
