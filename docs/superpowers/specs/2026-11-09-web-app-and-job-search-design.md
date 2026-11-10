# Design: local web app + automatic job search

Date: 2026-11-09
Status: approved in conversation, pending written-spec review

## 1. Goal

Turn `job-apply-agent` from a CLI into a **local web app** (FastAPI backend + React/TypeScript
UI) and add **automatic job search**: on demand and on a schedule (hourly/daily), the app
collects Data Analyst, Data Scientist and Data Engineer jobs from job sites and Canadian
company career pages, scores **every relevant job** against the candidate's resume and
profile with Claude Haiku 5.5, and lists them ranked by match score. From any job, one click
runs the existing resume-tailoring flow in the browser.

### Who and where

- One user (the candidate), on her own computer. `job-agent serve` opens
  `http://localhost:8000`. No accounts, no hosting. Uses her Claude subscription through
  the Agent SDK, as today.
- Background: mostly data analyst work. Targets: Data Analyst, Data Scientist, Data Engineer.
- Locations, in priority order: **Toronto/GTA**, **Remote (Canada)**, **Ottawa**.
- Seniority: **no hard filter**; Claude's score judges fit.

### Success criteria

1. One click ("Search now") or the schedule collects jobs from all enabled sources, and
   every relevant job ends up scored and listed by match score.
2. Two tabs, **New (24h)** and **All jobs**, both ranked by score, with re-sortable columns.
3. From any job, "Tailor resume" produces the DOCX/PDF/MD + report in the browser, including
   the ask-then-rewrite questions.
4. All free sources work without paying; paid-tier sources stay inside their free quota.
5. The existing CLI commands (`tailor`, `fetch-job`, `render`) keep working.

### Non-goals

- Hosting, multiple users, login.
- Automatic applying or form filling (ROADMAP Phase 3).
- A cheap pre-ranking score. Every job that passes the relevance gate is scored by Claude.
- Getting around quotas, terms or bot protection (multiple API accounts, proxies, CAPTCHA
  solving, logged-in scraping).

## 2. Principles carried over from the repo

- **Honesty:** nothing is invented. The match score reports gaps; tailoring never adds
  false experience.
- **Privacy:** all personal data (`data/`: resume, profile, `app.db`, preferences, `.env`)
  stays on the machine and is git-ignored.
- **She stays in control:** the app finds and prepares; she decides and applies.
- **Respect site rules:** prefer public/official APIs; LinkedIn is read slowly through its
  public, logged-out pages, and her LinkedIn account is never used.

## 3. Architecture

```
job-agent serve  ->  FastAPI (localhost:8000) -- serves the built React UI
                        |
     +------------------+--------------------+
  /api/jobs        /api/search           /api/tailor
     |                  |                     |
  db.py (SQLite)   search pipeline        tailor_flow.py -> tailor.py (existing)
  data/app.db        |
                     +- sources/  greenhouse, lever, ashby, workday,
                     |            jsearch, adzuna, linkedin
                     +- dedupe.py
                     +- filters.py   (relevance gate: role title + location)
                     +- scoring.py   (Haiku 5.5 via Agent SDK, structured JSON)
                     +- scheduler.py (per-source intervals, asyncio)
```

### 3.1 Backend package layout (`src/job_apply_agent/`)

| Module | Purpose |
| --- | --- |
| `paths.py` (new) | Single source of truth for folders. `DATA_DIR` = `$JOB_AGENT_DATA_DIR` or `./data`; derived: `profile/`, `jobs/`, `app.db`, `preferences.yaml`, `companies.yaml`, `.env`; `OUTPUT_DIR` = `./output`. |
| `preferences.py` (new) | Load/save/validate `preferences.yaml`; defaults when missing. |
| `jobs.py` (changed) | `JobPosting` gains `source`, `external_id`, `posted_at`, `remote` fields. Existing fetch/parse code unchanged. |
| `sources/` (new) | One module per source, all implementing `async def fetch(ctx) -> list[JobPosting]`. `ctx` gives preferences, companies, an HTTP helper, and the quota guard. |
| `sources/http.py` (new) | Shared HTTP helper: timeouts, a polite User-Agent, retry with backoff on 429/5xx, per-host delay. Standard library (`urllib`) run via `asyncio.to_thread`, matching the repo. |
| `dedupe.py` (new) | Merge the same job found on several sources. |
| `filters.py` (new) | Relevance gate: title matches a role term AND location matches a target location; excluded companies dropped. |
| `scoring.py` (new) | Claude match scoring of jobs against resume + profile + answers. |
| `db.py` (new) | `sqlite3` schema, migrations (a `schema_version` table), and query functions. |
| `pipeline.py` (new) | One search run: fetch (parallel) -> dedupe/upsert -> filter -> score unscored -> record run. Emits progress events. |
| `scheduler.py` (new) | asyncio loop inside the server; runs each source on its own interval. |
| `tailor_flow.py` (new, extracted from `cli.py`) | The ask-then-rewrite loop with an injected async `ask(questions) -> answers` callback and a progress callback. |
| `outputs.py` (new, moved from `cli.py`) | `save_outputs(...)`: write MD/report/DOCX/PDF to `output/<date>_<company>_<title>/`. |
| `web/app.py` (new) | FastAPI app, routes, SSE progress, static UI serving. |
| `web/static/` (built) | Production build of the React UI (committed, so Python alone runs the app). |
| `cli.py` (changed) | Existing commands use `tailor_flow` + `outputs`; new `serve` and `search` commands. |

Existing modules `tailor.py`, `prompts.py`, `render.py`, `documents.py` and
`career_profile.py` are reused. Only their path defaults move to `paths.py`.

New dependencies: `fastapi`, `uvicorn[standard]`, `pyyaml`. Dev: `httpx` (FastAPI
TestClient).

### 3.2 Frontend (`frontend/`)

React + TypeScript + Vite. `npm run build` writes to `src/job_apply_agent/web/static/`.
In development, Vite's dev server proxies `/api` to FastAPI. No UI component library; small
hand-written CSS. A tiny typed API client (`src/api.ts`) mirrors the backend's JSON
shapes.

## 4. Job sources

Every source returns `JobPosting`s with the full description where the source provides
one. Each source can be switched on or off, has its own interval in `preferences.yaml`,
and fails independently of the others.

| Source | Endpoint (public) | Query | Default interval | Limits |
| --- | --- | --- | --- | --- |
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` | per company in `companies.yaml` | 1 h | none known; polite delay |
| Lever | `api.lever.co/v0/postings/{company}?mode=json` | per company | 1 h | same |
| Ashby | `api.ashbyhq.com/posting-api/job-board/{name}?includeCompensation=true` | per company | 1 h | same |
| Workday | `{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` (POST, `searchText`) + job detail GET | per company, per role term | 1 h | slower; fetch details only for jobs that pass the gate |
| JSearch (RapidAPI) | `jsearch.p.rapidapi.com/search` | role x location queries, `country=ca`, `date_posted=today` (or `3days` after a gap) | 24 h | free tier ~200 requests/month; guarded by quota |
| Adzuna | `api.adzuna.com/v1/api/jobs/ca/search/{page}` | role x location, `max_days_old` | 8 h | free key; descriptions truncated, so the full posting is fetched on demand with the existing `fetch_job` when tailoring |
| LinkedIn (guest) | `linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search` + existing per-job fetch | role x location, `f_TPR=r86400` | 12 h | slow (several seconds between requests); stops at the first 429/999; logged-out only |

Endpoint details, free-tier numbers and query parameters are checked against each
provider's current documentation during implementation. The defaults above become the
initial `preferences.yaml` values.

**Quota guard:** a `quota` table counts calls per source per calendar month (or day, for
sources with daily limits). Before each call the guard checks the configured budget
(default: documented free limit minus a 10% margin). Once the budget is used, the source is
skipped with status "quota reached until <date>". Settings shows the meters.

**Companies list:** `companies.yaml` is seeded from a bundled `default_companies.yaml` of
about 40 Canada-based tech/fintech/data employers, each with `name`, `ats`
(greenhouse/lever/ashby/workday), and board identifiers. Entries are verified against live
boards during implementation; entries that don't resolve are dropped. Settings has a
"Test" button per company and allows add/edit/remove.

## 5. Relevance gate (`filters.py`)

Not a ranking step. It only keeps Claude from scoring the many unrelated jobs that company
career APIs return (engineering, sales, design...).

- **Role:** the normalized title contains one of the role terms (default: `data analyst`,
  `data scientist`, `data engineer`, `analytics engineer`, `business intelligence`,
  `bi analyst`, `bi developer`, `analytics`, `machine learning engineer`, `product analyst`,
  `reporting analyst`, `insights analyst`). Editable in Settings.
- **Location:** matches Toronto/GTA (Toronto, Mississauga, Markham, Vaughan, Brampton,
  Oakville, Richmond Hill, North York, Etobicoke, Scarborough, "Greater Toronto"), Ottawa
  (Ottawa, Kanata, Gatineau), or remote in Canada (remote/anywhere plus Canada, or a
  Canada-only source). A job listing several locations passes if any one matches. A job
  with no location data passes and is labeled "location unknown".
- **Excluded companies:** dropped.
- Jobs that fail the gate are stored with `relevant = 0` (so later runs don't re-check
  them) and are never shown or scored. If role terms or locations change, the gate re-runs
  over stored jobs.

## 6. Dedupe (`dedupe.py`)

- **Exact:** same `(source, external_id)` or same canonical URL -> same job, so data is
  updated, not duplicated.
- **Cross-source:** key = normalized company (lowercase, legal suffixes like Inc/Ltd/Corp
  removed) + normalized title (lowercase, punctuation and location tags like "(Remote)"
  removed; seniority words are kept, so "Senior Data Analyst" and "Data Analyst" stay separate) + primary city. A match adds a row to `job_links` instead of a new
  job. The longest description wins.
- **Closed jobs:** a company-API job missing from its feed for 2 consecutive successful
  runs is marked `closed` and hidden by default (shown with a filter).

## 7. Scoring (`scoring.py`)

- Agent SDK `query()` with the same locked-down options pattern as `tailor.py`: no tools,
  `setting_sources=[]`, `permission_mode="dontAsk"`, structured JSON output.
- **Model:** `claude-haiku-5-5` by default (configurable in Settings).
- **Input:** resume Markdown + profile + saved answers (the same sources the tailor uses),
  plus a batch of up to 5 jobs (title, company, location, description trimmed of
  boilerplate such as benefits/EEO text; never cut inside requirements).
- **Output per job:** `job_id`, `score` 0-100, `reasons` (up to 3), `gaps` (up to 3),
  `seniority_fit` (`under` / `fit` / `over`), and a one-line `summary`.
- The scoring prompt says to score honestly against the real background and to treat
  seniority mismatch as a gap, not a reason to inflate or hide.
- Each score stores `profile_hash` (hash of resume + profile + answers) and the model.
  Only unscored jobs, or jobs whose `profile_hash` differs from the current one, are scored.
  This makes hourly runs cheap. Changing the resume/profile triggers a background re-score
  (with a confirmation in the UI, because it re-scores everything).
- Batches run with limited concurrency (2 at a time).

## 8. Data model (`data/app.db`)

```
jobs(
  id INTEGER PK, dedupe_key TEXT UNIQUE,
  title, company, location, remote INTEGER, employment_type,
  description TEXT, description_is_partial INTEGER,
  posted_at TEXT NULL, first_seen_at TEXT, last_seen_at TEXT,
  relevant INTEGER, closed INTEGER DEFAULT 0,
  score INTEGER NULL, reasons JSON, gaps JSON, seniority_fit, summary,
  scored_at, score_model, profile_hash,
  status TEXT DEFAULT 'new',    -- new|saved|applied|interview|offer|rejected
  notes TEXT, tailored_folder TEXT NULL, status_updated_at
)
job_links(id PK, job_id FK, source, external_id, url, first_seen_at, last_seen_at,
          missed_runs INTEGER DEFAULT 0, UNIQUE(source, external_id))
runs(id PK, started_at, finished_at, trigger,  -- manual|schedule|cli
     sources JSON,   -- per source: status, fetched, relevant, new, error
     scored INTEGER, error TEXT NULL)
quota(source, period, calls, PRIMARY KEY(source, period))
schema_version(version)
```

**"New (24h)" tab:** `posted_at >= now - 24h`, or (`posted_at` unknown and
`first_seen_at >= now - 24h` and the job was not found by the very first run). This keeps
the first run's backlog out of "New".

## 9. API (FastAPI, JSON)

| Method & path | Purpose |
| --- | --- |
| `GET /api/jobs?tab=new|all&sort=score|posted|company|title&order=&role=&location=&source=&status=&min_score=&include_closed=` | List jobs (relevant only). |
| `GET /api/jobs/{id}` | Job detail with links. |
| `PATCH /api/jobs/{id}` | Update `status` / `notes`. |
| `POST /api/search` | Start a run (all enabled sources, or `{"sources": [...]}`). 409 if one is running. |
| `GET /api/runs?limit=` / `GET /api/runs/{id}` | Run history and detail. |
| `GET /api/events` | SSE stream: run progress, scoring progress, tailor progress/questions. |
| `POST /api/jobs/{id}/tailor` | Start tailoring for a job -> `tailor_id`. |
| `POST /api/tailor/{tailor_id}/answers` | Submit answers (empty list = skip) to the waiting round. |
| `GET /api/tailor/{tailor_id}` | State: running / waiting_for_answers(questions) / done(files, score) / error. |
| `GET /api/files/{path}` | Download a generated file (only under `output/`). |
| `GET/PUT /api/preferences` | Read/update preferences. |
| `GET/PUT /api/companies`, `POST /api/companies/test` | Manage and test company boards. |
| `GET /api/profile`, `POST /api/profile/resume`, `POST /api/profile/documents`, `DELETE /api/profile/documents/{name}` | Manage the master resume and profile files. |
| `GET /api/status` | Setup checks: resume present, Claude auth hint, API keys present, LibreOffice found, quota meters, scheduler state. |

The server binds to `127.0.0.1` only.

## 10. UI

- **Top bar:** app name, "Search now", last-run summary ("Last run 14 min ago, 12 new"),
  Settings link. A first-launch banner asks for the master resume if it's missing.
- **Tabs:** New (24h) | All jobs. The same table in both: score badge (>=75 green, 50-74
  amber, <50 grey, unscored "..."), title, company, location/remote, posted, source icons
  (several when merged), status. The default sort is score descending; clicking a header
  re-sorts. Filter bar: role, location, source, status, min score, hide applied/rejected,
  show closed.
- **Detail panel** (row click): score, summary, why you fit, gaps, seniority fit, full
  description, all source links, status dropdown, notes, "Tailor resume".
- **Tailor in panel:** live progress, then an inline question form when the agent asks;
  final score, download buttons (DOCX/PDF/MD/report); the job shows "Resume ready".
- **Search progress drawer:** one row per source ("Greenhouse: 214 fetched, 9 relevant,
  3 new"; "JSearch: skipped, quota reached until Dec 1"), then "Scoring 7/9".
- **Settings:** resume + profile documents; role terms; locations; excluded companies;
  companies list with Test; sources on/off + intervals; API key status (keys live in
  `data/.env`, never shown); models (scoring, tailoring); quota meters; target match score
  for tailoring.

## 11. Changes to existing code

1. Extract the tailoring loop from `cli.run_tailor` into `tailor_flow.run_tailor_flow(...)`
   with injected `ask` (async) and `progress` callbacks. The CLI passes a terminal prompt,
   the web passes a browser round-trip.
2. Move `save_outputs` (+ `slugify`, `candidate_name`) from `cli.py` to `outputs.py`.
3. Extend `JobPosting` (new optional fields; `to_text()` and `save()` unchanged for
   existing callers).
4. Introduce `paths.py`; replace hard-coded `data/...` defaults.
5. Master resume path stored in preferences (`resume_path`), defaulting to
   `data/my_resume.docx`; the CLI `--resume` flag still works and wins.
6. Separate model settings: tailoring = account default (as now), scoring =
   `claude-haiku-5-5`.

Existing tests keep passing, with imports updated where code moved.

## 12. Error handling

- **Source isolation:** each source runs in its own task with a try/except. A failure is
  recorded on the run (`status: error`, message) and shown in the drawer; other sources
  continue. A run is "partial" if any source failed.
- **HTTP:** 20-30 s timeouts; up to 2 retries with exponential backoff on 429/5xx/network
  errors; a per-host minimum delay (0.5 s company APIs, 3-6 s jittered LinkedIn).
  LinkedIn stops for the rest of the run on its first 429/999 response.
- **Quota:** checked before each call; when the budget is reached the source is skipped,
  not failed.
- **Missing keys:** JSearch/Adzuna without keys are skipped with "no API key", plus a hint
  in Settings.
- **Scoring:** a failed batch leaves its jobs unscored (listed with "..."), to be retried
  next run. If the SDK reports a usage-limit / rate-limit error, scoring stops for this run
  and a banner says "Claude usage limit reached; scoring resumes on the next run."
- **Concurrency:** one search run at a time (asyncio lock). The scheduler skips a tick if a
  run is active. Tailoring runs are independent of search runs.
- **Tailor:** errors (`TailoringError`, fetch failures, PDF conversion) surface in the panel;
  a missing LibreOffice gives DOCX/MD with a "PDF skipped: install LibreOffice" note, as the
  CLI does today. A tailor waiting for answers times out after 30 minutes and finishes with
  the current best version.
- **Startup checks:** `/api/status` drives setup banners (no resume, no Claude login hint,
  `ANTHROPIC_API_KEY` set warning, as in `auth_warning()`).
- **DB:** WAL mode; all writes go through `db.py`; schema migrations at startup.

## 13. Testing

- **Unit (pytest, no network, no Claude):**
  - each source's parser against recorded JSON/HTML fixtures in `tests/fixtures/sources/`;
  - quota guard; HTTP helper retry/backoff with a fake opener;
  - `dedupe` (exact and cross-source merges, closed-job marking);
  - `filters` (role and location cases: GTA cities, "Remote - Canada", multi-location,
    US-only remote rejected);
  - `scoring` with a fake `query` (same pattern as `tests/test_tailor.py`): batching,
    `profile_hash` skip, failure leaves jobs unscored, usage-limit stop;
  - `db` migrations and queries, including the "New (24h)" rule;
  - `tailor_flow` with fake ask/progress callbacks (ports the current CLI loop tests);
  - `pipeline` end-to-end with fake sources and fake scorer;
  - `scheduler` interval logic with an injected clock.
- **API:** FastAPI `TestClient` for every route, with a temporary `DATA_DIR`.
- **Frontend:** `tsc --noEmit` type-check and `vite build` must pass; Vitest for the pure
  sorting/filtering/"new" helpers.
- **Live smoke check (manual, not CI):** `job-agent search --no-score --sources greenhouse,lever,...`
  against the real endpoints to confirm parsers and the companies list; one real scored
  run and one real tailor through the UI before calling the work done.

## 14. Open items decided during implementation

- Exact free-tier numbers and query parameters for JSearch and Adzuna (checked against
  their docs; they set the quota defaults).
- The seed company list (each entry verified against its live board).
